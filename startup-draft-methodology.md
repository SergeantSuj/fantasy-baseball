# Startup Draft Methodology

This file defines how to convert the player pool and source inputs into actual picks for the 10-team dynasty startup.

## Objective

Build believable 2026 startup rosters for a 10-team OBP roto dynasty league with:

- weekly lineups
- 25 MLB keepers
- 15 minor-league keepers
- one combined startup pool of MLB players and prospects

The simulation should behave like a real dynasty room, not a pure projection list.

## Core Draft Principles

### 1. Hitters Are The Foundation

In a 10-team format with only 9 pitcher slots and full dynasty carryover, elite bats are the safest first-round assets.

Default rule:

- prefer hitters in Round 1 unless an ace is clearly in the top overall tier

### 2. OBP Matters More Than Redraft Defaults

Because this league uses OBP instead of AVG:

- patient sluggers get a meaningful bump
- empty batting-average bats lose value
- category builds should avoid low-OBP sinkholes early

### 3. Age Matters, But Not Blindly

Dynasty age adjustment should be strongest in the first 10 rounds.

- elite players under 28 get a premium
- elite players 29-32 take only a mild discount
- aging stars remain viable if their category base is exceptional

### 4. Prospects Are Supplements, Not The Entire Plan

With 15 minor-league slots, every team can carry prospects. That does not mean every team should force them early.

Default rule:

- fill the major-league core first
- start aggressive prospect pushes once the active MLB foundation is stable

## Draft Flow

### Step 1. Build The Available Player Board

Start from:

- `data/draft-board-input-2026.csv`
- `data/startup-draft-settings-2026.json`

The consolidated draft input should be built from:

- `data/player-pool-2026.csv`
- `data/player-stats-2025.csv`
- `data/dynasty-rankings-2026.csv`
- `data/market-adp-2026.csv`
- `data/player-context-2026.csv`
- `data/player-injuries-2026.csv`
- `data/player-transactions-2026.csv`
- `data/skill-metrics-2026.csv`

If the current prep pass is focused on the MLB-core startup board first, `data/prospect-rankings-2026.csv` can be deferred and added in a later prospect-focused pass.

Every available player should have:

- name
- age
- eligible positions
- 2026 projection line
- dynasty value tier
- market timing estimate
- risk flag

Strongly preferred additional fields:

- prior-year MLB actual stat line for direct performance context
- player stage: MLB or prospect
- current level or current MLB transaction context
- ETA for prospects
- current injury status and expected return from a forward-looking injury tracker
- starter or reliever role, which can be inferred from games started when explicit role data is absent
- optional skill-validation flag from Statcast inputs

### Step 2. Create A Base Player Score

Each player receives a base score made from six components:

1. dynasty value
2. 2026 roto contribution
3. age curve
4. positional flexibility and scarcity
5. market ADP value
6. current injury and role security

Suggested baseline formula:

- dynasty value: 35%
- 2026 projection: 25%
- age curve: 15%
- position/flexibility: 10%
- market ADP: 10%
- risk/security: 5%

This is the neutral board before manager behavior is applied.

### Step 3. Apply Manager Personality Modifiers

Each manager file should modify the neutral board in a distinct way.

Examples:

- aggressive contender: boosts present-year production and ace pitching
- upside hunter: boosts prospects and post-hype breakouts
- conservative drafter: discounts injury risk and role uncertainty
- category optimizer: boosts scarce steals, saves, or OBP stabilizers depending on roster state

Manager behavior should move picks within a tier more often than it rewrites the entire board.

### Step 4. Apply Roster Construction Rules

At every pick, adjust for current roster state.

#### Hitting Rules

- prioritize one strong OBP anchor in the first two rounds
- avoid leaving the first 8 rounds without speed
- avoid building a corner-only roster too early
- favor multi-position bats in the middle rounds

#### Pitching Rules

- do not force two early aces unless the manager profile is specifically ace-heavy
- closers should usually be delayed relative to redraft norms
- avoid overloading ratio-risk starters early

#### Prospect Rules

- first prospect can arrive early if the MLB core is already stable
- do not allow more than 2 high-risk prospects in the first 10 rounds for conservative teams
- more aggressive profiles can begin prospect pushes earlier, but still need a competitive active lineup

### Step 5. Use Market Timing

When two players are similarly valued:

- take the player less likely to survive to the next turn
- if both are likely to survive, prefer the better dynasty asset

This is the main use of ADP in the simulation.

### Step 6. Enforce Tier-Based Decisions

The simulation should prefer tier logic over strict ordinal logic.

Rules:

- when a tier is about to break, managers can reach within reason
- when a tier is flat, manager personality and roster fit decide the pick
- once a category hole becomes obvious, managers can pivot even if the neutral board disagrees slightly

## Early-Round Defaults

### Rounds 1-3

- secure one franchise bat
- add either a second elite bat or a true ace
- do not chase saves
- do not overreact to single-position scarcity

### Rounds 4-8

- complete the core offense
- add first frontline starter if still needed
- stabilize speed or OBP gaps
- begin selecting the first premium prospect only if value is justified

### Rounds 9-15

- build depth
- add flexible hitters
- target second-tier starters and upside arms
- mix in prospects based on manager profile

### Rounds 16+

- attack role upside
- stash impact prospects
- speculate on closers and breakout pitchers
- fill categorical gaps with specialists where necessary

## Modeling Notes

- Do not use historical injury frequency as a baked-in negative modifier unless a source-backed injury-history layer is intentionally added later.
- Use the separate current injury tracker only for present availability and expected-return context.
- Use the transaction tracker for assignments, promotions, demotions, and latest current-level context.
- Do not model batting-order slot separately as a primary feature; public ADP already absorbs much of that expected production signal.

## Pitcher Discount Rule

Because this is dynasty and only 9 pitchers start each week, pitchers should usually receive a structural discount versus bats.

Default rule:

- only Skenes/Skubal-tier pitchers should seriously challenge for Round 1 in a neutral room
- most other starters should slide behind similarly valued bats

## Output Expectation

When the simulation is run correctly, each pick should be explainable in one sentence:

- player value
- manager style
- roster fit
- market timing

If any pick cannot be explained by those four elements, the board logic probably needs revision.