---
description: "Use when updating weekly roster decisions, lineup snapshots, weekly results, roster compliance, or manager roster files. Limits context to live roster-era docs and excludes startup draft planning notes."
applyTo:
  - "scripts/build_weekly_roster_decisions.py"
  - "scripts/build_weekly_lineup_snapshot.py"
  - "scripts/update_weekly_results.py"
  - "scripts/check_minor_league_eligibility.py"
  - "manager-rosters/*.csv"
  - "data/weekly-decisions/**"
  - "data/weekly-lineups/**"
  - "data/weekly-stats/**"
  - "data/season-results-2026.json"
  - "data/player-contributions-2026.csv"
  - "sunday-workflow.md"
  - "weekly-results-workflow.md"
---
# Weekly Roster Operations

- For live roster management and weekly accounting, prefer these markdown sources first: in-season-operations.md and manager-weekly-tendencies.md.
- Escalate to dynasty-league-rules.md, sunday-workflow.md, weekly-results-workflow.md, manager-profiles.md, or a single manager-profiles/*.md file only when the task needs exact rule language or a close manager-specific judgment call.
- Use manager-rosters/*.csv and the current files under data/weekly-* as the source of truth for roster state and weekly outputs.
- Do not pull in startup draft planning docs for normal weekly work: draft-simulation-inputs.md, draft-source-plan.md, startup-draft-board.md, startup-draft-methodology.md, and startup-draft-prep.md.
- Only consult draft-era docs if the user explicitly asks for historical draft logic or startup-draft methodology.