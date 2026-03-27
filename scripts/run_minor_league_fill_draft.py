"""
Minor League Fill Draft — Snake format, reverse of startup order.

Each team selects prospects to fill empty minor league roster slots (max 15).
Teams with many young players on their roster prioritize deep-minors stashes;
others prioritize the highest-ranked available prospect.
"""

import csv
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ROSTERS_DIR = ROOT / "manager-rosters"

# ---------------------------------------------------------------------------
# 1.  Load minor league draft settings (draft order)
# ---------------------------------------------------------------------------
with open(DATA / "minor-league-draft-settings-2026.json") as f:
    draft_settings = json.load(f)

DRAFT_ORDER = draft_settings["draft_order"]
# ['Josh V', 'Greg', 'Shane', 'Josh M', 'Paul', 'Michael', 'Matt', 'Wendell', 'Rob', 'Chris']

MINOR_LEAGUE_LIMIT = 15

# ---------------------------------------------------------------------------
# 2.  Map manager names → roster file names
# ---------------------------------------------------------------------------
MANAGER_FILE_MAP = {
    "Chris": "chris-roster.csv",
    "Greg": "greg-roster.csv",
    "Josh M": "josh-m-roster.csv",
    "Josh V": "josh-v-roster.csv",
    "Matt": "matt-roster.csv",
    "Michael": "michael-roster.csv",
    "Paul": "paul-roster.csv",
    "Rob": "rob-roster.csv",
    "Shane": "shane-roster.csv",
    "Wendell": "wendell-roster.csv",
}

# ---------------------------------------------------------------------------
# 3.  Read rosters — count minor-league players & collect rostered names
# ---------------------------------------------------------------------------
team_minor_count: dict[str, int] = {}
team_young_player_count: dict[str, int] = {}  # players age ≤ 25 or current_level != MLB
rostered_names: set[str] = set()
roster_rows: dict[str, list[dict]] = {}  # manager -> list of rows

for manager, fname in MANAGER_FILE_MAP.items():
    path = ROSTERS_DIR / fname
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    roster_rows[manager] = rows

    minor_count = 0
    young_count = 0
    for row in rows:
        rostered_names.add(row["player_name"].strip())
        if row["roster_bucket"].strip() == "Minors":
            minor_count += 1
        # Count "young" players: those at non-MLB levels or with low dynasty rank
        level = row.get("current_level", "").strip()
        if level in ("AA", "High-A", "Single-A", "Rookie", "Prospect"):
            young_count += 1

    team_minor_count[manager] = minor_count
    team_young_player_count[manager] = young_count

# ---------------------------------------------------------------------------
# 4.  Calculate open slots per team
# ---------------------------------------------------------------------------
team_open_slots: dict[str, int] = {}
for manager in DRAFT_ORDER:
    team_open_slots[manager] = max(0, MINOR_LEAGUE_LIMIT - team_minor_count[manager])

print("=" * 70)
print("MINOR LEAGUE ROSTER STATUS (pre-draft)")
print("=" * 70)
for manager in DRAFT_ORDER:
    print(f"  {manager:12s}  MiLB: {team_minor_count[manager]:2d}/15  "
          f"Open: {team_open_slots[manager]}  "
          f"Young-level players: {team_young_player_count[manager]}")

total_picks = sum(team_open_slots.values())
print(f"\nTotal picks to make: {total_picks}")

if total_picks == 0:
    print("All minor league rosters are full. No draft needed.")
    exit(0)

# ---------------------------------------------------------------------------
# 5.  Load prospect rankings (priority ordering for picks)
# ---------------------------------------------------------------------------
prospects_by_rank: list[dict] = []
with open(DATA / "prospect-rankings-2026.csv", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        prospects_by_rank.append(row)

# Also load the full minor league draft pool for position/level metadata
pool_index: dict[str, dict] = {}  # player_name -> row from draft pool
with open(DATA / "minor-league-draft-pool-2026.csv", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        pool_index[row["player_name"].strip()] = row

# ---------------------------------------------------------------------------
# 6.  Build ranked available-player list
# ---------------------------------------------------------------------------
# Prospect rankings file has columns: source, mlbam_id, fg_id, player_name,
# org, prospect_rank, org_rank, current_level, eta, prospect_fv, prospect_risk, notes
# We want: (prospect_rank as int, player_name, metadata)

available: list[dict] = []
seen_names: set[str] = set()

for row in prospects_by_rank:
    name = row["player_name"].strip()
    if name in rostered_names:
        continue
    if name in seen_names:
        continue  # skip duplicates in rankings
    seen_names.add(name)

    rank_str = row.get("prospect_rank", "9999")
    try:
        rank = int(rank_str)
    except ValueError:
        rank = 9999

    level = row.get("current_level", "").strip()
    fv = row.get("prospect_fv", "").strip()

    # Determine if "deep minors" (Single-A, Rookie, or prospect)
    is_deep = level in ("Single-A", "Rookie", "Prospect", "")

    available.append({
        "player_name": name,
        "prospect_rank": rank,
        "org": row.get("org", "").strip(),
        "current_level": level,
        "eta": row.get("eta", "").strip(),
        "fv": fv,
        "is_deep": is_deep,
        "notes": row.get("notes", "").strip(),
    })

# Sort by prospect rank (lower = better)
available.sort(key=lambda x: x["prospect_rank"])

print(f"\nAvailable ranked prospects: {len(available)}")

# ---------------------------------------------------------------------------
# 7.  Define team draft strategy
# ---------------------------------------------------------------------------
# Teams with many young players (lots of minor-level guys already) should
# prioritize deep-minors upside.  Others prioritize pure best-available.
YOUNG_PLAYER_THRESHOLD = 10  # if a team has >= this many young-level players

def pick_for_team(manager: str, avail: list[dict]) -> dict | None:
    """Select the best available prospect for this team."""
    if not avail:
        return None

    young = team_young_player_count[manager]

    if young >= YOUNG_PLAYER_THRESHOLD:
        # Prefer deep-minors prospects (Single-A / Rookie / Prospect)
        # but still pick from top-ranked available overall
        deep_pool = [p for p in avail if p["is_deep"]]
        if deep_pool:
            return deep_pool[0]

    # Default: best available by prospect rank
    return avail[0]

# ---------------------------------------------------------------------------
# 8.  Build snake draft order and execute picks
# ---------------------------------------------------------------------------
# Figure out max rounds needed
max_slots = max(team_open_slots.values())
rounds_needed = max_slots  # one pick per round per team (if they still need)

picks: list[dict] = []  # all picks made
pick_number = 0

print("\n" + "=" * 70)
print("MINOR LEAGUE FILL DRAFT RESULTS")
print("=" * 70)

for rd in range(1, rounds_needed + 1):
    # Snake: odd rounds = normal order, even rounds = reverse
    if rd % 2 == 1:
        order = DRAFT_ORDER
    else:
        order = list(reversed(DRAFT_ORDER))

    for manager in order:
        if team_open_slots[manager] <= 0:
            continue  # team is full

        selection = pick_for_team(manager, available)
        if selection is None:
            print(f"  WARNING: No prospects available for {manager} in round {rd}")
            continue

        pick_number += 1
        available.remove(selection)

        team_open_slots[manager] -= 1
        team_minor_count[manager] += 1

        # Look up pool data for extra metadata
        pool_row = pool_index.get(selection["player_name"], {})
        position = pool_row.get("position", selection.get("notes", "").split("position ")[1].split(";")[0] if "position " in selection.get("notes", "") else "")
        mlbam_id = pool_row.get("mlbam_id", "")

        pick_record = {
            "pick_number": pick_number,
            "round": rd,
            "team": manager,
            "player_name": selection["player_name"],
            "prospect_rank": selection["prospect_rank"],
            "org": selection["org"],
            "current_level": selection["current_level"],
            "eta": selection["eta"],
            "fv": selection["fv"],
            "position": position,
            "is_deep_pick": selection["is_deep"],
        }
        picks.append(pick_record)

        deep_tag = " [deep-minors priority]" if selection["is_deep"] and team_young_player_count[manager] >= YOUNG_PLAYER_THRESHOLD else ""
        print(f"  Pick {pick_number:3d} | Rd {rd} | {manager:12s} | "
              f"{selection['player_name']:25s} | Rank {selection['prospect_rank']:3d} | "
              f"{selection['current_level']:8s} | FV {selection['fv']:3s} | "
              f"ETA {selection['eta']}{deep_tag}")

print(f"\nTotal picks made: {len(picks)}")

# ---------------------------------------------------------------------------
# 9.  Write draft results to CSV
# ---------------------------------------------------------------------------
output_path = DATA / "minor-league-fill-draft-results-2026.csv"
fieldnames = ["pick_number", "round", "team", "player_name", "prospect_rank",
              "org", "current_level", "eta", "fv", "position", "is_deep_pick"]

with open(output_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(picks)
print(f"\nDraft results written to: {output_path}")

# ---------------------------------------------------------------------------
# 10.  Append picks to each manager's roster CSV
# ---------------------------------------------------------------------------
# Find the max pick_number across all existing rosters to continue numbering
max_existing_pick = 0
for manager in MANAGER_FILE_MAP:
    for row in roster_rows[manager]:
        try:
            pn = int(row["pick_number"])
            if pn > max_existing_pick:
                max_existing_pick = pn
        except (ValueError, KeyError):
            pass

# Roster CSV columns:
# pick_number,round,pick_in_round,team,player_name,player_type,position_bucket,
# eligible_positions,roster_bucket,current_level,dynasty_rank,adp,
# injury_status,transaction_status,rationale
roster_fields = [
    "pick_number", "round", "pick_in_round", "team", "player_name",
    "player_type", "position_bucket", "eligible_positions", "roster_bucket",
    "current_level", "dynasty_rank", "adp", "injury_status",
    "transaction_status", "rationale"
]

picks_by_team: dict[str, list[dict]] = {m: [] for m in MANAGER_FILE_MAP}
for p in picks:
    picks_by_team[p["team"]].append(p)

for manager, fname in MANAGER_FILE_MAP.items():
    team_picks = picks_by_team[manager]
    if not team_picks:
        continue

    path = ROSTERS_DIR / fname
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for i, p in enumerate(team_picks, 1):
            max_existing_pick += 1
            # Determine position bucket and player type from pool data or notes
            pool_row = pool_index.get(p["player_name"], {})
            pos = pool_row.get("primary_position", pool_row.get("position", p.get("position", "")))
            player_type = "pitcher" if pos in ("P", "SP", "RP", "LHP", "RHP") else "hitter"
            pos_bucket = pos if pos else "UTIL"

            # Parse position from prospect notes if needed
            notes = ""
            for pr in prospects_by_rank:
                if pr["player_name"].strip() == p["player_name"]:
                    notes = pr.get("notes", "")
                    break

            if not pos and "position " in notes:
                try:
                    pos = notes.split("position ")[1].split(";")[0].strip()
                    pos_bucket = pos
                    if pos in ("RHP", "LHP"):
                        player_type = "pitcher"
                        pos_bucket = "SP"
                except IndexError:
                    pass

            rationale = (f"Minor league fill draft pick; prospect rank {p['prospect_rank']}; "
                        f"FV {p['fv']}; ETA {p['eta']}; "
                        f"{'deep-minors priority pick' if p['is_deep_pick'] and team_young_player_count[manager] >= YOUNG_PLAYER_THRESHOLD else 'best available prospect'}")

            row = [
                max_existing_pick,  # pick_number
                f"MiLB-{p['round']}",  # round indicator
                i,  # pick_in_round for this team
                manager,
                p["player_name"],
                player_type,
                pos_bucket,
                pos_bucket,  # eligible_positions
                "Minors",
                p["current_level"],
                p["prospect_rank"],  # using prospect rank as dynasty rank proxy
                "",  # adp
                "",  # injury_status
                "",  # transaction_status
                rationale,
            ]
            writer.writerow(row)

    print(f"  Updated roster: {path.name} (+{len(team_picks)} picks)")

# ---------------------------------------------------------------------------
# 11.  Final summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("POST-DRAFT MINOR LEAGUE ROSTER STATUS")
print("=" * 70)
for manager in DRAFT_ORDER:
    print(f"  {manager:12s}  MiLB: {team_minor_count[manager]:2d}/15  "
          f"Open: {team_open_slots[manager]}")
