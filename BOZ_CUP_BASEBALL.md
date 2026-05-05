# Boz Cup Baseball

A fully automated 10-team dynasty rotisserie fantasy baseball league. Every stage of league operations — from the startup draft through weekly lineup optimization, free agent acquisitions, injury list management, and stat ingestion — is driven by Python scripts that pull live data from the MLB Stats API and publish results to a GitHub Pages league site.

## League Format

- **Type:** Dynasty, 5×5 rotisserie (R, HR, RBI, SB, OBP / W, K, SV, ERA, WHIP)
- **Teams:** Chris, Greg, Josh M, Josh V, Matt, Michael, Paul, Rob, Shane, Wendell
- **Rosters:** 22 active (13 hitters + 9 pitchers), 8 bench, 5 IL, 15 minor league slots
- **Scoring:** Teams ranked 1st–10th in each category; 10 pts for 1st down to 1 pt for 10th. Season champion has the most total roto points.
- **Cadence:** Lineups lock weekly on Sunday. Monday morning ingestion posts the prior week's stats to standings.

## Project Structure

```
scripts/           Python automation pipeline
data/              Source imports, weekly decisions, lineup snapshots, stats
docs/              GitHub Pages league site (HTML/JS/CSS + JSON payload)
manager-rosters/   Per-manager roster CSVs
manager-profiles/  Scouting reports and tendencies for each manager
```

## Automation Pipeline

| Script | Purpose |
|--------|---------|
| `build_weekly_roster_decisions.py` | Sunday automation — refreshes MLB transaction statuses, auto-applies IL moves, runs waiver-order FA acquisitions informed by manager profiles, and builds the weekly lineup |
| `build_weekly_lineup_snapshot.py` | Creates the weekly lineup snapshot CSV used for stat tracking |
| `update_weekly_results.py` | Monday ingestion — pulls boxscores from the MLB Stats API, credits active-lineup players, and updates season totals |
| `build_league_site.py` | Rebuilds the league site JSON payload (standings, rosters, leaders, transactions) and writes it to `docs/data/` |
| `import_rank_sources.py` | Imports dynasty rankings and market ADP from external sources |
| `build_draft_board_input.py` | Merges rankings, ADP, and player context into the master draft board |
| `run_startup_draft.py` | Executes the automated startup draft |
| `run_minor_league_fill_draft.py` | Runs the minor league prospect fill draft |
| `build_player_pool.py` | Generates the master player pool from Chadwick Bureau and MLB data |
| `update_player_injuries.py` | Refreshes injury statuses from the MLB Stats API |
| `update_prospect_rankings_from_mlb_pipeline.py` | Ingests prospect rankings from MLB Pipeline |

## League Site

The `docs/` folder is published via GitHub Pages. Pages include:

- **League Hub** — standings, league leaders, team snapshots
- **Team Pages** — per-manager roster, contribution ledger, lineup details
- **MLB Team Usage** — which MLB clubs have the most fantasy-rostered players
- **Minor League Prospects** — rostered prospects grouped by MLB affiliate
- **Transactions** — filterable log of FA adds, drops, IL moves, and status updates

## Data Sources

- **MLB Stats API** — live rosters, boxscores, transactions, prospect rankings
- **FantasyPros / RotoWire** — market ADP consensus
- **FantraxHQ** — dynasty rankings
- **Chadwick Bureau** — player ID register
