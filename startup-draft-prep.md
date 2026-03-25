# Startup Draft Prep

This file defines the structured artifacts that should exist before simulating the 2026 startup draft.

## Required Draft Prep Outputs

The startup simulation should be driven by the following files in `data/`:

- `player-pool-2026.csv`
- `player-stats-2025.csv`
- `dynasty-rankings-2026.csv`
- `prospect-rankings-2026.csv`
- `market-adp-2026.csv`
- `player-context-2026.csv`
- `player-injuries-2026.csv`
- `player-transactions-2026.csv`
- `skill-metrics-2026.csv`
- `startup-draft-settings-2026.json`
- `draft-board-input-2026.csv`
- `draft-board-input-summary-2026.json`

## Source-Specific Raw Inputs

Load source-native rows into these files before rebuilding the final draft outputs:

- `dynasty-rankings-fantraxhq-2026.csv`
- `market-adp-fantasypros-2026.csv`
- `market-adp-rotowire-2026.csv`
- `chadwick-register-2026.csv`

For direct copy/paste workflows, first paste source exports into the staging files in `data/imports/` and run `scripts/import_rank_sources.py`.

## Source Mapping

### Canonical player identity

- MLB Stats API
- Chadwick Register when external IDs are needed

### Recent MLB actuals

- MLB Stats API 2025 season stats

### Projection baseline

- FanGraphs exports when stable
- Razzball Steamer as the public-first fallback

### Dynasty and prospect value

- FantraxHQ dynasty rankings
- FantraxHQ prospect rankings
- MLB Pipeline
- Prospects Live

### Market timing

- FantasyPros ADP
- RotoWire ADP

### Identity bridge

- Chadwick Register

### Injury, role, and assignment context

- MLB Stats API transactions
- RotoWire injury report
- RotoWire closer context

### Skill validation

- Baseball Savant / Statcast

## Build Workflow

1. Refresh `player-pool-2026.csv` from the projection and metadata pipeline.
2. Paste source exports into the staging files under `data/imports/`.
3. Run `scripts/import_rank_sources.py` to normalize those pasted exports into canonical source files.
4. Load Chadwick ID mappings when external IDs are available.
5. Run `scripts/build_baseline_rankings.py` to compile source-specific final dynasty and market files with baseline fallback.
6. Run `scripts/build_actual_stats_2025.py` to add prior-year MLB production to the board.
7. Run `scripts/build_transaction_tracker_2026.py` to refresh latest transaction and current-level data.
8. Use `scripts/update_player_injuries.py` to maintain the forward-looking injury tracker.
9. Load any role overlays if available.
10. Load skill overlays if available.
11. Defer prospect rankings until the later prospect-focused prep pass if needed.
12. Update `startup-draft-settings-2026.json` with the confirmed draft order and any commissioner settings.
13. Run `scripts/build_draft_board_input.py`.
14. Use `draft-board-input-summary-2026.json` to identify any remaining blockers and fallback-heavy areas before simulating picks.

## Draft-Ready Minimum

The draft input is minimally ready when:

- dynasty ranks are populated for the MLB core
- ADP is populated for market timing
- current injury tracking is populated when available
- current transaction tracking is populated when available
- the startup draft order is confirmed

If the prep cycle is intentionally focused on MLB-core startup decisions first, prospect rankings can be deferred without blocking the initial board build.

If the source-native files are still empty, the build will use baseline fallback rows. That is playable for an internal first pass, but the summary should be checked for advisory items so those fallback rows can be replaced later.

Skill metrics improve tie-breaks and risk labels, but they are not required for the first playable simulation.

Pitcher role can be estimated from games started when no explicit role file is loaded, so a full bullpen-depth feed is helpful but not mandatory for the initial draft build.

For manual injury maintenance, use a command like:

- `c:/FantasyBaseball/.venv/Scripts/python.exe scripts/update_player_injuries.py --player "Player Name" --status "15-day IL" --expected-return "mid-April" --notes "manual update"`