        print(f"🏆 Kirim Script of the Day {prev_label} ({len(daily_rs) + len(daily_sb)} kandidat)")
        if send_script_of_the_day(daily_rs, daily_sb, prev_label):
            daily_rs.clear()
            daily_sb.clear()
            state["daily_date"] = today_str
            save_state(state)
        else:
            print("[Error] SOTD gagal terkirim, dicoba lagi di run berikutnya")
            sys.exit(1)

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
