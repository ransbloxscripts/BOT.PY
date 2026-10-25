import os
import sys
import json
import requests
import time
from datetime import datetime, timezone, timedelta

# ── CONFIG ────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8627053450:AAFykZGpMgtphcyiTU4hI9nz4XiDlbJ2wOI")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "-1003767281176")
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
DIGEST_INTERVAL = 2 * 3600
STATE_FILE = "state.json"

# ── DATE UTILS ────────────────────────────────────────────────────────────────
WIB = timezone(timedelta(hours=7))

def parse_dt(iso_str):
    if not iso_str:
        return None
    try:
        iso_str = iso_str.replace("Z", "+00:00")
        if "." in iso_str:
            iso_str = iso_str.split(".")[0] + "+00:00"
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except:
        try:
            dt = datetime.strptime(iso_str[:19], "%Y-%m-%dT%H:%M:%S")
            return dt.replace(tzinfo=timezone.utc)
        except:
            return None

def time_ago(iso_str):
    dt = parse_dt(iso_str)
    if not dt:
        return "?"
    diff = int((datetime.now(timezone.utc) - dt).total_seconds())
    if diff < 60:
        return "baru saja"
    elif diff < 3600:
        return f"{diff // 60}m lalu"
    elif diff < 86400:
        h = diff // 3600
        m = (diff % 3600) // 60
        return f"{h}j {m}m lalu" if m else f"{h}j lalu"
    else:
        return f"{diff // 86400}h lalu"

def is_today(iso_str):
    dt = parse_dt(iso_str)
    if not dt:
        return False
