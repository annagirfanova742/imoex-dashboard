"""
Собирает историю цен рынков Polymarket ceasefire через prices-history,
разбивая период на окна по 30 дней и склеивая.
"""
import requests
import pandas as pd
import time
import json
from datetime import datetime, timedelta

import os as _os
WORKDIR = _os.environ.get("WORKDIR", "/home/user/workspace")

SLUGS = [
    "will-russia-ukraine-declare-a-ceasefire-by-eoy",
    "ceasefire-between-russia-and-ukraine-by-june",
    "ceasefire-between-russia-and-ukraine-before-october",
    "russia-x-ukraine-ceasefire-in-2024",
    "russia-x-ukraine-ceasefire-in-2025",
    "russia-x-ukraine-ceasefire-before-2027",
]

def get_meta(slug):
    r = requests.get(f"https://gamma-api.polymarket.com/events?slug={slug}", timeout=15).json()
    if not r: return None
    m = r[0]["markets"][0]
    tokens = json.loads(m["clobTokenIds"])
    return {
        "slug": slug,
        "token_yes": tokens[0],
        "start": r[0]["startDate"][:10],
        "end": r[0]["endDate"][:10],
        "closed": r[0].get("closed", False),
    }

def fetch_window(token, start_ts, end_ts, fidelity=1440):
    """Одна window запрос — fidelity в минутах (1440 = дневная)."""
    url = f"https://clob.polymarket.com/prices-history?market={token}&startTs={start_ts}&endTs={end_ts}&fidelity={fidelity}"
    r = requests.get(url, timeout=30)
    if r.status_code == 200:
        return r.json().get("history", [])
    else:
        # Уменьшаем окно
        return None

def fetch_all_history(token, start_date, end_date):
    """Разбиваем на окна по 25 дней."""
    all_pts = []
    cur = pd.Timestamp(start_date).timestamp()
    end_ts = pd.Timestamp(end_date).timestamp() + 86400
    now_ts = time.time()
    end_ts = min(end_ts, now_ts)

    while cur < end_ts:
        window_end = min(cur + 25 * 86400, end_ts)
        pts = fetch_window(token, int(cur), int(window_end), fidelity=1440)
        if pts is None:
            # Пробуем половину
            window_end = cur + 12 * 86400
            pts = fetch_window(token, int(cur), int(window_end), fidelity=1440)
        if pts:
            all_pts.extend(pts)
        cur = window_end
        time.sleep(0.15)

    if not all_pts:
        return None
    df = pd.DataFrame(all_pts)
    df["date"] = pd.to_datetime(df["t"], unit="s").dt.tz_localize(None).dt.normalize()
    df["price"] = df["p"]
    # По дню — последняя точка
    daily = df.groupby("date").agg(price=("price", "last")).reset_index()
    return daily

all_data = []
for slug in SLUGS:
    meta = get_meta(slug)
    if not meta:
        print(f"{slug}: нет meta")
        continue
    print(f"\n=== {slug} ({meta['start']} → {meta['end']}) ===")
    df = fetch_all_history(meta["token_yes"], meta["start"], meta["end"])
    if df is None or len(df) == 0:
        print("  нет истории")
        continue
    df["slug"] = slug
    df["market_end"] = meta["end"]
    df["market_start"] = meta["start"]
    all_data.append(df)
    print(f"  собрано: {len(df)} дней, {df['date'].min().date()} → {df['date'].max().date()}, price {df['price'].min():.3f}..{df['price'].max():.3f}")

if all_data:
    combined = pd.concat(all_data, ignore_index=True)
    combined.to_csv(f"{WORKDIR}/polymarket_ceasefire_raw.csv", index=False)
    print(f"\nВсего строк: {len(combined)}, уник. дат: {combined['date'].nunique()}")
    print(f"Диапазон: {combined['date'].min().date()} → {combined['date'].max().date()}")
