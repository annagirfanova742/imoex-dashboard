"""
Синтетический индекс «геополитический трек к деэскалации»:
  - до 2026-05-08: Polymarket p (склеенный ряд ceasefire-рынков)
  - с  2026-05-09: Kalshi p (KXZELENSKYPUTIN-29-VPUT)

Три версии стыковки:
  1. RAW: просто конкатенация — видна «ступенька» на стыке
  2. LEVEL-MATCH: сдвигаем Kalshi так, чтобы среднее последних 30 дней Kalshi
     = среднему последних 30 дней Polymarket → плавный переход
  3. Z-SCORE: нормируем каждый источник (mean=0, std=1), склеиваем — «относительный
     трек» без привязки к абсолютной вероятности
"""
import pandas as pd
import numpy as np
from scipy import stats

import os as _os
WORKDIR = _os.environ.get("WORKDIR", "/home/user/workspace")

# Загружаем ряды
poly = pd.read_csv(f"{WORKDIR}/polymarket_ceasefire_series.csv", parse_dates=["date"])
kalshi = pd.read_csv(f"{WORKDIR}/kalshi_KXZELENSKYPUTIN-29-VPUT.csv", parse_dates=["date"])
factors = pd.read_csv(f"{WORKDIR}/imoex_factors.csv", parse_dates=["date"])
model_out = pd.read_csv(f"{WORKDIR}/imoex_model_output.csv", parse_dates=["date"])

poly = poly[["date", "p"]].rename(columns={"p": "p_raw"}).sort_values("date")
kalshi = kalshi[["date", "p"]].rename(columns={"p": "p_raw"}).sort_values("date")

# Точка сшивания — последняя дата Polymarket
SPLICE = pd.Timestamp("2026-05-08")

poly_pre  = poly[poly["date"] <= SPLICE].copy()
kalshi_post = kalshi[kalshi["date"] > SPLICE].copy()

print(f"Polymarket до склейки: {len(poly_pre)} дней, {poly_pre['date'].min().date()} → {poly_pre['date'].max().date()}")
print(f"Kalshi после склейки:   {len(kalshi_post)} дней, {kalshi_post['date'].min().date()} → {kalshi_post['date'].max().date()}")

# === Версия 1: RAW ===
poly_pre["source"] = "polymarket"
kalshi_post["source"] = "kalshi"
raw = pd.concat([poly_pre, kalshi_post], ignore_index=True).sort_values("date").reset_index(drop=True)
raw["p_synthetic_raw"] = raw["p_raw"]

# === Версия 2: LEVEL-MATCH (сдвиг Kalshi по среднему уровня) ===
# Берём последние 30 дней Polymarket ДО его резолюции (когда цена шла к 1)
# и первые 30 дней Kalshi ПОСЛЕ склейки. Ищем сдвиг.
# Проблема: Polymarket в последние дни спекулятивно рос к 1 (война формально
# заканчивалась). Kalshi же считает "встречу" самостоятельно. Прямое выравнивание
# по средним даст неверную картину. Лучше выравнивать по перекрытию:
# Есть 111 дней, где оба ряда доступны. Возьмём медианный сдвиг за этот период.

overlap = poly.merge(kalshi, on="date", suffixes=("_poly", "_kalshi"))
if len(overlap) > 20:
    shift = (overlap["p_raw_poly"] - overlap["p_raw_kalshi"]).median()
    print(f"\nМедианный сдвиг Polymarket - Kalshi (на перекрытии {len(overlap)} дней): {shift:+.3f}")
else:
    shift = 0

kalshi_shifted = kalshi_post.copy()
kalshi_shifted["p_raw"] = kalshi_shifted["p_raw"] + shift
poly_lm = poly_pre.copy()
poly_lm["p_synthetic_lm"] = poly_lm["p_raw"]
kalshi_lm = kalshi_shifted.copy()
kalshi_lm["p_synthetic_lm"] = kalshi_lm["p_raw"].clip(0.001, 0.999)
lm = pd.concat([poly_lm[["date","p_synthetic_lm","source"]], kalshi_lm[["date","p_synthetic_lm","source"]] if "source" in kalshi_lm else kalshi_lm.assign(source="kalshi")[["date","p_synthetic_lm","source"]]], ignore_index=True)

# === Версия 3: Z-SCORE ===
poly_z = poly_pre.copy()
p_mean_poly = poly_pre["p_raw"].mean()
p_std_poly = poly_pre["p_raw"].std()
poly_z["p_synthetic_z"] = (poly_pre["p_raw"] - p_mean_poly) / p_std_poly

# Для Kalshi берём z-score по КАЛШИ (не по poly)
p_mean_kalshi = kalshi["p_raw"].mean()
p_std_kalshi = kalshi["p_raw"].std()
kalshi_z = kalshi_post.copy()
kalshi_z["p_synthetic_z"] = (kalshi_post["p_raw"] - p_mean_kalshi) / p_std_kalshi

z_series = pd.concat([poly_z[["date","p_synthetic_z","source"]], kalshi_z[["date","p_synthetic_z","source"]]], ignore_index=True)

# === Собираем итоговый датафрейм ===
synth = raw[["date","source","p_synthetic_raw"]].copy()
synth = synth.merge(lm[["date","p_synthetic_lm"]], on="date", how="left")
synth = synth.merge(z_series[["date","p_synthetic_z"]], on="date", how="left")

print(f"\nСинтетический индекс: {len(synth)} дней, {synth['date'].min().date()} → {synth['date'].max().date()}")
print(f"Polymarket days: {(synth['source']=='polymarket').sum()}, Kalshi days: {(synth['source']=='kalshi').sum()}")

# Мерджим с IMOEX
merged = factors.merge(synth, on="date", how="inner")
merged = merged.merge(model_out[["date","deviation_A","deviation_B","fair_value_A"]], on="date", how="left")

merged["log_imoex"] = np.log(merged["imoex"])
merged["dp"] = merged["p_synthetic_raw"].diff()
merged["dp_5d"] = merged["p_synthetic_raw"].diff(5)
merged["dp_20d"] = merged["p_synthetic_raw"].diff(20)
merged["r_imoex"] = merged["log_imoex"].diff()
merged["r_imoex_5d"] = merged["imoex"].pct_change(5)
merged["r_imoex_20d"] = merged["imoex"].pct_change(20)

print(f"\nМердж с IMOEX: {len(merged)} дней")

# === Корреляции с 3 версиями стыковки ===
print("\n" + "="*80)
print("КОРРЕЛЯЦИИ синтетический индекс vs IMOEX")
print("="*80)

for col, label in [("p_synthetic_raw","RAW"), ("p_synthetic_lm","LEVEL-MATCH"), ("p_synthetic_z","Z-SCORE")]:
    print(f"\n--- Версия {label} ---")
    for yn, y in [("log(IMOEX)", merged["log_imoex"]),
                   ("deviation_A", merged["deviation_A"]),
                   ("ОФЗ 5Y", merged["ofz5y"]),
                   ("USDRUB", merged["usdrub"])]:
        x = merged[col]
        mask = x.notna() & y.notna()
        if mask.sum() < 20: continue
        pear = stats.pearsonr(x[mask], y[mask])
        spear = stats.spearmanr(x[mask], y[mask])
        print(f"  vs {yn:<15}: Pearson {pear.statistic:+.3f} (p={pear.pvalue:.1e}), Spearman {spear.statistic:+.3f}, n={mask.sum()}")

print("\n--- Изменения (RAW, наиболее интерпретируемо) ---")
for xn, x, yn, y in [
    ("Δp 1d",  merged["dp"],    "Δlog(IMOEX)",  merged["r_imoex"]),
    ("Δp 5d",  merged["dp_5d"], "IMOEX 5d ret", merged["r_imoex_5d"]),
    ("Δp 20d", merged["dp_20d"],"IMOEX 20d ret", merged["r_imoex_20d"]),
]:
    mask = x.notna() & y.notna()
    pear = stats.pearsonr(x[mask], y[mask])
    print(f"  {xn:<8} vs {yn:<15}: Pearson {pear.statistic:+.3f} (p={pear.pvalue:.1e}), n={mask.sum()}")

# === Регрессия ===
print("\n" + "="*80)
print("РЕГРЕССИЯ: log(IMOEX) ~ log(oil) + ofz + p_synthetic")
print("="*80)
import statsmodels.api as sm

for col, label in [("p_synthetic_raw","RAW"), ("p_synthetic_lm","LEVEL-MATCH"), ("p_synthetic_z","Z-SCORE")]:
    sub = merged.dropna(subset=["log_imoex","brent_rub_ma3m","ofz5y",col]).copy()
    sub["log_oil"] = np.log(sub["brent_rub_ma3m"])
    X_base = sm.add_constant(sub[["log_oil","ofz5y"]])
    X_ext  = sm.add_constant(sub[["log_oil","ofz5y",col]])
    y = sub["log_imoex"]
    m_base = sm.OLS(y, X_base).fit(cov_type="HAC", cov_kwds={"maxlags":20})
    m_ext  = sm.OLS(y, X_ext).fit(cov_type="HAC", cov_kwds={"maxlags":20})
    print(f"\n{label}: Base R²={m_base.rsquared:.4f}  →  +factor R²={m_ext.rsquared:.4f}  (Δ={m_ext.rsquared-m_base.rsquared:+.4f}), n={int(m_ext.nobs)}")
    for pn, c, se, t, pv in zip(m_ext.params.index, m_ext.params.values, m_ext.bse.values, m_ext.tvalues.values, m_ext.pvalues.values):
        print(f"  {pn:<20} = {c:+.4f} (SE={se:.4f}, t={t:+.2f}, p={pv:.3f})")

# === Обновлённая fair value с учётом синтетического индекса ===
print("\n" + "="*80)
print("FAIR VALUE с учётом синтетического индекса (сегодня)")
print("="*80)

# Берём модель RAW (легче интерпретировать), считаем расширенный fair value
sub = merged.dropna(subset=["log_imoex","brent_rub_ma3m","ofz5y","p_synthetic_raw"]).copy()
sub["log_oil"] = np.log(sub["brent_rub_ma3m"])
X = sm.add_constant(sub[["log_oil","ofz5y","p_synthetic_raw"]])
y = sub["log_imoex"]
m_ext = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags":20})

# Прогноз fair value с новым фактором для всех дат
all_dates = merged.dropna(subset=["brent_rub_ma3m","ofz5y","p_synthetic_raw"]).copy()
all_dates["log_oil"] = np.log(all_dates["brent_rub_ma3m"])
X_all = sm.add_constant(all_dates[["log_oil","ofz5y","p_synthetic_raw"]])
X_all = X_all[X.columns]  # совпадение порядка
all_dates["log_fair_ext"] = X_all @ m_ext.params
all_dates["fair_ext"] = np.exp(all_dates["log_fair_ext"])
all_dates["dev_ext"] = all_dates["imoex"] / all_dates["fair_ext"] - 1

last = all_dates.iloc[-1]
print(f"\nНа {last['date'].date()}:")
print(f"  IMOEX факт: {last['imoex']:,.2f}")
print(f"  Fair value (модель A базовая): {last['fair_value_A']:,.2f}, откл {(last['imoex']/last['fair_value_A']-1)*100:+.2f}%")
print(f"  Fair value (модель + синт.):   {last['fair_ext']:,.2f}, откл {last['dev_ext']*100:+.2f}%")
print(f"  Синтетический индекс сегодня: {last['p_synthetic_raw']:.3f} (источник: {last['source']})")

# Сохраняем
merged.to_csv(f"{WORKDIR}/synthetic_index_merged.csv", index=False)
synth.to_csv(f"{WORKDIR}/synthetic_index.csv", index=False)
all_dates[["date","source","p_synthetic_raw","imoex","fair_value_A","fair_ext","dev_ext"]].to_csv(
    f"{WORKDIR}/fair_value_extended.csv", index=False)

# Финальная сводка коэффициентов расширенной модели
coefs = {name: {"value": float(m_ext.params[name]), "se": float(m_ext.bse[name]),
                "t": float(m_ext.tvalues[name]), "p": float(m_ext.pvalues[name])}
         for name in m_ext.params.index}
import json
with open(f"{WORKDIR}/model_extended.json","w") as f:
    json.dump({
        "coefficients": coefs,
        "r_squared": float(m_ext.rsquared),
        "adj_r_squared": float(m_ext.rsquared_adj),
        "n_obs": int(m_ext.nobs),
    }, f, indent=2)
print("\nСохранено: synthetic_index.csv, synthetic_index_merged.csv, fair_value_extended.csv, model_extended.json")
