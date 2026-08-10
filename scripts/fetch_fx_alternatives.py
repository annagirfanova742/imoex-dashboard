"""
Собираем альтернативные меры USD/RUB после 12 июня 2024 (санкции OFAC на MOEX):
  1. Официальный курс ЦБ РФ (метод после июня 2024 = OTC/внебиржевой)
  2. Кросс через CNY/RUB (MOEX торгуется) × USD/CNY (глобальный рынок)
  3. Фьючерсы Si (USDRUB) на MOEX
  4. Золото в рублях (GLDRUB_TOM на MOEX) / gold USD (спот)
"""
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

import os as _os
WORKDIR = _os.environ.get("WORKDIR", "/home/user/workspace")

# ============================================================
# 1. ЦБ РФ — официальный курс USD/RUB
# ============================================================
print("=" * 70)
print("1. ЦБ РФ USD/RUB (официальный)")
print("=" * 70)

def fetch_cbr_usd(start, end):
    url = f"https://www.cbr.ru/scripts/XML_dynamic.asp?date_req1={start}&date_req2={end}&VAL_NM_RQ=R01235"
    r = requests.get(url, timeout=30)
    r.encoding = "windows-1251"
    root = ET.fromstring(r.text)
    rows = []
    for rec in root.findall("Record"):
        d = pd.to_datetime(rec.attrib["Date"], format="%d.%m.%Y")
        val = float(rec.find("Value").text.replace(",", "."))
        nom = int(rec.find("Nominal").text)
        rows.append({"date": d, "usdrub_cbr": val/nom})
    return pd.DataFrame(rows)

# ЦБ разрешает только промежутки, тянем частями
cbr_frames = []
for year in range(2014, 2027):
    df = fetch_cbr_usd(f"01/01/{year}", f"31/12/{year}")
    if len(df) > 0:
        cbr_frames.append(df)
        print(f"  {year}: {len(df)} дней, {df['usdrub_cbr'].iloc[0]:.2f} → {df['usdrub_cbr'].iloc[-1]:.2f}")
cbr = pd.concat(cbr_frames, ignore_index=True).drop_duplicates("date").sort_values("date")
cbr.to_csv(f"{WORKDIR}/usdrub_cbr.csv", index=False)
print(f"\nВсего дней ЦБ: {len(cbr)}, диапазон {cbr['date'].min().date()} → {cbr['date'].max().date()}")


# ============================================================
# 2. MOEX ISS — CNY/RUB spot
# ============================================================
print("\n" + "=" * 70)
print("2. CNY/RUB spot на MOEX (CNYRUB_TOM)")
print("=" * 70)

def fetch_moex_iss(secid, engine="currency", market="selt", board="CETS", start="2014-01-01"):
    """MOEX ISS API — история торгов"""
    rows = []
    date_from = pd.Timestamp(start)
    while date_from < pd.Timestamp.now():
        date_to = min(date_from + pd.Timedelta(days=100), pd.Timestamp.now())
        url = (f"https://iss.moex.com/iss/history/engines/{engine}/markets/{market}/boards/{board}"
               f"/securities/{secid}.json"
               f"?from={date_from.strftime('%Y-%m-%d')}&till={date_to.strftime('%Y-%m-%d')}"
               f"&limit=100&start=0")
        offset = 0
        while True:
            r = requests.get(url + f"&start={offset}", timeout=30)
            if r.status_code != 200:
                break
            data = r.json()
            h = data.get("history", {})
            cols = h.get("columns", [])
            dat = h.get("data", [])
            if not dat:
                break
            df = pd.DataFrame(dat, columns=cols)
            rows.append(df)
            if len(dat) < 100:
                break
            offset += 100
        date_from = date_to + pd.Timedelta(days=1)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)

cnyrub = fetch_moex_iss("CNYRUB_TOM", start="2014-01-01")
if len(cnyrub) > 0:
    cnyrub["date"] = pd.to_datetime(cnyrub["TRADEDATE"])
    keep = [c for c in ["date","CLOSE","NUMTRADES","WAPRICE"] if c in cnyrub.columns]
    cnyrub = cnyrub[keep].rename(columns={"CLOSE":"cnyrub","NUMTRADES":"cnyrub_numtrades","WAPRICE":"cnyrub_wap"})
    cnyrub = cnyrub.sort_values("date").drop_duplicates("date")
    cnyrub.to_csv(f"{WORKDIR}/cnyrub_moex.csv", index=False)
    print(f"CNY/RUB на MOEX: {len(cnyrub)} дней, {cnyrub['date'].min().date()} → {cnyrub['date'].max().date()}")
    if "cnyrub_numtrades" in cnyrub.columns:
        print(f"Средние сделки/день: {cnyrub['cnyrub_numtrades'].mean():,.0f}")


# ============================================================
# 3. MOEX ISS — фьючерсы Si (USDRUB)
# ============================================================
print("\n" + "=" * 70)
print("3. Фьючерсы Si (USD/RUB futures на MOEX)")
print("=" * 70)

# Фьючерсы имеют коды вида SiU4 (сентябрь 2024) и т.д. Проще брать «непрерывный» ряд.
# У MOEX есть Si-фьючерс как «активный контракт», но история сложная — соберём по кодам.
# Простой путь: тянем помесячно ближайший ликвидный контракт.

# Коды: SiH4, SiM4, SiU4, SiZ4 (март, июнь, сентябрь, декабрь)
# Собираем ежедневную «переходящую» серию — берём последнюю известную цену для каждого дня

futures_frames = []
months_map = {3: "H", 6: "M", 9: "U", 12: "Z"}
for year in range(2014, 2027):
    yr = str(year)[-1]
    for m_code in months_map.values():
        secid = f"Si{m_code}{yr}"
        df = fetch_moex_iss(secid, engine="futures", market="forts", board="RFUD",
                            start=f"{year-1}-06-01")
        if len(df) > 0 and "TRADEDATE" in df.columns and "CLOSE" in df.columns:
            df["date"] = pd.to_datetime(df["TRADEDATE"])
            df = df[["date", "CLOSE", "VOLUME", "OPENPOSITION"]].dropna(subset=["CLOSE"])
            df["contract"] = secid
            df["si_price"] = df["CLOSE"].astype(float)
            futures_frames.append(df[["date","contract","si_price","VOLUME","OPENPOSITION"]])

if futures_frames:
    fut = pd.concat(futures_frames, ignore_index=True)
    # Берём для каждого дня самый ликвидный контракт (наибольший OI)
    fut["VOLUME"] = pd.to_numeric(fut["VOLUME"], errors="coerce").fillna(0)
    fut["OPENPOSITION"] = pd.to_numeric(fut["OPENPOSITION"], errors="coerce").fillna(0)
    fut = fut.sort_values(["date", "OPENPOSITION"], ascending=[True, False])
    active = fut.drop_duplicates("date", keep="first").sort_values("date")
    # si_price даёт цену за 1000 долларов
    active["si_usdrub"] = active["si_price"] / 1000.0
    active = active[["date", "contract", "si_usdrub"]]
    active.to_csv(f"{WORKDIR}/si_futures.csv", index=False)
    print(f"Si futures: {len(active)} дней, {active['date'].min().date()} → {active['date'].max().date()}")


# ============================================================
# 4. Global USD/CNY (для кросс-курса)
# ============================================================
print("\n" + "=" * 70)
print("4. USD/CNY spot (глобальный, для кросс-курса)")
print("=" * 70)
# Берём через ЦБ (у ЦБ есть CNY/RUB и USD/RUB — можем восстановить USD/CNY = USDRUB/CNYRUB)
# Но CNY/RUB официальный ЦБ выходит из тех же торгов. Лучше пойти через открытый источник — YFinance USDCNY=X
try:
    import yfinance as yf
    ycn = yf.download("USDCNY=X", start="2014-01-01", end="2026-08-11",
                       progress=False, auto_adjust=False)
    if not ycn.empty:
        ycn = ycn.reset_index()
        ycn.columns = [c[0] if isinstance(c, tuple) else c for c in ycn.columns]
        ycn = ycn[["Date", "Close"]].rename(columns={"Date":"date","Close":"usdcny"})
        ycn["date"] = pd.to_datetime(ycn["date"]).dt.tz_localize(None).dt.normalize()
        ycn.to_csv(f"{WORKDIR}/usdcny.csv", index=False)
        print(f"USD/CNY: {len(ycn)} дней, {ycn['date'].min().date()} → {ycn['date'].max().date()}")
except Exception as e:
    print(f"Ошибка YFinance: {e}")


# ============================================================
# 5. Золото на MOEX в рублях (GLDRUB_TOM)
# ============================================================
print("\n" + "=" * 70)
print("5. Золото в рублях на MOEX (GLDRUB_TOM)")
print("=" * 70)
gld = fetch_moex_iss("GLDRUB_TOM", start="2014-01-01")
if len(gld) > 0:
    gld["date"] = pd.to_datetime(gld["TRADEDATE"])
    keep = [c for c in ["date","CLOSE","NUMTRADES","WAPRICE"] if c in gld.columns]
    gld = gld[keep].rename(columns={"CLOSE":"gldrub","NUMTRADES":"gld_numtrades","WAPRICE":"gld_wap"})
    gld = gld.sort_values("date").drop_duplicates("date")
    gld.to_csv(f"{WORKDIR}/gldrub_moex.csv", index=False)
    print(f"GLDRUB на MOEX: {len(gld)} дней, {gld['date'].min().date()} → {gld['date'].max().date()}")
else:
    print("GLDRUB не удалось получить")

print("\nВсе источники собраны")
