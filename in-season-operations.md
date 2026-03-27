# In-Season Operations

This is the default reference for routine league work during the season. Use it first, and only open the longer workflow or rules docs when a task needs extra detail.

## Weekly Cadence

The season runs on a two-step weekly cycle:

1. Sunday evening: set each team's lineup and roster state for the next scoring week before the Sunday 12:00 AM lock.
2. Monday morning: post the completed week's stats, update standings, and refresh league outputs.

Only active players earn stats.

## Core League Constraints

- 10 teams
- 5x5 roto categories
- Active lineup: 13 hitters and 9 pitchers
- Bench: 8
- Injured List: 5
- Minors: 15
- Minor-league eligibility ends at 130 MLB at-bats or 50 MLB innings pitched
- Pitching minimum: 950 innings
- Pitching maximum: 1400 innings
- FAAB budget: 1000
- Trade deadline: August 15

## Sunday Task

Goal: lock legal, optimized active rosters for the coming scoring week.

Default command:

```powershell
c:/FantasyBaseball/.venv/Scripts/python.exe scripts/build_weekly_roster_decisions.py --week 2026-week-01
```

Primary checks:

- active lineup is complete
- bench, IL, and minors are legal
- injured players are handled correctly
- players with an MLB injured-list status are moved into the fantasy IL bucket before lock
- each IL move that opens an MLB slot is auto-paired with a replacement add from the unrostered pool
- minors slots do not contain ineligible players
- active choices fit each team's category needs and manager tendencies

Primary outputs:

- `data/weekly-lineups/<week>.csv`
- `data/weekly-decisions/<week>.json`
- `data/weekly-decisions/<week>.csv`

## Injury Check Process

Run this before setting weekly lineups whenever MLB injury statuses have changed.

1. Refresh `data/player-transactions-2026.csv` from the MLB transaction feed and use `scripts/update_player_injuries.py` for any manual override notes.
2. Rebuild `data/draft-board-input-2026.csv` so the latest `injury_status` values flow into the weekly tools.

```powershell
c:/FantasyBaseball/.venv/Scripts/python.exe scripts/build_draft_board_input.py
```

3. Run the weekly decision builder for the scoring week.

```powershell
c:/FantasyBaseball/.venv/Scripts/python.exe scripts/build_weekly_roster_decisions.py --week 2026-week-01
```

4. Review the `injury-il-add` recommendations in `data/weekly-decisions/<week>.json` or `.csv`.
5. By default, `scripts/build_weekly_roster_decisions.py` auto-applies each clear IL move to the relevant `manager-rosters/*.csv` file and auto-adds the selected unrostered replacement with `roster_bucket` set to `MLB`.
6. Review the `auto_apply` section in `data/weekly-decisions/<week>.json` for the applied transaction log.
7. Rerun only if you intentionally used `--skip-auto-apply` or if the report still shows blocked IL moves.

Weekly lock rule:

- players with an IL or disabled-list status must not appear as `ACTIVE` in `data/weekly-lineups/<week>.csv`
- players already stored in the `IL` roster bucket are excluded from the weekly optimizer automatically
- the weekly decision builder is the authoritative place that auto-updates IL roster state unless `--skip-auto-apply` is used

## Monday Task

Goal: add the completed week's counted stats into season totals and standings.

Default command:

```powershell
c:/FantasyBaseball/.venv/Scripts/python.exe scripts/update_weekly_results.py --week 2026-week-01 --start-date 2026-03-29 --end-date 2026-04-04
```

Primary outputs:

- `data/weekly-stats/<week>.csv`
- `data/weekly-stats/<week>-games.json`
- `data/season-results-2026.json`
- `data/player-contributions-2026.csv`

## Compliance Audit

Run after the weekly results update and before the next lock when you need a legal-roster check.

Command:

```powershell
c:/FantasyBaseball/.venv/Scripts/python.exe scripts/check_minor_league_eligibility.py
```

Primary questions:

- which minors players have crossed 130 AB or 50 IP
- which teams must promote or cut players before the next lock
- which MLB drops or replacement minors adds are the cleanest legal resolution
- which teams still have unresolved IL moves before the next weekly lock

## Site Refresh

Run after standings change if the docs site needs current league-state data.

Command:

```powershell
c:/FantasyBaseball/.venv/Scripts/python.exe scripts/build_league_site.py
```

Primary dependency:

- `data/season-results-2026.json`

## Context By Task

Load only these markdown files for routine work.

Sunday roster setting:

- `in-season-operations.md`
- `manager-weekly-tendencies.md`

Monday results posting:

- `in-season-operations.md`

Minor-league eligibility audit:

- `in-season-operations.md`

League site refresh:

- `in-season-operations.md`

Escalate to the longer docs only when needed:

- `dynasty-league-rules.md` for exact league-rule interpretation
- `sunday-workflow.md` for full Sunday decision detail
- `weekly-results-workflow.md` for full Monday ingestion detail
- `manager-profiles.md` or `manager-profiles/*.md` for a close manager-specific judgment call

## Exclude By Default

Do not load these for routine in-season work unless the user explicitly asks for startup-draft history or methodology:

- `draft-simulation-inputs.md`
- `draft-source-plan.md`
- `startup-draft-board.md`
- `startup-draft-methodology.md`
- `startup-draft-prep.md`