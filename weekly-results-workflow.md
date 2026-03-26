# Weekly Results Workflow

This document defines the process for turning the previous scoring week's active-lineup stats into updated season totals and standings.

The process has two parts:

1. Sunday evening: snapshot the active lineup that will count for the coming scoring week
2. Monday morning: import the completed week's player stats and update standings using only players who were active in that lineup snapshot

## Files Written By The Process

Sunday lineup snapshot:

- `data/weekly-lineups/<week>.csv`

Monday stat import and standings outputs:

- `data/weekly-stats/<week>.csv`
- `data/season-results-2026.json`
- `data/player-contributions-2026.csv`

Optional Monday roster-compliance audit outputs:

- `data/minor-league-eligibility-report-2026.json`
- `data/minor-league-eligibility-report-2026.csv`

## Sunday Step

Create the lineup snapshot template:

```powershell
c:/FantasyBaseball/.venv/Scripts/python.exe scripts/build_weekly_lineup_snapshot.py --week 2026-week-01
```

That writes a CSV with one row per rostered player and these key fields:

- `lineup_status`
- `lineup_slot`
- `mlbam_id`
- `player_name`
- `player_type`

The script seeds the file with the workspace's projected best lineup. Review that CSV and edit it so it matches the lineup that was actually active at lock.

Required validation target for each team:

- 13 active hitters
- 9 active pitchers

## Monday Step

After the scoring week ends, import the completed week's stats and update standings:

```powershell
c:/FantasyBaseball/.venv/Scripts/python.exe scripts/update_weekly_results.py --week 2026-week-01 --start-date 2026-03-29 --end-date 2026-04-04
```

Default behavior:

- reads `data/weekly-lineups/2026-week-01.csv`
- fetches player stats for the date range from the MLB Stats API
- writes `data/weekly-stats/2026-week-01.csv`
- updates `data/season-results-2026.json`
- updates `data/player-contributions-2026.csv`

If you already have a weekly stats CSV and do not want the script to fetch data again:

```powershell
c:/FantasyBaseball/.venv/Scripts/python.exe scripts/update_weekly_results.py --week 2026-week-01 --start-date 2026-03-29 --end-date 2026-04-04 --skip-fetch
```

If a week's results need to be corrected and rebuilt:

```powershell
c:/FantasyBaseball/.venv/Scripts/python.exe scripts/update_weekly_results.py --week 2026-week-01 --start-date 2026-03-29 --end-date 2026-04-04 --replace-week
```

## Monday Minor-League Eligibility Audit

After the weekly results update, run the minor-league eligibility audit before making new roster decisions for the next lock:

```powershell
c:/FantasyBaseball/.venv/Scripts/python.exe scripts/check_minor_league_eligibility.py
```

The audit:

- reads all current `manager-rosters/*.csv` files
- joins rostered players to `data/draft-board-input-2026.csv`
- pulls live MLB career hitting and pitching totals from the MLB Stats API
- flags any player still stored in a `Minors` roster slot who has crossed 130 MLB at-bats or 50 MLB innings pitched
- suggests the two legal resolution paths for each offender:
	- drop the offender and add a new eligible minor leaguer
	- promote the offender to the MLB bucket, drop one MLB player, and add a new eligible minor leaguer
- ranks likely MLB drop candidates and replacement minor-league adds for each team

Review the generated JSON or CSV report before editing roster files for the next week.

## What Counts

Only players marked `ACTIVE` in the lineup snapshot count toward team totals.

This applies to both:

- team standings
- player contribution tracking

Bench and minors rows do not receive credit unless they were active in that week's snapshot.

## Player Contribution Tracking

The process tracks each player's counted contributions by category, by team, across all processed weeks.

Counting categories accumulate directly:

- Runs
- Home Runs
- RBI
- Stolen Bases
- Wins
- Strikeouts
- Saves

Rate categories are tracked from their real components so they only reflect counted active-lineup production:

- OBP from hits, walks, hit by pitch, at-bats, and sacrifice flies
- ERA from earned runs and innings pitched
- WHIP from hits allowed, walks allowed, and innings pitched

## Rebuild The League Site Payload

After updating weekly results, rebuild the league site payload so the docs JSON picks up the new standings:

```powershell
c:/FantasyBaseball/.venv/Scripts/python.exe scripts/build_league_site.py
```

The site builder now reads `data/season-results-2026.json` when it exists and uses those standings and season totals instead of zero placeholders.