# Minor League Source Notes

This file summarizes the MLB Stats API lower-level player feeds that can support the initial minor-league draft pool.

## Affiliated Minor-League Feeds

The following sport IDs are populated and useful:

- `11` = Triple-A
- `12` = Double-A
- `13` = High-A
- `14` = Single-A
- `16` = Rookie

## Feed Sizes

Observed player counts on March 24, 2026:

- Triple-A: 2088
- Double-A: 1744
- High-A: 1771
- Single-A: 2080
- Rookie: 3437

The umbrella feed `21` (`Minor League Baseball`) returned `0` players and should not be used.

## Combined Coverage

Across affiliated minor-league levels `11/12/13/14/16`, the union contained:

- 7813 unique player IDs

Unique-only players by level:

- Triple-A only: 1082
- Double-A only: 439
- High-A only: 478
- Single-A only: 738
- Rookie only: 2378

This means Rookie ball contributes the largest amount of unique inventory, but it is also the noisiest group for fantasy purposes.

## Overlap Pattern

Largest pairwise overlaps observed:

- Triple-A / Double-A: 709
- Double-A / High-A: 639
- High-A / Single-A: 636
- Single-A / Rookie: 718

Interpretation:

- adjacent levels overlap heavily, which is expected for promoted or reassigned players
- the feeds are not cleanly partitioned season rosters
- a merged pool must deduplicate by player ID

## Adjacent Non-Affiliated Feeds

These endpoints are populated but should be treated separately:

- `17` = Winter Leagues: 2016 players
- `22` = College Baseball: 4062 players
- `23` = Independent Leagues: 1004 players

Recommended usage:

- Winter Leagues: ignore for the initial minor-league draft pool
- College Baseball: ignore for league roster purposes until players are drafted by an MLB organization
- Independent Leagues: optional edge-case source only

## Recommendation For The Initial Minor-League Draft

Use this hierarchy:

1. MLB player feed `1`
2. Triple-A `11`
3. Double-A `12`
4. High-A `13`
5. Single-A `14`
6. Rookie `16`

Build one deduplicated player dimension table keyed by MLBAM ID.

## Practical Rule Set

For the startup draft pool:

- include affiliated players from `11/12/13/14/16`
- deduplicate by player ID
- prefer the highest affiliated level seen for each player when storing a single `current_level`
- exclude `17`, `22`, and `23` from the default startup minors pool

For the later first-year player draft:

- do not use `22` College Baseball directly
- only add players to the eligible pool after they have been drafted or signed by an MLB organization

## Current Best Metadata Stack

For dynasty startup and minors coverage, the strongest public identity stack is:

- MLB `1`
- Triple-A `11`
- Double-A `12`
- High-A `13`
- Single-A `14`
- Rookie `16`

This is the best public MLB Stats API path currently available for age, birth date, handedness, and primary position across both MLB and affiliated minor-league players.

## Gaps These Feeds Do Not Solve Alone

The MLB Stats API minor-league feeds are strong for identity and org assignment, but they do not fully solve dynasty startup needs by themselves.

Still needed:

- Chadwick Register for cross-source ID mapping
- Prospects Live or MLB Pipeline for prospect grade, FV, and ETA fields
- projection sources for fantasy category expectations
- transaction polling to keep current level and org assignment fresh

## Recommended Integrated Minors Stack

Use the following order when building a fuller dynasty minors layer:

1. MLB Stats API for canonical affiliated-player coverage and assignments
2. Chadwick Register for ID bridges across external sources
3. Prospects Live for structured prospect metadata
4. MLB Pipeline for public validation at the top of the board
5. projection source overlays for players with MLB or upper-minors forecast value

## Practical Outcome For This Workspace

With the expanded source stack, the minors build can move from a simple identity pool to a fantasy-usable table that includes:

- MLBAM ID
- external IDs for safe joins
- current affiliated level
- org assignment
- age
- position
- ETA
- FV or scouting-grade summary
- dynasty prospect rank
- projection baseline where available