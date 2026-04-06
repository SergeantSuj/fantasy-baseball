from __future__ import annotations

import argparse
import csv
import json
import re
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from itertools import product
from pathlib import Path

from build_weekly_lineup_snapshot import (
    BOARD_PATH,
    OUTPUT_DIR as LINEUP_DIR,
    ROSTERS_DIR,
    assign_best_hitter_lineup,
    assign_pitchers,
    board_index_rows,
    build_lineup_rows,
    clean_value,
    hitter_value,
    injury_status_summary,
    is_il_roster_bucket,
    is_injured_list_player,
    is_hitter,
    is_major_league_level,
    is_minor_roster_bucket,
    is_pitcher,
    merge_player_rows,
    parse_float,
    parse_int,
    pitcher_value,
    player_key,
    read_csv_rows,
    read_settings,
    roster_order,
    write_csv,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = WORKSPACE_ROOT / "data"
DECISION_DIR = DATA_DIR / "weekly-decisions"
RESULTS_PATH = DATA_DIR / "season-results-2026.json"
PROFILES_DIR = WORKSPACE_ROOT / "manager-profiles"
IL_SLOT_LIMIT = 5
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0 Safari/537.36"
REFRESH_SPORT_LEVELS = {1: "MLB", 11: "AAA", 12: "AA", 13: "High-A", 14: "Single-A"}
IL_DESCRIPTION_RE = re.compile(r"(\d+-day)\s+(?:injured list|disabled list)", re.IGNORECASE)
STATUS_REFRESH_LOOKBACK_DAYS = 14


def resolve_output_path(path_value: str | None, default_path: Path) -> Path:
    if not path_value:
        return default_path
    path = Path(path_value)
    return path if path.is_absolute() else WORKSPACE_ROOT / path


def workspace_relative_path(path: Path) -> str:
    return str(path.relative_to(WORKSPACE_ROOT)).replace("\\", "/")


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def merge_roster_rows(roster_rows: list[dict[str, str]], board_index: dict[str, dict[str, str]]) -> list[dict[str, object]]:
    roster: list[dict[str, object]] = []
    for roster_row in roster_rows:
        joined = merge_player_rows(board_index.get(player_key(roster_row), {}), roster_row)
        joined["mlb_team"] = clean_value(str(joined.get("mlb_team", ""))) or clean_value(str(joined.get("proj_team", "")))
        roster.append(joined)
    return roster


def canonical_roster_key(roster_row: dict[str, str], board_index: dict[str, dict[str, str]]) -> str:
    return player_key(merge_player_rows(board_index.get(player_key(roster_row), {}), roster_row))


def find_roster_row(
    roster_rows: list[dict[str, str]],
    board_index: dict[str, dict[str, str]],
    player_id: str,
    player_name: str,
) -> dict[str, str] | None:
    normalized_name = clean_value(player_name)
    for row in roster_rows:
        if canonical_roster_key(row, board_index) == player_id:
            return row
        if normalized_name and clean_value(row.get("player_name", "")).lower() == normalized_name.lower():
            return row
    return None


def team_name_from_path(roster_path: Path) -> str:
    return clean_value(roster_path.stem.replace("-roster", "").replace("-", " ")).title()


def player_value(player: dict[str, object]) -> float:
    hitter_score = hitter_value(player) if is_hitter(player) else float("-inf")
    pitcher_score = pitcher_value(player) if is_pitcher(player) else float("-inf")
    best = max(hitter_score, pitcher_score)
    return 0.0 if best == float("-inf") else best


def dynasty_rank_value(player: dict[str, object]) -> int:
    value = parse_int(str(player.get("dynasty_rank", "")))
    return value if value > 0 else 999999


def adp_value(player: dict[str, object]) -> float:
    value = parse_float(str(player.get("adp", "")))
    return value if value > 0 else 999999.0


def dedupe_board_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    merged_by_key: dict[str, dict[str, str]] = {}
    order: list[str] = []
    for row in rows:
        key = player_key(row)
        if not key:
            continue
        if key not in merged_by_key:
            merged_by_key[key] = dict(row)
            order.append(key)
            continue
        merged_by_key[key] = merge_player_rows(merged_by_key[key], row)
    return [merged_by_key[key] for key in order]


def build_free_agent_candidates(board_rows: list[dict[str, str]], rostered_keys: set[str]) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for board_row in dedupe_board_rows(board_rows):
        key = player_key(board_row)
        if not key or key in rostered_keys:
            continue
        candidate = dict(board_row)
        candidate["mlb_team"] = clean_value(str(candidate.get("mlb_team", ""))) or clean_value(str(candidate.get("proj_team", "")))
        if not is_major_league_level(candidate):
            continue
        if is_injured_list_player(candidate):
            continue
        if clean_value(str(candidate.get("mlb_team", ""))).upper() in {"", "FA"}:
            continue
        if player_value(candidate) <= 0:
            continue
        candidates.append(candidate)

    candidates.sort(
        key=lambda player: (
            -player_value(player),
            dynasty_rank_value(player),
            adp_value(player),
            clean_value(str(player.get("player_name", ""))),
        )
    )
    return candidates


def optimize_roster(players: list[dict[str, object]]) -> dict[str, object]:
    two_way_players = [player for player in players if clean_value(str(player.get("player_type", ""))) == "two-way"]
    scenario_labels = ["hitter", "pitcher"] if two_way_players else [""]
    scenario_results: list[dict[str, object]] = []

    for choices in product(scenario_labels, repeat=len(two_way_players)):
        choice_map = {player_key(player): choice for player, choice in zip(two_way_players, choices)}
        hitters = []
        pitchers = []
        for player in players:
            key = player_key(player)
            choice = choice_map.get(key)
            if clean_value(str(player.get("player_type", ""))) == "two-way":
                if choice == "pitcher":
                    pitchers.append(player)
                else:
                    hitters.append(player)
                continue
            if is_hitter(player):
                hitters.append(player)
            if is_pitcher(player):
                pitchers.append(player)

        active_hitters, _ = assign_best_hitter_lineup(hitters)
        active_pitchers, _ = assign_pitchers(pitchers)
        active_keys = {player_key(player) for player in [*active_hitters, *active_pitchers]}
        bench_players = [dict(player) for player in players if player_key(player) not in active_keys]
        score = sum(hitter_value(player) for player in active_hitters) + sum(pitcher_value(player) for player in active_pitchers)
        scenario_results.append(
            {
                "score": score,
                "active_hitters": active_hitters,
                "active_pitchers": active_pitchers,
                "bench_players": bench_players,
            }
        )

    return max(scenario_results, key=lambda item: float(item["score"]))


def projected_role_map(players: list[dict[str, object]]) -> dict[str, str]:
    optimized = optimize_roster(players)
    role_map: dict[str, str] = {}
    for player in optimized["active_hitters"]:
        role_map[player_key(player)] = clean_value(str(player.get("lineup_slot", ""))) or "Active"
    for player in optimized["active_pitchers"]:
        role_map[player_key(player)] = clean_value(str(player.get("lineup_slot", ""))) or "Active"
    for player in optimized["bench_players"]:
        role_map[player_key(player)] = "Bench"
    return role_map


def weakest_drop_candidate(players: list[dict[str, object]], exclude_keys: set[str]) -> dict[str, object] | None:
    role_map = projected_role_map(players)
    eligible = [player for player in players if player_key(player) not in exclude_keys]
    if not eligible:
        return None

    def sort_key(player: dict[str, object]) -> tuple[object, ...]:
        role = role_map.get(player_key(player), "Bench")
        role_priority = 0 if role == "Bench" else 1
        return (
            role_priority,
            player_value(player),
            parse_int(str(player.get("dynasty_rank", 0))),
            clean_value(str(player.get("player_name", ""))),
        )

    return min(eligible, key=sort_key)


def replacement_candidate_pool(
    injured_player: dict[str, object],
    free_agent_candidates: list[dict[str, object]],
) -> list[dict[str, object]]:
    if is_pitcher(injured_player) and not is_hitter(injured_player):
        return [candidate for candidate in free_agent_candidates if is_pitcher(candidate)]
    if is_hitter(injured_player) and not is_pitcher(injured_player):
        return [candidate for candidate in free_agent_candidates if is_hitter(candidate)]
    return free_agent_candidates


def evaluate_free_agent_add(candidate: dict[str, object], current_mlb_roster: list[dict[str, object]]) -> dict[str, object]:
    added_candidate = dict(candidate)
    added_candidate["roster_bucket"] = "MLB"
    optimized = optimize_roster([*current_mlb_roster, added_candidate])
    active_keys = {player_key(player) for player in [*optimized["active_hitters"], *optimized["active_pitchers"]]}
    candidate_key = player_key(added_candidate)
    candidate_role = "Bench"
    candidate_slot = ""
    if candidate_key in active_keys:
        candidate_role = "Starter"
        for player in [*optimized["active_hitters"], *optimized["active_pitchers"]]:
            if player_key(player) == candidate_key:
                candidate_slot = clean_value(str(player.get("lineup_slot", "")))
                break

    candidate_value = round(player_value(added_candidate), 1)
    if candidate_role == "Starter":
        rationale = f"Best available unrostered replacement; would enter the active lineup at {candidate_slot or 'an active slot'} after the IL move."
    else:
        rationale = "Best available unrostered replacement for the MLB bucket after the IL move, even if the player opens on the bench."

    return {
        "projected_role_if_added": candidate_role,
        "projected_slot_if_added": candidate_slot,
        "candidate_projection_value": candidate_value,
        "rationale": rationale,
    }


def evaluate_minor_promotion(candidate: dict[str, object], current_mlb_roster: list[dict[str, object]]) -> dict[str, object]:
    promoted_candidate = dict(candidate)
    promoted_candidate["roster_bucket"] = "MLB"
    promoted_roster = [dict(player) for player in current_mlb_roster] + [promoted_candidate]
    optimized = optimize_roster(promoted_roster)
    active_keys = {player_key(player) for player in [*optimized["active_hitters"], *optimized["active_pitchers"]]}
    candidate_key = player_key(promoted_candidate)
    candidate_role = "Bench"
    candidate_slot = ""
    if candidate_key in active_keys:
        candidate_role = "Starter"
        for player in [*optimized["active_hitters"], *optimized["active_pitchers"]]:
            if player_key(player) == candidate_key:
                candidate_slot = clean_value(str(player.get("lineup_slot", "")))
                break

    drop_candidate = weakest_drop_candidate(promoted_roster, {candidate_key})
    candidate_value = round(player_value(promoted_candidate), 1)
    drop_value = round(player_value(drop_candidate), 1) if drop_candidate else 0.0
    improvement = round(candidate_value - drop_value, 1)

    if candidate_role == "Starter":
        recommendation = "Move to MLB roster as starter"
        rationale = f"Would crack the active lineup at {candidate_slot or 'an active slot'} under the current optimizer."
    elif drop_candidate and player_value(promoted_candidate) > player_value(drop_candidate):
        recommendation = "Move to MLB roster as bench player"
        rationale = "Improves the 30-man MLB bucket even though the player would open on the fantasy bench."
    else:
        recommendation = "Keep in minors for now"
        rationale = "Does not currently beat the weakest projected MLB roster player on the fantasy roster."

    return {
        "recommendation": recommendation,
        "projected_role_if_promoted": candidate_role,
        "projected_slot_if_promoted": candidate_slot,
        "candidate_projection_value": candidate_value,
        "drop_candidate": {
            "player_name": clean_value(str(drop_candidate.get("player_name", ""))) if drop_candidate else "",
            "current_projected_role": projected_role_map(current_mlb_roster).get(player_key(drop_candidate), "") if drop_candidate else "",
            "roster_value": drop_value,
        },
        "improvement": improvement,
        "rationale": rationale,
    }


def summarize_player(player: dict[str, object]) -> dict[str, object]:
    return {
        "player_name": clean_value(str(player.get("player_name", ""))),
        "player_type": clean_value(str(player.get("player_type", ""))),
        "eligible_positions": clean_value(str(player.get("eligible_positions", ""))),
        "mlb_team": clean_value(str(player.get("mlb_team", ""))),
        "current_level": clean_value(str(player.get("current_level", ""))),
        "lineup_slot": clean_value(str(player.get("lineup_slot", ""))),
        "projection_value": round(player_value(player), 1),
    }


def build_il_move_recommendations(
    team_name: str,
    mlb_roster: list[dict[str, object]],
    il_players: list[dict[str, object]],
    free_agent_candidates: list[dict[str, object]],
) -> list[dict[str, object]]:
    recommendations: list[dict[str, object]] = []
    il_slots_open = max(IL_SLOT_LIMIT - len(il_players), 0)
    injured_players = [player for player in mlb_roster if is_injured_list_player(player)]

    for index, injured_player in enumerate(
        sorted(injured_players, key=lambda player: (-player_value(player), clean_value(str(player.get("player_name", "")))))
    ):
        open_slot = index < il_slots_open
        replacement_pool = replacement_candidate_pool(injured_player, free_agent_candidates)
        remaining_roster = [player for player in mlb_roster if player_key(player) != player_key(injured_player)]
        replacement = replacement_pool[0] if replacement_pool else None
        evaluation = evaluate_free_agent_add(replacement, remaining_roster) if replacement else {}

        recommendation = "Move player to IL"
        rationale = "Player has an IL or disabled-list status and should not remain in the active or bench MLB bucket for the scoring week."
        if open_slot and replacement:
            recommendation = "Move player to IL and add unrostered replacement"
            rationale = evaluation["rationale"]
        elif open_slot and not replacement:
            recommendation = "Move player to IL and review free agents manually"
            rationale = "No strong unrostered replacement cleared the automated filter, so this IL move needs a manual add decision."
        elif not open_slot:
            recommendation = "Open an IL slot before lock"
            rationale = "All five IL slots are already occupied. Clear or reactivate one IL spot before moving this player."

        recommendations.append(
            {
                "team": team_name,
                "injured_player_key": player_key(injured_player),
                "injured_player_name": clean_value(str(injured_player.get("player_name", ""))),
                "injured_player_type": clean_value(str(injured_player.get("player_type", ""))),
                "injured_player_positions": clean_value(str(injured_player.get("eligible_positions", ""))),
                "current_injury_status": injury_status_summary(injured_player),
                "recommendation": recommendation,
                "replacement_add": {
                    "player_key": player_key(replacement) if replacement else "",
                    "player_name": clean_value(str(replacement.get("player_name", ""))) if replacement else "",
                    "player_type": clean_value(str(replacement.get("player_type", ""))) if replacement else "",
                    "eligible_positions": clean_value(str(replacement.get("eligible_positions", ""))) if replacement else "",
                    "mlb_team": clean_value(str(replacement.get("mlb_team", ""))) if replacement else "",
                    "current_level": clean_value(str(replacement.get("current_level", ""))) if replacement else "",
                    "projected_role_if_added": evaluation.get("projected_role_if_added", ""),
                    "projected_slot_if_added": evaluation.get("projected_slot_if_added", ""),
                    "candidate_projection_value": evaluation.get("candidate_projection_value", ""),
                },
                "rationale": rationale,
            }
        )

    return recommendations


def next_pick_number(roster_rows: list[dict[str, str]]) -> int:
    existing = [parse_int(row.get("pick_number", "")) for row in roster_rows]
    return max(existing, default=0) + 1


def position_bucket_for_player(player: dict[str, str]) -> str:
    primary_position = clean_value(player.get("primary_position", ""))
    if primary_position:
        return primary_position
    proj_pos = clean_value(player.get("proj_pos", ""))
    if proj_pos:
        return proj_pos.split("/")[0]
    eligible = clean_value(player.get("eligible_positions", ""))
    return eligible.split("/")[0] if eligible else ""


def build_auto_add_row(
    team_name: str,
    candidate: dict[str, str],
    injured_player_name: str,
    fieldnames: list[str],
    pick_number: int,
) -> dict[str, str]:
    row = {field: "" for field in fieldnames}
    row.update(
        {
            "pick_number": str(pick_number),
            "round": "FA",
            "pick_in_round": "",
            "team": team_name,
            "player_name": clean_value(candidate.get("player_name", "")),
            "player_type": clean_value(candidate.get("player_type", "")),
            "position_bucket": position_bucket_for_player(candidate),
            "eligible_positions": clean_value(candidate.get("eligible_positions", "")),
            "roster_bucket": "MLB",
            "current_level": clean_value(candidate.get("current_level", "")),
            "dynasty_rank": clean_value(candidate.get("dynasty_rank", "")),
            "adp": clean_value(candidate.get("adp", "")),
            "injury_status": clean_value(candidate.get("injury_status", "")),
            "transaction_status": clean_value(candidate.get("transaction_status", "")),
            "rationale": f"Auto-added as an IL replacement for {injured_player_name}.",
        }
    )
    return row


def write_roster_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Manager FA Profile Configuration
# ---------------------------------------------------------------------------
# Each profile encodes: how aggressively the manager acquires free agents,
# whether they protect young assets, and how large an improvement they need
# before dropping an active roster player.
#
# Fields:
#   aggression       - 0.0 (very conservative) to 1.0 (very aggressive)
#   min_improvement  - minimum player_value gap (FA minus drop candidate)
#                      required for the manager to approve the swap
#   protect_youth    - if True, young players (age <= 26 with dynasty_rank
#                      <= 200) get a value floor boost and are harder to drop
#   prefer_category  - list of roto categories this manager targets when
#                      choosing among FA candidates of similar value

MANAGER_FA_PROFILES: dict[str, dict[str, object]] = {
    "Chris": {
        "aggression": 0.5,
        "min_improvement": 8.0,
        "protect_youth": False,
        "prefer_category": [],
    },
    "Greg": {
        "aggression": 0.5,
        "min_improvement": 10.0,
        "protect_youth": False,
        "prefer_category": [],
    },
    "Josh M": {
        "aggression": 0.6,
        "min_improvement": 6.0,
        "protect_youth": True,
        "prefer_category": [],
    },
    "Josh V": {
        "aggression": 0.7,
        "min_improvement": 4.0,
        "protect_youth": True,
        "prefer_category": [],
    },
    "Matt": {
        "aggression": 0.9,
        "min_improvement": 2.0,
        "protect_youth": False,
        "prefer_category": [],
    },
    "Michael": {
        "aggression": 0.4,
        "min_improvement": 10.0,
        "protect_youth": True,
        "prefer_category": [],
    },
    "Paul": {
        "aggression": 0.8,
        "min_improvement": 3.0,
        "protect_youth": False,
        "prefer_category": ["obp", "saves", "stolen_bases"],
    },
    "Rob": {
        "aggression": 0.4,
        "min_improvement": 10.0,
        "protect_youth": False,
        "prefer_category": ["obp", "era", "whip"],
    },
    "Shane": {
        "aggression": 0.7,
        "min_improvement": 4.0,
        "protect_youth": False,
        "prefer_category": ["saves", "stolen_bases"],
    },
    "Wendell": {
        "aggression": 0.3,
        "min_improvement": 12.0,
        "protect_youth": False,
        "prefer_category": [],
    },
}

DEFAULT_FA_PROFILE: dict[str, object] = {
    "aggression": 0.5,
    "min_improvement": 8.0,
    "protect_youth": False,
    "prefer_category": [],
}

# Category->stat mapping for FA candidate preference scoring
# These are small tiebreaker nudges, not dominant value overrides.
CATEGORY_FA_BONUS: dict[str, tuple[str, float]] = {
    "runs": ("proj_r", 0.05),
    "home_runs": ("proj_hr", 0.2),
    "rbi": ("proj_rbi", 0.06),
    "stolen_bases": ("proj_sb", 0.25),
    "obp": ("proj_obp", 8.0),
    "wins": ("proj_w", 0.2),
    "strikeouts": ("proj_k", 0.04),
    "saves": ("proj_sv", 0.3),
    "era": ("proj_era", -1.0),
    "whip": ("proj_whip", -3.0),
}


def get_fa_profile(team_name: str) -> dict[str, object]:
    return MANAGER_FA_PROFILES.get(team_name, DEFAULT_FA_PROFILE)


def read_standings() -> list[dict[str, object]]:
    """Read current standings from season-results-2026.json."""
    if not RESULTS_PATH.exists():
        return []
    data = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    return data.get("standings", [])


def waiver_order(standings: list[dict[str, object]], all_team_names: list[str]) -> list[str]:
    """Return team names sorted worst-to-first (reverse standings order).

    Teams not in standings yet (no games played) are ordered alphabetically
    at the front of the waiver wire.
    """
    standings_by_name = {clean_value(str(s.get("name", ""))): s for s in standings}
    ranked_teams = []
    unranked_teams = []
    for name in all_team_names:
        entry = standings_by_name.get(name)
        if entry:
            ranked_teams.append((name, float(entry.get("total_points", 0)), int(entry.get("rank", 999))))
        else:
            unranked_teams.append(name)
    # Sort ranked teams worst-first (lowest points first, highest rank number first)
    ranked_teams.sort(key=lambda t: (t[1], -t[2]))
    return sorted(unranked_teams) + [t[0] for t in ranked_teams]


def youth_protected_value(player: dict[str, object]) -> float:
    """Return a value floor for young, high-dynasty-rank players."""
    age = parse_int(str(player.get("age", "")))
    dynasty_rank = dynasty_rank_value(player)
    base = player_value(player)
    if age > 0 and age <= 26 and dynasty_rank <= 200:
        # Boost effective value so youth is harder to drop
        return max(base, base + 15.0)
    return base


def category_bonus(player: dict[str, object], prefer_categories: list[str]) -> float:
    """Small tiebreaker bonus for FA candidates who contribute to preferred categories."""
    if not prefer_categories:
        return 0.0
    bonus = 0.0
    for cat in prefer_categories:
        mapping = CATEGORY_FA_BONUS.get(cat)
        if not mapping:
            continue
        field, weight = mapping
        value = parse_float(str(player.get(field, "")))
        bonus += value * weight
    return bonus


def build_fa_add_row(
    team_name: str,
    candidate: dict[str, str],
    drop_player_name: str,
    fieldnames: list[str],
    pick_number: int,
) -> dict[str, str]:
    row = {field: "" for field in fieldnames}
    row.update(
        {
            "pick_number": str(pick_number),
            "round": "FA",
            "pick_in_round": "",
            "team": team_name,
            "player_name": clean_value(candidate.get("player_name", "")),
            "player_type": clean_value(candidate.get("player_type", "")),
            "position_bucket": position_bucket_for_player(candidate),
            "eligible_positions": clean_value(candidate.get("eligible_positions", "")),
            "roster_bucket": "MLB",
            "current_level": clean_value(candidate.get("current_level", "")),
            "dynasty_rank": clean_value(candidate.get("dynasty_rank", "")),
            "adp": clean_value(candidate.get("adp", "")),
            "injury_status": clean_value(candidate.get("injury_status", "")),
            "transaction_status": clean_value(candidate.get("transaction_status", "")),
            "rationale": f"FA acquisition replacing {drop_player_name}.",
        }
    )
    return row


def apply_fa_acquisitions(board_rows: list[dict[str, str]]) -> dict[str, object]:
    """Evaluate and execute FA acquisitions in waiver order (worst-to-first).

    For each team, compare the best available free agent against the weakest
    MLB-bucket player, adjusted by the manager's FA profile.  If the FA
    clears the manager's improvement threshold, drop the weak player and
    add the FA.  Repeat in passes until no team wants to make a move.
    """
    settings = read_settings()
    board_index = board_index_rows(board_rows)
    board_rows_by_key = {player_key(row): row for row in dedupe_board_rows(board_rows)}
    standings = read_standings()

    # Build roster state
    roster_state: dict[str, tuple[Path, list[dict[str, str]]]] = {}
    rostered_keys: set[str] = set()
    all_team_names: list[str] = []

    for roster_path in roster_order(ROSTERS_DIR, settings):
        team_name = team_name_from_path(roster_path)
        roster_rows = read_csv_rows(roster_path)
        roster_state[team_name] = (roster_path, roster_rows)
        all_team_names.append(team_name)
        for row in roster_rows:
            key = canonical_roster_key(row, board_index)
            if key:
                rostered_keys.add(key)

    order = waiver_order(standings, all_team_names)
    acquisitions: list[dict[str, object]] = []
    dropped_keys_by_team: dict[str, set[str]] = {name: set() for name in all_team_names}
    MAX_FA_PASSES = 5  # Max passes through the waiver order

    for pass_number in range(MAX_FA_PASSES):
        any_move_this_pass = False

        for team_name in order:
            roster_path, roster_rows = roster_state[team_name]
            profile = get_fa_profile(team_name)
            min_improvement = float(profile["min_improvement"])
            protect_youth = bool(profile["protect_youth"])
            prefer_cats = list(profile.get("prefer_category", []))

            # Build current available roster (non-IL, non-minors, MLB-level)
            roster = merge_roster_rows(roster_rows, board_index)
            available_roster = [
                p for p in roster
                if not is_minor_roster_bucket(p)
                and not is_il_roster_bucket(p)
                and not is_injured_list_player(p)
                and is_major_league_level(p)
            ]

            if not available_roster:
                continue

            # Find the weakest drop candidate
            drop_candidate = weakest_drop_candidate(available_roster, set())
            if not drop_candidate:
                continue

            drop_value = youth_protected_value(drop_candidate) if protect_youth else player_value(drop_candidate)
            drop_key = player_key(drop_candidate)
            drop_name = clean_value(str(drop_candidate.get("player_name", "")))

            # Rebuild FA pool for this pick, excluding players this team already dropped
            team_excluded = rostered_keys | dropped_keys_by_team[team_name]
            free_agents = build_free_agent_candidates(board_rows, team_excluded)
            if not free_agents:
                continue

            # Find the best FA for this manager
            best_fa = None
            best_fa_score = float("-inf")
            for fa in free_agents:
                fa_val = player_value(fa) + category_bonus(fa, prefer_cats)
                if fa_val > best_fa_score:
                    best_fa_score = fa_val
                    best_fa = fa

            if not best_fa:
                continue

            improvement = best_fa_score - drop_value
            if improvement < min_improvement:
                continue

            # Execute the swap: drop the weak player, add the FA
            fa_key = player_key(best_fa)
            fa_name = clean_value(str(best_fa.get("player_name", "")))

            # Find and remove the drop candidate from roster CSV rows
            drop_roster_row = find_roster_row(roster_rows, board_index, drop_key, drop_name)
            if drop_roster_row is None:
                continue

            fieldnames = list(roster_rows[0].keys()) if roster_rows else []
            roster_rows.remove(drop_roster_row)

            # Get FA board row for the add
            fa_board_row = board_rows_by_key.get(fa_key)
            if fa_board_row is None:
                # Put the drop row back
                roster_rows.append(drop_roster_row)
                continue

            pick_number = next_pick_number(roster_rows)
            roster_rows.append(build_fa_add_row(team_name, fa_board_row, drop_name, fieldnames, pick_number))
            rostered_keys.add(fa_key)
            rostered_keys.discard(drop_key)
            dropped_keys_by_team[team_name].add(drop_key)

            write_roster_csv(roster_path, fieldnames, roster_rows)
            any_move_this_pass = True
            acquisitions.append({
                "team": team_name,
                "pass": pass_number + 1,
                "added_player_name": fa_name,
                "added_player_type": clean_value(str(best_fa.get("player_type", ""))),
                "added_positions": clean_value(str(best_fa.get("eligible_positions", ""))),
                "added_value": round(player_value(best_fa), 1),
                "dropped_player_name": drop_name,
                "dropped_player_type": clean_value(str(drop_candidate.get("player_type", ""))),
                "dropped_value": round(player_value(drop_candidate), 1),
                "improvement": round(improvement, 1),
                "manager_profile": clean_value(str(profile.get("aggression", ""))),
                "min_threshold": min_improvement,
            })

        if not any_move_this_pass:
            break

    print(f"FA acquisitions complete: {len(acquisitions)} moves across {pass_number + 1 if acquisitions else 0} passes")
    return {"acquisitions": acquisitions, "acquisition_count": len(acquisitions)}


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def transaction_api_url(sport_id: int, start_date: str, end_date: str) -> str:
    query = urllib.parse.urlencode({
        "startDate": start_date,
        "endDate": end_date,
        "sportId": sport_id,
        "limit": 5000,
    })
    return f"https://statsapi.mlb.com/api/v1/transactions?{query}"


def fetch_recent_transactions(start_date: str, end_date: str) -> dict[str, dict[str, str]]:
    """Fetch the latest MLB transaction per player across all sport levels."""
    latest_by_player: dict[str, dict[str, str]] = {}
    for sport_id, level in REFRESH_SPORT_LEVELS.items():
        payload = fetch_json(transaction_api_url(sport_id, start_date, end_date))
        for txn in payload.get("transactions", []):
            person = txn.get("person", {})
            mlbam_id = str(person.get("id", ""))
            if not mlbam_id:
                continue
            effective_date = clean_value(
                txn.get("effectiveDate") or txn.get("date") or txn.get("resolutionDate")
            )
            txn_id = int(txn.get("id", 0) or 0)
            candidate = {
                "mlbam_id": mlbam_id,
                "player_name": clean_value(person.get("fullName", "")),
                "current_level": level,
                "transaction_type": clean_value(txn.get("typeDesc", "")),
                "transaction_date": effective_date,
                "description": clean_value(txn.get("description", "")),
                "transaction_id": str(txn_id),
            }
            existing = latest_by_player.get(mlbam_id)
            if existing is None or (effective_date, txn_id) >= (
                existing["transaction_date"],
                int(existing.get("transaction_id", "0") or 0),
            ):
                latest_by_player[mlbam_id] = candidate
    return latest_by_player


def classify_transaction_update(txn: dict[str, str]) -> dict[str, str]:
    """Return roster-field updates implied by a recent MLB transaction."""
    description = txn.get("description", "").lower()
    type_desc = txn.get("transaction_type", "").lower()
    level = clean_value(txn.get("current_level", ""))
    updates: dict[str, str] = {}

    # IL placements
    if "placed" in description and ("injured list" in description or "disabled list" in description):
        il_match = IL_DESCRIPTION_RE.search(txn.get("description", ""))
        il_status = f"{il_match.group(1)} Injured List" if il_match else "Injured List"
        updates["injury_status"] = il_status
        updates["transaction_status"] = txn.get("transaction_type", "")
        return updates

    # Activations / reinstatements from IL
    if ("activated" in description or "reinstated" in description) and (
        "injured list" in description or "disabled list" in description
    ):
        updates["injury_status"] = ""
        updates["transaction_status"] = txn.get("transaction_type", "")
        updates["current_level"] = "MLB"
        return updates

    # Options to minors
    if "optioned" in type_desc:
        updates["current_level"] = level if level and level.upper() != "MLB" else "AAA"
        updates["transaction_status"] = "Optioned"
        return updates

    # Recalls from minors
    if "recalled" in type_desc or ("recalled" in description and "from" in description):
        updates["current_level"] = "MLB"
        updates["injury_status"] = ""
        updates["transaction_status"] = "Recalled"
        return updates

    # Designated for assignment
    if "designated for assignment" in description:
        updates["transaction_status"] = "Designated for Assignment"
        return updates

    return updates


def refresh_roster_statuses(board_rows: list[dict[str, str]]) -> dict[str, object]:
    """Fetch recent MLB transactions and update roster CSVs with current statuses."""
    today = datetime.now(UTC).date()
    start_date = (today - timedelta(days=STATUS_REFRESH_LOOKBACK_DAYS)).isoformat()
    end_date = today.isoformat()
    print(f"Refreshing player statuses from MLB transactions ({start_date} to {end_date}) ...")
    transactions = fetch_recent_transactions(start_date, end_date)
    settings = read_settings()
    board_index = board_index_rows(board_rows)
    changes: list[dict[str, object]] = []

    for roster_path in roster_order(ROSTERS_DIR, settings):
        team_name = team_name_from_path(roster_path)
        roster_rows = read_csv_rows(roster_path)
        fieldnames = list(roster_rows[0].keys()) if roster_rows else []
        changed = False

        for row in roster_rows:
            mlbam_id = clean_value(row.get("mlbam_id", ""))
            if not mlbam_id:
                key = canonical_roster_key(row, board_index)
                if key and key.isdigit():
                    mlbam_id = key
            if not mlbam_id or mlbam_id not in transactions:
                continue

            txn = transactions[mlbam_id]
            updates = classify_transaction_update(txn)
            if not updates:
                continue

            applied: dict[str, str] = {}
            for field, new_value in updates.items():
                old_value = clean_value(row.get(field, ""))
                if old_value != new_value:
                    row[field] = new_value
                    applied[field] = new_value
                    changed = True

            if applied:
                changes.append({
                    "team": team_name,
                    "player_name": clean_value(row.get("player_name", "")),
                    "mlbam_id": mlbam_id,
                    "updates": applied,
                    "transaction": txn.get("description", ""),
                })

        if changed:
            write_roster_csv(roster_path, fieldnames, roster_rows)

    print(f"Status refresh complete: {len(changes)} roster updates applied")
    return {"changes": changes, "change_count": len(changes)}


def apply_il_moves(board_rows: list[dict[str, str]]) -> dict[str, object]:
    settings = read_settings()
    board_index = board_index_rows(board_rows)
    board_rows_by_key = {player_key(row): row for row in dedupe_board_rows(board_rows)}
    roster_rows_by_team: list[tuple[Path, list[dict[str, str]]]] = []
    rostered_keys: set[str] = set()

    for roster_path in roster_order(ROSTERS_DIR, settings):
        roster_rows = read_csv_rows(roster_path)
        roster_rows_by_team.append((roster_path, roster_rows))
        for row in roster_rows:
            key = canonical_roster_key(row, board_index)
            if key:
                rostered_keys.add(key)

    applied_moves: list[dict[str, object]] = []
    blocked_moves: list[dict[str, object]] = []

    for roster_path, roster_rows in roster_rows_by_team:
        team_name = team_name_from_path(roster_path)
        fieldnames = list(roster_rows[0].keys()) if roster_rows else [
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
        ]
        changed = False
        pick_number = next_pick_number(roster_rows)

        # Re-evaluate IL recommendations iteratively so each successive move
        # sees an updated free-agent pool and roster state.
        MAX_IL_PASSES = 10
        for _ in range(MAX_IL_PASSES):
            free_agent_candidates = build_free_agent_candidates(board_rows, rostered_keys)
            _, team_report = build_team_report("auto-apply", team_name, roster_rows, board_index, free_agent_candidates)
            il_moves = team_report["recommended_il_moves"]
            if not il_moves:
                break

            applied_this_pass = False
            for il_move in il_moves:
                injured_key = clean_value(str(il_move.get("injured_player_key", "")))
                injured_name = clean_value(str(il_move.get("injured_player_name", "")))
                replacement_add = il_move.get("replacement_add", {})
                replacement_key = clean_value(str(replacement_add.get("player_key", "")))

                injured_row = find_roster_row(roster_rows, board_index, injured_key, injured_name)
                if injured_row is None:
                    blocked_moves.append(
                        {
                            "team": team_name,
                            "injured_player_name": injured_name,
                            "reason": "Roster row not found for the injured player.",
                        }
                    )
                    continue

                if not replacement_key:
                    blocked_moves.append(
                        {
                            "team": team_name,
                            "injured_player_name": injured_name,
                            "reason": clean_value(str(il_move.get("rationale", ""))) or "No eligible replacement was available.",
                        }
                    )
                    continue

                replacement_row = board_rows_by_key.get(replacement_key)
                if replacement_row is None:
                    blocked_moves.append(
                        {
                            "team": team_name,
                            "injured_player_name": injured_name,
                            "reason": "Replacement player was not found in the board input.",
                        }
                    )
                    continue

                if replacement_key in rostered_keys:
                    blocked_moves.append(
                        {
                            "team": team_name,
                            "injured_player_name": injured_name,
                            "reason": f"Replacement {clean_value(replacement_row.get('player_name', ''))} is already rostered.",
                        }
                    )
                    continue

                injured_row["roster_bucket"] = "IL"
                current_injury_status = clean_value(str(il_move.get("current_injury_status", "")))
                if current_injury_status:
                    injured_row["injury_status"] = current_injury_status

                roster_rows.append(build_auto_add_row(team_name, replacement_row, injured_name, fieldnames, pick_number))
                pick_number += 1
                rostered_keys.add(replacement_key)
                changed = True
                applied_this_pass = True
                applied_moves.append(
                    {
                        "team": team_name,
                        "injured_player_name": injured_name,
                        "injury_status": current_injury_status,
                        "replacement_player_name": clean_value(replacement_row.get("player_name", "")),
                        "replacement_player_type": clean_value(replacement_row.get("player_type", "")),
                        "replacement_positions": clean_value(replacement_row.get("eligible_positions", "")),
                    }
                )
                # Break out to re-evaluate with the updated roster/pool state
                break

            if not applied_this_pass:
                break

        if changed:
            write_roster_csv(roster_path, fieldnames, roster_rows)

    return {
        "applied_il_moves": applied_moves,
        "blocked_il_moves": blocked_moves,
        "applied_count": len(applied_moves),
        "blocked_count": len(blocked_moves),
    }


def build_team_report(
    week: str,
    team_name: str,
    roster_rows: list[dict[str, str]],
    board_index: dict[str, dict[str, str]],
    free_agent_candidates: list[dict[str, object]],
) -> tuple[list[dict[str, str]], dict[str, object]]:
    roster = merge_roster_rows(roster_rows, board_index)
    mlb_roster = [player for player in roster if not is_minor_roster_bucket(player) and not is_il_roster_bucket(player)]
    available_roster = [player for player in mlb_roster if is_major_league_level(player)]
    il_players = [player for player in roster if is_il_roster_bucket(player)]
    minors = [player for player in roster if is_minor_roster_bucket(player)]
    optimized = optimize_roster(available_roster)
    lineup_rows = build_lineup_rows(team_name, roster_rows, board_index, week)
    il_move_recommendations = build_il_move_recommendations(team_name, available_roster, il_players, free_agent_candidates)

    recommendations = []
    for candidate in minors:
        evaluation = evaluate_minor_promotion(candidate, available_roster)
        if evaluation["recommendation"].startswith("Move to MLB roster"):
            recommendations.append(
                {
                    "player_name": clean_value(str(candidate.get("player_name", ""))),
                    "player_type": clean_value(str(candidate.get("player_type", ""))),
                    "eligible_positions": clean_value(str(candidate.get("eligible_positions", ""))),
                    "mlb_team": clean_value(str(candidate.get("mlb_team", ""))),
                    "current_level": clean_value(str(candidate.get("current_level", ""))),
                    **evaluation,
                }
            )

    recommendations.sort(
        key=lambda row: (
            0 if row["projected_role_if_promoted"] == "Starter" else 1,
            -float(row["improvement"]),
            -float(row["candidate_projection_value"]),
            row["player_name"],
        )
    )

    return lineup_rows, {
        "team": team_name,
        "week": week,
        "mlb_bucket_count": len(mlb_roster),
        "il_bucket_count": len(il_players),
        "minor_bucket_count": len(minors),
        "active_hitter_count": len(optimized["active_hitters"]),
        "active_pitcher_count": len(optimized["active_pitchers"]),
        "bench_count": len(optimized["bench_players"]),
        "active_hitters": [summarize_player(player) for player in optimized["active_hitters"]],
        "active_pitchers": [summarize_player(player) for player in optimized["active_pitchers"]],
        "bench": [summarize_player(player) for player in optimized["bench_players"]],
        "recommended_il_moves": il_move_recommendations,
        "recommended_minor_promotions": recommendations,
    }


def build_report(week: str) -> tuple[list[dict[str, str]], dict[str, object]]:
    settings = read_settings()
    board_rows = read_csv_rows(BOARD_PATH)
    board_index = board_index_rows(board_rows)
    lineup_rows: list[dict[str, str]] = []
    teams: list[dict[str, object]] = []
    rostered_keys: set[str] = set()
    roster_rows_by_team: list[tuple[Path, list[dict[str, str]]]] = []

    for roster_path in roster_order(ROSTERS_DIR, settings):
        roster_rows = read_csv_rows(roster_path)
        roster_rows_by_team.append((roster_path, roster_rows))
        for row in roster_rows:
            key = canonical_roster_key(row, board_index)
            if key:
                rostered_keys.add(key)

    free_agent_candidates = build_free_agent_candidates(board_rows, rostered_keys)

    for roster_path, roster_rows in roster_rows_by_team:
        team_name = team_name_from_path(roster_path)
        team_lineup_rows, team_report = build_team_report(week, team_name, roster_rows, board_index, free_agent_candidates)
        lineup_rows.extend(team_lineup_rows)
        teams.append(team_report)

    teams_with_promotions = [team for team in teams if team["recommended_minor_promotions"]]
    teams_with_il_moves = [team for team in teams if team["recommended_il_moves"]]
    total_recommendations = sum(len(team["recommended_minor_promotions"]) for team in teams)
    total_il_moves = sum(len(team["recommended_il_moves"]) for team in teams)

    return lineup_rows, {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
        "week": week,
        "summary": {
            "teams_checked": len(teams),
            "teams_with_recommended_il_moves": len(teams_with_il_moves),
            "teams_with_recommended_promotions": len(teams_with_promotions),
            "total_il_move_recommendations": total_il_moves,
            "total_promotion_recommendations": total_recommendations,
        },
        "teams": teams,
    }


def build_csv_rows(report: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    auto_apply_by_team: dict[str, list[dict[str, object]]] = {}
    for move in report.get("auto_apply", {}).get("applied_il_moves", []):
        team_name = clean_value(str(move.get("team", "")))
        if team_name:
            auto_apply_by_team.setdefault(team_name, []).append(move)
    for team in report.get("teams", []):
        team_name = clean_value(str(team.get("team", "")))
        for applied_move in auto_apply_by_team.get(team_name, []):
            rows.append(
                {
                    "week": report.get("week", ""),
                    "team": team_name,
                    "recommendation_type": "auto-applied-il-add",
                    "trigger_player_name": applied_move.get("injured_player_name", ""),
                    "trigger_reason": applied_move.get("injury_status", ""),
                    "recommendation": "Auto-applied IL move and replacement add",
                    "player_name": applied_move.get("replacement_player_name", ""),
                    "player_type": applied_move.get("replacement_player_type", ""),
                    "eligible_positions": applied_move.get("replacement_positions", ""),
                    "current_level": "",
                    "projected_role_if_promoted": "",
                    "projected_slot_if_promoted": "",
                    "candidate_projection_value": "",
                    "drop_candidate_name": "",
                    "drop_candidate_role": "",
                    "drop_candidate_value": "",
                    "improvement": "",
                    "rationale": "Applied automatically before rebuilding the weekly lineup and decision outputs.",
                }
            )
        il_moves = team.get("recommended_il_moves", [])
        recommendations = team.get("recommended_minor_promotions", [])
        if not il_moves and not recommendations:
            rows.append(
                {
                    "week": report.get("week", ""),
                    "team": team_name,
                    "recommendation_type": "no-change",
                    "trigger_player_name": "",
                    "trigger_reason": "",
                    "recommendation": "No change recommended",
                    "player_name": "",
                    "player_type": "",
                    "eligible_positions": "",
                    "current_level": "",
                    "projected_role_if_promoted": "",
                    "projected_slot_if_promoted": "",
                    "candidate_projection_value": "",
                    "drop_candidate_name": "",
                    "drop_candidate_role": "",
                    "drop_candidate_value": "",
                    "improvement": "",
                    "rationale": (
                        "Current MLB bucket already optimizes above all rostered minor-league alternatives."
                        if not auto_apply_by_team.get(team_name)
                        else "No additional moves recommended after auto-applying IL updates."
                    ),
                }
            )
            continue
        for il_move in il_moves:
            replacement = il_move.get("replacement_add", {})
            rows.append(
                {
                    "week": report.get("week", ""),
                    "team": team.get("team", ""),
                    "recommendation_type": "injury-il-add",
                    "trigger_player_name": il_move.get("injured_player_name", ""),
                    "trigger_reason": il_move.get("current_injury_status", ""),
                    "recommendation": il_move.get("recommendation", ""),
                    "player_name": replacement.get("player_name", ""),
                    "player_type": replacement.get("player_type", ""),
                    "eligible_positions": replacement.get("eligible_positions", ""),
                    "current_level": replacement.get("current_level", ""),
                    "projected_role_if_promoted": replacement.get("projected_role_if_added", ""),
                    "projected_slot_if_promoted": replacement.get("projected_slot_if_added", ""),
                    "candidate_projection_value": replacement.get("candidate_projection_value", ""),
                    "drop_candidate_name": "",
                    "drop_candidate_role": "",
                    "drop_candidate_value": "",
                    "improvement": replacement.get("candidate_projection_value", ""),
                    "rationale": il_move.get("rationale", ""),
                }
            )
        for recommendation in recommendations:
            drop_candidate = recommendation.get("drop_candidate", {})
            rows.append(
                {
                    "week": report.get("week", ""),
                    "team": team.get("team", ""),
                    "recommendation_type": "minor-promotion",
                    "trigger_player_name": "",
                    "trigger_reason": "",
                    "recommendation": recommendation.get("recommendation", ""),
                    "player_name": recommendation.get("player_name", ""),
                    "player_type": recommendation.get("player_type", ""),
                    "eligible_positions": recommendation.get("eligible_positions", ""),
                    "current_level": recommendation.get("current_level", ""),
                    "projected_role_if_promoted": recommendation.get("projected_role_if_promoted", ""),
                    "projected_slot_if_promoted": recommendation.get("projected_slot_if_promoted", ""),
                    "candidate_projection_value": recommendation.get("candidate_projection_value", ""),
                    "drop_candidate_name": drop_candidate.get("player_name", ""),
                    "drop_candidate_role": drop_candidate.get("current_projected_role", ""),
                    "drop_candidate_value": drop_candidate.get("roster_value", ""),
                    "improvement": recommendation.get("improvement", ""),
                    "rationale": recommendation.get("rationale", ""),
                }
            )
    # FA acquisition rows
    for acq in report.get("fa_acquisitions", {}).get("acquisitions", []):
        rows.append(
            {
                "week": report.get("week", ""),
                "team": acq.get("team", ""),
                "recommendation_type": "fa-acquisition",
                "trigger_player_name": acq.get("dropped_player_name", ""),
                "trigger_reason": f"Weakest active player (value {acq.get('dropped_value', '')})",
                "recommendation": "Drop and add free agent",
                "player_name": acq.get("added_player_name", ""),
                "player_type": acq.get("added_player_type", ""),
                "eligible_positions": acq.get("added_positions", ""),
                "current_level": "",
                "projected_role_if_promoted": "",
                "projected_slot_if_promoted": "",
                "candidate_projection_value": acq.get("added_value", ""),
                "drop_candidate_name": acq.get("dropped_player_name", ""),
                "drop_candidate_role": "",
                "drop_candidate_value": acq.get("dropped_value", ""),
                "improvement": acq.get("improvement", ""),
                "rationale": f"FA acquisition (pass {acq.get('pass', '')}, threshold {acq.get('min_threshold', '')})",
            }
        )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the weekly lineup snapshot plus a current-state active-roster decision report."
    )
    parser.add_argument("--week", required=True, help="Week key such as 2026-week-01")
    parser.add_argument("--lineup-output", help="Optional explicit weekly lineup snapshot path")
    parser.add_argument("--report-json", help="Optional explicit weekly decision JSON path")
    parser.add_argument("--report-csv", help="Optional explicit weekly decision CSV path")
    parser.add_argument(
        "--skip-auto-apply",
        action="store_true",
        help="Do not auto-apply IL moves to manager roster CSVs before building the final report.",
    )
    parser.add_argument(
        "--skip-status-refresh",
        action="store_true",
        help="Do not fetch recent MLB transactions to refresh roster injury and level statuses.",
    )
    parser.add_argument(
        "--skip-fa-acquisitions",
        action="store_true",
        help="Do not run the waiver-order free agent acquisition pass.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    lineup_output = resolve_output_path(args.lineup_output, LINEUP_DIR / f"{args.week}.csv")
    report_json = resolve_output_path(args.report_json, DECISION_DIR / f"{args.week}.json")
    report_csv = resolve_output_path(args.report_csv, DECISION_DIR / f"{args.week}.csv")

    board_rows = read_csv_rows(BOARD_PATH)

    status_refresh_summary: dict[str, object] = {"changes": [], "change_count": 0}
    if not args.skip_status_refresh:
        status_refresh_summary = refresh_roster_statuses(board_rows)

    auto_apply_summary = {
        "applied_il_moves": [],
        "blocked_il_moves": [],
        "applied_count": 0,
        "blocked_count": 0,
    }
    if not args.skip_auto_apply:
        auto_apply_summary = apply_il_moves(board_rows)

    fa_acquisition_summary: dict[str, object] = {"acquisitions": [], "acquisition_count": 0}
    if not args.skip_fa_acquisitions:
        fa_acquisition_summary = apply_fa_acquisitions(board_rows)

    lineup_rows, report = build_report(args.week)
    report["status_refresh"] = status_refresh_summary
    report["auto_apply"] = auto_apply_summary
    report["fa_acquisitions"] = fa_acquisition_summary
    report["output_files"] = {
        "lineup_snapshot": workspace_relative_path(lineup_output),
        "decision_json": workspace_relative_path(report_json),
        "decision_csv": workspace_relative_path(report_csv),
    }

    write_csv(
        lineup_output,
        [
            "week",
            "team",
            "lineup_status",
            "lineup_slot",
            "mlbam_id",
            "player_name",
            "player_type",
            "eligible_positions",
            "mlb_team",
            "current_level",
            "roster_bucket",
            "injury_status",
            "transaction_status",
        ],
        lineup_rows,
    )
    write_json(report_json, report)
    write_csv(
        report_csv,
        [
            "week",
            "team",
            "recommendation_type",
            "trigger_player_name",
            "trigger_reason",
            "recommendation",
            "player_name",
            "player_type",
            "eligible_positions",
            "current_level",
            "projected_role_if_promoted",
            "projected_slot_if_promoted",
            "candidate_projection_value",
            "drop_candidate_name",
            "drop_candidate_role",
            "drop_candidate_value",
            "improvement",
            "rationale",
        ],
        build_csv_rows(report),
    )

    summary = report["summary"]
    print(f"Wrote weekly lineup snapshot to {lineup_output}")
    print(f"Wrote weekly decision JSON report to {report_json}")
    print(f"Wrote weekly decision CSV report to {report_csv}")
    print(
        "Teams with recommended IL moves: "
        f"{summary['teams_with_recommended_il_moves']} / {summary['teams_checked']}"
    )
    print(
        "Teams with recommended promotions: "
        f"{summary['teams_with_recommended_promotions']} / {summary['teams_checked']}"
    )
    print(f"Total IL move recommendations: {summary['total_il_move_recommendations']}")
    print(f"Total promotion recommendations: {summary['total_promotion_recommendations']}")
    print(f"Status refresh updates: {status_refresh_summary['change_count']}")
    print(f"Auto-applied IL moves: {auto_apply_summary['applied_count']}")
    print(f"Blocked auto-applied IL moves: {auto_apply_summary['blocked_count']}")
    print(f"FA acquisitions: {fa_acquisition_summary['acquisition_count']}")


if __name__ == "__main__":
    main()