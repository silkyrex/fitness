#!/usr/bin/env python3
"""
Sync all Oura daily data -> Notion Daily Log.

Usage:
    python3 scripts/oura_sync.py                         # yesterday + today
    python3 scripts/oura_sync.py --date 2026-06-29       # single day
    python3 scripts/oura_sync.py --start 2026-06-01 --end 2026-06-30
    python3 scripts/oura_sync.py --all                   # backfill from 2026-04-01
    python3 scripts/oura_sync.py --dry-run

Env (~/.config/credentials/notion.env, oura.env):
    NOTION_API_KEY, OURA_PAT, NOTION_DAILY_LOG_DB_ID (optional)
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

NOTION_DB_ID = "0091c15a-1b3e-4115-8597-1dbc0a26e6f6"
OURA_BASE = "https://api.ouraring.com/v2/usercollection"
NOTION_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "oura"
BACKFILL_START = "2026-04-01"

DATED_ENDPOINTS = [
    "daily_readiness",
    "daily_sleep",
    "sleep",
    "daily_activity",
    "daily_spo2",
    "daily_stress",
    "daily_resilience",
    "daily_cardiovascular_age",
    "vO2_max",
    "workout",
    "session",
    "tag",
    "enhanced_tag",
    "sleep_time",
    "rest_mode_period",
]

SLEEP_STRIP_KEYS = {
    "heart_rate",
    "hrv",
    "movement_30_sec",
    "app_sleep_phase_5_min",
    "readiness",
}


def load_env(path: str):
    p = Path(path).expanduser()
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


def sec_to_min(seconds):
    if seconds is None:
        return None
    return round(seconds / 60, 1)


def sec_to_hours(seconds):
    if seconds is None:
        return None
    return round(seconds / 3600, 2)


def oura_fetch(token: str, endpoint: str, params: dict | None = None) -> list[dict]:
    params = dict(params or {})
    rows: list[dict] = []
    while True:
        r = requests.get(
            f"{OURA_BASE}/{endpoint}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=30,
        )
        r.raise_for_status()
        body = r.json()
        if isinstance(body, dict) and "data" in body:
            rows.extend(body.get("data") or [])
            token_next = body.get("next_token")
            if not token_next:
                break
            params["next_token"] = token_next
            continue
        if isinstance(body, dict):
            return [body]
        return rows
    return rows


def oura_fetch_range(token: str, endpoint: str, start: str, end: str) -> list[dict]:
    return oura_fetch(token, endpoint, {"start_date": start, "end_date": end})


def oura_fetch_heartrate(token: str, start: str, end: str) -> list[dict]:
    rows: list[dict] = []
    cur = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    while cur <= end_d:
        chunk_end = min(cur + timedelta(days=6), end_d)
        rows.extend(
            oura_fetch(
                token,
                "heartrate",
                {
                    "start_datetime": f"{cur.isoformat()}T00:00:00+00:00",
                    "end_datetime": f"{chunk_end.isoformat()}T23:59:59+00:00",
                },
            )
        )
        cur = chunk_end + timedelta(days=1)
    return rows


def save_json_cache(name: str, rows: list | dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"{name}.json"
    payload = {"data": rows} if isinstance(rows, list) else rows
    path.write_text(json.dumps(payload, indent=2))


def heartrate_by_day(samples: list[dict]) -> dict[str, dict]:
    buckets: dict[str, list[int]] = defaultdict(list)
    for item in samples:
        ts = item.get("timestamp") or item.get("producer_timestamp")
        bpm = item.get("bpm")
        if not ts or bpm is None:
            continue
        day = ts[:10]
        buckets[day].append(int(bpm))
    out = {}
    for day, bpms in buckets.items():
        out[day] = {
            "Avg HR": round(sum(bpms) / len(bpms), 1),
            "_hr_min": min(bpms),
            "_hr_max": max(bpms),
            "_hr_samples": len(bpms),
        }
    return out


def primary_sleep_by_day(sleeps: list[dict]) -> dict[str, dict]:
    best: dict[str, dict] = {}
    for item in sleeps:
        day = item["day"]
        cur = best.get(day)
        if not cur or item.get("total_sleep_duration", 0) > cur.get("total_sleep_duration", 0):
            best[day] = item
    return best


def slim_sleep(item: dict) -> dict:
    out = dict(item)
    for key in SLEEP_STRIP_KEYS:
        out.pop(key, None)
    return out


def merge_oura(
    readiness,
    daily_sleep,
    sleeps,
    activity,
    spo2,
    stress,
    resilience,
    cardio_age,
    vo2,
    hr_days,
):
    rows: dict[str, dict] = {}

    def day_row(d: str) -> dict:
        return rows.setdefault(d, {"day": d, "_raw": {}})

    for item in readiness:
        d = item["day"]
        row = day_row(d)
        row["_raw"]["daily_readiness"] = item
        c = item.get("contributors") or {}
        row["Readiness"] = item.get("score")
        row["HRV Balance"] = c.get("hrv_balance")
        row["Resting HR"] = c.get("resting_heart_rate")
        row["Body Temp Dev"] = item.get("temperature_deviation")
        row["Activity Balance"] = c.get("activity_balance")
        row["Previous Day Activity"] = c.get("previous_day_activity")
        row["Previous Night"] = c.get("previous_night")
        row["Recovery Index"] = c.get("recovery_index")
        row["Sleep Balance"] = c.get("sleep_balance")

    for item in daily_sleep:
        d = item["day"]
        row = day_row(d)
        row["_raw"]["daily_sleep"] = item
        c = item.get("contributors") or {}
        row["Sleep Score"] = item.get("score")
        row["Deep Sleep Score"] = c.get("deep_sleep")
        row["REM Sleep Score"] = c.get("rem_sleep")
        row["Total Sleep Score"] = c.get("total_sleep")
        row["Sleep Efficiency Score"] = c.get("efficiency")
        row["Sleep Latency Score"] = c.get("latency")
        row["Sleep Restfulness Score"] = c.get("restfulness")
        row["Sleep Timing Score"] = c.get("timing")

    for d, item in primary_sleep_by_day(sleeps).items():
        row = day_row(d)
        row["_raw"]["sleep"] = slim_sleep(item)
        row["Total Sleep (hrs)"] = sec_to_hours(item.get("total_sleep_duration"))
        row["Sleep (hrs)"] = sec_to_hours(item.get("total_sleep_duration"))
        row["Deep Sleep (hrs)"] = sec_to_hours(item.get("deep_sleep_duration"))
        row["REM Sleep (hrs)"] = sec_to_hours(item.get("rem_sleep_duration"))
        row["Light Sleep (hrs)"] = sec_to_hours(item.get("light_sleep_duration"))
        row["Sleep Latency (min)"] = sec_to_min(item.get("latency"))
        row["Sleep Efficiency %"] = item.get("efficiency")
        row["Avg HR Sleep"] = item.get("average_heart_rate")
        row["Avg HRV Sleep"] = item.get("average_hrv")
        row["Lowest HR Sleep"] = item.get("lowest_heart_rate")
        if item.get("bedtime_start"):
            row["Bedtime Start"] = item["bedtime_start"]
        if item.get("bedtime_end"):
            row["Bedtime End"] = item["bedtime_end"]
        if item.get("bedtime_start") and item.get("bedtime_end"):
            try:
                start = datetime.fromisoformat(item["bedtime_start"])
                end = datetime.fromisoformat(item["bedtime_end"])
                row["Time in Bed (hrs)"] = round((end - start).total_seconds() / 3600, 2)
            except ValueError:
                pass

    for item in activity:
        d = item["day"]
        row = day_row(d)
        row["_raw"]["daily_activity"] = item
        row["Steps"] = item.get("steps")
        row["Active Cal"] = item.get("active_calories")
        row["Active Calories"] = item.get("active_calories")
        row["Total Calories"] = item.get("total_calories")
        row["High Activity (min)"] = sec_to_min(item.get("high_activity_time"))
        row["Medium Activity (min)"] = sec_to_min(item.get("medium_activity_time"))
        row["Low Activity (min)"] = sec_to_min(item.get("low_activity_time"))
        row["Sedentary (min)"] = sec_to_min(item.get("sedentary_time"))
        row["Resting Time (min)"] = sec_to_min(item.get("resting_time"))
        row["Inactivity Alerts"] = item.get("inactivity_alerts")
        row["Equivalent Walking Distance (m)"] = item.get("equivalent_walking_distance")
        row["Meters to Target"] = item.get("meters_to_target")

    for item in spo2:
        d = item["day"]
        row = day_row(d)
        row["_raw"]["daily_spo2"] = item
        spo2_data = item.get("spo2_percentage") or {}
        avg = spo2_data.get("average") if isinstance(spo2_data, dict) else spo2_data
        row["SpO2 Avg"] = avg
        row["Breathing Disturbance Index"] = item.get("breathing_disturbance_index")

    for item in stress:
        d = item["day"]
        row = day_row(d)
        row["_raw"]["daily_stress"] = item
        row["Stress"] = sec_to_min(item.get("stress_high"))
        row["Recovery High (min)"] = sec_to_min(item.get("recovery_high"))
        if item.get("day_summary"):
            row["Stress Day Summary"] = item["day_summary"]

    for item in resilience:
        d = item["day"]
        row = day_row(d)
        row["_raw"]["daily_resilience"] = item
        c = item.get("contributors") or {}
        row["Resilience Daytime Recovery"] = c.get("daytime_recovery")
        row["Resilience Sleep Recovery"] = c.get("sleep_recovery")
        row["Resilience Stress"] = c.get("stress")
        if item.get("level"):
            row["Resilience Level"] = str(item["level"])

    for item in cardio_age:
        d = item["day"]
        row = day_row(d)
        row["_raw"]["daily_cardiovascular_age"] = item
        row["Vascular Age"] = item.get("vascular_age")

    for item in vo2:
        d = item["day"]
        row = day_row(d)
        row["_raw"]["vO2_max"] = item

    for d, hr in hr_days.items():
        row = day_row(d)
        row["_raw"]["heartrate_summary"] = {
            "avg_bpm": hr["Avg HR"],
            "min_bpm": hr["_hr_min"],
            "max_bpm": hr["_hr_max"],
            "samples": hr["_hr_samples"],
        }
        row["Avg HR"] = hr["Avg HR"]

    return rows


def attach_by_day(rows: dict[str, dict], endpoint: str, items: list[dict]):
    for item in items:
        d = item.get("day")
        if not d:
            continue
        row = rows.setdefault(d, {"day": d, "_raw": {}})
        if endpoint in row["_raw"]:
            cur = row["_raw"][endpoint]
            row["_raw"][endpoint] = cur if isinstance(cur, list) else [cur]
            row["_raw"][endpoint].append(item)
        else:
            row["_raw"][endpoint] = item


def notion_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def find_page_by_date(notion_token: str, db_id: str, day: str) -> str | None:
    r = requests.post(
        f"{NOTION_BASE}/databases/{db_id}/query",
        headers=notion_headers(notion_token),
        json={"filter": {"property": "Date", "title": {"equals": day}}},
        timeout=15,
    )
    r.raise_for_status()
    results = r.json().get("results", [])
    return results[0]["id"] if results else None


def notion_props(row: dict) -> dict:
    props = {"Date": {"title": [{"text": {"content": row["day"]}}]}}
    rich_text_keys = {"Stress Day Summary", "Resilience Level"}
    date_keys = {"Bedtime Start", "Bedtime End"}

    for key, value in row.items():
        if key in ("day", "_raw") or value is None:
            continue
        if isinstance(value, (int, float)):
            props[key] = {"number": value}
        elif key in rich_text_keys:
            props[key] = {"rich_text": [{"text": {"content": str(value)[:2000]}}]}
        elif key in date_keys:
            props[key] = {"date": {"start": value}}

    return props


def chunk_text(text: str, size: int = 1900) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def replace_page_raw_json(notion_token: str, page_id: str, payload: dict, dry_run: bool):
    if dry_run:
        return
    headers = notion_headers(notion_token)
    blocks = []
    cursor = None
    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        r = requests.get(
            f"{NOTION_BASE}/blocks/{page_id}/children",
            headers=headers,
            params=params,
            timeout=15,
        )
        r.raise_for_status()
        body = r.json()
        blocks.extend(body.get("results", []))
        if not body.get("has_more"):
            break
        cursor = body.get("next_cursor")

    for block in blocks:
        txt = ""
        if block.get("type") == "code":
            rich = block["code"].get("rich_text") or []
            txt = "".join(t.get("plain_text", "") for t in rich)
        if txt.startswith("OURA_RAW:"):
            requests.delete(
                f"{NOTION_BASE}/blocks/{block['id']}",
                headers=headers,
                timeout=15,
            ).raise_for_status()

    raw = json.dumps(payload, indent=2, default=str)
    children = []
    for part in chunk_text(f"OURA_RAW:{raw}"):
        children.append(
            {
                "object": "block",
                "type": "code",
                "code": {
                    "rich_text": [{"type": "text", "text": {"content": part}}],
                    "language": "json",
                },
            }
        )
    requests.patch(
        f"{NOTION_BASE}/blocks/{page_id}/children",
        headers=headers,
        json={"children": children},
        timeout=15,
    ).raise_for_status()


def upsert_page(notion_token: str, db_id: str, row: dict, dry_run: bool) -> str:
    day = row["day"]
    props = notion_props(row)
    existing_id = find_page_by_date(notion_token, db_id, day)
    raw_payload = row.get("_raw") or {}

    if dry_run:
        filled = [k for k in props if k != "Date"]
        action = "UPDATE" if existing_id else "CREATE"
        print(f"  [{action}] {day}: {len(filled)} props, raw={list(raw_payload)}")
        return existing_id or "(dry-run)"

    if existing_id:
        page_id = existing_id
        r = requests.patch(
            f"{NOTION_BASE}/pages/{page_id}",
            headers=notion_headers(notion_token),
            json={"properties": props},
            timeout=15,
        )
    else:
        r = requests.post(
            f"{NOTION_BASE}/pages",
            headers=notion_headers(notion_token),
            json={"parent": {"database_id": db_id}, "properties": props},
            timeout=15,
        )
    r.raise_for_status()
    page_id = r.json()["id"]
    if raw_payload:
        replace_page_raw_json(notion_token, page_id, raw_payload, dry_run=False)
    return page_id


def pull_all(token: str, start: str, end: str) -> dict:
    print(f"Pulling Oura {start} -> {end}")
    fetched = {}
    for ep in DATED_ENDPOINTS:
        rows = oura_fetch_range(token, ep, start, end)
        fetched[ep] = rows
        save_json_cache(ep if ep != "sleep" else "sleep_detail", rows)
        print(f"  {ep}: {len(rows)} rows")

    heartrate = oura_fetch_heartrate(token, start, end)
    fetched["heartrate"] = heartrate
    save_json_cache("heartrate", heartrate)
    print(f"  heartrate: {len(heartrate)} samples")

    personal = oura_fetch(token, "personal_info")
    fetched["personal_info"] = personal
    save_json_cache("personal_info", personal[0] if personal else {})
    print(f"  personal_info: {len(personal)} row(s)")

    hr_days = heartrate_by_day(heartrate)
    rows = merge_oura(
        fetched["daily_readiness"],
        fetched["daily_sleep"],
        fetched["sleep"],
        fetched["daily_activity"],
        fetched["daily_spo2"],
        fetched["daily_stress"],
        fetched["daily_resilience"],
        fetched["daily_cardiovascular_age"],
        fetched["vO2_max"],
        hr_days,
    )
    for ep in (
        "workout",
        "session",
        "tag",
        "enhanced_tag",
        "sleep_time",
        "rest_mode_period",
    ):
        attach_by_day(rows, ep, fetched[ep])
    print(f"  merged: {len(rows)} days")
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Single date YYYY-MM-DD")
    parser.add_argument("--start", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", help="End date YYYY-MM-DD")
    parser.add_argument("--all", action="store_true", help=f"Backfill from {BACKFILL_START}")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_env("~/.config/credentials/notion.env")
    load_env("~/.config/credentials/oura.env")

    oura_token = os.environ.get("OURA_PAT")
    notion_token = os.environ.get("NOTION_API_KEY")
    if not oura_token:
        sys.exit("ERROR: OURA_PAT not set. Add to ~/.config/credentials/oura.env")
    if not notion_token:
        sys.exit("ERROR: NOTION_API_KEY not set. Add to ~/.config/credentials/notion.env")

    if args.date:
        start = end = args.date
    elif args.start and args.end:
        start, end = args.start, args.end
    elif args.all:
        start, end = BACKFILL_START, date.today().isoformat()
    else:
        start = (date.today() - timedelta(days=1)).isoformat()
        end = date.today().isoformat()

    rows = pull_all(oura_token, start, end)

    if args.dry_run:
        print("\n[DRY RUN] Would write:")

    db_id = os.environ.get("NOTION_DAILY_LOG_DB_ID", NOTION_DB_ID)
    for day in sorted(rows):
        upsert_page(notion_token, db_id, rows[day], dry_run=args.dry_run)
        if not args.dry_run:
            print(f"  synced {day}")

    print("Done.")


if __name__ == "__main__":
    main()
