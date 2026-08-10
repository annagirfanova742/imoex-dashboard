"""
Эконометрическая модель IMOEX на факторах Brent×USDRUB (сглаженная) и ОФЗ 5Y.

Пять блоков:
  A. Лог-линейная регрессия на уровнях: ln(IMOEX) = b1*ln(brent_rub_ma3m) + b2*ofz5y + c,
     стандартные ошибки HAC (Newey-West).
  B. То же + дамми post2022 (сдвиг уровня и наклонов).
  C. Модель коррекции ошибками (ECM): Δln(IMOEX) на Δln(brent_rub_ma3m), Δofz5y, lag(residual A).
  D. Walk-forward валидация ECM против random walk на последних 20% выборки.
  E. Fair value: справедливое значение IMOEX при текущих факторах и отклонение факта от него.

Плюс блок статистических тестов (ADF, Энгл–Грейнджер, тест Чоу — приближённо).
"""
import json
import warnings

import os as _os
WORKDIR = _os.environ.get("WORKDIR", "/home/user/workspace")
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller

df = pd.read_csv(f"{WORKDIR}/imoex_factors.csv", parse_dates=["date"])
df = df.sort_values("date").reset_index(drop=True)

# Логарифмы
df["log_imoex"] = np.log(df["imoex"])
df["log_brent_rub_ma3m"] = np.log(df["brent_rub_ma3m"])
df["post2022"] = (df["date"] >= "2022-02-24").astype(int)

results = {}

# ==================== ADF-тесты ====================
def adf_pvalue(series, name):
    s = series.dropna()
    if len(s) < 30:
        return None
    stat, p, *_ = adfuller(s, autolag="AIC")
    return {"adf_stat": float(stat), "p_value": float(p)}

results["adf_tests"] = {
    "log_imoex": adf_pvalue(df["log_imoex"], "log_imoex"),
    "log_brent_rub_ma3m": adf_pvalue(df["log_brent_rub_ma3m"], "log_brent_rub_ma3m"),
    "ofz5y": adf_pvalue(df["ofz5y"], "ofz5y"),
    "d_log_imoex": adf_pvalue(df["log_imoex"].diff(), "d_log_imoex"),
    "d_log_brent_rub_ma3m": adf_pvalue(df["log_brent_rub_ma3m"].diff(), "d_log_brent_rub_ma3m"),
    "d_ofz5y": adf_pvalue(df["ofz5y"].diff(), "d_ofz5y"),
}

# ==================== A. OLS на уровнях + HAC ====================
# Отбрасываем NaN — они возникают в первых 29 строках из-за rolling 63d
df = df.dropna(subset=["log_brent_rub_ma3m", "ofz5y", "log_imoex"]).reset_index(drop=True)
X_A = sm.add_constant(df[["log_brent_rub_ma3m", "ofz5y"]])
y = df["log_imoex"]
model_A = sm.OLS(y, X_A).fit(cov_type="HAC", cov_kwds={"maxlags": 20})

results["model_A"] = {
    "n_obs": int(model_A.nobs),
    "r_squared": float(model_A.rsquared),
    "adj_r_squared": float(model_A.rsquared_adj),
    "coefficients": {
        "const": {"value": float(model_A.params["const"]),
                  "std_err_HAC": float(model_A.bse["const"]),
                  "t": float(model_A.tvalues["const"]),
                  "p": float(model_A.pvalues["const"])},
        "log_brent_rub_ma3m": {"value": float(model_A.params["log_brent_rub_ma3m"]),
                               "std_err_HAC": float(model_A.bse["log_brent_rub_ma3m"]),
                               "t": float(model_A.tvalues["log_brent_rub_ma3m"]),
                               "p": float(model_A.pvalues["log_brent_rub_ma3m"])},
        "ofz5y": {"value": float(model_A.params["ofz5y"]),
                  "std_err_HAC": float(model_A.bse["ofz5y"]),
                  "t": float(model_A.tvalues["ofz5y"]),
                  "p": float(model_A.pvalues["ofz5y"])},
    },
}

# Тест Энгла–Грейнджера на коинтеграцию: ADF на остатках модели A
resid_A = model_A.resid
adf_resid_A = adfuller(resid_A.dropna(), autolag="AIC")
# Критические значения ЭГ отличаются от обычных ADF, но приведём p-value как ориентир
results["engle_granger"] = {
    "adf_stat_on_residuals": float(adf_resid_A[0]),
    "adf_p_value": float(adf_resid_A[1]),
    "note": "если stat ниже критических Э-Г ~-3.34 (5%), ряды коинтегрированы",
}

# ==================== B. С дамми post2022 (сдвиг уровня и наклонов) ====================
df["oil_post"] = df["log_brent_rub_ma3m"] * df["post2022"]
df["ofz_post"] = df["ofz5y"] * df["post2022"]
X_B = sm.add_constant(df[["log_brent_rub_ma3m", "ofz5y", "post2022", "oil_post", "ofz_post"]])
model_B = sm.OLS(y, X_B).fit(cov_type="HAC", cov_kwds={"maxlags": 20})

results["model_B"] = {
    "n_obs": int(model_B.nobs),
    "r_squared": float(model_B.rsquared),
    "adj_r_squared": float(model_B.rsquared_adj),
    "coefficients": {k: {"value": float(model_B.params[k]),
                         "std_err_HAC": float(model_B.bse[k]),
                         "t": float(model_B.tvalues[k]),
                         "p": float(model_B.pvalues[k])}
                     for k in X_B.columns},
}

# Отдельные подпериоды
pre = df[df["date"] < "2022-02-24"].copy()
post = df[df["date"] >= "2022-02-24"].copy()

for label, sub in [("pre_2022", pre), ("post_2022", post)]:
    if len(sub) < 100:
        continue
    Xp = sm.add_constant(sub[["log_brent_rub_ma3m", "ofz5y"]])
    m = sm.OLS(sub["log_imoex"], Xp).fit(cov_type="HAC", cov_kwds={"maxlags": 20})
    results[f"submodel_{label}"] = {
        "n_obs": int(m.nobs),
        "r_squared": float(m.rsquared),
        "coefficients": {k: float(m.params[k]) for k in Xp.columns},
        "std_errs": {k: float(m.bse[k]) for k in Xp.columns},
    }

# ==================== C. ECM ====================
# Δln(IMOEX) = γ * ect_{t-1} + a1*Δln(brent_rub_ma3m) + a2*Δofz5y + const
df["d_log_imoex"] = df["log_imoex"].diff()
df["d_log_oil"] = df["log_brent_rub_ma3m"].diff()
df["d_ofz5y"] = df["ofz5y"].diff()
df["ect"] = resid_A.shift(1)  # лагированный остаток модели A

ecm_df = df.dropna(subset=["d_log_imoex","d_log_oil","d_ofz5y","ect"]).copy()
X_C = sm.add_constant(ecm_df[["ect","d_log_oil","d_ofz5y"]])
model_C = sm.OLS(ecm_df["d_log_imoex"], X_C).fit(cov_type="HAC", cov_kwds={"maxlags": 20})

gamma = model_C.params["ect"]
half_life = np.log(2) / (-gamma) if gamma < 0 else None

results["model_C_ECM"] = {
    "n_obs": int(model_C.nobs),
    "r_squared": float(model_C.rsquared),
    "coefficients": {k: {"value": float(model_C.params[k]),
                         "std_err_HAC": float(model_C.bse[k]),
                         "t": float(model_C.tvalues[k]),
                         "p": float(model_C.pvalues[k])}
                     for k in X_C.columns},
    "gamma_ect": float(gamma),
    "half_life_days": float(half_life) if half_life else None,
    "interpretation": ("Отрицательный γ означает возврат к равновесию модели A; "
                       "период полураспада — сколько дней нужно, чтобы отклонение сократилось вдвое."),
}

# ==================== D. Walk-forward валидация ECM ====================
# На последних 20% выборки: на каждом шаге переоцениваем модель A и ECM на прошлом,
# делаем прогноз Δln(IMOEX)_{t} → IMOEX_t = IMOEX_{t-1} * exp(pred).
# Сравниваем с random walk (прогноз = IMOEX_{t-1}, т.е. Δ=0).

full = df.dropna(subset=["log_imoex","log_brent_rub_ma3m","ofz5y"]).copy().reset_index(drop=True)
n = len(full)
split = int(n * 0.8)
preds_ecm, preds_rw, actuals, dates = [], [], [], []

for t in range(split, n - 1):
    train = full.iloc[:t]
    # Модель A на трейне
    Xa = sm.add_constant(train[["log_brent_rub_ma3m","ofz5y"]])
    mA = sm.OLS(train["log_imoex"], Xa).fit()
    resid = train["log_imoex"] - mA.predict(Xa)
    # ECM на трейне
    ecm_train = pd.DataFrame({
        "d_log_imoex": train["log_imoex"].diff(),
        "d_log_oil": train["log_brent_rub_ma3m"].diff(),
        "d_ofz5y": train["ofz5y"].diff(),
        "ect": resid.shift(1),
    }).dropna()
    Xc = sm.add_constant(ecm_train[["ect","d_log_oil","d_ofz5y"]])
    mC = sm.OLS(ecm_train["d_log_imoex"], Xc).fit()
    # Прогноз на t+1 (используем факт факторов на t+1 — тест на способность объяснять)
    ect_t = full.iloc[t]["log_imoex"] - mA.predict(sm.add_constant(full.iloc[[t]][["log_brent_rub_ma3m","ofz5y"]], has_constant="add")).iloc[0]
    d_oil = full.iloc[t+1]["log_brent_rub_ma3m"] - full.iloc[t]["log_brent_rub_ma3m"]
    d_ofz = full.iloc[t+1]["ofz5y"] - full.iloc[t]["ofz5y"]
    x_new = pd.DataFrame({"const":[1.0], "ect":[ect_t], "d_log_oil":[d_oil], "d_ofz5y":[d_ofz]})
    pred_d = mC.predict(x_new).iloc[0]
    pred_log_imoex = full.iloc[t]["log_imoex"] + pred_d
    actual_log_imoex = full.iloc[t+1]["log_imoex"]
    preds_ecm.append(pred_log_imoex)
    preds_rw.append(full.iloc[t]["log_imoex"])
    actuals.append(actual_log_imoex)
    dates.append(full.iloc[t+1]["date"])

preds_ecm = np.array(preds_ecm); preds_rw = np.array(preds_rw); actuals = np.array(actuals)

def rmse(a, b):
    return float(np.sqrt(np.mean((a-b)**2)))

def mape(a, b):
    return float(np.mean(np.abs((np.exp(a)-np.exp(b))/np.exp(a))) * 100)

# Точность направления
d_actual = np.diff(actuals, prepend=actuals[0]) if len(actuals) else np.array([])
# Направление на шаге t: знак предсказанного изменения vs фактического
sign_actual = np.sign(actuals - preds_rw)  # реальное изменение
sign_ecm    = np.sign(preds_ecm - preds_rw)  # предсказанное изменение
hit_ecm = float(np.mean(sign_actual == sign_ecm)) if len(sign_actual) else None
hit_rw  = 0.5

results["model_D_walkforward"] = {
    "n_test": int(len(actuals)),
    "train_end": full.iloc[split-1]["date"].strftime("%Y-%m-%d") if split > 0 else None,
    "test_start": full.iloc[split]["date"].strftime("%Y-%m-%d") if split < n else None,
    "test_end": full.iloc[n-1]["date"].strftime("%Y-%m-%d") if n > 0 else None,
    "rmse_log_ecm": rmse(preds_ecm, actuals),
    "rmse_log_random_walk": rmse(preds_rw, actuals),
    "mape_pct_ecm": mape(preds_ecm, actuals),
    "mape_pct_random_walk": mape(preds_rw, actuals),
    "direction_hit_rate_ecm": hit_ecm,
    "direction_hit_rate_random_walk": hit_rw,
    "note": "Прогноз на t+1 использует ФАКТ факторов на t+1 (не их прогноз) — тест на объясняющую силу.",
}

# Сохраняем прогноз для графика
wf_df = pd.DataFrame({
    "date": dates,
    "log_imoex_actual": actuals,
    "log_imoex_pred_ecm": preds_ecm,
    "log_imoex_pred_rw": preds_rw,
})
wf_df["imoex_actual"] = np.exp(wf_df["log_imoex_actual"])
wf_df["imoex_pred_ecm"] = np.exp(wf_df["log_imoex_pred_ecm"])
wf_df["imoex_pred_rw"] = np.exp(wf_df["log_imoex_pred_rw"])
wf_df.to_csv(f"{WORKDIR}/walkforward.csv", index=False)

# ==================== E. Fair value ====================
# На каждый день считаем модель A → fair_value = exp(pred),
# отклонение = actual/fair - 1.
df["log_fit_A"] = model_A.predict(X_A)
df["fair_value_A"] = np.exp(df["log_fit_A"])
df["deviation_A"] = df["imoex"] / df["fair_value_A"] - 1

# Также fair value по модели B (с учётом post2022)
df["log_fit_B"] = model_B.predict(X_B)
df["fair_value_B"] = np.exp(df["log_fit_B"])
df["deviation_B"] = df["imoex"] / df["fair_value_B"] - 1

df.to_csv(f"{WORKDIR}/imoex_model_output.csv", index=False)

# Текущее fair value и отклонение
last = df.iloc[-1]
results["fair_value_now"] = {
    "date": last["date"].strftime("%Y-%m-%d"),
    "imoex_actual": float(last["imoex"]),
    "fair_value_model_A": float(last["fair_value_A"]),
    "deviation_pct_A": float(last["deviation_A"] * 100),
    "fair_value_model_B": float(last["fair_value_B"]),
    "deviation_pct_B": float(last["deviation_B"] * 100),
    "inputs": {
        "brent": float(last["brent"]),
        "usdrub": float(last["usdrub"]),
        "brent_rub_ma3m": float(last["brent_rub_ma3m"]),
        "ofz5y": float(last["ofz5y"]),
    },
}

# ==================== Сохранение ====================
with open(f"{WORKDIR}/model_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

# Печатаем сжатую сводку
def pcoef(m, key):
    c = m["coefficients"][key]
    return f"{c['value']:+.4f} (SE={c['std_err_HAC']:.4f}, t={c['t']:+.2f}, p={c['p']:.3f})"

print("=== ADF-тесты (H0: единичный корень) ===")
for k, v in results["adf_tests"].items():
    if v: print(f"  {k}: stat={v['adf_stat']:+.2f}, p={v['p_value']:.3f}")

print("\n=== Модель A: OLS на уровнях с HAC ===")
mA = results["model_A"]
print(f"  n={mA['n_obs']}, R²={mA['r_squared']:.4f}, adj R²={mA['adj_r_squared']:.4f}")
print(f"  const              = {pcoef(mA, 'const')}")
print(f"  log(brent_rub_ma3m) = {pcoef(mA, 'log_brent_rub_ma3m')}")
print(f"  ofz5y              = {pcoef(mA, 'ofz5y')}")

print("\n=== Engle-Granger ===")
eg = results["engle_granger"]
print(f"  ADF на остатках: stat={eg['adf_stat_on_residuals']:+.2f}, p={eg['adf_p_value']:.3f}")

print("\n=== Модель B: со сдвигом post2022 ===")
mB = results["model_B"]
print(f"  n={mB['n_obs']}, R²={mB['r_squared']:.4f}, adj R²={mB['adj_r_squared']:.4f}")
for k in ["const","log_brent_rub_ma3m","ofz5y","post2022","oil_post","ofz_post"]:
    print(f"  {k:22s}= {pcoef(mB, k)}")

print("\n=== Подпериоды ===")
for k in ["submodel_pre_2022","submodel_post_2022"]:
    if k in results:
        r = results[k]
        print(f"  {k}: n={r['n_obs']}, R²={r['r_squared']:.4f}, coef={r['coefficients']}")

print("\n=== Модель C: ECM ===")
mC = results["model_C_ECM"]
print(f"  n={mC['n_obs']}, R²={mC['r_squared']:.4f}")
for k in ["const","ect","d_log_oil","d_ofz5y"]:
    print(f"  {k:12s}= {pcoef(mC, k)}")
print(f"  γ (ect) = {mC['gamma_ect']:+.4f}, полураспад отклонения ≈ {mC['half_life_days']:.0f} дн" if mC["half_life_days"] else "  γ >= 0")

print("\n=== Модель D: walk-forward валидация ===")
mD = results["model_D_walkforward"]
print(f"  тест {mD['test_start']} → {mD['test_end']}, n={mD['n_test']}")
print(f"  RMSE log: ECM={mD['rmse_log_ecm']:.4f}, RW={mD['rmse_log_random_walk']:.4f}")
print(f"  MAPE %:   ECM={mD['mape_pct_ecm']:.2f}, RW={mD['mape_pct_random_walk']:.2f}")
print(f"  Direction hit: ECM={mD['direction_hit_rate_ecm']:.1%}")

print("\n=== E: Fair value сейчас ===")
fv = results["fair_value_now"]
print(f"  на {fv['date']}: IMOEX факт {fv['imoex_actual']:.2f}")
print(f"  Модель A: fair {fv['fair_value_model_A']:.2f}, откл {fv['deviation_pct_A']:+.1f}%")
print(f"  Модель B: fair {fv['fair_value_model_B']:.2f}, откл {fv['deviation_pct_B']:+.1f}%")
