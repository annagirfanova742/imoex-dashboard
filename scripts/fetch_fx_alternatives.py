"""
Инкрементно обновляет USD/RUB от ЦБ РФ и CNY/RUB с MOEX.
Читает существующие CSV и дозагружает только свежие даты.
При отсутствии CSV — тянет с 2014 года кусками по годам.
"""
import os
import time
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import date, timedelta

_os_env = os.environ.get
WORKDIR = _os_env("WORKDIR", "/home/user/workspace")

TIMEOUT = 20

# ============================================================
# 1. ЦБ РФ — USD/RUB (R01235)
# ============================================================
def fetch_cbr_usd(start_ddmmyyyy, end_ddmmyyyy):
    url = (f"https://www.cbr.ru/scripts/XML_dynamic.asp?"
           f"date_req1={start_ddmmyyyy}&date_req2={end_ddmmyyyy}&VAL_NM_RQ=R01235")
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=TIMEOUT)
            r.encoding = "windows-1251"
            root = ET.fromstring(r.text)
            rows = []
            for rec in root.findall("Record"):
                d = pd.to_datetime(rec.attrib["Date"], format="%d.%m.%Y")
                val = float(rec.find("Value").text.replace(",", "."))
                nom = int(rec.find("Nominal").text)
                rows.append({"date": d, "usdrub_cbr": val/nom})
            return pd.DataFrame(rows)
        except Exception as e:
            print(f"  CBR retry {attempt+1}: {e}")
            time.sleep(2 * (attempt + 1))
    return pd.DataFrame(columns=["date", "usdrub_cbr"])

cbr_path = f"{WORKDIR}/usdrub_cbr.csv"
if os.path.exists(cbr_path):
    cbr = pd.read_csv(cbr_path, parse_dates=["date"])
    last = cbr["date"].max().date()
    start = (last + timedelta(days=1)).strftime("%d/%m/%Y")
    end = date.today().strftime("%d/%m/%Y")
    print(f"ЦБ USD/RUB: incremental {start} → {end}")
    if pd.to_datetime(start) <= pd.to_datetime(end):
        new = fetch_cbr_usd(start, end)
        print(f"  добавлено {len(new)} новых записей")
        cbr = pd.concat([cbr, new], ignore_index=True).drop_duplicates("date").sort_values("date")
    else:
        print("  уже актуально")
else:
    print("ЦБ USD/RUB: полная загрузка по годам")
    frames = []
    for year in range(2014, date.today().year + 1):
        df = fetch_cbr_usd(f"01/01/{year}", f"31/12/{year}")
        if len(df) > 0:
            frames.append(df)
            print(f"  {year}: {len(df)} дней")
    cbr = pd.concat(frames, ignore_index=True).drop_duplicates("date").sort_values("date")
cbr.to_csv(cbr_path, index=False)
print(f"Итого ЦБ USD/RUB: {len(cbr)}, {cbr['date'].min().date()} → {cbr['date'].max().date()}\n")


# ============================================================
# 2. MOEX ISS — CNY/RUB spot (CNYRUB_TOM)
# ============================================================
def fetch_moex_history(secid, start_iso):
    rows = []
    cols = None
    date_from = pd.Timestamp(start_iso)
    end = pd.Timestamp.today() + pd.Timedelta(days=1)
    while date_from < end:
        date_to = min(date_from + pd.Timedelta(days=100), end)
        url = (f"https://iss.moex.com/iss/history/engines/currency/markets/selt/boards/CETS"
               f"/securities/{secid}.json"
               f"?from={date_from.strftime('%Y-%m-%d')}&till={date_to.strftime('%Y-%m-%d')}")
        for attempt in range(4):
            try:
                r = requests.get(url, timeout=TIMEOUT)
                data = r.json()
                cols = data["history"]["columns"] if cols is None else cols
                rows.extend(data["history"]["data"])
                break
            except Exception as e:
                print(f"  MOEX {secid} retry {attempt+1}: {e}")
                time.sleep(2 * (attempt + 1))
        date_from = date_to + pd.Timedelta(days=1)
    if not rows:
        return pd.DataFrame(columns=["date", "cnyrub"])
    df = pd.DataFrame(rows, columns=cols)
    df["date"] = pd.to_datetime(df["TRADEDATE"])
    df["cnyrub"] = df["CLOSE"].astype(float)
    return df[["date", "cnyrub"]].drop_duplicates("date").sort_values("date")

cny_path = f"{WORKDIR}/cnyrub_moex.csv"
if os.path.exists(cny_path):
    cny = pd.read_csv(cny_path, parse_dates=["date"])
    last = cny["date"].max().date()
    start = (last + timedelta(days=1)).isoformat()
    print(f"CNY/RUB MOEX: incremental с {start}")
    if pd.Timestamp(start) <= pd.Timestamp.today():
        new = fetch_moex_history("CNYRUB_TOM", start)
        print(f"  добавлено {len(new)} новых записей")
        cny = pd.concat([cny, new], ignore_index=True).drop_duplicates("date").sort_values("date")
    else:
        print("  уже актуально")
else:
    print("CNY/RUB MOEX: полная загрузка")
    cny = fetch_moex_history("CNYRUB_TOM", "2014-01-01")
cny.to_csv(cny_path, index=False)
print(f"Итого CNY/RUB: {len(cny)}, {cny['date'].min().date()} → {cny['date'].max().date()}")
