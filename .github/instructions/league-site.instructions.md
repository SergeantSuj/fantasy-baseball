---
description: "Use when updating the league site, docs pages, or site payload builders. Prefers live league-state docs and data outputs and excludes startup draft planning markdown from normal site work."
applyTo:
  - "docs/**"
  - "scripts/build_league_site.py"
---
# League Site Context

- For current site work, prefer in-season-operations.md first.
- Escalate to weekly-results-workflow.md, dynasty-league-rules.md, manager-weekly-tendencies.md, manager-profiles.md, or a single manager-profiles/*.md file only when the page or payload change needs that extra detail.
- Use current generated outputs such as data/season-results-2026.json, data/player-contributions-2026.csv, and docs/data/* as the primary source of live league state.
- Do not use startup draft planning docs for routine site updates: draft-simulation-inputs.md, draft-source-plan.md, startup-draft-board.md, startup-draft-methodology.md, and startup-draft-prep.md.
- Only consult draft-era markdown if a page or request is explicitly about archived startup-draft history or methodology.