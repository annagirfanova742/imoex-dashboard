"""Загрузка IMOEX и USD/RUB с MOEX ISS с 2014 года. Постранично, с ретраями."""
import time, sys, os
import requests
import pandas as pd
from datetime import date

import os as _os
WORKDIR = _os.environ.get("WORKDIR", "/home/user/workspace")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0"})

def fetch_candles(url_tmpl, start="2014-01-01", till=None, interval=24):
    """Постранично тянет свечи по 500 штук."""
    till = till or date.today().isoformat()
    rows = []
    cursor_start = 0
    while True:
        url = url_tmpl.format(start=start, till=till, interval=interval, cursor=cursor_start)
        for attempt in range(5):
            try:
                r = SESSION.get(url, timeout=30)
                r.raise_for_status()
                data = r.json()
                break
            except Exception as e:
                if attempt == 4:
                    raise
                time.sleep(2 ** attempt)
        cols = data["candles"]["columns"]
        chunk = data["candles"]["data"]
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < 500:
            break
        cursor_start += 500
        time.sleep(0.05)
    df = pd.DataFrame(rows, columns=cols)
    return df

def fetch_imoex():
    url = ("https://iss.moex.com/iss/engines/stock/markets/index/securities/IMOEX/candles.json"
           "?from={start}&till={till}&interval={interval}&start={cursor}")
    df = fetch_candles(url)
    df["begin"] = pd.to_datetime(df["begin"])
    df["date"] = df["begin"].dt.date
    out = df[["date", "close"]].rename(columns={"close": "imoex"}).drop_duplicates("date")
    return out

def fetch_usdrub():
    url = ("https://iss.moex.com/iss/engines/currency/markets/selt/securities/USD000UTSTOM/candles.json"
           "?from={start}&till={till}&interval={interval}&start={cursor}")
    df = fetch_candles(url)
    df["begin"] = pd.to_datetime(df["begin"])
    df["date"] = df["begin"].dt.date
    out = df[["date", "close"]].rename(columns={"close": "usdrub"}).drop_duplicates("date")
    return out

if __name__ == "__main__":
    print("Загружаю IMOEX...", flush=True)
    t0 = time.time()
    imoex = fetch_imoex()
    print(f"  {len(imoex)} строк, {imoex['date'].min()}..{imoex['date'].max()}, {time.time()-t0:.1f}с", flush=True)
    imoex.to_csv(f"{WORKDIR}/imoex_daily.csv", index=False)

    print("Загружаю USD/RUB...", flush=True)
    t0 = time.time()
    usd = fetch_usdrub()
    print(f"  {len(usd)} строк, {usd['date'].min()}..{usd['date'].max()}, {time.time()-t0:.1f}с", flush=True)
    usd.to_csv(f"{WORKDIR}/usdrub_daily.csv", index=False)
    print("OK")
