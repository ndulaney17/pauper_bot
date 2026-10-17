# NRPL Leaderboard → Discord

Checks https://pauperleague.com/leaderboard and, when standings change, posts to your Discord channel:

1. **What changed** - top-12 movement and new players only
2. **Top 12** - qualification spots, with points, bonus points, and W-L-D
3. **Full standings** - everyone (auto-splits if the list gets long)

## Files
- `bot.py` - the whole bot (single file)
- `requirements.txt` - dependencies
- `.github/workflows/leaderboard.yml` - runs the bot every ~15 min on GitHub (no computer needed)
- `.gitignore` - keeps `.venv/` etc. out of the repo
- `state.json` - created on first run; the last-seen standings (keep it in the repo)

## Commands
```
python bot.py --test      # send a "connected" message
python bot.py --preview   # post the real format using live data + made-up changes
python bot.py --once      # single check (what GitHub Actions runs)
python bot.py             # run forever on your own machine
```
Set your webhook first: `DISCORD_WEBHOOK_URL` (PowerShell: `$env:DISCORD_WEBHOOK_URL="..."`, Mac/Linux: `export DISCORD_WEBHOOK_URL="..."`).

## GitHub setup
Push this folder to a GitHub repo, add a repository secret named `DISCORD_WEBHOOK_URL`
(Settings → Secrets and variables → Actions), then run the workflow once from the Actions tab.
The first run saves a baseline without posting.

## Options (environment variables)
| Variable | Default | Purpose |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | required | Where to post |
| `LEADERBOARD_URL` | `https://pauperleague.com/leaderboard` | Use `/leaderboard/1` to pin Season One |
| `POLL_MINUTES` | 15 | Check frequency (local mode only) |
| `QUALIFY_CUTOFF` | 12 | Size of the "top" list |
| `STATE_FILE` | `state.json` | Last-seen standings |
