#!/usr/bin/env python3
"""
NRPL leaderboard watcher.

Polls https://pauperleague.com/leaderboard, and when standings change,
posts a summary embed to a Discord channel via webhook.

Usage:
    python bot.py            # run forever, polling every POLL_MINUTES
    python bot.py --once     # single check (for cron / systemd timers)
    python bot.py --test     # send a test message to Discord and exit
    python bot.py --preview  # post the real format using live data + made-up changes
"""
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------- config ---
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
# /leaderboard shows the current season; use /leaderboard/1 to pin Season One.
LEADERBOARD_URL = os.environ.get("LEADERBOARD_URL", "https://pauperleague.com/leaderboard")
POLL_MINUTES = float(os.environ.get("POLL_MINUTES", "15"))
STATE_FILE = Path(os.environ.get("STATE_FILE", "state.json"))
QUALIFY_CUTOFF = int(os.environ.get("QUALIFY_CUTOFF", "12"))  # top N qualify
MAX_CHANGE_LINES = 20
USER_AGENT = "NRPL-Discord-Watcher/1.0"


# --------------------------------------------------------------- scraping ---
def to_int(text):
    m = re.search(r"-?\d+", text)
    return int(m.group()) if m else 0


def fetch_leaderboard():
    """Return an ordered list of player dicts from the leaderboard page."""
    resp = requests.get(LEADERBOARD_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # The page has a wide table (Wins/Losses/Draws columns) and a compact
    # mobile one (Record column). Use the wide one.
    table = None
    for t in soup.find_all("table"):
        headers = [th.get_text(strip=True).lower() for th in t.find_all("th")]
        if "wins" in headers and "points" in headers:
            table = t
            break
    if table is None:
        raise RuntimeError("Could not find leaderboard table - has the site layout changed?")

    headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
    idx = {name: i for i, name in enumerate(headers)}

    players = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < len(headers):
            continue
        link = cells[idx["name"]].find("a")
        if not link:
            continue
        m = re.search(r"/players/(\d+)", link.get("href", ""))
        pid = m.group(1) if m else link.get_text(strip=True)
        players.append({
            "id": pid,
            "name": link.get_text(" ", strip=True),
            "rank": to_int(cells[0].get_text()),
            "points": to_int(cells[idx["points"]].get_text()),
            "bonus": to_int(cells[idx["bonus"]].get_text()),
            "wins": to_int(cells[idx["wins"]].get_text()),
            "losses": to_int(cells[idx["losses"]].get_text()),
            "draws": to_int(cells[idx["draws"]].get_text()),
            "weeks": to_int(cells[idx["weeks"]].get_text()),
            "matches": to_int(cells[idx["matches"]].get_text()),
        })
    if not players:
        raise RuntimeError("Leaderboard table was empty.")
    return players


# ------------------------------------------------------------------- diff ---
def diff(old, new, top_n=None):
    """Compare two snapshots. Returns a list of change lines (empty = no change).

    If top_n is set, only report players who are in (or just left) the top N, plus new players.
    """
    old_by_id = {p["id"]: p for p in old}
    lines = []
    for p in new:
        o = old_by_id.get(p["id"])
        if o is None:
            lines.append((p["rank"], f"🆕 **{p['name']}** joins at #{p['rank']} "
                                     f"({p['points']} pts, {p['wins']}-{p['losses']}-{p['draws']})"))
            continue
        changed = any(p[k] != o[k] for k in ("points", "wins", "losses", "draws", "weeks", "rank"))
        if not changed:
            continue
        if top_n and p["rank"] > top_n and o["rank"] > top_n:
            continue  # outside the top N before and after
        gained = p["points"] - o["points"]
        pts = f"{p['points']} pts" + (f" (+{gained})" if gained else "")
        if p["rank"] < o["rank"]:
            move = f"⬆️ #{o['rank']} → #{p['rank']}"
        elif p["rank"] > o["rank"]:
            move = f"⬇️ #{o['rank']} → #{p['rank']}"
        else:
            move = f"#{p['rank']}"
        lines.append((p["rank"], f"{move} **{p['name']}** - {pts}, "
                                 f"{p['wins']}-{p['losses']}-{p['draws']}"))
    lines.sort(key=lambda x: x[0])
    return [text for _, text in lines]


def fake_previous(players):
    """Make a pretend 'previous' snapshot so --preview has changes to show."""
    import copy
    old = copy.deepcopy(players)
    if len(old) > 1:
        old[0]["points"] = max(0, old[0]["points"] - 3)          # top player gained points
        old[0]["rank"], old[1]["rank"] = old[1]["rank"], old[0]["rank"]  # top two swapped
    if len(old) > 2:
        old.pop()                                                # last player "joined"
    return old


LEGEND = "*Format: Rank · Player · **Points** (Bonus points) · **Wins-Losses-Draws***"


def row(p):
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    badge = medals.get(p["rank"]) or "`%2d`" % p["rank"]
    return (f"{badge} {p['name']} - **{p['points']} pts** ({p['bonus']} bonus) · "
            f"{p['wins']}-{p['losses']}-{p['draws']}")


def no_changes_text():
    return f"No changes in the top {QUALIFY_CUTOFF} and no new players - lower standings were updated."


def top_block(players, n=QUALIFY_CUTOFF):
    return LEGEND + "\n" + "\n".join(row(p) for p in players[:n])


# ---------------------------------------------------------------- discord ---
def post_embed(title, description, fields=None):
    embed = {
        "title": title,
        "url": LEADERBOARD_URL,
        "description": description[:4000],
        "color": 0x5865F2,
        "fields": fields or [],
        "footer": {"text": "pauperleague.com"},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    r = requests.post(WEBHOOK_URL, json={"username": "NRPL Leaderboard", "embeds": [embed]}, timeout=30)
    if r.status_code == 429:  # rate limited; wait and retry once
        time.sleep(float(r.json().get("retry_after", 2)) + 0.5)
        r = requests.post(WEBHOOK_URL, json={"username": "NRPL Leaderboard", "embeds": [embed]}, timeout=30)
    r.raise_for_status()


def announce(changes, players):
    shown = changes[:MAX_CHANGE_LINES]
    desc = "\n".join(shown) or no_changes_text()
    if len(changes) > len(shown):
        desc += f"\n…and {len(changes) - len(shown)} more"
    post_embed(
        "🏆 Leaderboard updated!",
        desc,
        fields=[{"name": f"Top {QUALIFY_CUTOFF} (qualification spots)",
                 "value": top_block(players)[:1024]}],
    )


# ------------------------------------------------------------------- main ---
def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return None


def save_state(players):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(players, indent=1))
    tmp.replace(STATE_FILE)


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
    save_state(new)  # only after a successful post, so failures retry next cycle


def main():
    if not WEBHOOK_URL:
        sys.exit("Set DISCORD_WEBHOOK_URL (see README).")
    if "--test" in sys.argv:
        post_embed("✅ Test message", "The NRPL leaderboard watcher is connected.")
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
    print(f"Watching {LEADERBOARD_URL} every {POLL_MINUTES:g} min. Ctrl+C to stop.")
    while True:
        try:
            check_once()
        except Exception as e:  # keep running through site/network hiccups
            print(f"[warn] check failed: {e}")
        time.sleep(POLL_MINUTES * 60)


if __name__ == "__main__":
    main()
