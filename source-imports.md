# Source Import Workflow

This file defines the paste-friendly import workflow for source-native dynasty rankings and market ADP.

## Paste Targets

Paste source exports into these staging files:

- `data/imports/fantraxhq-dynasty-2026.csv`
- `data/imports/fantraxhq-adp-2026.csv` if your Fantrax export is already saved there
- `data/imports/fantasypros-adp-2026.csv`
- `data/imports/rotowire-adp-2026.csv`

These files are intended to be easy paste targets in VS Code. Use comma-separated values when possible.

## Recommended Columns

### FantraxHQ dynasty rankings

Recommended headers:

- `player_name`
- `team`
- `dynasty_rank`
- `dynasty_tier`
- `notes`

Also accepted:

- `player`
- `name`
- `rank`
- `overall_rank`
- `overall`
- `tier`

### FantasyPros ADP

Recommended headers:

- `player_name`
- `team`
- `adp`
- `overall_rank`
- `format`
- `notes`

Also accepted:

- `player`
- `name`
- `avg_pick`
- `average_pick`
- `average_pick_overall`
- `overall_adp`
- `rank`

### RotoWire ADP

Recommended headers:

- `player_name`
- `team`
- `adp`
- `overall_rank`
- `format`
- `notes`

Also accepted:

- `player`
- `name`
- `avg_pick`
- `average_pick`
- `overall_adp`
- `rank`

## Optional ID Columns

If your pasted exports include identifiers, the import script will use them:

- `mlbam_id`
- `fg_id`

If those columns are not present, the script will try to match by player name and team using the player pool and optional Chadwick register.

## Build Order

1. Paste source exports into the staging files in `data/imports/`.
2. If available, load ID mappings into `data/chadwick-register-2026.csv`.
3. Run `scripts/import_rank_sources.py`.
4. Run `scripts/build_baseline_rankings.py`.
5. Run `scripts/build_draft_board_input.py`.

## Output Files

The import script normalizes pasted source rows into these canonical raw-source files:

- `data/dynasty-rankings-fantraxhq-2026.csv`
- `data/market-adp-fantasypros-2026.csv`
- `data/market-adp-rotowire-2026.csv`

Those files then feed the final compiled outputs:

- `data/dynasty-rankings-2026.csv`
- `data/market-adp-2026.csv`

## Practical Notes

- If a source file is empty, the downstream build will fall back to the internal baseline.
- The draft summary will flag fallback-only coverage in advisory items.
- Tab-delimited exports are accepted in addition to CSV.
- Player fields with embedded tags such as `(DET) NRI`, `(CIN) IL60`, or `(2B)` are normalized during import.
- Team aliases such as `ARI`/`AZ` and `OAK`/`ATH` are normalized during import and downstream matching.