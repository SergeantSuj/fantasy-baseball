## 2026 MLB Projection Source Research

### Recommended metadata source

#### MLB Stats API

- Players: https://statsapi.mlb.com/api/v1/sports/1/players?season=2026
- Teams: https://statsapi.mlb.com/api/v1/teams?sportId=1&season=2026
- People endpoint docs reference: https://github.com/toddrob99/MLB-StatsAPI/wiki/Endpoints

What it provides:

- `id`
- `fullName`
- `currentTeam.id`
- `primaryPosition.abbreviation`
- `birthDate`
- `currentAge`
- `active`
- `batSide`
- `pitchHand`
- `mlbDebutDate`

Gap:

- No projection data.

Additional high-value endpoints for this workspace:

- Player career stats: `https://statsapi.mlb.com/api/v1/people/{playerId}/stats?stats=career&group=hitting`
- Team rosters: `https://statsapi.mlb.com/api/v1/teams/{teamId}/roster`
- Transactions: `https://statsapi.mlb.com/api/v1/transactions`

Practical role:

- career stats support historical baseline checks
- rosters support current org assignment and affiliate context
- transactions support promotions, demotions, IL, DFA, trades, and minor-league assignments

### Skill-data source

#### Baseball Savant / Statcast

- Search / CSV layer: `https://baseballsavant.mlb.com/statcast_search/csv`

What it provides:

- exit velocity
- launch angle
- xBA
- xSLG
- pitch spin
- pitch movement
- sprint speed
- OAA and related defensive signals

Assessment:

- best public skill-validation layer for explaining why projections may be sustainable or fragile
- should sit behind the core projection table rather than replace it
- useful for tiebreaks, breakout flags, and risk labels

### Best projection candidates

#### FanGraphs projections

- Hitter ATC: https://www.fangraphs.com/projections?pos=all&stats=bat&type=atc
- Pitcher ATC: https://www.fangraphs.com/projections?pos=all&stats=pit&type=atc
- Hitter Steamer: https://www.fangraphs.com/projections?pos=all&stats=bat&type=steamer
- Pitcher Steamer: https://www.fangraphs.com/projections?pos=all&stats=pit&type=steamer

Observed / likely:

- Publicly indexed for 2026.
- Search snippets indicate a built-in export feature and community reports refer to a JSON export behind the page.
- Pages exist for multiple systems (`atc`, `steamer`, `steameru`, `steamer600`, `zips`, `oopsy`, etc.).

Likely fields:

- Player name
- Team
- Projection stats for hitters or pitchers
- Projection-system-specific derived stats

Likely gaps:

- Age is not the primary use case of the table and should be enriched from MLB Stats API.
- Eligible fantasy positions may not be cleanly represented for your league rules.
- In this environment, direct page fetching was unreliable because requests were redirected through ad/tracking layers.
- Exact export endpoint was not resolved from public HTML in this session.

Assessment:

- Best projection quality and breadth.
- Operationally higher risk for unattended ingestion unless you first lock down the export call or confirm the raw table HTML is stable.

#### Razzball public projection pages

- Hitters: https://razzball.com/steamer-hitter-projections/
- Pitchers: https://razzball.com/steamer-pitcher-projections/
- Grey top projections: https://razzball.com/projections-grey/
- Rankings hub: https://razzball.com/2026-fantasy-baseball-rankings/

Observed / likely:

- Publicly indexed for 2026.
- Search snippets describe these as free projections pages.
- Razzball also exposes some explicit CSV-oriented DFS pages, which suggests they are generally export-friendly.

Likely fields:

- Player name
- Team
- Hitter or pitcher projection categories
- Some split-aware or playing-time-adjusted stats

Likely gaps:

- Age likely missing.
- Eligible positions may need normalization or enrichment.
- Separate hitter and pitcher pages must be merged.
- Table markup still needs validation with a real scraper.

Assessment:

- Strong fallback or even primary source if FanGraphs export is unstable.
- Public and fantasy-oriented, but less canonical for IDs and roster metadata.

#### RotoWire projections

- Main projections: https://www.rotowire.com/baseball/projections.php
- ATC-flavored page: https://www.rotowire.com/baseball/projections-atc.php

Observed / likely:

- Publicly indexed for 2026.
- Search results describe the page as open and mention downloadable projections.
- Prior shell context in this workspace already found CSV-related strings in the HTML of the main projections page.

Likely fields:

- Player name
- Team
- Position
- Fantasy points and/or projected stat categories

Likely gaps:

- Age may not be present in the projections table.
- Exact public CSV URL still needs to be captured.
- Projection methodology is less transparent than FanGraphs + ATC/Steamer naming.

Assessment:

- Promising because the page appears export-aware.
- Good secondary candidate if you want a single-source fantasy-focused table.

### Lower-priority or gated candidates

#### CBS Sports

- Example utility page: https://www.cbssports.com/fantasy/baseball/stats/U/2026/season/projections/
- Stats home: https://www.cbssports.com/fantasy/baseball/stats/

Observed / likely:

- Search results confirm 2026 projected stats pages exist and are publicly indexed.
- Pages appear position-specific and static enough to scrape.

Likely fields:

- Player
- Team
- Position bucket
- Points and projected stat categories

Likely gaps:

- You may need to scrape many position URLs to infer multi-position eligibility.
- Age is not likely included.
- Site redirects and ad/tracking behavior may complicate raw fetches.

Assessment:

- Usable as a backup or cross-check.
- Not my first choice for a clean canonical database pipeline.

#### ESPN

- Projections: https://fantasy.espn.com/baseball/players/projections

Observed / likely:

- Publicly indexed for 2026.
- Search snippets show player-level projected stats and fantasy-facing rankings.

Likely gaps:

- Usually more app/session-oriented.
- Export path is not obvious.
- Scraping stability is weaker than a true API or static table source.

Assessment:

- Better as a manual validation source than as your ingestion backbone.

#### Baseball Prospectus / PECOTA

- PECOTA hub: https://www.baseballprospectus.com/pecota-projections/
- Standings: https://www.baseballprospectus.com/standings/

Observed / likely:

- 2026 PECOTA pages exist.
- Player-level spreadsheet download is explicitly premium-only.

Likely gaps:

- Not publicly accessible enough for an automated free pipeline.

Assessment:

- Exclude from the free/public build plan.

### Identity and historical reference layers

#### Chadwick Bureau Register

- GitHub: https://github.com/chadwickbureau/register

What it provides:

- ID mapping across MLBAM, FanGraphs, Baseball Reference, Retrosheet, and related systems
- coverage beyond MLB-only player pools

Assessment:

- the best identity-resolution layer to join projections, rankings, and prospect feeds safely
- should be part of the next structured ingest step if FanGraphs or Prospects Live are added

#### Lahman Database

- Archive: https://www.seanlahman.com/baseball-archive/statistics/

What it provides:

- historical MLB player and team data
- award and bio context
- long-range baseline and aging-curve support

Assessment:

- not needed for the first playable draft pool
- very useful for future model tuning and historical comp work

### Prospect data layers

#### MLB Pipeline

- Prospects hub: https://www.mlb.com/prospects

What it provides:

- Top 100 anchors
- org-level prospect rankings
- public scouting grades

Assessment:

- strong public validation layer for the top of the prospect pool
- less complete than a deeper structured prospect API

#### Prospects Live API

- API: https://api.prospectslive.com

What it provides:

- prospect grades
- future value
- ETA
- org rankings
- deeper minor-league player coverage

Assessment:

- best candidate to fill the current structured prospect-data gap
- especially useful for a dynasty startup with 15 minor-league slots per team

### Best practical plan for this workspace

1. Use MLB Stats API as the canonical player dimension table.
2. Choose one projection source as primary.
3. Normalize names and team abbreviations to MLB IDs.
4. Store raw source pulls and a cleaned merged table in the repo.

Recommended primary plan:

1. Build `players_raw_mlb_2026.json` from `sports/1/players?season=2026`.
2. Build `teams_raw_mlb_2026.json` from `teams?sportId=1&season=2026`.
3. Build affiliated minor-league player pulls for `11`, `12`, `13`, `14`, and `16`.
4. Add Chadwick Register as the ID bridge before joining FanGraphs or deeper prospect feeds.
5. Use FanGraphs ATC as primary if you can confirm the raw export call.
6. Use Razzball hitter + pitcher pages as the fallback public projection source.
7. Add Prospects Live or MLB Pipeline prospect metadata for ETA, FV, and scouting context.
8. Use Statcast metrics as a secondary skill-validation layer.
9. Derive your league-specific eligible positions from your rules plus primary position, instead of trusting any one public fantasy site.

Recommended columns for the first database version:

- `mlbam_id`
- `player_name`
- `team_mlbam`
- `team_abbrev`
- `primary_position`
- `eligible_positions_raw`
- `eligible_positions_final`
- `birth_date`
- `age`
- `projection_source`
- `projection_system`
- Hitter columns such as `g`, `pa`, `ab`, `r`, `hr`, `rbi`, `sb`, `avg`, `obp`, `slg`
- Pitcher columns such as `g`, `gs`, `ip`, `w`, `sv`, `hld`, `so`, `era`, `whip`
- `source_url`
- `ingested_at`
- `fg_id`
- `bbref_id`
- `retrosheet_id`
- `current_level`
- `eta`
- `prospect_fv`
- `prospect_grade_summary`
- `injury_status`
- `transaction_status`

Recommendation:

- Best practical higher-ceiling stack is MLB Stats API + Chadwick + FanGraphs ATC + Prospects Live + Statcast.
- Best practical public-first stack today is MLB Stats API + affiliated minors + Razzball hitter/pitcher pages + MLB Pipeline, with Chadwick added as soon as cross-source joins expand.