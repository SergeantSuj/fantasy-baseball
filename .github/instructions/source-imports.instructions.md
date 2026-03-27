---
description: "Use when importing dynasty or ADP sources, rebuilding ranking inputs, or maintaining source-mapping files. Keeps context on current import docs and excludes obsolete startup draft planning markdown unless explicitly requested."
applyTo:
  - "scripts/import_rank_sources.py"
  - "scripts/build_baseline_rankings.py"
  - "scripts/build_draft_board_input.py"
  - "source-imports.md"
  - "projection-data-sources-2026.md"
  - "minor-league-source-notes.md"
  - "data/imports/**"
  - "data/chadwick-register-2026.csv"
  - "data/dynasty-rankings-2026.csv"
  - "data/dynasty-rankings-fantraxhq-2026.csv"
  - "data/market-adp-2026.csv"
  - "data/market-adp-fantasypros-2026.csv"
  - "data/market-adp-rotowire-2026.csv"
  - "data/prospect-rankings-2026.csv"
  - "data/player-context-2026.csv"
  - "data/skill-metrics-2026.csv"
---
# Source Imports And Ranking Inputs

- For ingest and ranking refresh work, prefer source-imports-quickref.md first.
- Escalate to source-imports.md, projection-data-sources-2026.md, and minor-league-source-notes.md only when the task needs accepted-header detail, source provenance, or minor-league sourcing context.
- Treat the files under data/imports/ and the compiled rankings and ADP CSVs as the current working context.
- Do not load startup draft planning docs for routine import work: draft-simulation-inputs.md, draft-source-plan.md, startup-draft-board.md, startup-draft-methodology.md, and startup-draft-prep.md.
- Only consult draft-era markdown if the user is asking about startup-draft outputs, historical ranking logic, or the provenance of older draft inputs.