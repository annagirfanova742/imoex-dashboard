"""
Загружает параметры КБД (ZCYC) с MOEX ISS для каждого торгового дня начиная с 2014-01-06.
Считает доходность ОФЗ 5Y по формуле MOEX Nelson-Siegel с 9 гауссовыми поправками.

Берём ПОСЛЕДНЮЮ строку param-таблицы на день (конец торговой сессии).
"""
import time
import requests
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import os as _os
WORKDIR = _os.environ.get("WORKDIR", "/home/user/workspace")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})

# Рекуррентные a_i, b_i согласно методике MOEX: a1=0, a2=0.6, k=1.6, b1=a2, b_{i+1}=b_i*k
_A = np.zeros(9)
_B = np.zeros(9)
_A[0] = 0.0
_A[1] = 0.6
_B[0] = _A[1]
K = 1.6
for i in range(2, 9):
    _A[i] = _A[i - 1] + K ** (i - 1)
    _B[i - 1] = _B[i - 2] * K
_B[8] = _B[7] * K


def _gt_bp(t, b0, b1, b2, tau, g):
    """G(t) в базисных пунктах (не делённое на 10000)."""
    x = t / tau
    ex = np.exp(-x)
    term1 = b0 + b1 * tau * (1 - ex) / t
    term2 = b2 * ((1 - ex) * tau / t - ex)
    term3 = 0.0
    for i in range(9):
        if _B[i] != 0:
            term3 += g[i] * np.exp(-((t - _A[i]) ** 2) / (_B[i] ** 2))
    return term1 + term2 + term3


def kbd_yield_pct(t, b0, b1, b2, tau, g):
    """Спот-доходность на сроке t лет в процентах годовых (эффективная)."""
    gt = _gt_bp(t, b0, b1, b2, tau, g) / 10000.0
    return 100.0 * (np.exp(gt) - 1.0)


def fetch_zcyc_last_row(date_str):
    """Возвращает последние параметры КБД за день (конец сессии) или None.
    Тянем всё одним пакетом (limit=100000 гарантированно захватывает весь день, обычно ~20k строк).
    """
    for attempt in range(4):
        try:
            r = SESSION.get(
                f"https://iss.moex.com/iss/history/engines/stock/zcyc.json?date={date_str}&iss.meta=off&limit=100000",
                timeout=60,
            )
            r.raise_for_status()
            d = r.json()
            break
        except Exception:
            if attempt == 3:
                return None
            time.sleep(2 ** attempt * 0.3)

    params = d.get("params", {})
    cols = params.get("columns", [])
    rows = params.get("data", [])
    if not rows:
        return None
    return dict(zip(cols, rows[-1]))


def compute_ofz5y_from_row(row):
    if row is None:
        return None
    try:
        def _g(*keys):
            for k in keys:
                if k in row and row[k] is not None:
                    return row[k]
            return None
        b0 = _g("b1", "B1"); b1 = _g("b2", "B2"); b2 = _g("b3", "B3"); tau = _g("t1", "T1")
        if b0 is None or tau is None or tau == 0:
            return None
        g = [(_g(f"g{i}", f"G{i}") or 0.0) for i in range(1, 10)]
        return float(kbd_yield_pct(5.0, b0, b1 or 0.0, b2 or 0.0, tau, g))
    except Exception:
        return None


def load_trading_dates():
    """Собираем объединение дат IMOEX и USD/RUB."""
    dates = set()
    for f in ["imoex_daily.csv", "usdrub_daily.csv"]:
        df = pd.read_csv(f"{WORKDIR}/{f}")
        dates.update(df["date"].astype(str))
    dates = sorted(dates)
    dates = [d for d in dates if d >= "2014-01-06"]
    return dates


def main():
    cache_path = Path(f"{WORKDIR}/ofz5y_cache.csv")
    cache = {}
    if cache_path.exists():
        cdf = pd.read_csv(cache_path)
        cache = dict(zip(cdf["date"].astype(str), cdf["ofz5y"]))
        print(f"из кэша: {len(cache)} дат")

    dates = load_trading_dates()
    todo = [d for d in dates if d not in cache]
    print(f"всего дат: {len(dates)}, к загрузке: {len(todo)}")

    if not todo:
        print("всё уже посчитано")
        return

    results = {}
    t0 = time.time()

    def _work(d):
        try:
            row = fetch_zcyc_last_row(d)
            y = compute_ofz5y_from_row(row)
            return d, y
        except Exception:
            return d, None

    with ThreadPoolExecutor(max_workers=16) as ex:
        futs = [ex.submit(_work, d) for d in todo]
        done = 0
        for f in as_completed(futs):
            d, y = f.result()
            if y is not None:
                results[d] = y
            done += 1
            if done % 200 == 0:
                elapsed = time.time() - t0
                rate = done / elapsed
                eta = (len(todo) - done) / rate if rate > 0 else 0
                print(f"  {done}/{len(todo)}, ok={len(results)}, {elapsed:.0f}с, ETA {eta:.0f}с", flush=True)
                # Промежуточное сохранение
                cache.update(results); results.clear()
                out = pd.DataFrame({"date": list(cache.keys()), "ofz5y": list(cache.values())})
                out.sort_values("date").to_csv(cache_path, index=False)

    cache.update(results)
    out = pd.DataFrame({"date": list(cache.keys()), "ofz5y": list(cache.values())})
    out = out.sort_values("date").reset_index(drop=True)
    out.to_csv(cache_path, index=False)
    print(f"сохранил {len(out)} строк в ofz5y_cache.csv, время {time.time()-t0:.0f}с")


if __name__ == "__main__":
    main()
