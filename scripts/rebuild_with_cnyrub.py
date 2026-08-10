"""
Пересобираем факторный ряд и модель с использованием CNY/RUB вместо USD/RUB.
CNY/RUB на MOEX торгуется без перерыва (в отличие от USD/RUB после июня 2024).

Логика:
  1. Строим "чистый" USD/RUB ряд:
     - до 2024-06-11 — как было (USD/RUB на MOEX)
     - с 2024-06-12  — реконструируем через CNY/RUB × USD/CNY (кросс)
  2. Плюс отдельная колонка cnyrub — прямой ряд с 2014
  3. Пересчитываем brent_rub, корреляции с IMOEX, регрессию модели
  4. Сохраняем новый imoex_factors.csv и обновлённый imoex_model_output.csv
"""
import pandas as pd
import numpy as np
from scipy import stats
import statsmodels.api as sm
import requests

import os as _os
WORKDIR = _os.environ.get("WORKDIR", "/home/user/workspace")

# ============================================================
# Загружаем существующие ряды
# ============================================================
factors = pd.read_csv(f"{WORKDIR}/imoex_factors.csv", parse_dates=["date"])
cnyrub = pd.read_csv(f"{WORKDIR}/cnyrub_moex.csv", parse_dates=["date"])
cbr = pd.read_csv(f"{WORKDIR}/usdrub_cbr.csv", parse_dates=["date"])

print(f"factors: {len(factors)} строк, {factors['date'].min().date()} → {factors['date'].max().date()}")
print(f"cnyrub:  {len(cnyrub)} строк, {cnyrub['date'].min().date()} → {cnyrub['date'].max().date()}")
print(f"cbr USDRUB: {len(cbr)} строк, {cbr['date'].min().date()} → {cbr['date'].max().date()}")

# ============================================================
# USD/CNY глобальный — тянем через yfinance с retries
# ============================================================
usdcny = None
try:
    import yfinance as yf
    ycn = yf.download("CNY=X", start="2014-01-01", end="2026-08-11",
                      progress=False, auto_adjust=False, threads=False)
    if not ycn.empty:
        ycn = ycn.reset_index()
        ycn.columns = [c[0] if isinstance(c, tuple) else c for c in ycn.columns]
        usdcny = ycn[["Date","Close"]].rename(columns={"Date":"date","Close":"usdcny"})
        usdcny["date"] = pd.to_datetime(usdcny["date"]).dt.tz_localize(None).dt.normalize()
        usdcny.to_csv(f"{WORKDIR}/usdcny.csv", index=False)
        print(f"USD/CNY: {len(usdcny)} строк, {usdcny['date'].min().date()} → {usdcny['date'].max().date()}")
except Exception as e:
    print(f"yfinance error: {e}")

# ============================================================
# Собираем новый usdrub_clean
# ============================================================
# Точка разрыва — 12 июня 2024 (санкции OFAC на MOEX)
SANCTIONS = pd.Timestamp("2024-06-12")

# ЦБ РФ как базовый — он продолжает публиковать курс, но после июня 2024
# методология — OTC-фиксинг, что тоже пригодно
df = factors[["date","imoex","brent","usdrub","ofz5y","brent_rub","brent_rub_ma3m"]].copy()

# Мерджим все альтернативные ряды
df = df.merge(cnyrub[["date","cnyrub"]], on="date", how="left")
df = df.merge(cbr[["date","usdrub_cbr"]], on="date", how="left")
if usdcny is not None:
    df = df.merge(usdcny[["date","usdcny"]], on="date", how="left")
    df["usdcny"] = df["usdcny"].ffill()

# Реконструированный USD/RUB через кросс-курс
if "usdcny" in df.columns:
    df["usdrub_cross"] = df["cnyrub"] * df["usdcny"]
else:
    df["usdrub_cross"] = np.nan

# ============================================================
# Проверка: сравниваем варианты до/после санкций
# ============================================================
print("\n=== Сравнение USDRUB после санкций OFAC (июнь 2024) ===")
comp = df[(df["date"] >= "2024-05-15") & (df["date"] <= "2024-07-15")][
    ["date","usdrub","usdrub_cbr","usdrub_cross","cnyrub"]]
print(comp.to_string(index=False))

# Как далеко расходятся варианты за 2024-2026?
recent = df[df["date"] >= "2024-06-15"].dropna(subset=["usdrub_cbr","usdrub_cross"])
if len(recent) > 0:
    diff = (recent["usdrub_cbr"] - recent["usdrub_cross"]).abs()
    print(f"\nРасхождение ЦБ vs cross-курс с 2024-06-15: медиана {diff.median():.2f}, макс {diff.max():.2f}")

# ============================================================
# Строим "чистый" USD/RUB:
#   до санкций — оригинальный usdrub (MOEX torg + market)
#   после — берём ЦБ как канонический (публикуется каждый день, реальные значения)
# ============================================================
df["usdrub_clean"] = df["usdrub"].copy()
mask_post = df["date"] >= SANCTIONS
# Если у нас есть usdrub_cbr — используем его после санкций
df.loc[mask_post, "usdrub_clean"] = df.loc[mask_post, "usdrub_cbr"].fillna(df.loc[mask_post, "usdrub_cross"])

# Мостим пробелы через ffill (если ЦБ не публиковал — редкое исключение)
df["usdrub_clean"] = df["usdrub_clean"].ffill()

# ============================================================
# Пересчитываем brent_rub с новым USD/RUB
# ============================================================
df["brent_rub_clean"] = df["brent"] * df["usdrub_clean"]
df["brent_rub_ma3m_clean"] = df["brent_rub_clean"].rolling(63, min_periods=30).mean()

# Также — brent × CNY/RUB напрямую (альтернатива)
df["brent_cnyrub"] = df["brent"] * df["cnyrub"]
df["brent_cnyrub_ma3m"] = df["brent_cnyrub"].rolling(63, min_periods=30).mean()

# ============================================================
# Проверяем: сколько изменилось
# ============================================================
df["usdrub_diff"] = df["usdrub_clean"] - df["usdrub"]
big_diff = df[df["usdrub_diff"].abs() > 1][["date","usdrub","usdrub_clean","usdrub_cbr","cnyrub"]]
print(f"\n=== Дней где usdrub_clean отличается от старого >1 руб: {len(big_diff)} ===")
print(big_diff.head(15).to_string(index=False))
print("...")
print(big_diff.tail(10).to_string(index=False))

# Особенно интересно: залипший период с 2024-06-11 по 2025-08-11 
# в старом ряду был плоский 89.1025 — сколько там реальная волатильность?
lipped = df[(df["date"] >= "2024-06-11") & (df["date"] <= "2025-08-11")]
print(f"\n=== Залипший период 2024-06-11 → 2025-08-11 ===")
print(f"Старый usdrub: min={lipped['usdrub'].min():.2f}, max={lipped['usdrub'].max():.2f}, std={lipped['usdrub'].std():.2f}")
print(f"Новый usdrub_clean: min={lipped['usdrub_clean'].min():.2f}, max={lipped['usdrub_clean'].max():.2f}, std={lipped['usdrub_clean'].std():.2f}")

# ============================================================
# КОРРЕЛЯЦИИ: IMOEX vs USDRUB — как изменились?
# ============================================================
print("\n" + "=" * 80)
print("КОРРЕЛЯЦИИ IMOEX vs USD/RUB (старый vs новый)")
print("=" * 80)

df["log_imoex"] = np.log(df["imoex"])
df["r_imoex"] = df["log_imoex"].diff()
df["r_imoex_20d"] = df["imoex"].pct_change(20)

for period_name, mask in [
    ("Вся история 2014-2026", df["date"] >= "2014-02-03"),
    ("До санкций 2014-2024/06", df["date"] < SANCTIONS),
    ("После санкций 2024/06+", df["date"] >= SANCTIONS),
]:
    sub = df[mask].dropna(subset=["log_imoex","usdrub","usdrub_clean"])
    if len(sub) < 30: continue
    print(f"\n--- {period_name} (n={len(sub)}) ---")
    for xn, x_col in [("USDRUB старый", "usdrub"),
                        ("USDRUB новый (ЦБ+кросс)", "usdrub_clean"),
                        ("CNYRUB прямой", "cnyrub")]:
        x = sub[x_col]
        y = sub["log_imoex"]
        mask2 = x.notna() & y.notna()
        if mask2.sum() < 20: continue
        r = stats.pearsonr(x[mask2], y[mask2])
        print(f"  {xn:<30}: r = {r.statistic:+.3f} (p={r.pvalue:.1e}), n={mask2.sum()}")

# ============================================================
# РЕГРЕССИЯ модели: log(IMOEX) ~ log(brent_rub_ma3m) + ofz5y
# ============================================================
print("\n" + "=" * 80)
print("РЕГРЕССИЯ модели A: старый ряд vs новый")
print("=" * 80)

def run_reg(sub, oil_col, label):
    X = sub[["log_oil", "ofz5y"]].copy()
    X = sm.add_constant(X)
    y = sub["log_imoex"]
    m = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags":10})
    print(f"\n{label}: R²={m.rsquared:.4f}, adj R²={m.rsquared_adj:.4f}, n={int(m.nobs)}")
    for pn, c, se, t, pv in zip(m.params.index, m.params.values, m.bse.values, m.tvalues.values, m.pvalues.values):
        print(f"  {pn:<10} = {c:+.4f} (SE={se:.4f}, t={t:+.2f}, p={pv:.3f})")
    return m

# Модель на старом oil ряду
sub_old = df.dropna(subset=["log_imoex","brent_rub_ma3m","ofz5y"]).copy()
sub_old["log_oil"] = np.log(sub_old["brent_rub_ma3m"])
m_old = run_reg(sub_old, "brent_rub_ma3m", "Старая (brent × old USDRUB, 3m MA)")

sub_new = df.dropna(subset=["log_imoex","brent_rub_ma3m_clean","ofz5y"]).copy()
sub_new["log_oil"] = np.log(sub_new["brent_rub_ma3m_clean"])
m_new = run_reg(sub_new, "brent_rub_ma3m_clean", "Новая (brent × clean USDRUB, 3m MA)")

sub_cny = df.dropna(subset=["log_imoex","brent_cnyrub_ma3m","ofz5y"]).copy()
sub_cny["log_oil"] = np.log(sub_cny["brent_cnyrub_ma3m"])
m_cny = run_reg(sub_cny, "brent_cnyrub_ma3m", "CNY-вариант (brent × CNYRUB, 3m MA)")

# ============================================================
# Fair value с новой моделью
# ============================================================
print("\n" + "=" * 80)
print("Fair value: старый vs новый vs CNY-вариант")
print("=" * 80)

# Прогноз fair value для всех дат
for label, sub, m, oil_col in [
    ("A_old",  sub_old, m_old, "brent_rub_ma3m"),
    ("A_new",  sub_new, m_new, "brent_rub_ma3m_clean"),
    ("A_cny",  sub_cny, m_cny, "brent_cnyrub_ma3m"),
]:
    sub = sub.copy()
    X = sm.add_constant(sub[["log_oil","ofz5y"]])
    sub[f"log_fv_{label}"] = X @ m.params
    sub[f"fv_{label}"] = np.exp(sub[f"log_fv_{label}"])
    sub[f"dev_{label}"] = sub["imoex"] / sub[f"fv_{label}"] - 1
    df = df.merge(sub[["date", f"fv_{label}", f"dev_{label}"]], on="date", how="left")

last = df.iloc[-1]
print(f"\nНа {last['date'].date()}: IMOEX = {last['imoex']:,.2f}")
print(f"  Модель A_old (стар. USDRUB): fair {last['fv_A_old']:,.2f}, откл {last['dev_A_old']*100:+.2f}%")
print(f"  Модель A_new (clean USDRUB): fair {last['fv_A_new']:,.2f}, откл {last['dev_A_new']*100:+.2f}%")
print(f"  Модель A_cny (CNY-вариант):  fair {last['fv_A_cny']:,.2f}, откл {last['dev_A_cny']*100:+.2f}%")

# Средние отклонения в залипший период — насколько они систематически смещены
lipped = df[(df["date"] >= "2024-06-11") & (df["date"] <= "2025-08-11")]
print(f"\n=== Средние отклонения в период с плоским USDRUB (2024-06-11 → 2025-08-11) ===")
print(f"  A_old: mean {lipped['dev_A_old'].mean()*100:+.2f}%, std {lipped['dev_A_old'].std()*100:.2f}%")
print(f"  A_new: mean {lipped['dev_A_new'].mean()*100:+.2f}%, std {lipped['dev_A_new'].std()*100:.2f}%")
print(f"  A_cny: mean {lipped['dev_A_cny'].mean()*100:+.2f}%, std {lipped['dev_A_cny'].std()*100:.2f}%")

# Сохраняем финальный ряд
df.to_csv(f"{WORKDIR}/imoex_factors_clean.csv", index=False)
print(f"\nСохранено: imoex_factors_clean.csv, {len(df)} строк")

# Сохраняем краткую сводку с ключевыми метриками
summary = {
    "R2_old": float(m_old.rsquared),
    "R2_new": float(m_new.rsquared),
    "R2_cny": float(m_cny.rsquared),
    "coefs_old": {k: {"value": float(m_old.params[k]), "se": float(m_old.bse[k])} for k in m_old.params.index},
    "coefs_new": {k: {"value": float(m_new.params[k]), "se": float(m_new.bse[k])} for k in m_new.params.index},
    "coefs_cny": {k: {"value": float(m_cny.params[k]), "se": float(m_cny.bse[k])} for k in m_cny.params.index},
    "current_imoex": float(last["imoex"]),
    "current_fv_A_old": float(last["fv_A_old"]),
    "current_fv_A_new": float(last["fv_A_new"]),
    "current_fv_A_cny": float(last["fv_A_cny"]),
}
import json
with open(f"{WORKDIR}/model_comparison.json","w") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)
print("Сохранено: model_comparison.json")
