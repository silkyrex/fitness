# AGENTS.md

## Cursor Cloud specific instructions

This repo is a personal fitness data hub. The only runnable code is `scripts/oura_sync.py`, which pulls Oura API v2 data and upserts it into a Notion "Daily Log" database. There is no server, database, or build step. Sole Python dependency is `requests`, installed via `.cursor/environment.json` (`install: pip install requests`). See `README.md` for schemas, workflows, and CLI flags.

- Credentials are read from `~/.config/credentials/oura.env` (`OURA_PAT`) and `~/.config/credentials/notion.env` (`NOTION_API_KEY`), OR from matching environment variables. The script also accepts `NOTION_DAILY_LOG_DB_ID` to override the hardcoded Daily Log DB id. Without `OURA_PAT` and `NOTION_API_KEY` the script exits immediately, and even `--dry-run` needs `OURA_PAT` because it still calls the live Oura API (dry-run only skips Notion writes).
- The Notion integration must be shared with the target databases (Notion → Connections) or API calls return 404.
- The `renpho` CLI referenced in `README.md` lives at `~/.local/bin/renpho` and is NOT in this repo; the Renpho pipeline cannot be run or tested from here.
- No lint config, tests, or CI exist. To verify code without credentials, exercise the pure transform functions (`merge_oura`, `heartrate_by_day`, `primary_sleep_by_day`, `notion_props`) with mock Oura JSON. `data/` is gitignored and auto-created on sync.
