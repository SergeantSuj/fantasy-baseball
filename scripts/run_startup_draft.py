from __future__ import annotations

import csv
import json
import math
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = WORKSPACE_ROOT / "data"

BOARD_PATH = DATA_DIR / "draft-board-input-2026.csv"
SETTINGS_PATH = DATA_DIR / "startup-draft-settings-2026.json"
OUTPUT_RESULTS_PATH = WORKSPACE_ROOT / "draft-results.csv"
OUTPUT_ROSTERS_DIR = WORKSPACE_ROOT / "manager-rosters"

TOTAL_ROUNDS = 30
TOTAL_PICKS = 300
TARGET_MLB_SLOTS = 30
TARGET_HITTERS = 18
TARGET_PITCHERS = 12
ACTIVE_PITCHER_SLOTS = 9

ACTIVE_HITTER_SLOTS = {
    "C": 1,
    "1B": 1,
    "2B": 1,
    "3B": 1,
    "SS": 1,
    "CI": 1,
    "MI": 1,
    "OF": 5,
    "UTIL": 1,
}

HITTER_SLOT_PRIORITY = [
    ("C", {"C"}, 1.2),
    ("SS", {"SS"}, 1.0),
    ("2B", {"2B"}, 0.95),
    ("3B", {"3B"}, 0.9),
    ("1B", {"1B"}, 0.85),
    ("OF", {"OF", "LF", "CF", "RF"}, 0.8),
    ("CI", {"1B", "3B"}, 0.75),
    ("MI", {"2B", "SS"}, 0.75),
    ("UTIL", None, 0.45),
]

POSITION_FAMILIES = {
    "C": {"C"},
    "1B": {"1B"},
    "2B": {"2B"},
    "3B": {"3B"},
    "SS": {"SS"},
    "OF": {"OF", "LF", "CF", "RF"},
}

MINOR_LEVELS = {"AAA", "AA", "HIGH-A", "SINGLE-A", "ROOKIE", "PROSPECT"}


@dataclass
class ManagerConfig:
    dynasty_weight: float
    adp_weight: float
    projection_weight: float
    actual_weight: float
    youth_weight: float
    veteran_weight: float
    prospect_bias: float
    role_weight: float
    risk_aversion: float
    closer_bias: float
    flexibility_bias: float
    category_bias: float
    pitcher_aggression: float
    scarcity_bias: float
    scarcity_positions: tuple[str, ...]
    early_minor_round: int
    focus_phrase: str


@dataclass
class TeamState:
    name: str
    picks: list[dict[str, str]] = field(default_factory=list)
    mlb_count: int = 0
    minor_count: int = 0
    hitter_count: int = 0
    pitcher_count: int = 0
    active_slots_remaining: dict[str, int] = field(default_factory=lambda: dict(ACTIVE_HITTER_SLOTS))
    hitter_proj_sb: float = 0.0
    hitter_proj_obp_pa: float = 0.0
    hitter_proj_pa: float = 0.0
    pitcher_proj_sv: float = 0.0


MANAGER_CONFIGS = {
    "Chris": ManagerConfig(1.10, 1.00, 0.95, 0.70, 0.10, 0.00, -0.10, 0.15, 0.50, -0.20, 0.35, 0.25, 0.10, 0.00, (), 10, "consensus support across dynasty rank, ADP, and roster balance"),
    "Greg": ManagerConfig(0.95, 1.00, 1.20, 1.00, -0.20, 0.45, -0.70, 0.45, 0.90, -0.15, 0.10, 0.10, 0.35, 0.00, (), 15, "present-year reliability and secure MLB roles"),
    "Josh M": ManagerConfig(1.10, 1.05, 0.95, 0.80, 0.20, 0.05, 0.15, 0.15, 0.55, -0.10, 0.35, 0.15, 0.15, 0.42, ("C", "3B", "SS"), 9, "portfolio balance and optional roster construction"),
    "Josh V": ManagerConfig(1.20, 0.75, 0.85, 0.55, 0.55, -0.15, 0.95, 0.00, 0.20, -0.10, 0.10, 0.20, 0.20, 0.18, ("3B", "SS"), 5, "long-term ceiling and upside over market conservatism"),
    "Matt": ManagerConfig(0.90, 1.10, 1.05, 0.70, 0.05, 0.00, -0.50, 0.60, 0.55, 0.55, 0.55, 0.40, 0.25, 0.32, ("C", "3B", "SS"), 12, "weekly usability, flexibility, and role-driven edges"),
    "Michael": ManagerConfig(1.20, 0.70, 0.85, 0.55, 0.60, -0.20, 0.90, 0.00, 0.35, -0.15, 0.10, 0.10, 0.10, 0.10, ("3B",), 5, "age-adjusted growth, minors value, and long-horizon assets"),
    "Paul": ManagerConfig(0.95, 1.00, 1.15, 0.85, 0.00, 0.00, -0.20, 0.30, 0.45, 0.45, 0.15, 0.70, 0.20, 0.22, ("C", "SS"), 11, "category leverage in OBP, speed, saves, and point swings"),
    "Rob": ManagerConfig(1.00, 0.95, 1.05, 0.85, 0.05, 0.00, -0.25, 0.25, 1.10, -0.25, 0.10, 0.25, 0.10, 0.00, (), 11, "ratio protection and downside control in OBP, ERA, and WHIP"),
    "Shane": ManagerConfig(0.95, 1.05, 1.10, 0.80, 0.10, 0.10, -0.05, 0.50, 0.60, 0.30, 0.25, 0.35, 0.20, 0.12, ("C",), 10, "clear jobs, volume paths, and role-change usability"),
    "Wendell": ManagerConfig(0.90, 1.15, 0.95, 1.00, -0.15, 0.40, -0.85, 0.20, 0.70, -0.20, 0.10, 0.05, 0.10, 0.00, (), 16, "track record, market comfort, and familiar MLB certainty"),
}


def clean_value(value: str | None) -> str:
    return (value or "").strip()


def parse_float(value: str | None) -> float | None:
    text = clean_value(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_int(value: str | None) -> int | None:
    number = parse_float(value)
    if number is None:
        return None
    return int(number)


def merge_notes(existing_note: str, new_note: str) -> str:
    existing = clean_value(existing_note)
    new = clean_value(new_note)
    if not existing:
        return new
    if not new or new in existing:
        return existing
    return f"{existing}; {new}"


def normalize_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().replace(".", " ").replace("-", " ")
    normalized = " ".join(normalized.split())
    return normalized


def slugify(name: str) -> str:
    return normalize_name(name).replace(" ", "-")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def age_bonus(age: int | None, peak_start: int, peak_end: int, decline_rate: float, youth_penalty_rate: float) -> float:
    if age is None:
        return 0.0
    if peak_start <= age <= peak_end:
        return 0.0
    if age < peak_start:
        return -(peak_start - age) * youth_penalty_rate
    return -(age - peak_end) * decline_rate


def hitter_projection_score(row: dict[str, str]) -> float:
    hr = parse_float(row.get("proj_hr")) or 0.0
    runs = parse_float(row.get("proj_r")) or 0.0
    rbi = parse_float(row.get("proj_rbi")) or 0.0
    steals = parse_float(row.get("proj_sb")) or 0.0
    obp = parse_float(row.get("proj_obp")) or 0.300
    plate_appearances = parse_float(row.get("proj_pa")) or 0.0
    age = parse_int(row.get("age"))
    eligible_positions = (row.get("eligible_positions") or "").upper().split("/")

    score = 0.0
    score += runs * 1.0
    score += hr * 3.8
    score += rbi * 1.2
    score += steals * 4.2
    score += max(obp - 0.300, 0.0) * 360.0
    score += plate_appearances * 0.06
    score += age_bonus(age, 24, 28, 3.0, 0.4)
    if "C" in eligible_positions:
        score += 8.0
    if "SS" in eligible_positions:
        score += 4.0
    if "2B" in eligible_positions:
        score += 2.0
    if len([position for position in eligible_positions if position]) >= 2:
        score += 2.5
    return score


def pitcher_projection_score(row: dict[str, str]) -> float:
    innings = parse_float(row.get("proj_ip")) or 0.0
    wins = parse_float(row.get("proj_w")) or 0.0
    saves = parse_float(row.get("proj_sv")) or 0.0
    strikeouts = parse_float(row.get("proj_k")) or 0.0
    era = parse_float(row.get("proj_era")) or 4.50
    whip = parse_float(row.get("proj_whip")) or 1.35
    starts = parse_float(row.get("proj_gs")) or 0.0
    age = parse_int(row.get("age"))

    score = 0.0
    score += wins * 4.0
    score += strikeouts * 0.85
    score += saves * 5.0
    score += innings * 0.18
    score += max(0.0, 4.20 - era) * 30.0
    score += max(0.0, 1.30 - whip) * 120.0
    score += starts * 1.5
    score += age_bonus(age, 25, 29, 4.0, 0.2)
    score -= 22.0
    return score


def hitter_actual_score(row: dict[str, str]) -> float:
    hr = parse_float(row.get("actual_2025_hr")) or 0.0
    runs = parse_float(row.get("actual_2025_r")) or 0.0
    rbi = parse_float(row.get("actual_2025_rbi")) or 0.0
    steals = parse_float(row.get("actual_2025_sb")) or 0.0
    obp = parse_float(row.get("actual_2025_obp")) or 0.300
    plate_appearances = parse_float(row.get("actual_2025_pa")) or 0.0

    score = 0.0
    score += runs * 0.9
    score += hr * 3.6
    score += rbi * 1.1
    score += steals * 3.8
    score += max(obp - 0.300, 0.0) * 320.0
    score += plate_appearances * 0.05
    return score


def pitcher_actual_score(row: dict[str, str]) -> float:
    innings = parse_float(row.get("actual_2025_ip")) or 0.0
    wins = parse_float(row.get("actual_2025_w")) or 0.0
    saves = parse_float(row.get("actual_2025_sv")) or 0.0
    strikeouts = parse_float(row.get("actual_2025_k")) or 0.0
    era = parse_float(row.get("actual_2025_era")) or 4.50
    whip = parse_float(row.get("actual_2025_whip")) or 1.35
    starts = parse_float(row.get("actual_2025_gs")) or 0.0

    score = 0.0
    score += wins * 3.5
    score += strikeouts * 0.80
    score += saves * 4.5
    score += innings * 0.15
    score += max(0.0, 4.20 - era) * 28.0
    score += max(0.0, 1.30 - whip) * 115.0
    score += starts * 1.2
    score -= 18.0
    return score


def determine_position_bucket(row: dict[str, str]) -> str:
    player_type = clean_value(row.get("player_type"))
    if player_type in {"pitcher", "two-way"}:
        role = clean_value(row.get("pitcher_role_estimate"))
        if player_type == "two-way":
            return "TWP"
        if role == "reliever":
            return "RP"
        return "SP"

    positions = (row.get("eligible_positions") or row.get("primary_position") or "").upper().split("/")
    for preferred in ["C", "SS", "2B", "3B", "1B", "OF"]:
        if preferred in positions:
            return preferred
    return clean_value(row.get("primary_position")) or "UTIL"


def eligible_positions(row: dict[str, str]) -> list[str]:
    return [position for position in (row.get("eligible_positions") or row.get("primary_position") or "").upper().split("/") if position]


def determine_minor_eligibility(row: dict[str, str]) -> bool:
    current_level = clean_value(row.get("current_level")).upper()
    if current_level in MINOR_LEVELS:
        return True

    player_stage = clean_value(row.get("player_stage")).upper()
    if player_stage == "PROSPECT":
        return True

    actual_ab = parse_float(row.get("actual_2025_ab")) or 0.0
    actual_ip = parse_float(row.get("actual_2025_ip")) or 0.0
    age = parse_int(row.get("age")) or 99
    dynasty_rank = parse_int(row.get("dynasty_rank")) or 9999
    if age <= 24 and actual_ab < 130 and actual_ip < 50 and dynasty_rank <= 500:
        return True
    return False


def normalize_scores(rows: list[dict[str, str]], key: str) -> None:
    values = [parse_float(row.get(key)) or 0.0 for row in rows]
    low = min(values)
    high = max(values)
    for row in rows:
        value = parse_float(row.get(key)) or 0.0
        if high == low:
            row[f"{key}_norm"] = "0.5"
        else:
            row[f"{key}_norm"] = f"{(value - low) / (high - low):.6f}"


def enrich_board_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    dynasty_ranks = [parse_int(row.get("dynasty_rank")) or 9999 for row in rows]
    adp_ranks = [parse_float(row.get("adp")) or 9999.0 for row in rows]
    max_dynasty = max(dynasty_ranks)
    max_adp = max(adp_ranks)

    for row in rows:
        player_type = clean_value(row.get("player_type"))
        if player_type == "pitcher":
            proj_score = pitcher_projection_score(row)
            actual_score = pitcher_actual_score(row)
        elif player_type == "two-way":
            proj_score = hitter_projection_score(row) + pitcher_projection_score(row)
            actual_score = hitter_actual_score(row) + pitcher_actual_score(row)
        else:
            proj_score = hitter_projection_score(row)
            actual_score = hitter_actual_score(row)

        dynasty_rank = parse_int(row.get("dynasty_rank")) or max_dynasty
        adp = parse_float(row.get("adp")) or max_adp
        age = parse_int(row.get("age")) or 30
        injury_status = clean_value(row.get("injury_status"))
        sb = parse_float(row.get("proj_sb")) or 0.0
        obp = parse_float(row.get("proj_obp")) or 0.300
        sv = parse_float(row.get("proj_sv")) or 0.0
        era = parse_float(row.get("proj_era")) or 4.50
        whip = parse_float(row.get("proj_whip")) or 1.35
        positions = eligible_positions(row)

        row["position_bucket"] = determine_position_bucket(row)
        row["minor_eligible"] = "yes" if determine_minor_eligibility(row) else "no"
        row["is_prospect_like"] = "yes" if row["minor_eligible"] == "yes" and (clean_value(row.get("current_level")).upper() in MINOR_LEVELS or age <= 24) else "no"
        row["is_closer"] = "yes" if row["position_bucket"] == "RP" and sv >= 8 else "no"
        row["proj_score"] = f"{proj_score:.6f}"
        row["actual_score"] = f"{actual_score:.6f}"
        row["dynasty_score"] = f"{1.0 - ((dynasty_rank - 1) / max(max_dynasty - 1, 1)):.6f}"
        row["adp_score"] = f"{1.0 - ((adp - 1.0) / max(max_adp - 1.0, 1.0)):.6f}"
        row["youth_score"] = f"{max(min((31 - age) / 12.0, 1.0), -1.0):.6f}"
        row["veteran_score"] = f"{max(min((age - 27) / 10.0, 1.0), 0.0):.6f}"
        row["risk_score"] = f"{-1.0 if injury_status else 0.0:.6f}"
        row["speed_score"] = f"{min(sb / 25.0, 1.0):.6f}"
        row["obp_score"] = f"{max(min((obp - 0.300) / 0.120, 1.0), -1.0):.6f}"
        row["saves_score"] = f"{min(sv / 35.0, 1.0):.6f}"
        row["ratio_score"] = f"{(max(0.0, 4.20 - era) * 0.4) + (max(0.0, 1.30 - whip) * 1.2):.6f}"
        row["flex_score"] = f"{0.4 if len(positions) >= 2 else 0.0:.6f}"

    normalize_scores(rows, "proj_score")
    normalize_scores(rows, "actual_score")
    normalize_scores(rows, "ratio_score")
    return rows


def generate_snake_order(teams: list[str], rounds: int) -> list[str]:
    order: list[str] = []
    for round_number in range(1, rounds + 1):
        sequence = teams if round_number % 2 == 1 else list(reversed(teams))
        order.extend(sequence)
    return order


def remaining_minor_room(team: TeamState) -> int:
    return 0


def remaining_mlb_room(team: TeamState) -> int:
    return TARGET_MLB_SLOTS - team.mlb_count


def remaining_active_hitter_slots(team: TeamState) -> int:
    return sum(team.active_slots_remaining.values())


def remaining_active_pitcher_slots(team: TeamState) -> int:
    return max(0, ACTIVE_PITCHER_SLOTS - team.pitcher_count)


def should_include_in_mlb_draft(row: dict[str, str]) -> bool:
    if clean_value(row.get("minor_eligible")) == "yes":
        return False
    if clean_value(row.get("is_prospect_like")) == "yes":
        return False
    return True


def best_open_hitter_slot(team: TeamState, row: dict[str, str]) -> tuple[str | None, float]:
    positions = set(eligible_positions(row))
    for slot_name, slot_positions, bonus in HITTER_SLOT_PRIORITY:
        if team.active_slots_remaining.get(slot_name, 0) <= 0:
            continue
        if slot_positions is None:
            return slot_name, bonus
        if positions.intersection(slot_positions):
            return slot_name, bonus
    return None, 0.0


def player_has_position(row: dict[str, str], position: str) -> bool:
    positions = set(eligible_positions(row))
    return bool(positions.intersection(POSITION_FAMILIES.get(position, {position})))


def team_position_inventory(team: TeamState, position: str) -> int:
    return sum(
        1
        for pick in team.picks
        if determine_position_bucket(pick) not in {"SP", "RP", "TWP"} and player_has_position(pick, position)
    )


def scarcity_target_count(position: str) -> int:
    if position == "C":
        return 2
    if position in {"1B", "2B", "3B", "SS"}:
        return 3
    return 2


def position_scarcity_bonus(team: TeamState, config: ManagerConfig, row: dict[str, str], round_number: int, picks_remaining: int) -> tuple[float, str]:
    if config.scarcity_bias <= 0.0:
        return 0.0, ""
    if round_number < 4 or round_number > 18:
        return 0.0, ""
    if determine_position_bucket(row) in {"SP", "RP", "TWP"}:
        return 0.0, ""
    if remaining_active_hitter_slots(team) >= picks_remaining:
        return 0.0, ""

    best_bonus = 0.0
    best_note = ""
    for position in config.scarcity_positions:
        if not player_has_position(row, position):
            continue

        inventory = team_position_inventory(team, position)
        target_count = scarcity_target_count(position)
        if inventory >= target_count:
            best_bonus = max(best_bonus, -0.35 * config.scarcity_bias)
            continue

        slot_open = team.active_slots_remaining.get(position, 0) > 0
        if inventory == 0 and slot_open:
            continue

        bonus = config.scarcity_bias * (0.45 + (0.18 * inventory))
        if not slot_open:
            bonus += config.scarcity_bias * 0.20
        if round_number <= 10:
            bonus += config.scarcity_bias * 0.15

        if bonus > best_bonus:
            best_bonus = bonus
            best_note = f"position scarcity play at {position} pushed the pick up"

    return best_bonus, best_note


def assign_hitter_slot(team: TeamState, row: dict[str, str]) -> float:
    _, bonus = best_open_hitter_slot(team, row)
    return bonus


def adp_timing_bonus(row: dict[str, str], overall_pick: int, round_number: int) -> float:
    adp = parse_float(row.get("adp"))
    if adp is None:
        return 0.0

    # Early rounds should track market timing more tightly; later rounds can drift more.
    timing_gap = overall_pick - adp
    if timing_gap >= 0:
        timing_score = min(timing_gap / 50.0, 1.0)
    else:
        timing_score = max(timing_gap / 30.0, -1.0)

    early_round_multiplier = max(0.35, 1.15 - ((round_number - 1) / max(TOTAL_ROUNDS - 1, 1)))
    return timing_score * early_round_multiplier


def starting_lineup_pressure(team: TeamState, row: dict[str, str], round_number: int, picks_remaining: int) -> tuple[float, str]:
    hitter_slots_open = remaining_active_hitter_slots(team)
    pitcher_slots_open = remaining_active_pitcher_slots(team)
    starting_slots_open = hitter_slots_open + pitcher_slots_open
    if starting_slots_open <= 0:
        return 0.0, ""

    is_pitcher = determine_position_bucket(row) in {"SP", "RP", "TWP"}
    hitter_slot_bonus = 0.0 if is_pitcher else assign_hitter_slot(team, row)
    fills_open_slot = pitcher_slots_open > 0 if is_pitcher else hitter_slot_bonus > 0.0
    surplus_picks = picks_remaining - starting_slots_open

    pressure = 0.0
    if round_number >= 8:
        pressure += 0.15
    if round_number >= 12:
        pressure += 0.25
    if surplus_picks <= 6:
        pressure += 0.45
    if surplus_picks <= 3:
        pressure += 0.85

    if fills_open_slot:
        if is_pitcher:
            bonus = (0.55 + pressure) + max(0, pitcher_slots_open - 3) * 0.08
        else:
            bonus = hitter_slot_bonus * (0.55 + pressure)
        note = "starting lineup need pushed the pick up" if pressure >= 0.60 else ""
        return bonus, note

    if surplus_picks <= 0:
        return -10_000.0, "starting-slot pressure required a lineup fit"
    if round_number >= 12 and surplus_picks <= 6:
        return -0.60, ""
    if round_number >= 16 and surplus_picks <= 3:
        return -1.20, ""
    return 0.0, ""


def update_team_state(team: TeamState, row: dict[str, str], roster_bucket: str) -> None:
    team.picks.append(row)
    team.mlb_count += 1
    if clean_value(row.get("player_type")) in {"pitcher", "two-way"} and determine_position_bucket(row) in {"SP", "RP", "TWP"}:
        team.pitcher_count += 1
        team.pitcher_proj_sv += parse_float(row.get("proj_sv")) or 0.0
    else:
        team.hitter_count += 1
        team.hitter_proj_sb += parse_float(row.get("proj_sb")) or 0.0
        proj_pa = parse_float(row.get("proj_pa")) or 0.0
        team.hitter_proj_pa += proj_pa
        team.hitter_proj_obp_pa += (parse_float(row.get("proj_obp")) or 0.300) * proj_pa

        slot_name, _ = best_open_hitter_slot(team, row)
        if slot_name:
            team.active_slots_remaining[slot_name] -= 1


def describe_player(row: dict[str, str]) -> str:
    bucket = determine_position_bucket(row)
    if bucket == "SP" and (parse_int(row.get("dynasty_rank")) or 999) <= 20:
        return "top-tier ace"
    if bucket == "RP":
        return "late-inning reliever"
    if bucket == "TWP":
        return "two-way franchise piece"
    obp = parse_float(row.get("proj_obp")) or 0.0
    sb = parse_float(row.get("proj_sb")) or 0.0
    hr = parse_float(row.get("proj_hr")) or 0.0
    if obp >= 0.360 and hr >= 25:
        return "OBP anchor bat"
    if sb >= 20:
        return "speed-impact bat"
    return f"{bucket.lower()} contributor"


def build_reason(team: str, config: ManagerConfig, row: dict[str, str], round_number: int, roster_bucket: str, need_note: str) -> str:
    descriptor = describe_player(row)
    dynasty_rank = clean_value(row.get("dynasty_rank"))
    adp = clean_value(row.get("adp"))
    parts = [f"{team} prioritized {config.focus_phrase}"]
    parts.append(f"{clean_value(row.get('player_name'))} fit as a {descriptor}")
    if dynasty_rank:
        parts.append(f"dynasty rank {dynasty_rank}")
    if adp:
        parts.append(f"market ADP {adp}")
    if roster_bucket == "Minors":
        parts.append("as a minor-league stash")
    if need_note:
        parts.append(need_note)
    if round_number <= 3 and determine_position_bucket(row) in {"SP", "RP"}:
        parts.append("despite an early pitching slot")
    return "; ".join(parts) + "."


def candidate_score(team: TeamState, config: ManagerConfig, row: dict[str, str], round_number: int, overall_pick: int) -> tuple[float, str]:
    dynasty_component = (parse_float(row.get("dynasty_score")) or 0.0) * config.dynasty_weight
    adp_component = (parse_float(row.get("adp_score")) or 0.0) * config.adp_weight
    adp_timing_component = adp_timing_bonus(row, overall_pick, round_number) * (0.85 + (config.adp_weight * 0.55))
    projection_component = (parse_float(row.get("proj_score_norm")) or 0.0) * config.projection_weight
    actual_component = (parse_float(row.get("actual_score_norm")) or 0.0) * config.actual_weight
    youth_component = (parse_float(row.get("youth_score")) or 0.0) * config.youth_weight
    veteran_component = (parse_float(row.get("veteran_score")) or 0.0) * config.veteran_weight
    prospect_component = 0.0
    role_component = 0.0
    if determine_position_bucket(row) == "SP":
        role_component += 0.25 * config.pitcher_aggression
    if determine_position_bucket(row) == "RP":
        role_component += (parse_float(row.get("saves_score")) or 0.0) * config.closer_bias
    role_component += (parse_float(row.get("flex_score")) or 0.0) * config.flexibility_bias
    risk_component = (parse_float(row.get("risk_score")) or 0.0) * config.risk_aversion
    category_component = (
        (parse_float(row.get("speed_score")) or 0.0) * 0.6
        + (parse_float(row.get("obp_score")) or 0.0) * 0.6
        + (parse_float(row.get("ratio_score_norm")) or 0.0) * 0.6
        + (parse_float(row.get("saves_score")) or 0.0) * 0.5
    ) * config.category_bias

    score = dynasty_component + adp_component + adp_timing_component + projection_component + actual_component + youth_component + veteran_component + prospect_component + role_component + risk_component + category_component
    need_note = ""

    remaining_picks = TOTAL_ROUNDS - len(team.picks)
    remaining_mlb = remaining_mlb_room(team)
    if remaining_mlb < 0:
        return -10_000.0, need_note

    if remaining_mlb <= 0:
        return -10_000.0, need_note
    if remaining_picks == remaining_mlb:
        score += 3.0
        need_note = "MLB-slot pressure required immediate production"

    is_pitcher = determine_position_bucket(row) in {"SP", "RP", "TWP"}
    is_closer = clean_value(row.get("is_closer")) == "yes"
    if is_pitcher and round_number <= 3 and (parse_int(row.get("dynasty_rank")) or 999) > 15:
        score -= 1.2
    if is_closer and round_number <= 7:
        score -= 1.6
    if is_pitcher and round_number <= 8 and team.pitcher_count >= max(1, 1 + int(config.pitcher_aggression * 2)):
        score -= 0.7
    if not is_pitcher and round_number <= 8 and team.hitter_count < max(0, round_number - 2):
        score += 0.5
    if team.mlb_count < TARGET_MLB_SLOTS:
        if is_pitcher and team.pitcher_count < 9 and round_number >= 6:
            score += 0.15
        if not is_pitcher and assign_hitter_slot(team, row) > 0:
            score += assign_hitter_slot(team, row) * 0.8
            need_note = merge_notes(need_note, "roster construction needed this position fit")

    lineup_pressure_bonus, lineup_pressure_note = starting_lineup_pressure(team, row, round_number, remaining_picks)
    if lineup_pressure_bonus <= -10_000.0:
        return lineup_pressure_bonus, lineup_pressure_note
    score += lineup_pressure_bonus
    need_note = merge_notes(need_note, lineup_pressure_note)

    scarcity_bonus, scarcity_note = position_scarcity_bonus(team, config, row, round_number, remaining_picks)
    score += scarcity_bonus
    need_note = merge_notes(need_note, scarcity_note)

    if not is_pitcher and round_number >= 5:
        if team.hitter_proj_pa > 0:
            team_obp = team.hitter_proj_obp_pa / team.hitter_proj_pa
            if team_obp < 0.335:
                score += (parse_float(row.get("obp_score")) or 0.0) * 0.6
                need_note = merge_notes(need_note, "team OBP build needed reinforcement")
        if team.hitter_proj_sb < max(12.0, 1.8 * round_number):
            score += (parse_float(row.get("speed_score")) or 0.0) * 0.8
            if (parse_float(row.get("speed_score")) or 0.0) > 0.35:
                need_note = merge_notes(need_note, "speed scarcity pushed the pick up")

    if is_pitcher and round_number >= 10 and team.pitcher_proj_sv < max(10.0, round_number * 1.2):
        score += (parse_float(row.get("saves_score")) or 0.0) * max(0.0, config.closer_bias)
        if is_closer:
            need_note = merge_notes(need_note, "team save totals needed attention")

    if clean_value(row.get("injury_status")) and config.risk_aversion >= 0.5:
        score -= 0.5
    if clean_value(row.get("transaction_status")) == "Optioned":
        score -= 0.4

    score += max(0.0, 0.08 - overall_pick * 0.0001)
    return score, need_note


def choose_player(team: TeamState, config: ManagerConfig, available_rows: list[dict[str, str]], round_number: int, overall_pick: int) -> tuple[dict[str, str], str, str]:
    best_row: dict[str, str] | None = None
    best_score = -10_000.0
    best_note = ""
    for row in available_rows:
        score, need_note = candidate_score(team, config, row, round_number, overall_pick)
        if score > best_score:
            best_score = score
            best_row = row
            best_note = need_note
    if best_row is None:
        raise RuntimeError(f"No candidate found for {team.name} at pick {overall_pick}")

    roster_bucket = "MLB"
    rationale = build_reason(team.name, config, best_row, round_number, roster_bucket, best_note)
    return best_row, roster_bucket, rationale


def run_draft(board_rows: list[dict[str, str]], settings: dict) -> tuple[list[dict[str, str]], dict[str, TeamState]]:
    order = settings.get("draft_order", [])
    if not order:
        raise RuntimeError("Draft order missing from startup-draft-settings-2026.json")

    teams = {name: TeamState(name=name) for name in order}
    available_by_id = {
        clean_value(row.get("mlbam_id")) or normalize_name(clean_value(row.get("player_name"))): row
        for row in board_rows
        if should_include_in_mlb_draft(row)
    }
    snake_order = generate_snake_order(order, TOTAL_ROUNDS)

    results: list[dict[str, str]] = []
    for overall_pick, team_name in enumerate(snake_order, start=1):
        round_number = ((overall_pick - 1) // len(order)) + 1
        pick_in_round = ((overall_pick - 1) % len(order)) + 1
        team = teams[team_name]
        config = MANAGER_CONFIGS[team_name]
        available_rows = list(available_by_id.values())
        selected_row, roster_bucket, rationale = choose_player(team, config, available_rows, round_number, overall_pick)
        player_key = clean_value(selected_row.get("mlbam_id")) or normalize_name(clean_value(selected_row.get("player_name")))
        available_by_id.pop(player_key, None)

        update_team_state(team, selected_row, roster_bucket)

        results.append(
            {
                "pick_number": str(overall_pick),
                "round": str(round_number),
                "pick_in_round": str(pick_in_round),
                "team": team_name,
                "player_name": clean_value(selected_row.get("player_name")),
                "player_type": clean_value(selected_row.get("player_type")),
                "position_bucket": determine_position_bucket(selected_row),
                "eligible_positions": clean_value(selected_row.get("eligible_positions")),
                "roster_bucket": roster_bucket,
                "current_level": clean_value(selected_row.get("current_level")),
                "dynasty_rank": clean_value(selected_row.get("dynasty_rank")),
                "adp": clean_value(selected_row.get("adp")),
                "injury_status": clean_value(selected_row.get("injury_status")),
                "transaction_status": clean_value(selected_row.get("transaction_status")),
                "rationale": rationale,
            }
        )

    return results, teams


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(results: list[dict[str, str]], teams: dict[str, TeamState]) -> None:
    write_csv(
        OUTPUT_RESULTS_PATH,
        [
            "pick_number",
            "round",
            "pick_in_round",
            "team",
            "player_name",
            "player_type",
            "position_bucket",
            "eligible_positions",
            "roster_bucket",
            "current_level",
            "dynasty_rank",
            "adp",
            "injury_status",
            "transaction_status",
            "rationale",
        ],
        results,
    )

    OUTPUT_ROSTERS_DIR.mkdir(parents=True, exist_ok=True)
    for team_name, state in teams.items():
        rows: list[dict[str, str]] = []
        for pick in results:
            if pick["team"] != team_name:
                continue
            rows.append(pick)
        write_csv(
            OUTPUT_ROSTERS_DIR / f"{slugify(team_name)}-roster.csv",
            [
                "pick_number",
                "round",
                "pick_in_round",
                "team",
                "player_name",
                "player_type",
                "position_bucket",
                "eligible_positions",
                "roster_bucket",
                "current_level",
                "dynasty_rank",
                "adp",
                "injury_status",
                "transaction_status",
                "rationale",
            ],
            rows,
        )


def main() -> None:
    board_rows = enrich_board_rows(read_csv_rows(BOARD_PATH))
    settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    results, teams = run_draft(board_rows, settings)
    write_outputs(results, teams)
    print(f"Wrote {len(results)} picks to {OUTPUT_RESULTS_PATH}")
    print(f"Wrote {len(teams)} roster files to {OUTPUT_ROSTERS_DIR}")


if __name__ == "__main__":
    main()