# fitness

Three data sources: Strong (workouts), Renpho (body comp), Oura (recovery/sleep).

## Notion Schema

### Workout Log
One row per session.

| Property | Type | Notes |
|---|---|---|
| Workout | Title | Session name (e.g. "Afternoon Workout") |
| Date | Date | Session date |
| Type | Select | Push / Pull / Legs / Upper / Full Body / Cardio |
| Source | Select | Strong App / Manual |

Page body contains a formatted table of exercises for that session.

**URL:** https://app.notion.com/p/bbe1375c01bf4656b64d4a16302c319f

### Sets Log
One row per exercise. Linked to Workout Log via relation — lets you filter by exercise name and track weight/reps progression over time.

| Property | Type | Notes |
|---|---|---|
| Exercise | Title | e.g. "Bench Press (Barbell)" |
| Date | Date | Session date (rename from "date:Date:start" in Notion) |
| Weight | Number | Working weight |
| Weight Unit | Select | lb / kg |
| Reps | Number | Reps per set |
| Sets | Number | Number of sets |
| Workout | Relation | Links to Workout Log session |
| Notes | Text | e.g. warmup info, dropped sets |

**URL:** https://app.notion.com/p/e973fc6833d14724a656be08c3303e1e

## Logging Workflow

1. Finish workout in the Strong app
2. Export session as text (Share → Copy as Text)
3. Paste into Claude with "log this workout"
4. Claude creates one row in Workout Log + one row per exercise in Sets Log

### Body Metrics
One row per weigh-in from the Renpho scale.

| Property | Type |
|---|---|
| Date | Title |
| Weight | Number (lb) |
| BMI | Number |
| Body Fat Pct / Mass | Number |
| Skeletal Muscle Pct / Mass | Number |
| Visceral Fat | Number |
| BMR | Number (kcal) |
| Metabolic Age | Number |
| Fat-Free Mass | Number (lb) |
| Muscle Mass | Number (lb) |
| Bone Mass | Number (lb) |
| Body Water Pct | Number |
| Protein Pct | Number |
| Source | Select (Renpho / Manual) |

**URL:** https://app.notion.com/p/a36282227ee24758a46f9dbdad0c08a2

### Renpho Integration

Sync script: `~/.local/bin/renpho` imports a Renpho CSV export into Notion Body Metrics and refreshes `data/renpho_history.json`.

### Usage

```bash
renpho                                    # interactive: finds CSV in Downloads
renpho --file ~/Downloads/RENPHO*.csv    # specific file
renpho --file PATH --all --yes            # non-interactive backfill
```

Workflow:
1. Renpho app → Me → Data Export → CSV (AirDrop to Mac)
2. Run `renpho`
3. Choose latest or all measurements

Credentials: `~/.config/credentials/notion.env` (`NOTION_API_KEY`).

**Setup:** share the Body Metrics database with your Notion integration (Connections in Notion). Without this, `renpho` returns 404.

## Oura Integration

Sync script: `scripts/oura_sync.py` pulls all daily Oura API v2 data into Notion Daily Log and refreshes `data/oura/` JSON caches.

### Usage

```bash
python3 scripts/oura_sync.py                         # yesterday + today
python3 scripts/oura_sync.py --date 2026-06-29       # single day
python3 scripts/oura_sync.py --start 2026-06-01 --end 2026-06-30
python3 scripts/oura_sync.py --all                   # backfill from 2026-04-01
python3 scripts/oura_sync.py --dry-run
```

Credentials: `~/.config/credentials/oura.env` (`OURA_PAT`), `notion.env` (`NOTION_API_KEY`).

### API sources (16 calls per run, heartrate chunked by week)

| Endpoint | Notion destination |
|---|---|
| `daily_readiness` | Readiness, HRV Balance, Resting HR, Body Temp Dev, Activity/Sleep Balance, Recovery Index, etc. |
| `daily_sleep` | Sleep Score + contributor scores |
| `sleep` | Stage hours, latency, efficiency, bedtime, sleep HR/HRV |
| `daily_activity` | Steps, calories, activity minutes, sedentary time |
| `daily_spo2` | SpO2 Avg, Breathing Disturbance Index |
| `daily_stress` | Stress (min), Recovery High (min), day summary |
| `daily_resilience` | Resilience contributors + level (when available) |
| `daily_cardiovascular_age` | Vascular Age |
| `vO2_max` | Raw JSON on page (no scalar column yet) |
| `heartrate` | Avg HR + min/max summary in page JSON; full series in `data/oura/heartrate.json` |
| `workout`, `session`, `tag`, `enhanced_tag`, `sleep_time`, `rest_mode_period` | Raw JSON on page when present |
| `personal_info` | Cached to `data/oura/personal_info.json` |

Each Notion page gets all scalar fields mapped to existing DB columns plus a code block (`OURA_RAW:`) with the full daily JSON payload.

Minute-level HR time series are too large for Notion blocks; they live in `data/oura/heartrate.json` only.

### Local JSON cache (`data/oura/`)

Refreshed on every sync run. Key files: `daily_readiness.json`, `daily_sleep.json`, `sleep_detail.json`, `daily_activity.json`, `daily_stress.json`, `daily_spo2.json`, `heartrate.json`, `personal_info.json`, plus endpoint files for optional data.

## Known Issues

- Sets Log date property is named `date:Date:start` — rename it to `Date` manually in Notion for cleaner display

## logs/

Raw Strong app text exports stored here for reference.
