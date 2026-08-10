"""
Собираю данные Kalshi KXZELENSKYPUTIN-29-VPUT и проверяю корреляцию с IMOEX.
Также сравниваю его с Polymarket ceasefire до момента разрешения.
"""
import requests, pandas as pd, numpy as np
from scipy import stats

import os as _os
WORKDIR = _os.environ.get("WORKDIR", "/home/user/workspace")

base = "https://api.elections.kalshi.com/trade-api/v2"

def fetch_candles(series, ticker, start_iso, end_iso, period=1440):
    start_ts = int(pd.Timestamp(start_iso).timestamp())
    end_ts = int(pd.Timestamp(end_iso).timestamp())
    url = f"{base}/series/{series}/markets/{ticker}/candlesticks"
    r = requests.get(url, params={"start_ts": start_ts, "end_ts": end_ts, "period_interval": period}, timeout=30)
    r.raise_for_status()
    candles = r.json().get("candlesticks", [])
    rows = []
    for c in candles:
        ts = c["end_period_ts"]
        # Приоритет: цена сделки, потом mid bid-ask
        p = None
        price = c.get("price", {})
        if price.get("close_dollars"):
            p = float(price["close_dollars"])
        elif price.get("mean_dollars"):
            p = float(price["mean_dollars"])
        else:
            # берём mid of bid-ask close
            bid = c.get("yes_bid", {}).get("close_dollars")
            ask = c.get("yes_ask", {}).get("close_dollars")
            if bid and ask:
                p = (float(bid) + float(ask)) / 2
        if p is not None:
            rows.append({"date": pd.to_datetime(ts, unit="s").normalize(), "p": p,
                         "volume": float(c.get("volume_fp", 0)),
                         "oi": float(c.get("open_interest_fp", 0))})
    return pd.DataFrame(rows)

# Три рынка Kalshi
markets = {
    "KXZELENSKYPUTIN-29-VPUT":   ("2025-10-13", "2029-01-20", "Zelensky-Putin meet by Jan 2029"),
    "KXZELENSKYPUTIN-29-27":     ("2025-12-30", "2027-01-01", "Zelensky-Putin meet by Jan 2027"),
    "KXZELENSKYPUTIN-29-26JUL":  ("2025-12-30", "2026-07-01", "Zelensky-Putin meet by Jul 2026"),
}

kalshi_data = {}
for tic, (start, end, name) in markets.items():
    print(f"=== {tic}: {name} ===")
    df = fetch_candles("KXZELENSKYPUTIN", tic, start, "2026-08-11")
    if len(df) > 0:
        df = df.groupby("date").agg(p=("p", "last"), volume=("volume", "sum"), oi=("oi", "last")).reset_index()
        print(f"  {len(df)} дней, {df['date'].min().date()} → {df['date'].max().date()}")
        print(f"  p: {df['p'].min():.3f}..{df['p'].max():.3f}, средний OI {df['oi'].mean():,.0f}")
        kalshi_data[tic] = df
        df.to_csv(f"{WORKDIR}/kalshi_{tic}.csv", index=False)

# ==== Мерджим с IMOEX ====
factors = pd.read_csv(f"{WORKDIR}/imoex_factors.csv", parse_dates=["date"])
model_out = pd.read_csv(f"{WORKDIR}/imoex_model_output.csv", parse_dates=["date"])

# Используем самый длинный ряд — VPUT
main = kalshi_data["KXZELENSKYPUTIN-29-VPUT"].copy()
main["p_kalshi"] = main["p"]
merged = factors.merge(main[["date","p_kalshi","volume","oi"]], on="date", how="inner")
merged = merged.merge(model_out[["date","deviation_A","deviation_B","fair_value_A"]], on="date", how="left")
print(f"\n=== Мердж IMOEX × Kalshi VPUT ===")
print(f"Дней: {len(merged)}, диапазон {merged['date'].min().date()} → {merged['date'].max().date()}")
print(f"Средний OI: {merged['oi'].mean():,.0f}, средний объём: {merged['volume'].mean():,.0f}")

merged["log_imoex"] = np.log(merged["imoex"])
merged["dp_kalshi"] = merged["p_kalshi"].diff()
merged["dp_5d"] = merged["p_kalshi"].diff(5)
merged["dp_20d"] = merged["p_kalshi"].diff(20)
merged["r_imoex"] = merged["log_imoex"].diff()
merged["r_imoex_5d"] = merged["imoex"].pct_change(5)
merged["r_imoex_20d"] = merged["imoex"].pct_change(20)

print("\n=== Корреляции: уровни ===")
tests = [
    ("p_kalshi",     "log(IMOEX)",     merged["p_kalshi"],  merged["log_imoex"]),
    ("p_kalshi",     "IMOEX",          merged["p_kalshi"],  merged["imoex"]),
    ("p_kalshi",     "ОФЗ 5Y",         merged["p_kalshi"],  merged["ofz5y"]),
    ("p_kalshi",     "USDRUB",         merged["p_kalshi"],  merged["usdrub"]),
    ("p_kalshi",     "deviation_A",    merged["p_kalshi"],  merged["deviation_A"]),
]
print(f"{'X':<15} {'Y':<15} {'Pearson':>10} {'p-value':>12} {'Spearman':>10} {'n':>6}")
for xn, yn, x, y in tests:
    mask = x.notna() & y.notna()
    if mask.sum() < 20: continue
    xv, yv = x[mask].values, y[mask].values
    pear = stats.pearsonr(xv, yv)
    spear = stats.spearmanr(xv, yv)
    print(f"{xn:<15} {yn:<15} {pear.statistic:>+10.3f} {pear.pvalue:>12.2e} {spear.statistic:>+10.3f} {mask.sum():>6}")

print("\n=== Корреляции: изменения ===")
tests2 = [
    ("Δp (день)",  "Δlog(IMOEX)",  merged["dp_kalshi"], merged["r_imoex"]),
    ("Δp (5д)",    "IMOEX 5d ret", merged["dp_5d"],     merged["r_imoex_5d"]),
    ("Δp (20д)",   "IMOEX 20d ret", merged["dp_20d"],    merged["r_imoex_20d"]),
]
for xn, yn, x, y in tests2:
    mask = x.notna() & y.notna()
    if mask.sum() < 20: continue
    xv, yv = x[mask].values, y[mask].values
    pear = stats.pearsonr(xv, yv)
    spear = stats.spearmanr(xv, yv)
    print(f"{xn:<15} {yn:<15} {pear.statistic:>+10.3f} {pear.pvalue:>12.2e} {spear.statistic:>+10.3f} {mask.sum():>6}")

# ==== Сравнение с Polymarket за общий период ====
poly = pd.read_csv(f"{WORKDIR}/imoex_polymarket_merged.csv", parse_dates=["date"])
combined = merged.merge(poly[["date","p"]].rename(columns={"p":"p_poly"}), on="date", how="inner")
print(f"\n=== Общий период Kalshi × Polymarket: {len(combined)} дней ===")
if len(combined) > 20:
    m = combined["p_kalshi"].notna() & combined["p_poly"].notna()
    pear = stats.pearsonr(combined.loc[m, "p_kalshi"], combined.loc[m, "p_poly"])
    print(f"Корреляция p_kalshi vs p_polymarket: {pear.statistic:+.3f} (p={pear.pvalue:.2e})")
    print(f"Средние: Kalshi p={combined['p_kalshi'].mean():.3f}, Polymarket p={combined['p_poly'].mean():.3f}")

# ==== Регрессия с добавлением Kalshi ====
print("\n=== Регрессия: log(IMOEX) ~ log(oil) + ofz + p_kalshi ===")
import statsmodels.api as sm
sub = merged.dropna(subset=["log_imoex","brent_rub_ma3m","ofz5y","p_kalshi"]).copy()
sub["log_oil"] = np.log(sub["brent_rub_ma3m"])
X_base = sm.add_constant(sub[["log_oil", "ofz5y"]])
X_ext = sm.add_constant(sub[["log_oil", "ofz5y", "p_kalshi"]])
y = sub["log_imoex"]
for name, X in [("Base A", X_base), ("+ p_kalshi", X_ext)]:
    m = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags":10})
    print(f"\n{name}: R²={m.rsquared:.4f}, adj R²={m.rsquared_adj:.4f}, n={int(m.nobs)}")
    for pn, c, se, t, pv in zip(m.params.index, m.params.values, m.bse.values, m.tvalues.values, m.pvalues.values):
        print(f"  {pn:<15} = {c:+.4f} (SE={se:.4f}, t={t:+.2f}, p={pv:.3f})")

# Сохраним
merged.to_csv(f"{WORKDIR}/imoex_kalshi_merged.csv", index=False)
print(f"\nСохранено imoex_kalshi_merged.csv")
