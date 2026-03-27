# Weekly Results Workflow

This document defines the process for turning the previous scoring week's active-lineup stats into updated season totals and standings.

The process has two parts:

1. Sunday evening: snapshot the active lineup that will count for the coming scoring week
2. Monday morning: import the completed week's player stats and update standings using only players who were active in that lineup snapshot

## Files Written By The Process

Sunday lineup snapshot:

- `data/weekly-lineups/<week>.csv`
- `data/weekly-decisions/<week>.json`
- `data/weekly-decisions/<week>.csv`

Monday stat import and standings outputs:

- `data/weekly-stats/<week>.csv`
- `data/weekly-stats/<week>-games.json`
- `data/season-results-2026.json`
- `data/player-contributions-2026.csv`

Optional Monday roster-compliance audit outputs:

- `data/minor-league-eligibility-report-2026.json`
- `data/minor-league-eligibility-report-2026.csv`

## Sunday Step

Preferred one-step automation:

```powershell
c:/FantasyBaseball/.venv/Scripts/python.exe scripts/build_weekly_roster_decisions.py --week 2026-week-01
```

That command:

- rewrites the projected lineup snapshot in `data/weekly-lineups/<week>.csv`
- writes a current-state decision report to `data/weekly-decisions/<week>.json`
- writes a spreadsheet-friendly recommendation file to `data/weekly-decisions/<week>.csv`
- auto-applies clear IL or disabled-list moves into the fantasy IL bucket before lock
- auto-adds an unrostered replacement for each applied IL move when an MLB slot opens
- flags any rostered minor leaguers who now project as better MLB-bucket holds or fantasy starters

If you only want the lineup snapshot without the decision report, you can still run the narrower command below.

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

The weekly decision report adds team-by-team automation for:

- projected active hitters
- projected active pitchers
- projected bench players
- IL moves that must be applied before lock
- replacement adds from the unrostered pool after an IL move
- current rostered minor leaguers who now merit MLB promotion consideration

The script seeds the file with the workspace's projected best lineup. Review that CSV and edit it so it matches the lineup that was actually active at lock.

Required validation target for each team:

- 13 active hitters
- 9 active pitchers

Players with an IL or disabled-list status are excluded from the projected weekly active lineup automatically. The weekly decision builder now updates clear IL moves in the roster CSVs before writing the final outputs. If the report still shows a blocked IL move, resolve that condition and rerun the command.

## Monday Step

After the scoring week ends, import the completed week's stats and update standings:

```powershell
c:/FantasyBaseball/.venv/Scripts/python.exe scripts/update_weekly_results.py --week 2026-week-01 --start-date 2026-03-29 --end-date 2026-04-04
```

Default behavior:

- reads `data/weekly-lineups/2026-week-01.csv`
- fetches the MLB schedule for the date range, ingests only completed game IDs that have not already been processed, and builds player totals from game boxscores
- writes `data/weekly-stats/2026-week-01.csv`
- writes `data/weekly-stats/2026-week-01-games.json`
- updates `data/season-results-2026.json`
- updates `data/player-contributions-2026.csv`

The weekly game ledger JSON is the source of truth for tracked ingestion state. It records which completed MLB games are already in the weekly CSV and which games in the requested date range are still pending, so the command can be rerun on demand without double-counting finished games.

If you already have a weekly stats CSV and do not want the script to fetch data again:

```powershell
c:/FantasyBaseball/.venv/Scripts/python.exe scripts/update_weekly_results.py --week 2026-week-01 --start-date 2026-03-29 --end-date 2026-04-04 --skip-fetch
```

`--skip-fetch` now expects the matching `data/weekly-stats/<week>-games.json` ledger to exist alongside the CSV.

If a week's results need to be corrected and rebuilt:

```powershell
c:/FantasyBaseball/.venv/Scripts/python.exe scripts/update_weekly_results.py --week 2026-week-01 --start-date 2026-03-29 --end-date 2026-04-04 --replace-week
```

Rerunning the command for the same week without `--replace-week` updates that week in place and ingests only newly final games. Use `--replace-week` when you want to discard the current weekly CSV and ledger and rebuild the week from scratch.

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
- evaluates each flagged player as a forced roster decision and recommends whether to promote the player or cut the player outright
- labels any promotion recommendation as a projected fantasy starter or bench move under the current optimizer
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