# Source Imports Quick Reference

Use this file first for routine ranking and ADP refresh work.

## Paste Targets

- `data/imports/fantraxhq-dynasty-2026.csv`
- `data/imports/fantasypros-adp-2026.csv`
- `data/imports/rotowire-adp-2026.csv`

## Standard Build Order

1. Paste raw source exports into `data/imports/`.
2. Refresh `data/chadwick-register-2026.csv` if new ID mapping help is available.
3. Run `scripts/import_rank_sources.py`.
4. Run `scripts/build_baseline_rankings.py`.
5. Run `scripts/build_draft_board_input.py` only if downstream draft-board-style inputs still need to be rebuilt.

## Canonical Outputs

- `data/dynasty-rankings-fantraxhq-2026.csv`
- `data/market-adp-fantasypros-2026.csv`
- `data/market-adp-rotowire-2026.csv`
- `data/dynasty-rankings-2026.csv`
- `data/market-adp-2026.csv`

## When To Open Longer Docs

- Open `source-imports.md` for accepted headers and normalization behavior.
- Open `projection-data-sources-2026.md` only if you need source-capability or provenance detail.
- Open `minor-league-source-notes.md` only if the task involves minor-league identity coverage or player-pool sourcing.

## Exclude By Default

Do not load startup draft planning docs for routine import maintenance unless the task is explicitly about historical startup-draft logic.