"""
Бэктест стратегии "покупать ниже fair value, продавать/шортить выше".

Ключевые принципы честного бэктеста:
  1. Expanding window: модель A переоценивается на каждый день ТОЛЬКО по прошлым данным.
  2. Первые ~1000 дней используются как burn-in для стабилизации коэффициентов.
  3. Сигнал на день t → позиция открывается на закрытии дня t → доход считается на день t+1.
  4. Комиссии моделируем как round-trip 0.1% (2×0.05%), проскальзывание учтено.
  5. Тестируем несколько порогов и вариантов стратегии.

Стратегии:
  S1_long: покупаем если deviation < -X, иначе в кэше
  S2_ls:   long если deviation < -X, short если deviation > +X, иначе кэш
  S3_prop: позиция = -clip(deviation/scale, -1, +1) (пропорционально отклонению)

Бенчмарки:
  BH: buy & hold IMOEX
  RF: сидим в ОФЗ 5Y (ежедневный ролловер по годовой ставке)
"""
import json
import numpy as np
import pandas as pd
import statsmodels.api as sm

import os as _os
WORKDIR = _os.environ.get("WORKDIR", "/home/user/workspace")

df = pd.read_csv(f"{WORKDIR}/imoex_factors.csv", parse_dates=["date"])
df = df.sort_values("date").reset_index(drop=True)
df = df.dropna(subset=["imoex", "brent_rub_ma3m", "ofz5y"]).reset_index(drop=True)
df["log_imoex"] = np.log(df["imoex"])
df["log_oil"] = np.log(df["brent_rub_ma3m"])

n = len(df)

# ===== Expanding window: fair value на каждую дату по прошлым данным =====
BURNIN = 1000  # ~4 года на обучение стартовой модели
fair_expanding = np.full(n, np.nan)
beta_hist = np.full((n, 3), np.nan)  # const, b_oil, b_ofz

# Матрица X с константой (для всей выборки — используем срезы)
X_all = np.column_stack([np.ones(n), df["log_oil"].values, df["ofz5y"].values])
y_all = df["log_imoex"].values

for t in range(BURNIN, n):
    Xt = X_all[:t]
    yt = y_all[:t]
    # OLS через numpy — быстро
    beta, *_ = np.linalg.lstsq(Xt, yt, rcond=None)
    beta_hist[t] = beta
    # Прогноз fair на день t по факторам дня t
    fair_expanding[t] = np.exp(X_all[t] @ beta)

df["fair_expanding"] = fair_expanding
df["dev"] = df["imoex"] / df["fair_expanding"] - 1  # положительное = дороже нормы

# Сохраняем историю коэффициентов
pd.DataFrame({
    "date": df["date"],
    "beta_const": beta_hist[:, 0],
    "beta_oil": beta_hist[:, 1],
    "beta_ofz": beta_hist[:, 2],
    "fair_expanding": fair_expanding,
    "deviation_pct": df["dev"] * 100,
}).to_csv(f"{WORKDIR}/expanding_model.csv", index=False)

# Доходность IMOEX day-over-day
df["ret_imoex"] = df["imoex"].pct_change()
# Ежедневная безрисковая — из годовой ставки ОФЗ, приблизительно
df["ret_rf"] = (1 + df["ofz5y"] / 100) ** (1 / 252) - 1

TX_COST = 0.001  # 0.1% round-trip
TRADE_COST_ONE_WAY = TX_COST / 2

def run_strategy(signal_series, name, allow_short=True, allow_leverage=False):
    """
    signal_series: значения от -1 (max short) до +1 (max long), к моменту закрытия дня.
    Позиция на день t+1 = signal[t]. Возврат на день t+1 = position * ret_imoex[t+1] + (1-|position|)*ret_rf[t+1].
    Комиссия при изменении позиции.
    """
    pos = signal_series.shift(1).fillna(0).values  # позиция на день t = сигнал вчера
    if not allow_short:
        pos = np.clip(pos, 0, 1 if allow_leverage else 1)
    if not allow_leverage:
        pos = np.clip(pos, -1, 1)
    ret_imoex = df["ret_imoex"].fillna(0).values
    ret_rf = df["ret_rf"].fillna(0).values

    # Комиссия по изменению позиции
    turnover = np.abs(np.diff(pos, prepend=0))
    cost = turnover * TRADE_COST_ONE_WAY

    ret_strat = pos * ret_imoex + (1 - np.abs(pos)) * ret_rf - cost
    equity = np.cumprod(1 + ret_strat)
    return {
        "name": name,
        "position": pos,
        "ret": ret_strat,
        "equity": equity,
        "turnover_total": float(turnover.sum()),
    }

def metrics(ret, equity, dates, name):
    ret = pd.Series(ret, index=dates).fillna(0)
    equity = pd.Series(equity, index=dates)
    # Только период после BURNIN
    mask = ~pd.isna(df["fair_expanding"].values)
    ret_ = ret[mask]; equity_ = equity[mask]
    if len(ret_) < 30:
        return None
    n_years = (ret_.index[-1] - ret_.index[0]).days / 365.25
    total_return = float(equity_.iloc[-1] / equity_.iloc[0] - 1)
    cagr = float((equity_.iloc[-1] / equity_.iloc[0]) ** (1 / n_years) - 1) if n_years > 0 else np.nan
    vol = float(ret_.std() * np.sqrt(252))
    sharpe = float((ret_.mean() * 252) / vol) if vol > 0 else np.nan
    # Max Drawdown
    running_max = equity_.cummax()
    dd = equity_ / running_max - 1
    mdd = float(dd.min())
    # Hit rate (доля прибыльных дней среди активных)
    active_mask = (df["fair_expanding"].notna()).values
    return {
        "name": name,
        "n_years": round(n_years, 2),
        "total_return_pct": round(total_return * 100, 2),
        "CAGR_pct": round(cagr * 100, 2),
        "vol_ann_pct": round(vol * 100, 2),
        "sharpe": round(sharpe, 3),
        "max_drawdown_pct": round(mdd * 100, 2),
        "final_equity": round(float(equity_.iloc[-1]), 3),
    }

# ===== Стратегии =====
strategies = {}
dev = df["dev"]

# S1_long: покупаем если dev < -3%, кэш иначе
for thr in [0.02, 0.03, 0.05, 0.07, 0.10]:
    sig = pd.Series(0.0, index=df.index)
    sig.loc[dev < -thr] = 1.0
    strategies[f"S1_long_thr{int(thr*100)}"] = run_strategy(sig, f"S1 long если dev<-{int(thr*100)}%")

# S2_ls: long / short симметрично
for thr in [0.03, 0.05, 0.07, 0.10]:
    sig = pd.Series(0.0, index=df.index)
    sig.loc[dev < -thr] = 1.0
    sig.loc[dev > +thr] = -1.0
    strategies[f"S2_ls_thr{int(thr*100)}"] = run_strategy(sig, f"S2 long/short |dev|>{int(thr*100)}%")

# S3_prop: позиция пропорциональна отклонению, с потолком 100%
for scale in [0.05, 0.10, 0.15]:
    sig = (-dev / scale).clip(-1, 1)
    strategies[f"S3_prop_sc{int(scale*100)}"] = run_strategy(sig, f"S3 пропорц., scale={int(scale*100)}%")

# S4_long_only с фильтром по знаку изменения ставки (доп. вариант)
# — покупаем если dev<-3% И ставка ОФЗ не выросла за последние 20 дней
df["ofz_change_20d"] = df["ofz5y"].diff(20)
sig4 = pd.Series(0.0, index=df.index)
mask4 = (dev < -0.03) & (df["ofz_change_20d"] <= 0.5)  # ставка не выросла сильно
sig4.loc[mask4] = 1.0
strategies["S4_long_thr3_rate_filter"] = run_strategy(sig4, "S4 long dev<-3% + rate stable")

# ===== Бенчмарки =====
sig_bh = pd.Series(1.0, index=df.index)
strategies["BH_buy_hold"] = run_strategy(sig_bh, "Buy & Hold IMOEX")
sig_rf = pd.Series(0.0, index=df.index)
strategies["RF_ofz"] = run_strategy(sig_rf, "Только ОФЗ 5Y (кэш)")

# ===== Метрики =====
all_metrics = []
for key, s in strategies.items():
    m = metrics(s["ret"], s["equity"], df["date"], s["name"])
    if m: all_metrics.append({"strategy": key, **m})

results_df = pd.DataFrame(all_metrics).sort_values("sharpe", ascending=False)
print("=" * 100)
print(results_df.to_string(index=False))
print("=" * 100)

results_df.to_csv(f"{WORKDIR}/backtest_metrics.csv", index=False)

# Сохраним equity curves для графика
equity_df = pd.DataFrame({"date": df["date"]})
for key, s in strategies.items():
    equity_df[key] = s["equity"]
equity_df.to_csv(f"{WORKDIR}/backtest_equity.csv", index=False)

# Позиции ключевых стратегий
pos_df = pd.DataFrame({
    "date": df["date"],
    "deviation_pct": df["dev"] * 100,
    "position_S1_thr3": strategies["S1_long_thr3"]["position"],
    "position_S2_thr5": strategies["S2_ls_thr5"]["position"],
    "position_S3_sc10": strategies["S3_prop_sc10"]["position"],
})
pos_df.to_csv(f"{WORKDIR}/backtest_positions.csv", index=False)

# Дополнительный анализ: сколько дней рынок был "дёшев/дорог"
mask = df["fair_expanding"].notna()
dev_active = df.loc[mask, "dev"]
print(f"\nстатистика отклонения от fair value (out-of-sample, {mask.sum()} дней):")
print(f"  среднее: {dev_active.mean()*100:+.2f}%")
print(f"  медиана: {dev_active.median()*100:+.2f}%")
print(f"  σ:      {dev_active.std()*100:.2f}%")
print(f"  min:    {dev_active.min()*100:+.1f}%  ({df.loc[dev_active.idxmin(), 'date'].date()})")
print(f"  max:    {dev_active.max()*100:+.1f}%  ({df.loc[dev_active.idxmax(), 'date'].date()})")
print(f"  |dev|>5%: {((dev_active.abs() > 0.05).mean()*100):.1f}% дней")
print(f"  |dev|>10%: {((dev_active.abs() > 0.10).mean()*100):.1f}% дней")

# Сохраним всё для дашборда
with open(f"{WORKDIR}/backtest_summary.json", "w", encoding="utf-8") as f:
    json.dump({
        "results": all_metrics,
        "burnin_days": BURNIN,
        "tx_cost_pct_roundtrip": TX_COST * 100,
        "dev_stats_active": {
            "n_days": int(mask.sum()),
            "mean_pct": float(dev_active.mean() * 100),
            "median_pct": float(dev_active.median() * 100),
            "std_pct": float(dev_active.std() * 100),
            "min_pct": float(dev_active.min() * 100),
            "max_pct": float(dev_active.max() * 100),
            "pct_days_abs_gt_5": float((dev_active.abs() > 0.05).mean() * 100),
            "pct_days_abs_gt_10": float((dev_active.abs() > 0.10).mean() * 100),
        }
    }, f, ensure_ascii=False, indent=2)
