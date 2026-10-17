# NRPL Leaderboard → Discord

Checks https://pauperleague.com/leaderboard every 60 minutes and posts an embed to
your Discord channel when standings change (rank moves, points gained, new players,
plus the current Top 12).

## Setup

1. **Create a webhook:** Discord channel → Edit Channel → Integrations → Webhooks → New Webhook → Copy Webhook URL.
2. **Install:** `pip install -r requirements.txt` (Python 3.8+)
3. **Set the URL and test it:**
   ```
   export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
   python bot.py --test
   ```
4. **Run it:** `python bot.py`
   The first run saves a baseline silently; posts start on the next change.

## Running 24/7

- Any always-on machine, Raspberry Pi, or small VPS: `nohup python bot.py &` or a systemd service.
- Or use cron with `--once`, e.g. every 15 min: `*/15 * * * * cd /path/to/pauper_bot && DISCORD_WEBHOOK_URL=... python bot.py --once`

## Options (environment variables)
| Variable | Default | Purpose |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | required | Where to post |
| `LEADERBOARD_URL` | `https://pauperleague.com/leaderboard` | Use `/leaderboard/1` to pin Season One |
| `POLL_MINUTES` | 15 | Check frequency (local mode only) |
| `QUALIFY_CUTOFF` | 12 | Size of the "top" list |
| `STATE_FILE` | `state.json` | Last-seen standings |
