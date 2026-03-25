# Draft Source Plan

This file defines the public-input stack for the 2026 startup draft simulation.

## Active Data Build

The current database build is:

- player metadata and age: MLB Stats API using MLB plus affiliated minor-league player feeds
- 2026 projections: Razzball Steamer hitter and pitcher tables
- 2025 MLB season stats: MLB Stats API season-stat endpoints
- generated player pool: `data/player-pool-2026.csv`

This is the cleanest public source stack that can be ingested reliably in this workspace without browser automation.

## Expanded Data Source Stack

The broader source stack for this workspace should be organized in four layers.

### 1. Core League Data APIs

- MLB Stats API: canonical player identity, affiliated minor-league coverage, rosters, transactions, standings, and game-level data
- Baseball Savant / Statcast: pitch-level and batted-ball quality inputs such as exit velocity, launch angle, xBA, xSLG, sprint speed, and pitch characteristics

### 2. Projection Systems

- FanGraphs projections: Steamer, ZiPS, ATC, and Depth Charts as the preferred projection layer when exports are stable
- Razzball Steamer: practical public fallback for current build automation
- PECOTA: premium-only reference source for projection quality, MLEs, and prospect aging context, but not part of the public-first pipeline

### 3. Identity And Historical Layers

- Chadwick Bureau Register: identity mapping across MLBAM, FanGraphs, Baseball Reference, Retrosheet, and related IDs
- Lahman Database: historical MLB stats, bios, teams, awards, and long-range historical comp context

### 4. Prospect Layers

- MLB Pipeline: Top 100, org rankings, and scouting grades
- Prospects Live API: prospect grades, FV, ETA, org rankings, and deeper minor-league coverage

## Supporting Inputs For Draft Logic

These are not all stored as structured tables yet, but they should influence the board and simulated picks:

- FantraxHQ dynasty rankings
- FantraxHQ prospect rankings
- MLB Pipeline Top 100 prospects
- FantasyPros overall ADP
- RotoWire ADP
- RotoWire injury report
- RotoWire closer roles and bullpen context
- Chadwick Bureau Register ID mappings
- Baseball Savant quality-of-contact and pitch-shape data
- Lahman historical MLB baselines
- Prospects Live prospect grades, FV, and ETA

## Source Roles

### 1. MLB Stats API

Use for:

- canonical player identity
- age
- birth date
- primary position
- handedness
- affiliated minor-league player coverage beyond the active MLB player feed
- organizational rosters
- player transactions, including promotions, demotions, IL moves, and assignments

Do not use for:

- projections
- fantasy rank

### 2. Baseball Savant / Statcast

Use for:

- quality-of-contact context
- pitch movement and pitch-quality metrics
- sprint-speed and defensive athleticism signals
- skill validation when projections and surface stats disagree

Do not use alone for:

- complete fantasy value
- playing-time forecasts
- prospect valuation

### 3. Projection Systems

Use for:

- 2026 hitter stat baselines
- 2026 pitcher stat baselines
- playing-time expectations
- system-to-system comparison when projections materially disagree

Priority order:

1. FanGraphs exports when available and stable
2. Razzball Steamer as the current public-first ingestible source
3. PECOTA as a premium reference only

Do not use alone for:

- dynasty startup order
- prospect valuation

### 4. Dynasty Rankings

Use for:

- long-term value anchor
- age and growth weighting
- balancing present production against future value

This should drive the early rounds more than redraft ADP does.

### 5. ADP Sources

Use for:

- realistic pick timing
- identifying when a manager can wait on a player
- keeping the simulation close to public market behavior

Do not let ADP override dynasty value in the first half of the startup draft.

### 6. Prospect Sources

Use for:

- prospect rank and tier
- FV or scouting-grade context
- ETA and role path
- separating near-term MLB help from longer-horizon minors stashes

Priority order:

1. Prospects Live for structured prospect metadata
2. MLB Pipeline for public validation and Top 100 anchoring
3. FantraxHQ prospect rankings for fantasy-facing dynasty context

### 7. Identity Mapping Sources

Use for:

- MLBAM to FanGraphs ID mapping
- reconciling projections, rankings, and prospect tables from different ecosystems
- preventing duplicate or misjoined player records

Primary source:

- Chadwick Bureau Register

### 8. Historical Reference Sources

Use for:

- long-range baseline comparisons
- aging-curve research
- historical normalization work for future model extensions

Primary source:

- Lahman Database

### 9. Context Sources

Use for:

- injury, role, and bullpen context as tiebreakers, especially for:

- closers
- uncertain fifth starters
- playing-time battles
- injured stars versus healthy second-tier options

Practical modeling rules:

- derive starter versus reliever from games started when explicit role data is absent
- do not use batting-order slot as a primary model feature for the initial draft build because market ADP already captures much of the production expectation
- track current injuries in a separate forward-looking layer rather than penalizing players for past injury history
- track transactions in a separate latest-event layer so current level and recent assignment changes can be refreshed automatically

## Recommended Weighting

The draft engine should not use one static weight across all rounds. Early rounds are about franchise anchors. Middle rounds are about category balance and value pockets. Late rounds are where prospect and role volatility matter most.

### Rounds 1-5

- dynasty rank/value: 40%
- 2026 projection value: 25%
- OBP/category fit: 10%
- age curve: 10%
- market ADP: 10%
- risk adjustment: 5%

### Rounds 6-15

- dynasty rank/value: 30%
- 2026 projection value: 30%
- category fit: 10%
- positional flexibility/scarcity: 10%
- market ADP: 10%
- injury/role risk: 10%

### Rounds 16-30

- 2026 projection value: 25%
- prospect upside: 20%
- dynasty rank/value: 20%
- market ADP: 15%
- role opportunity: 10%
- age curve: 10%

### Reserve And Minor-League Focus

- prospect value: 35%
- dynasty rank/value: 25%
- ETA and opportunity: 20%
- market ADP: 10%
- current projection baseline: 10%

### Optional Skill Validation Layer

When two players are close in projection and dynasty value, use Statcast skill indicators as a tie-breaker rather than as a primary ordering engine.

Examples:

- boost hitters with strong contact quality and plate-discipline support
- boost pitchers with bat-missing traits or movement traits that support ERA and WHIP stability
- avoid overreacting to a single expected-stat metric without role or playing-time backing

## Position Handling

For the current public build, position eligibility is derived from the Razzball projection tables:

- hitters: union of ESPN and Yahoo position tags
- pitchers: Razzball pitcher position field

This is sufficient for a startup simulation seed board. If Fantrax-specific eligibility becomes available later, it should replace this field before final roster construction.

## Known Gaps

- no clean dynasty-only startup ADP feed
- the current structured player build still needs a formal identity-mapping layer across projection and ranking ecosystems
- the current structured player build still needs a deeper prospect table with ETA, FV, and scouting-grade fields
- public position eligibility is platform-based rather than Fantrax-native
- Statcast, Chadwick, Lahman, and Prospects Live are now part of the recommended source stack, but are not yet ingested into `data/player-pool-2026.csv`

## Practical Rule

When the market signal and dynasty value disagree, use this tie-break order:

1. dynasty value
2. category fit for this roster build
3. age and long-term window
4. public ADP
5. current-season projection

That order should keep the simulation behaving like a dynasty startup instead of a redraft room.