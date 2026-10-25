import os
import sys
import json
import requests
import time
from datetime import datetime, timezone, timedelta

# ── CONFIG ────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN") or "8627053450:AAFykZGpMgtphcyiTU4hI9nz4XiDlbJ2wOI"
CHANNEL_ID = os.environ.get("CHANNEL_ID") or "-1003767281176"
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
    dt_wib = dt.astimezone(WIB)
    today_wib = datetime.now(WIB).strftime("%Y-%m-%d")
    return dt_wib.strftime("%Y-%m-%d") == today_wib

def is_new(iso_str, cutoff):
    dt = parse_dt(iso_str)
    return bool(dt) and dt >= cutoff

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
        res = requests.post(f"{TELEGRAM_URL}/sendMessage", json={
            "chat_id": CHANNEL_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }, timeout=10)
        if not res.ok:
            print(f"[Telegram Error] {res.status_code} {res.text[:200]}")
            return False
        return True
    except Exception as e:
        print(f"[Telegram Error] {e}")
        return False

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
        return True

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
    ok = True
    for i, chunk in enumerate(chunks):
        if i > 0:
            time.sleep(0.5)
        ok = send_message(chunk) and ok
    return ok

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

def send_script_of_the_day(daily_rs, daily_sb, date_str):
    all_candidates = []
    for item in daily_rs:
        all_candidates.append({"item": item, "is_rs": True, "score": score_item(item, True)})
    for item in daily_sb:
        all_candidates.append({"item": item, "is_rs": False, "score": score_item(item, False)})

    if not all_candidates:
        return send_message(
            f"🏆 <b>SCRIPT OF THE DAY</b>\n"
            f"📅 {date_str}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"😴 Tidak ada script evergreen hari ini."
        )

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

    ok = send_message(msg)
    print(f"🏆 Script of the Day: {game_name} (skor: {best['score']})")
    return ok

def send_digest(rs_list, sb_list, hour_start, hour_end):
    date_str = datetime.now(WIB).strftime("%d %b %Y")
    total = len(rs_list) + len(sb_list)

    if total == 0:
        return send_message(
            f"🎮 <b>REKOMENDASI SCRIPT SHOWCASE HARI INI</b>\n"
            f"📅 {date_str} | {hour_start} – {hour_end} WIB\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"😴 Tidak ada script evergreen baru dalam 2 jam ini."
        )

    # Kirim ScriptBlox dulu, lalu RScripts
    ok_sb = send_source_digest(sb_list, "ScriptBlox", date_str, hour_start, hour_end, is_rs=False)
    time.sleep(1)
    ok_rs = send_source_digest(rs_list, "RScripts", date_str, hour_start, hour_end, is_rs=True)
    return ok_sb and ok_rs

# ── STATE ─────────────────────────────────────────────────────────────────────
RS_KEYS = ["slug", "title", "game", "keySystem", "likes", "dislikes", "views", "createdAt"]
SB_KEYS = ["slug", "title", "game", "key", "views", "verified", "createdAt", "lastBump"]

def slim(script, keys):
    return {k: script.get(k) for k in keys if k in script}

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            st = json.load(f)
    except Exception:
        st = {}
    st.setdefault("sent_map", {})
    st.setdefault("daily_rs", [])
    st.setdefault("daily_sb", [])
    st.setdefault("last_digest", None)
    st.setdefault("daily_date", "")
    return st

def save_state(st):
    # buang entri sent_map yang sudah lebih dari 3 hari biar file tidak membengkak
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)
    st["sent_map"] = {
        k: v for k, v in st["sent_map"].items()
        if (parse_dt(v) is None) or parse_dt(v) >= cutoff
    }
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False)

# ── PROCESS ───────────────────────────────────────────────────────────────────
def process_rscripts(scripts, sent_map, pending, daily, cutoff):
    for script in scripts:
        slug = script.get("slug", "")
        if not slug:
            continue
        created_at = script.get("createdAt", "")
        last_updated = script.get("lastUpdated", "") or created_at
        if not is_new(created_at, cutoff) and not is_new(last_updated, cutoff):
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
        entry = {"script": slim(script, RS_KEYS), "loadstring": loadstring, "players": -1}
        pending.append(entry)
        daily.append(entry)
        sent_map[f"rs_{slug}"] = last_updated
        label = "🔄" if prev else "✅"
        print(f"{label} [RScripts] {game_name}")

def process_scriptblox(scripts, sent_map, pending, daily, cutoff):
    for script in scripts:
        slug = script.get("slug", "")
        if not slug:
            continue
        created_at = script.get("createdAt", "")
        last_bump = script.get("lastBump", "") or created_at
        if not is_new(created_at, cutoff) and not is_new(last_bump, cutoff):
            continue
        prev = sent_map.get(f"sb_{slug}")
        if prev == last_bump:
            continue
        game_raw = script.get("game", "")
        game_name = game_raw.get("name", "") if isinstance(game_raw, dict) else str(game_raw)
        if not game_name:
            continue
        loadstring = script.get("script", None)
        entry = {"script": slim(script, SB_KEYS), "loadstring": loadstring, "players": -1}
        pending.append(entry)
        daily.append(entry)
        sent_map[f"sb_{slug}"] = last_bump
        label = "🔄" if prev else "✅"
        verified = "☑️" if script.get("verified") else ""
        print(f"{label} [ScriptBlox] {game_name} {verified}")

# ── MAIN (sekali jalan, dipanggil GitHub Actions tiap 2 jam) ──────────────────
def main():
    now_wib = datetime.now(WIB)
    today_str = now_wib.strftime("%Y-%m-%d")
    print(f"🤖 RANSBLOX Bot run... ({now_wib.strftime('%d %b %Y %H:%M')} WIB)")

    state = load_state()
    sent_map = state["sent_map"]
    daily_rs = state["daily_rs"]
    daily_sb = state["daily_sb"]
    pending_rs = []
    pending_sb = []

    if not state["daily_date"]:
        state["daily_date"] = today_str

    # Ganti hari (WIB) -> kirim Script of the Day untuk hari kemarin
    if state["daily_date"] != today_str:
        prev_label = datetime.strptime(state["daily_date"], "%Y-%m-%d").strftime("%d %b %Y")
        print(f"🏆 Kirim Script of the Day {prev_label} ({len(daily_rs) + len(daily_sb)} kandidat)")
        if send_script_of_the_day(daily_rs, daily_sb, prev_label):
            daily_rs.clear()
            daily_sb.clear()
            state["daily_date"] = today_str
            save_state(state)
        else:
            print("[Error] SOTD gagal terkirim, dicoba lagi di run berikutnya")
            sys.exit(1)

    # Batas waktu: semua script sejak run sukses terakhir (dikurangi 30 menit
    # sebagai pengaman). Duplikat dicegah oleh sent_map, jadi aman.
    now_utc = datetime.now(timezone.utc)
    if state["last_digest"]:
        cutoff = datetime.fromtimestamp(state["last_digest"], timezone.utc) - timedelta(minutes=30)
        cutoff = max(cutoff, now_utc - timedelta(hours=48))
    else:
        cutoff = now_wib.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    print(f"🕒 Ambil script sejak {cutoff.astimezone(WIB).strftime('%d %b %H:%M')} WIB")

    # Fetch RScripts: terus buka halaman berikutnya selama masih ada yang baru
    for page in range(1, 31):
        scripts = fetch_rscripts(page)
        if not scripts:
            break
        has_new = any(
            is_new(s.get("createdAt", ""), cutoff) or is_new(s.get("lastUpdated", ""), cutoff)
            for s in scripts
        )
        process_rscripts(scripts, sent_map, pending_rs, daily_rs, cutoff)
        if not has_new:
            break
        time.sleep(0.3)

    # Fetch ScriptBlox: sama
    for page in range(1, 16):
        scripts = fetch_scriptblox(page)
        if not scripts:
            break
        has_new = any(
            is_new(s.get("createdAt", ""), cutoff) or is_new(s.get("lastBump", ""), cutoff)
            for s in scripts
        )
        process_scriptblox(scripts, sent_map, pending_sb, daily_sb, cutoff)
        if not has_new:
            break
        time.sleep(0.3)

    # Digest (tiap run = tiap 2 jam)
    last_digest = state["last_digest"]
    elapsed = (time.time() - last_digest) if last_digest else DIGEST_INTERVAL
    hour_end = now_wib.strftime("%H:%M")
    hour_start = (now_wib - timedelta(seconds=elapsed)).strftime("%H:%M")
    total = len(pending_rs) + len(pending_sb)
    print(f"📤 Kirim digest: {total} script ({hour_start}–{hour_end} WIB)")

    if send_digest(pending_rs, pending_sb, hour_start, hour_end):
        state["last_digest"] = time.time()
        save_state(state)
    else:
        # state TIDAK disimpan -> script yang sama dicoba lagi di run berikutnya
        print("[Error] Digest gagal terkirim, state tidak disimpan")
        sys.exit(1)

if __name__ == "__main__":
    main()
