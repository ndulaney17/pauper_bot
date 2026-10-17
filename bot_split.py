#!/usr/bin/env python3
"""
NRPL leaderboard watcher - split-embed version.

When standings change, posts:
  Message 1:  [What changed] [Top 12 - qualification spots]
  Message 2+: [Full standings - everyone]  (auto-split if it gets long)

Reuses scraping/diff/state code from bot.py, and the same environment
variables and flags (--once, --test). Run this OR bot.py, not both
(they share state.json).
"""
import sys
import time

import requests

import bot
from bot import (LEGEND, MAX_CHANGE_LINES, QUALIFY_CUTOFF, diff, fake_previous, fetch_leaderboard,
                 load_state, no_changes_text, row, save_state)

EMBED_DESC_LIMIT = 3900     # Discord max is 4096 per embed description
MESSAGE_CHAR_LIMIT = 5500   # Discord max is 6000 total across a message's embeds
GOLD, BLUE, GREY = 0xF1C40F, 0x5865F2, 0x95A5A6


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def send(embeds):
    payload = {"username": "NRPL Leaderboard", "embeds": embeds}
    for attempt in range(2):
        r = requests.post(bot.WEBHOOK_URL, json=payload, timeout=30)
        if r.status_code == 429 and attempt == 0:
            time.sleep(float(r.json().get("retry_after", 2)) + 0.5)
            continue
        r.raise_for_status()
        return


def embed_size(e):
    return len(e.get("title", "")) + len(e.get("description", "")) + len(e.get("footer", {}).get("text", ""))


def changes_embed(changes):
    shown = changes[:MAX_CHANGE_LINES]
    desc = "\n".join(shown) or no_changes_text()
    if len(changes) > len(shown):
        desc += f"\n…and {len(changes) - len(shown)} more"
    return {"title": "🏆 Leaderboard updated!", "url": bot.LEADERBOARD_URL,
            "description": desc[:EMBED_DESC_LIMIT], "color": BLUE, "timestamp": now_iso()}


def top_embed(players):
    return {"title": f"🥇 Top {QUALIFY_CUTOFF} - Qualification Spots",
            "description": LEGEND + "\n\n" + "\n".join(row(p) for p in players[:QUALIFY_CUTOFF]),
            "color": GOLD}


def standings_embeds(players):
    """Full standings, chunked so each embed fits Discord's description limit."""
    budget = EMBED_DESC_LIMIT - len(LEGEND) - 2
    chunks, cur, size = [], [], 0
    for p in players:
        line = row(p)
        if cur and size + len(line) + 1 > budget:
            chunks.append(cur)
            cur, size = [], 0
        cur.append(line)
        size += len(line) + 1
    if cur:
        chunks.append(cur)
    embeds = []
    for i, lines in enumerate(chunks, 1):
        title = f"📋 Full Standings ({len(players)} players)"
        if len(chunks) > 1:
            title += f" - part {i}/{len(chunks)}"
        e = {"title": title, "description": LEGEND + "\n\n" + "\n".join(lines), "color": GREY}
        if i == len(chunks):
            e["footer"] = {"text": "pauperleague.com"}
            e["timestamp"] = now_iso()
        embeds.append(e)
    return embeds


def announce(changes, players):
    # Message 1: what changed + top 12
    send([changes_embed(changes), top_embed(players)])
    # Message 2+: everyone, grouped so each message stays under Discord's total limit
    batch, size = [], 0
    for e in standings_embeds(players):
        s = embed_size(e)
        if batch and size + s > MESSAGE_CHAR_LIMIT:
            time.sleep(1)
            send(batch)
            batch, size = [], 0
        batch.append(e)
        size += s
    if batch:
        time.sleep(1)
        send(batch)


def check_once():
    new = fetch_leaderboard()
    old = load_state()
    if old is None:
        save_state(new)
        print(f"First run: saved baseline of {len(new)} players (no post sent).")
        return
    if not diff(old, new):
        print("No changes.")
        return
    shown = diff(old, new, top_n=QUALIFY_CUTOFF)
    print(f"Standings changed ({len(shown)} in top {QUALIFY_CUTOFF}/new), posting to Discord.")
    announce(shown, new)
    save_state(new)


def main():
    if not bot.WEBHOOK_URL:
        sys.exit("Set DISCORD_WEBHOOK_URL (see README).")
    if "--test" in sys.argv:
        send([{"title": "✅ Test message", "description": "Split-embed watcher is connected.", "color": BLUE}])
        print("Sent.")
        return
    if "--preview" in sys.argv:
        new = fetch_leaderboard()
        announce(diff(fake_previous(new), new, QUALIFY_CUTOFF), new)
        print("Preview sent (made-up changes; saved state untouched).")
        return
    if "--once" in sys.argv:
        check_once()
        return
    print(f"Watching {bot.LEADERBOARD_URL} every {bot.POLL_MINUTES:g} min. Ctrl+C to stop.")
    while True:
        try:
            check_once()
        except Exception as e:
            print(f"[warn] check failed: {e}")
        time.sleep(bot.POLL_MINUTES * 60)


if __name__ == "__main__":
    main()
