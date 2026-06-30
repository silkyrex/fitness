# fitness

Workout tracking system — logs sessions from the Strong app into Notion.

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

## Known Issues

- Sets Log date property is named `date:Date:start` — rename it to `Date` manually in Notion for cleaner display

## logs/

Raw Strong app text exports stored here for reference.
