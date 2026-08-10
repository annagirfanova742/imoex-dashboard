"""
Расширенный сценарный анализ: сравниваем модели A и B, добавляем
"полное закрытие отклонения" как верхнюю границу.
"""
import json
import numpy as np
import pandas as pd

import os as _os
WORKDIR = _os.environ.get("WORKDIR", "/home/user/workspace")

with open(f"{WORKDIR}/model_results.json") as f:
    res = json.load(f)

mA = res["model_A"]["coefficients"]
mB = res["model_B"]["coefficients"]
mC = res["model_C_ECM"]
fv = res["fair_value_now"]

IMOEX_NOW = fv["imoex_actual"]
BRENT_NOW = fv["inputs"]["brent"]
USDRUB_NOW = fv["inputs"]["usdrub"]
BRENT_RUB_MA3M_NOW = fv["inputs"]["brent_rub_ma3m"]
OFZ_NOW = fv["inputs"]["ofz5y"]

# Модель A (единая) — сильные коэффициенты
def fair_A(brent_rub_ma3m, ofz5y):
    return np.exp(mA["const"]["value"]
                  + mA["log_brent_rub_ma3m"]["value"] * np.log(brent_rub_ma3m)
                  + mA["ofz5y"]["value"] * ofz5y)

# Модель B (post-2022)
def fair_B(brent_rub_ma3m, ofz5y):
    return np.exp(mB["const"]["value"]
                  + mB["log_brent_rub_ma3m"]["value"] * np.log(brent_rub_ma3m)
                  + mB["ofz5y"]["value"] * ofz5y
                  + mB["post2022"]["value"]
                  + mB["oil_post"]["value"] * np.log(brent_rub_ma3m)
                  + mB["ofz_post"]["value"] * ofz5y)

GAMMA = abs(mC["coefficients"]["ect"]["value"])
dev_A_now = IMOEX_NOW / fv["fair_value_model_A"] - 1  # -0.060
dev_B_now = IMOEX_NOW / fv["fair_value_model_B"] - 1  # -0.154

print(f"Стартовые отклонения:")
print(f"  По модели A (единая):   {dev_A_now*100:+.2f}%   (fair {fv['fair_value_model_A']:,.0f})")
print(f"  По модели B (post-2022): {dev_B_now*100:+.2f}%   (fair {fv['fair_value_model_B']:,.0f})")

def project(brent, usdrub, ofz, days, model="A", reversion_mode="ecm"):
    brent_rub_ma3m = (BRENT_RUB_MA3M_NOW + brent * usdrub) / 2
    if model == "A":
        fair_end = fair_A(brent_rub_ma3m, ofz)
        dev_now = dev_A_now
    else:
        fair_end = fair_B(brent_rub_ma3m, ofz)
        dev_now = dev_B_now
    
    if reversion_mode == "ecm":
        remaining = np.exp(-GAMMA * days)
    elif reversion_mode == "full":
        remaining = 0  # полное закрытие
    elif reversion_mode == "none":
        remaining = 1  # отклонение не закрывается
    
    dev_end = dev_now * remaining
    imoex_end = fair_end * (1 + dev_end)
    return imoex_end, fair_end, dev_end

# ==== Сравнение моделей на именованных сценариях ====
scenarios = [
    ("Пессимистичный", 55, 100, 17.0),
    ("Базовый",       68, 92,  14.0),
    ("Оптимистичный", 80, 85,  12.0),
    ("Статус-кво",    BRENT_NOW, USDRUB_NOW, OFZ_NOW),
]

print("\n" + "="*100)
print("СЦЕНАРИИ на 6 месяцев: модели A vs B, разные скорости возврата")
print("="*100)

results = []
for horizon_days, hlabel in [(63, "3М"), (126, "6М"), (252, "12М")]:
    print(f"\n--- Горизонт {hlabel} ({horizon_days} дней) ---")
    header = f"{'Сценарий':<18} | {'Мод A ECM':>10} {'Мод A full':>11} | {'Мод B ECM':>10} {'Мод B full':>11}"
    print(header)
    print("-" * len(header))
    for name, br, usd, ofz in scenarios:
        row = f"{name:<18} | "
        vals = {}
        for model in ["A", "B"]:
            for mode in ["ecm", "full"]:
                imoex_end, _, _ = project(br, usd, ofz, horizon_days, model, mode)
                ret = (imoex_end / IMOEX_NOW - 1) * 100
                vals[f"{model}_{mode}"] = ret
        row += f"{vals['A_ecm']:>+9.1f}% {vals['A_full']:>+10.1f}% | {vals['B_ecm']:>+9.1f}% {vals['B_full']:>+10.1f}%"
        print(row)
        if horizon_days == 126:
            results.append({
                "name": name, "brent": br, "usdrub": usd, "ofz5y": ofz,
                **{f"return_6m_{k}": round(v, 2) for k, v in vals.items()}
            })

# ==== Ключевая таблица: доходность в 6М по A с ECM-реверсией ====
print("\n" + "="*100)
print("МАТРИЦА: доходность 6М по модели A с ECM-реверсией (это лучшая честная оценка)")
print("USD/RUB фиксирован на 82.75")
print("="*100)
brent_grid = [55, 60, 65, 70, 75, 80, 85, 90]
ofz_grid = [10, 12, 14, 15.5, 17, 19]
print(f"\n{'Brent \\ ОФЗ':>12} " + "".join(f"{o:>8.1f}%" for o in ofz_grid))
for brent in brent_grid:
    row = f"${brent:>10}/bbl "
    for ofz in ofz_grid:
        imoex_end, _, _ = project(brent, USDRUB_NOW, ofz, 126, "A", "ecm")
        ret = (imoex_end / IMOEX_NOW - 1) * 100
        row += f"{ret:>+8.1f}%"
    print(row)

# ==== Взвешенная оценка ====
weights = {"Пессимистичный": 0.20, "Базовый": 0.50, "Оптимистичный": 0.20, "Статус-кво": 0.10}
print("\n" + "="*100)
print("ВЕРОЯТНОСТНО-ВЗВЕШЕННАЯ ДОХОДНОСТЬ (6М)")
for key in ["return_6m_A_ecm", "return_6m_A_full", "return_6m_B_ecm", "return_6m_B_full"]:
    pass
for key in ["A_ecm", "A_full", "B_ecm", "B_full"]:
    key_full = f"return_6m_{key}"
    ew = sum(weights[r["name"]] * r[key_full] for r in results)
    print(f"  {key_full:25s}: {ew:+.2f}%")

ofz_carry_6m = ((1 + OFZ_NOW/100)**0.5 - 1) * 100
print(f"\n  Carry в ОФЗ 5Y за 6М: +{ofz_carry_6m:.2f}%")

# Сохраним
with open(f"{WORKDIR}/scenario_results.json", "w", encoding="utf-8") as f:
    json.dump({
        "starting": {
            "date": "2026-08-10", "imoex": IMOEX_NOW, "brent": BRENT_NOW,
            "usdrub": USDRUB_NOW, "ofz5y": OFZ_NOW,
            "fair_A": fv["fair_value_model_A"], "fair_B": fv["fair_value_model_B"],
            "dev_A_pct": dev_A_now*100, "dev_B_pct": dev_B_now*100,
        },
        "reversion": {
            "gamma": GAMMA, "half_life_days": np.log(2)/GAMMA,
            "reversion_3m": (1-np.exp(-GAMMA*63))*100,
            "reversion_6m": (1-np.exp(-GAMMA*126))*100,
            "reversion_12m": (1-np.exp(-GAMMA*252))*100,
        },
        "scenarios_6m": results,
        "ofz_carry_6m_pct": ofz_carry_6m,
        "weights": weights,
    }, f, ensure_ascii=False, indent=2)
print("\nСохранено: scenario_results.json")
