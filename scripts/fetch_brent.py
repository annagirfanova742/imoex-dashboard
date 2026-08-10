"""
Собирает непрерывный ряд Brent из фьючерсов BR на MOEX FORTS.
Для каждого контракта пробуем варианты: BR<M><Y>_YYYY и BR<M><Y>.
На каждую дату берём фронтальный контракт с максимальным VALUE (оборот в рублях).
"""
import time
import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

import os as _os
WORKDIR = _os.environ.get("WORKDIR", "/home/user/workspace")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})

MONTHS = "FGHJKMNQUVXZ"  # F=янв ... Z=дек
# Соответствие: F->01, G->02, ...
MONTH_MAP = {c: i+1 for i, c in enumerate(MONTHS)}

def fetch_one(secid):
    """Тянет всю историю по одному тикеру."""
    rows_all = []
    cols = None
    start = 0
    while True:
        for attempt in range(4):
            try:
                r = SESSION.get(
                    f"https://iss.moex.com/iss/history/engines/futures/markets/forts/securities/{secid}.json"
                    f"?iss.meta=off&iss.only=history&limit=500&start={start}",
                    timeout=30,
                )
                r.raise_for_status()
                d = r.json()
                break
            except Exception:
                if attempt == 3:
                    return None, []
                time.sleep(2**attempt * 0.3)
        cols = d["history"]["columns"]
        rows = d["history"]["data"]
        if not rows:
            break
        rows_all.extend(rows)
        if len(rows) < 500:
            break
        start += 500
    return cols, rows_all


def build_ticker_list():
    """Формирует все кандидатные тикеры BR за 2013–2027."""
    tickers = []
    for year in range(2013, 2028):
        y1 = year % 10
        for m in MONTHS:
            # Оба формата — пробуем оба, взятое = где данные есть
            tickers.append((f"BR{m}{y1}_{year}", year, MONTH_MAP[m]))
            tickers.append((f"BR{m}{y1}", year, MONTH_MAP[m]))
    return tickers


def main():
    tickers = build_ticker_list()
    print(f"кандидатов тикеров: {len(tickers)}")

    all_data = []
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(fetch_one, t[0]): t for t in tickers}
        done = 0
        for f in as_completed(futs):
            secid, exp_year, exp_month = futs[f]
            cols, rows = f.result()
            done += 1
            if not rows:
                continue
            si = cols.index("SECID")
            di = cols.index("TRADEDATE")
            ci = cols.index("CLOSE")
            spi = cols.index("SETTLEPRICE")
            vi = cols.index("VALUE")  # оборот в рублях
            voli = cols.index("VOLUME")  # количество контрактов
            for row in rows:
                # Фильтруем спреды: SECID должен полностью совпадать с ожидаемым
                if row[si] != secid:
                    continue
                price = row[ci] if row[ci] is not None else row[spi]
                if price is None:
                    continue
                all_data.append({
                    "date": row[di],
                    "secid": secid,
                    "exp_year": exp_year,
                    "exp_month": exp_month,
                    "price": price,
                    "value": row[vi] or 0,
                    "volume": row[voli] or 0,
                })
            if done % 30 == 0:
                print(f"  готово {done}/{len(tickers)}, накоплено строк: {len(all_data)}, {time.time()-t0:.1f}с", flush=True)

    print(f"всего строк: {len(all_data)}, время {time.time()-t0:.1f}с")

    df = pd.DataFrame(all_data)
    df["date"] = pd.to_datetime(df["date"])
    # На каждую дату оставляем контракт с максимальным оборотом (VALUE, ₽)
    df = df.sort_values(["date", "value"], ascending=[True, False])
    front = df.drop_duplicates("date", keep="first").copy()
    front = front.sort_values("date").reset_index(drop=True)
    front["date"] = front["date"].dt.date

    print(f"уникальных дат: {len(front)}, {front['date'].min()}..{front['date'].max()}")
    front[["date", "secid", "price", "value", "volume"]].to_csv(
        f"{WORKDIR}/brent_moex_raw.csv", index=False
    )

    # Итоговый ряд
    front[["date", "price"]].rename(columns={"price": "brent"}).to_csv(
        f"{WORKDIR}/brent_daily.csv", index=False
    )
    print("сохранил brent_daily.csv, brent_moex_raw.csv")


if __name__ == "__main__":
    main()
