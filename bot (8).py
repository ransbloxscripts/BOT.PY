import requests
import time
from datetime import datetime, timezone, timedelta

# ── CONFIG ────────────────────────────────────────────────────────────────────
BOT_TOKEN = "8627053450:AAFykZGpMgtphcyiTU4hI9nz4XiDlbJ2wOI"
CHANNEL_ID = "-1003767281176"
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
FETCH_INTERVAL = 60
DIGEST_INTERVAL = 2 * 3600

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
