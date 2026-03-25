# Draft Simulation Inputs

This document lists the inputs needed to simulate a believable startup draft for the 10-team dynasty roto league.

## Required Inputs

These are the minimum inputs needed to draft intelligently for each manager.

### 1. Current Player Rankings

Provide one or more ranked lists for dynasty startup value.

Best options:

- dynasty startup overall rankings
- dynasty startup hitter rankings
- dynasty startup pitcher rankings
- dynasty prospect rankings

If only one source is available, use a single overall dynasty startup ranking.

### 2. Recent MLB Statistics

Provide recent MLB performance data, ideally from the most recent full season plus current projections.

Most useful fields:

- hitters: PA, R, HR, RBI, SB, OBP, age, team, projected lineup slot, injury status, positional eligibility
- pitchers: IP, W, K, SV, ERA, WHIP, age, role, injury status

### 3. Forward-Looking Projections

Startup dynasty drafts should not be based only on last year's stats.

Best inputs:

- rest-of-season or full-season projections
- playing-time projections
- role projections for closers and rotations
- age and growth/decline assumptions

### 4. Prospect Lists

Because this is dynasty, prospect information is required.

Most useful prospect inputs:

- overall professional prospect rankings
- ETA to MLB
- expected fantasy category shape
- risk tier
- likely position and organizational context

Do not include college or high school amateurs in the startup or minor league roster pool before they have been drafted or signed by an MLB organization.

### 5. Positional Eligibility

Every player should include current eligible positions so the draft can account for roster construction and lineup flexibility.

### 6. Injury and Availability Status

For realism, include:

- current injury status
- expected return timeline
- surgery or major durability concerns
- suspension or role uncertainty

### 7. Draft Pool Scope

Decide whether the startup draft includes:

- all MLB players only
- MLB players plus prospects in one combined pool

For this league, the recommended input is a combined MLB-plus-prospect startup pool.

## Strongly Recommended Inputs

These are not strictly mandatory, but they materially improve the draft simulation.

### 1. ADP or Market Cost

Average draft position or market cost helps simulate when players are realistically selected.

Useful sources:

- FantasyPros overall ADP
- dynasty startup ADP
- redraft ADP with dynasty adjustments
- expert mock draft results

### 2. Tier Sheets

Tiered rankings are especially helpful because startup drafts often hinge on tier breaks rather than exact ordinal ranks.

### 3. Role-Specific Notes

Examples:

- confirmed closer versus committee risk
- locked rotation spot versus competition
- lineup leadoff candidate versus platoon bat

### 4. Risk Labels

Labels such as low, medium, and high risk improve manager-specific behavior during the draft.

### 5. Team Context

Optional, but helpful:

- MLB team offensive environment
- park effects
- expected playing-time competition

## Best Practical Package

If you want a realistic draft simulation without overcomplicating it, the best package is:

1. One dynasty startup ranking source
2. One prospect ranking source
3. One projection source
4. One ADP source
5. Position eligibility and injury status for all players

## Cheat Sheets Versus Raw Stats

If choosing between them:

- cheat sheets and rankings are better for overall startup draft order
- projections are better for category fit
- prospect lists are essential for dynasty realism
- raw historical stats are useful, but should be secondary to projections and dynasty rankings

## Inputs Needed From You

To run a credible draft simulation, the cleanest input package from you would be:

1. A dynasty startup cheat sheet or ranking list
2. A prospect ranking list
3. A current projection set for MLB players
4. Any preferred source you want me to trust more than others
5. Whether you want the simulation to be more realistic to public ADP or more tailored to these manager personalities

## Current Input Status

The following inputs are now available or partially available for this league's startup draft process:

### Available

- FantraxHQ 2026 dynasty rankings
- FantraxHQ 2026 prospect rankings
- MLB Pipeline Top 100 prospects
- RotoWire 2026 projections
- RotoWire position eligibility and games-by-position data
- RotoWire injury report
- RotoWire closer roles and bullpen context
- RotoWire depth charts and batting-order context
- RotoWire ADP
- FantasyPros overall ADP, supplied manually by the user as a top-450 market list

### Remaining Caveat

- The league still does not have a clean dynasty-only startup ADP source
- FantasyPros ADP and RotoWire ADP are strong market inputs, but both should be treated as general fantasy market signals rather than pure dynasty startup ADP
- For this draft, ADP should be blended with dynasty rankings, projections, prospect value, and manager personality profiles

## Output Once Inputs Are Ready

Once the input data is available, the draft simulation can produce:

- a full startup draft board
- 10 initial rosters
- manager-specific pick logic
- notes explaining why each team drafted the way it did