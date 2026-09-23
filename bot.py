import requests
import time
import json
import os
import re
from datetime import datetime, timezone, timedelta

# ── CONFIG ────────────────────────────────────────────────────────────────────
BOT_TOKEN = "8627053450:AAFykZGpMgtphcyiTU4hI9nz4XiDlbJ2wOI"
CHANNEL_ID = "-1003767281176"
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
FETCH_INTERVAL = 60
DIGEST_INTERVAL = 2 * 3600
INSTANT_MODE = False  # True = kirim langsung tiap ada script baru kedetect (buat testing). False = balik ke digest per 2 jam.

# ── PLAYER MONITOR CONFIG ───────────────────────────────────────────────────
# Watchlist sekarang OTOMATIS — tiap ada script baru kedetect, nama game-nya
# langsung ditambahin ke daftar pantauan (dicari universeId-nya sendiri).
# Gak perlu isi manual lagi.
DYNAMIC_WATCHLIST_FILE = ".dynamic_watchlist.json"
MONITOR_INTERVAL = 5 * 60           # ngitung di background tiap 5 menit (biar cepet nangkep spike, gak nunggu lama)
HISTORY_FILE = ".player_history.json"
HISTORY_WINDOW_HOURS = 24           # baseline = rata-rata 24 jam terakhir
SPIKE_THRESHOLD = 0.15              # +15% dari baseline = RAME
DROP_THRESHOLD = -0.10              # -10% dari baseline = TURUN
MIN_ALERT_GAP = 3 * 3600            # jarak minimal antar alert status sama
MIN_DATA_POINTS = 3                 # minimal 3 titik data (≈15 menit history) sebelum berani nge-alert, biar gak kena noise/fluktuasi kecil
MAX_TRACKED_GAMES = 40              # batas jumlah game yang dipantau bareng (jaga API rate)

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
    dt_wib = dt.astimezone(WIB)
    today_wib = datetime.now(WIB).strftime("%Y-%m-%d")
    return dt_wib.strftime("%Y-%m-%d") == today_wib

# ── FETCH ─────────────────────────────────────────────────────────────────────
def fetch_rscripts(page=1):
    try:
        res = requests.get(
            f"https://rscripts.net/api/v2/scripts?page={page}&orderBy=date&sort=desc",
            timeout=10
        )
        return res.json().get("scripts", [])
    except Exception as e:
        print(f"[RScripts Error] {e}")
        return []

def fetch_scriptblox(page=1):
    try:
        res = requests.get(
            f"https://scriptblox.com/api/script/fetch?page={page}&max=20&mode=free",
            timeout=10
        )
        return res.json().get("result", {}).get("scripts", [])
    except Exception as e:
        print(f"[ScriptBlox Error] {e}")
        return []

def fetch_raw_loadstring(raw_url):
    if not raw_url:
        return None
    try:
        res = requests.get(raw_url, timeout=5)
        content = res.text.strip()
        if content.startswith("loadstring"):
            return content
        return f'loadstring(game:HttpGet("{raw_url}"))()' 
    except:
        return f'loadstring(game:HttpGet("{raw_url}"))()' 

# ── TELEGRAM ──────────────────────────────────────────────────────────────────
def send_message(text):
    try:
        requests.post(f"{TELEGRAM_URL}/sendMessage", json={
            "chat_id": CHANNEL_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }, timeout=10)
    except Exception as e:
        print(f"[Telegram Error] {e}")

def build_chunks(lines, header_next, max_len=4000):
    chunks = []
    current = ""
    for line in lines:
        addition = ("\n" if current else "") + line
        if len(current) + len(addition) > max_len:
            chunks.append(current)
            current = header_next + "\n" + line
        else:
            current += addition
    if current:
        chunks.append(current)
    return chunks

def send_source_digest(items, source_label, date_str, hour_start, hour_end, is_rs=True):
    if not items:
        return

    # Urutkan dari likes terbanyak (RScripts) atau views terbanyak (ScriptBlox)
    if is_rs:
        items = sorted(items, key=lambda x: x["script"].get("likes", 0), reverse=True)
    else:
        items = sorted(items, key=lambda x: x["script"].get("views", 0), reverse=True)

    header_icon = "🔴" if is_rs else "🔵"
    source_name = "RSCRIPTS" if is_rs else "SCRIPTBLOX"
    lines = []
    lines.append(f"🎮 <b>REKOMENDASI SCRIPT SHOWCASE HARI INI</b>")
    lines.append(f"📅 {date_str} | {hour_start} – {hour_end} WIB")
    lines.append(f"{header_icon} <b>{source_name}</b> — {len(items)} script evergreen")
    lines.append(f"━━━━━━━━━━━━━━━━━━")

    header_next = f"{header_icon} <b>{source_name} (lanjutan)</b>\n━━━━━━━━━━━━━━━━━━"

    for num, item in enumerate(items, 1):
        s = item["script"]
        loadstr = item.get("loadstring", "") or ""
        players = item.get("players", -1)
        player_str = f" | 🟢 {players:,} main" if players > 0 else ""

        if is_rs:
            game = s.get("game", {})
            game_name = game.get("title", game.get("name", "?")) if isinstance(game, dict) else str(game)
            title = s.get("title", "No Title")
            keyless = "✅ Keyless" if not s.get("keySystem") else "🔑 Key"
            likes = s.get("likes", 0)
            dislikes = s.get("dislikes", 0)
            views = s.get("views", 0)
            link = f"https://rscripts.net/script/{s.get('slug', '')}"
            uploaded = time_ago(s.get("createdAt", ""))
            lines.append(f"\n<b>{num}. {game_name}</b>{player_str}")
            lines.append(f"   📜 {title}")
            lines.append(f"   {keyless} | ❤️ {likes} 👎 {dislikes} | 👁 {views} | ⏱ {uploaded}")
            lines.append(f"   🔗 <a href='{link}'>View Script</a>")
        else:
            game_raw = s.get("game", "?")
            game_name = game_raw.get("name", "?") if isinstance(game_raw, dict) else str(game_raw)
            title = s.get("title", "No Title")
            keyless = "✅ Keyless" if not s.get("key") else "🔑 Key"
            views = s.get("views", 0)
            verified = " ☑️" if s.get("verified") else ""
            link = f"https://scriptblox.com/script/{s.get('slug', '')}"
            uploaded = time_ago(s.get("createdAt", ""))
            bumped = time_ago(s.get("lastBump", ""))
            lines.append(f"\n<b>{num}. {game_name}</b>{verified}{player_str}")
            lines.append(f"   📜 {title}")
            lines.append(f"   {keyless} | 👁 {views} | ⏱ {uploaded} | bump: {bumped}")
            lines.append(f"   🔗 <a href='{link}'>View Script</a>")

        if loadstr:
            lines.append(f"   <code>{loadstr[:300]}</code>")

    chunks = build_chunks(lines, header_next)
    for i, chunk in enumerate(chunks):
        if i > 0:
            time.sleep(0.5)
        send_message(chunk)

def score_item(item, is_rs):
    s = item["script"]
    if is_rs:
        likes = s.get("likes", 0)
        views = s.get("views", 0)
        return likes * 5 + views
    else:
        views = s.get("views", 0)
        verified_bonus = 500 if s.get("verified") else 0
        return views + verified_bonus

def send_script_of_the_day(daily_rs, daily_sb):
    date_str = datetime.now(WIB).strftime("%d %b %Y")
    all_candidates = []
    for item in daily_rs:
        all_candidates.append({"item": item, "is_rs": True, "score": score_item(item, True)})
    for item in daily_sb:
        all_candidates.append({"item": item, "is_rs": False, "score": score_item(item, False)})

    if not all_candidates:
        send_message(
            f"🏆 <b>SCRIPT OF THE DAY</b>\n"
            f"📅 {date_str}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"😴 Tidak ada script evergreen hari ini."
        )
        return

    best = max(all_candidates, key=lambda x: x["score"])
    item = best["item"]
    is_rs = best["is_rs"]
    s = item["script"]
    loadstr = item.get("loadstring", "") or ""
    players = item.get("players", -1)
    player_str = f"\n🟢 <b>{players:,} active players</b>" if players > 0 else ""

    if is_rs:
        game = s.get("game", {})
        game_name = game.get("title", game.get("name", "?")) if isinstance(game, dict) else str(game)
        title = s.get("title", "No Title")
        keyless = "✅ Keyless" if not s.get("keySystem") else "🔑 Key"
        likes = s.get("likes", 0)
        dislikes = s.get("dislikes", 0)
        views = s.get("views", 0)
        link = f"https://rscripts.net/script/{s.get('slug', '')}"
        source = "🔴 RScripts"
        stats = f"❤️ {likes} 👎 {dislikes} | 👁 {views} views"
    else:
        game_raw = s.get("game", "?")
        game_name = game_raw.get("name", "?") if isinstance(game_raw, dict) else str(game_raw)
        title = s.get("title", "No Title")
        keyless = "✅ Keyless" if not s.get("key") else "🔑 Key"
        views = s.get("views", 0)
        verified = " ☑️ Verified" if s.get("verified") else ""
        link = f"https://scriptblox.com/script/{s.get('slug', '')}"
        source = f"🔵 ScriptBlox{verified}"
        stats = f"👁 {views} views"

    msg = (
        f"🏆 <b>SCRIPT OF THE DAY</b>\n"
        f"📅 {date_str}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎮 <b>{game_name}</b>{player_str}\n"
        f"📜 {title}\n"
        f"{keyless} | {stats}\n"
        f"📦 {source}\n"
        f"🔗 <a href='{link}'>View Script</a>"
    )
    if loadstr:
        msg += f"\n\n<code>{loadstr[:400]}</code>"

    send_message(msg)
    print(f"🏆 Script of the Day: {game_name} (skor: {best['score']})")

def send_digest(rs_list, sb_list, hour_start, hour_end):
    date_str = datetime.now(WIB).strftime("%d %b %Y")
    total = len(rs_list) + len(sb_list)

    if total == 0:
        send_message(
            f"🎮 <b>REKOMENDASI SCRIPT SHOWCASE HARI INI</b>\n"
            f"📅 {date_str} | {hour_start} – {hour_end} WIB\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"😴 Tidak ada script evergreen baru dalam 6 jam ini."
        )
        return

    # Kirim ScriptBlox dulu, lalu RScripts
    send_source_digest(sb_list, "ScriptBlox", date_str, hour_start, hour_end, is_rs=False)
    time.sleep(1)
    send_source_digest(rs_list, "RScripts", date_str, hour_start, hour_end, is_rs=True)

# ── PLAYER MONITOR: RESOLVE GAME NAME → UNIVERSE ID ──────────────────────────
def _find_universe_id_anywhere(obj):
    """Nyisir seluruh struktur JSON (dict/list bersarang berapa pun dalamnya)
    buat nemuin field universeId/universeIds, gak peduli di path mana dia nyempil.
    Ini lebih tahan banting daripada nebak struktur response persis."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_lower = k.lower()
            if key_lower == "universeid" and isinstance(v, (int, str)):
                try:
                    return int(v)
                except (ValueError, TypeError):
                    pass
            if key_lower == "universeids" and isinstance(v, list) and v:
                try:
                    return int(v[0])
                except (ValueError, TypeError):
                    pass
            found = _find_universe_id_anywhere(v)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_universe_id_anywhere(item)
            if found:
                return found
    return None

def search_universe_id_by_name(game_name):
    """Cari universeId Roblox berdasarkan nama game (buat game yang baru kedetect
    dari script, otomatis, tanpa perlu input manual place_id)."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    attempts = [
        {"searchQuery": game_name, "verticalType": "game"},
        {"searchQuery": game_name},
    ]
    for params in attempts:
        try:
            res = requests.get(
                "https://apis.roblox.com/search-api/omni-search",
                params=params,
                headers=headers,
                timeout=10
            )
            if res.status_code != 200:
                print(f"[SearchUniverse] '{game_name}' -> HTTP {res.status_code}: {res.text[:200]}")
                continue
            data = res.json()
            uid = _find_universe_id_anywhere(data)
            if uid:
                return uid
            else:
                print(f"[SearchUniverse] '{game_name}' -> HTTP 200 tapi universeId gak ketemu di response: {str(data)[:200]}")
        except Exception as e:
            print(f"[SearchUniverse Error] '{game_name}': {e}")
    return None

ROBLOX_GAME_URL_RE = re.compile(r"roblox\.com/games/(\d+)", re.IGNORECASE)
ROBLOX_PLACEID_QS_RE = re.compile(r"[?&]placeId=(\d+)", re.IGNORECASE)

def _find_place_or_universe_id_anywhere(obj):
    """PRIORITAS UTAMA buat resolve ID game: nyisir data script MENTAH (dict/list/
    string, berapa pun dalamnya) buat nemuin ID ASLI dari game-nya — universeId,
    placeId/gameId, atau link roblox.com/games/<id> yang nyempil di field manapun
    (misal link donasi, deskripsi, dsb). Ini jauh lebih akurat daripada nebak
    universeId dari NAMA game doang, karena ID ini emang punya si game aslinya.
    Return (kind, id) dengan kind "universe" atau "place", biar caller tau perlu
    convert place->universe dulu atau enggak."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_lower = k.lower()
            if key_lower == "universeid" and isinstance(v, (int, str)):
                try:
                    return ("universe", int(v))
                except (ValueError, TypeError):
                    pass
            if key_lower == "universeids" and isinstance(v, list) and v:
                try:
                    return ("universe", int(v[0]))
                except (ValueError, TypeError):
                    pass
            if key_lower in ("placeid", "place_id", "gameid", "game_id") and isinstance(v, (int, str)):
                try:
                    return ("place", int(v))
                except (ValueError, TypeError):
                    pass
            found = _find_place_or_universe_id_anywhere(v)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_place_or_universe_id_anywhere(item)
            if found:
                return found
    elif isinstance(obj, str):
        m = ROBLOX_GAME_URL_RE.search(obj)
        if m:
            return ("place", int(m.group(1)))
        m = ROBLOX_PLACEID_QS_RE.search(obj)
        if m:
            return ("place", int(m.group(1)))
    return None

def place_id_to_universe_id(place_id):
    """PlaceId beda sama UniverseId — semua endpoint player count kita butuh
    universeId, jadi kalau yang ketemu di data script itu placeId, convert dulu."""
    try:
        res = requests.get(
            f"https://apis.roblox.com/universes/v1/places/{place_id}/universe",
            timeout=10
        )
        if res.status_code != 200:
            print(f"[PlaceToUniverse] place_id={place_id} -> HTTP {res.status_code}")
            return None
        data = res.json()
        uid = data.get("universeId")
        return int(uid) if uid else None
    except Exception as e:
        print(f"[PlaceToUniverse Error] place_id={place_id}: {e}")
        return None

def extract_universe_id_from_script(script_data):
    """Coba resolve universeId LANGSUNG dari data mentah script (kalau ada ID/link
    ke game aslinya nyempil di dalamnya). Dipanggil SEBELUM fallback search-by-name."""
    if not script_data:
        return None
    found = _find_place_or_universe_id_anywhere(script_data)
    if not found:
        return None
    kind, id_val = found
    if kind == "universe":
        return id_val
    return place_id_to_universe_id(id_val)

def fetch_player_count(universe_id):
    try:
        res = requests.get(
            f"https://games.roblox.com/v1/games?universeIds={universe_id}",
            timeout=10
        )
        data = res.json().get("data", [])
        return data[0].get("playing", None) if data else None
    except Exception as e:
        print(f"[PlayerCount Error] universe_id={universe_id}: {e}")
        return None

# ── PLAYER MONITOR: DYNAMIC WATCHLIST ────────────────────────────────────────
def load_dynamic_watchlist():
    if not os.path.exists(DYNAMIC_WATCHLIST_FILE):
        return {}
    try:
        with open(DYNAMIC_WATCHLIST_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_dynamic_watchlist(wl):
    try:
        with open(DYNAMIC_WATCHLIST_FILE, "w") as f:
            json.dump(wl, f)
    except Exception as e:
        print(f"[Watchlist Save Error] {e}")

def track_game(game_name, script_data=None):
    """Dipanggil tiap ada script baru kedetect. Nambahin game ke watchlist
    dinamis kalau belum ada, dan coba resolve universeId-nya.
    Prioritas resolve: (1) ekstrak ID langsung dari data mentah script (paling
    akurat, itu ID punya game aslinya), (2) fallback ke search by name kalau
    gak ketemu ID di data script-nya."""
    if not game_name or game_name == "?":
        return
    wl = load_dynamic_watchlist()
    if game_name in wl:
        wl[game_name]["last_seen"] = time.time()
        # kalau sebelumnya gagal resolve, coba lagi lewat data script kalau ada
        if not wl[game_name].get("universe_id") and script_data:
            uid = extract_universe_id_from_script(script_data)
            if uid:
                wl[game_name]["universe_id"] = uid
                print(f"[Watchlist] ~ {game_name} akhirnya resolve dari data script (universeId {uid})")
        save_dynamic_watchlist(wl)
        return

    if len(wl) >= MAX_TRACKED_GAMES:
        # buang entry yang paling lama gak muncul lagi
        oldest_key = min(wl, key=lambda k: wl[k].get("last_seen", 0))
        wl.pop(oldest_key, None)

    universe_id = extract_universe_id_from_script(script_data) if script_data else None
    source = "data script"
    if not universe_id:
        universe_id = search_universe_id_by_name(game_name)
        source = "search nama"

    wl[game_name] = {
        "universe_id": universe_id,
        "last_seen": time.time(),
        "added_at": time.time(),
    }
    save_dynamic_watchlist(wl)
    if universe_id:
        print(f"[Watchlist] + {game_name} (universeId {universe_id}, dari {source})")
    else:
        print(f"[Watchlist] + {game_name} (gagal resolve universeId, dilewati saat monitor)")

# ── PLAYER MONITOR: HISTORY ───────────────────────────────────────────────────
def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_history(history):
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f)
    except Exception as e:
        print(f"[History Save Error] {e}")

def record_point(history, key, count):
    now_ts = time.time()
    points = history.get(key, {"points": [], "last_status": None, "last_alert_ts": 0})
    points["points"].append([now_ts, count])
    cutoff = now_ts - (HISTORY_WINDOW_HOURS * 3600)
    points["points"] = [p for p in points["points"] if p[0] >= cutoff]
    history[key] = points
    return points

# ── PLAYER MONITOR: CLASSIFY & ALERT ─────────────────────────────────────────
def classify(current, baseline):
    if baseline <= 0:
        return "STABIL"
    change = (current - baseline) / baseline
    if change >= SPIKE_THRESHOLD:
        return "RAME"
    elif change <= DROP_THRESHOLD:
        return "TURUN"
    return "STABIL"

STATUS_META = {
    "RAME":   {"emoji": "🟢", "label": "RAME (SPIKE)", "tip": "Momen bagus buat upload showcase sekarang, traffic lagi tinggi."},
    "STABIL": {"emoji": "🟡", "label": "STABIL",        "tip": "Aman upload, tapi bukan waktu paling optimal."},
    "TURUN":  {"emoji": "🔴", "label": "TURUN",         "tip": "Tahan dulu uploadnya, tunggu player rebound biar exposure maksimal."},
}

def format_alert(name, status, current, baseline, change_pct):
    meta = STATUS_META[status]
    now_str = datetime.now(WIB).strftime("%d %b %Y, %H:%M WIB")
    return (
        f"{meta['emoji']} <b>{meta['label']} — {name}</b>\n"
        f"🕒 {now_str}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👥 Player sekarang: <b>{current:,}</b>\n"
        f"📊 Baseline 24 jam: {baseline:,.0f}\n"
        f"📈 Perubahan: {change_pct:+.1f}%\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💡 {meta['tip']}"
    )

def check_watchlist():
    history = load_history()
    wl = load_dynamic_watchlist()

    for game_name, info in list(wl.items()):
        universe_id = info.get("universe_id")

        # kalau belum kebresolve dulu (misal search sempat gagal), coba lagi
        if not universe_id:
            universe_id = search_universe_id_by_name(game_name)
            if universe_id:
                wl[game_name]["universe_id"] = universe_id
            else:
                print(f"[Skip] {game_name}: universeId belum ketemu")
                continue

        current = fetch_player_count(universe_id)
        if current is None:
            print(f"[Skip] {game_name}: gagal ambil player count")
            continue

        key = str(universe_id)
        record = history.get(key, {"points": [], "last_status": None, "last_alert_ts": 0})

        # baseline dihitung dari data LAMA (sebelum titik sekarang ditambahin),
        # biar perbandingannya jujur — bukan ke-average sama dirinya sendiri
        prev_counts = [p[1] for p in record["points"]]
        baseline = sum(prev_counts) / len(prev_counts) if prev_counts else current
        change_pct = ((current - baseline) / baseline * 100) if baseline > 0 else 0
        status = classify(current, baseline)

        # baru sekarang titik ini dicatet buat baseline berikutnya
        now_ts = time.time()
        record["points"].append([now_ts, current])
        cutoff = now_ts - (HISTORY_WINDOW_HOURS * 3600)
        record["points"] = [p for p in record["points"] if p[0] >= cutoff]

        prev_status = record.get("last_status")
        elapsed_since_alert = time.time() - record.get("last_alert_ts", 0)

        # skip alert kalau data historisnya masih terlalu sedikit (rawan noise)
        # sekarang kirim semua status (RAME/STABIL/TURUN) biar lu punya gambaran lengkap
        has_baseline = len(prev_counts) >= MIN_DATA_POINTS
        should_alert = (
            has_baseline and
            (status != prev_status or elapsed_since_alert >= MIN_ALERT_GAP)
        )

        print(f"[Monitor] {game_name}: {current:,} players | baseline {baseline:,.0f} | {change_pct:+.1f}% | {status}")

        if should_alert:
            send_message(format_alert(game_name, status, current, baseline, change_pct))
            record["last_alert_ts"] = time.time()

        record["last_status"] = status
        history[key] = record

    save_history(history)
    save_dynamic_watchlist(wl)

# ── INSTANT SEND (testing mode) ──────────────────────────────────────────────
def send_instant_item(item, is_rs):
    s = item["script"]
    loadstr = item.get("loadstring", "") or ""

    if is_rs:
        game = s.get("game", {})
        game_name = game.get("title", game.get("name", "?")) if isinstance(game, dict) else str(game)
        title = s.get("title", "No Title")
        keyless = "✅ Keyless" if not s.get("keySystem") else "🔑 Key"
        likes = s.get("likes", 0)
        dislikes = s.get("dislikes", 0)
        views = s.get("views", 0)
        link = f"https://rscripts.net/script/{s.get('slug', '')}"
        source = "🔴 RScripts"
        stats = f"❤️ {likes} 👎 {dislikes} | 👁 {views}"
    else:
        game_raw = s.get("game", "?")
        game_name = game_raw.get("name", "?") if isinstance(game_raw, dict) else str(game_raw)
        title = s.get("title", "No Title")
        keyless = "✅ Keyless" if not s.get("key") else "🔑 Key"
        views = s.get("views", 0)
        verified = " ☑️" if s.get("verified") else ""
        link = f"https://scriptblox.com/script/{s.get('slug', '')}"
        source = f"🔵 ScriptBlox{verified}"
        stats = f"👁 {views}"

    msg = (
        f"🆕 <b>SCRIPT BARU KEDETECT</b>\n"
        f"🎮 <b>{game_name}</b>\n"
        f"📜 {title}\n"
        f"{keyless} | {stats}\n"
        f"📦 {source}\n"
        f"🔗 <a href='{link}'>View Script</a>"
    )
    if loadstr:
        msg += f"\n\n<code>{loadstr[:300]}</code>"

    send_message(msg)

# ── PROCESS ───────────────────────────────────────────────────────────────────
def process_rscripts(scripts, sent_map, pending, daily):
    for script in scripts:
        slug = script.get("slug", "")
        if not slug:
            continue
        created_at = script.get("createdAt", "")
        last_updated = script.get("lastUpdated", "") or created_at
        if not is_today(created_at) and not is_today(last_updated):
            continue
        prev = sent_map.get(f"rs_{slug}")
        if prev == last_updated:
            continue
        game = script.get("game", {})
        game_name = game.get("title", game.get("name", "?")) if isinstance(game, dict) else str(game)
        if not game_name:
            continue
        raw_url = script.get("rawScript", "")
        loadstring = fetch_raw_loadstring(raw_url)
        entry = {"script": script, "loadstring": loadstring, "players": -1}
        track_game(game_name, script)
        if INSTANT_MODE:
            send_instant_item(entry, is_rs=True)
            time.sleep(0.5)
        else:
            pending.append(entry)
        daily.append(entry)
        sent_map[f"rs_{slug}"] = last_updated
        label = "🔄" if prev else "✅"
        print(f"{label} [RScripts] {game_name}")

def process_scriptblox(scripts, sent_map, pending, daily):
    for script in scripts:
        slug = script.get("slug", "")
        if not slug:
            continue
        created_at = script.get("createdAt", "")
        last_bump = script.get("lastBump", "") or created_at
        if not is_today(created_at) and not is_today(last_bump):
            continue
        prev = sent_map.get(f"sb_{slug}")
        if prev == last_bump:
            continue
        game_raw = script.get("game", "")
        game_name = game_raw.get("name", "") if isinstance(game_raw, dict) else str(game_raw)
        if not game_name:
            continue
        loadstring = script.get("script", None)
        entry = {"script": script, "loadstring": loadstring, "players": -1}
        track_game(game_name, script)
        if INSTANT_MODE:
            send_instant_item(entry, is_rs=False)
            time.sleep(0.5)
        else:
            pending.append(entry)
        daily.append(entry)
        sent_map[f"sb_{slug}"] = last_bump
        label = "🔄" if prev else "✅"
        verified = "☑️" if script.get("verified") else ""
        print(f"{label} [ScriptBlox] {game_name} {verified}")

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    today = datetime.now(WIB).strftime("%d %b %Y")
    print(f"🤖 RANSBLOX Bot starting... ({today} WIB)")
    print(f"🔍 No filter | digest tiap 2 jam\n")

    sent_map = {}
    pending_rs = []
    pending_sb = []
    daily_rs = []
    daily_sb = []
    last_sotd_date = ""
    last_monitor_check = 0

    # Load last_digest dari file supaya persist kalau restart
    DIGEST_STATE_FILE = ".last_digest"
    try:
        with open(DIGEST_STATE_FILE, "r") as f:
            last_digest = float(f.read().strip())
        print(f"⏱️  Loaded last_digest: {datetime.fromtimestamp(last_digest, WIB).strftime('%H:%M:%S WIB')}")
    except Exception:
        last_digest = time.time()
        print("⏱️  last_digest baru (restart pertama)")

    while True:
        try:
            # Fetch RScripts (sampai 5 halaman atau hingga tidak ada hari ini)
            for page in range(1, 6):
                scripts = fetch_rscripts(page)
                if not scripts:
                    break
                has_today = any(
                    is_today(s.get("createdAt", "")) or is_today(s.get("lastUpdated", ""))
                    for s in scripts
                )
                process_rscripts(scripts, sent_map, pending_rs, daily_rs)
                if not has_today:
                    break

            # Fetch ScriptBlox (sampai 3 halaman)
            for page in range(1, 4):
                scripts = fetch_scriptblox(page)
                if not scripts:
                    break
                has_today = any(
                    is_today(s.get("createdAt", "")) or is_today(s.get("lastBump", ""))
                    for s in scripts
                )
                process_scriptblox(scripts, sent_map, pending_sb, daily_sb)
                if not has_today:
                    break

            now_wib = datetime.now(WIB)
            now_str = now_wib.strftime("%H:%M:%S")
            today_str = now_wib.strftime("%Y-%m-%d")
            elapsed = time.time() - last_digest

            # Cek player watchlist (rame/turun)
            if time.time() - last_monitor_check >= MONITOR_INTERVAL:
                print("🔎 Cek player watchlist...")
                check_watchlist()
                last_monitor_check = time.time()

            # Cek Script of the Day jam 00:00 WIB
            if now_wib.hour == 0 and now_wib.minute == 0 and last_sotd_date != today_str:
                total_daily = len(daily_rs) + len(daily_sb)
                print(f"\n🏆 Kirim Script of the Day ({total_daily} kandidat)")
                send_script_of_the_day(daily_rs, daily_sb)
                daily_rs.clear()
                daily_sb.clear()
                last_sotd_date = today_str

            # Digest tiap 2 jam
            if elapsed >= DIGEST_INTERVAL:
                hour_end = now_wib.strftime("%H:%M")
                hour_start_dt = now_wib - timedelta(seconds=elapsed)
                hour_start = hour_start_dt.strftime("%H:%M")
                total = len(pending_rs) + len(pending_sb)
                print(f"\n📤 Kirim digest: {total} script ({hour_start}–{hour_end} WIB)")
                send_digest(pending_rs, pending_sb, hour_start, hour_end)
                pending_rs.clear()
                pending_sb.clear()
                last_digest = time.time()
                try:
                    with open(DIGEST_STATE_FILE, "w") as f:
                        f.write(str(last_digest))
                except Exception as e:
                    print(f"[Warn] Gagal simpan last_digest: {e}")
            else:
                sisa = int(DIGEST_INTERVAL - elapsed)
                total_pending = len(pending_rs) + len(pending_sb)
                total_daily = len(daily_rs) + len(daily_sb)
                print(f"⏳ [{now_str}] Pending: {total_pending} | Harian: {total_daily} | digest dalam {sisa//60}m {sisa%60}s")

        except Exception as e:
            print(f"[Loop Error] {e}")

        time.sleep(FETCH_INTERVAL)

if __name__ == "__main__":
    main()
