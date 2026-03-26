from __future__ import annotations

import argparse
import csv
import json
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from itertools import product
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = WORKSPACE_ROOT / "data"
ROSTERS_DIR = WORKSPACE_ROOT / "manager-rosters"
BOARD_PATH = DATA_DIR / "draft-board-input-2026.csv"
SETTINGS_PATH = DATA_DIR / "startup-draft-settings-2026.json"
OUTPUT_JSON_PATH = DATA_DIR / "minor-league-eligibility-report-2026.json"
OUTPUT_CSV_PATH = DATA_DIR / "minor-league-eligibility-report-2026.csv"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0 Safari/537.36"

ACTIVE_HITTER_SLOTS = ["C", "1B", "2B", "3B", "SS", "CI", "MI", "OF", "OF", "OF", "OF", "OF", "UTIL"]
PITCHER_SLOTS = 9
HITTER_AB_THRESHOLD = 130
PITCHER_OUT_THRESHOLD = 150
TOP_DROP_CANDIDATES = 5
TOP_MINOR_ADD_CANDIDATES = 8


def clean_value(value: str | None) -> str:
    return (value or "").strip()


def normalize_name(name: str) -> str:
    return " ".join(clean_value(name).lower().replace(".", " ").replace("-", " ").split())


def parse_float(value: str | None) -> float:
    text = clean_value(value)
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_int(value: str | None) -> int:
    number = parse_float(value)
    return int(number) if number else 0


def parse_innings_to_outs(value: str | None) -> int:
    text = clean_value(value)
    if not text:
        return 0
    if "." not in text:
        return parse_int(text) * 3
    whole, fraction = text.split(".", 1)
    outs = parse_int(whole) * 3
    if fraction == "1":
        return outs + 1
    if fraction == "2":
        return outs + 2
    if fraction in {"", "0"}:
        return outs
    return int(round(parse_float(text) * 3))


def outs_to_display_innings(outs: int) -> str:
    whole = outs // 3
    remainder = outs % 3
    return f"{whole}.{remainder}"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_settings() -> dict:
    return read_json(SETTINGS_PATH)


def workspace_relative_path(path: Path) -> str:
    return str(path.relative_to(WORKSPACE_ROOT)).replace("\\", "/")


def player_key(row: dict[str, str] | dict[str, object]) -> str:
    mlbam_id = clean_value(str(row.get("mlbam_id", "")))
    return mlbam_id or normalize_name(str(row.get("player_name", "")))


def dedupe_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
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
        existing = merged_by_key[key]
        for field, value in row.items():
            if not clean_value(existing.get(field)) and clean_value(value):
                existing[field] = value
    return [merged_by_key[key] for key in order]


def board_index_rows(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for row in dedupe_rows(rows):
        mlbam_id = clean_value(row.get("mlbam_id"))
        if mlbam_id:
            index[mlbam_id] = row
        name_key = normalize_name(row.get("player_name", ""))
        if name_key:
            index[name_key] = row
    return index


def roster_order(settings: dict) -> list[Path]:
    configured_order = settings.get("draft_order") or []
    roster_paths = sorted(ROSTERS_DIR.glob("*-roster.csv"))
    file_by_name = {clean_value(path.stem.replace("-roster", "").replace("-", " ")).title(): path for path in roster_paths}
    ordered_paths: list[Path] = []
    for team_name in configured_order:
        normalized_target = normalize_name(team_name)
        for display_name, roster_path in file_by_name.items():
            if normalize_name(display_name) == normalized_target and roster_path not in ordered_paths:
                ordered_paths.append(roster_path)
                break
    for roster_path in roster_paths:
        if roster_path not in ordered_paths:
            ordered_paths.append(roster_path)
    return ordered_paths


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def career_stats_url(group: str) -> str:
    query = urllib.parse.urlencode(
        {
            "stats": "career",
            "group": group,
            "playerPool": "ALL",
            "limit": 20000,
        }
    )
    return f"https://statsapi.mlb.com/api/v1/stats?{query}"


def build_stat_map(group: str) -> dict[str, dict]:
    payload = fetch_json(career_stats_url(group))
    splits = payload.get("stats", [{}])[0].get("splits", [])
    return {str(split.get("player", {}).get("id", "")): split for split in splits if split.get("player", {}).get("id")}


def eligible_positions(player: dict[str, object]) -> list[str]:
    value = clean_value(str(player.get("eligible_positions", "")))
    return [position for position in value.split("/") if position]


def is_pitcher(player: dict[str, object]) -> bool:
    player_type = clean_value(str(player.get("player_type", "")))
    return player_type in {"pitcher", "two-way"} and bool(parse_float(str(player.get("proj_ip", 0.0))))


def is_hitter(player: dict[str, object]) -> bool:
    player_type = clean_value(str(player.get("player_type", "")))
    return player_type in {"hitter", "two-way"} and bool(parse_float(str(player.get("proj_pa", 0.0))))


def can_fill_slot(player: dict[str, object], slot: str) -> bool:
    positions = set(eligible_positions(player))
    if slot == "UTIL":
        return is_hitter(player)
    if slot == "CI":
        return bool(positions.intersection({"1B", "3B"}))
    if slot == "MI":
        return bool(positions.intersection({"2B", "SS"}))
    if slot == "OF":
        return bool(positions.intersection({"OF", "LF", "CF", "RF"}))
    return slot in positions


def hitter_value(player: dict[str, object]) -> float:
    return (
        parse_float(str(player.get("proj_r", 0.0))) * 1.0
        + parse_float(str(player.get("proj_hr", 0.0))) * 4.0
        + parse_float(str(player.get("proj_rbi", 0.0))) * 1.2
        + parse_float(str(player.get("proj_sb", 0.0))) * 4.5
        + max(parse_float(str(player.get("proj_obp", 0.0))) - 0.3, 0.0) * 320.0
    )


def pitcher_value(player: dict[str, object]) -> float:
    return (
        parse_float(str(player.get("proj_w", 0.0))) * 4.0
        + parse_float(str(player.get("proj_k", 0.0))) * 0.85
        + parse_float(str(player.get("proj_sv", 0.0))) * 5.0
        + max(4.2 - parse_float(str(player.get("proj_era", 9.99))), 0.0) * 30.0
        + max(1.3 - parse_float(str(player.get("proj_whip", 9.99))), 0.0) * 100.0
    )


def assign_best_hitter_lineup(players: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    slots = list(ACTIVE_HITTER_SLOTS)
    ordered_players = sorted(players, key=hitter_value, reverse=True)
    active_assignment: list[tuple[str, dict[str, object]]] = []
    used_keys: set[str] = set()

    for slot in slots:
        for player in ordered_players:
            key = player_key(player)
            if key in used_keys:
                continue
            if can_fill_slot(player, slot):
                active_assignment.append((slot, player))
                used_keys.add(key)
                break

    active_keys = {player_key(player) for _, player in active_assignment}
    active = []
    for slot, player in active_assignment:
        active_player = dict(player)
        active_player["lineup_slot"] = slot
        active.append(active_player)
    bench = [dict(player) for player in players if player_key(player) not in active_keys]
    bench.sort(key=hitter_value, reverse=True)
    return active, bench


def assign_pitchers(players: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    ordered_players = sorted(players, key=pitcher_value, reverse=True)
    active = []
    for index, player in enumerate(ordered_players[:PITCHER_SLOTS], start=1):
        active_player = dict(player)
        active_player["lineup_slot"] = f"P{index}"
        active.append(active_player)
    bench = [dict(player) for player in ordered_players[PITCHER_SLOTS:]]
    return active, bench


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


def projected_active_key_set(players: list[dict[str, object]]) -> set[str]:
    two_way_players = [player for player in players if clean_value(str(player.get("player_type", ""))) == "two-way"]
    scenario_labels = ["hitter", "pitcher"] if two_way_players else [""]
    best_keys: set[str] = set()
    best_score = float("-inf")

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
        score = sum(hitter_value(player) for player in active_hitters) + sum(pitcher_value(player) for player in active_pitchers)
        if score > best_score:
            best_score = score
            best_keys = {player_key(player) for player in [*active_hitters, *active_pitchers]}

    return best_keys


def current_level_priority(level: str) -> int:
    normalized = clean_value(level).upper()
    priority = {
        "MLB": 6,
        "AAA": 5,
        "AA": 4,
        "HIGH-A": 3,
        "A+": 3,
        "SINGLE-A": 2,
        "LOW-A": 2,
        "ROOKIE": 1,
        "PROSPECT": 1,
    }
    return priority.get(normalized, 0)


def dynasty_rank_value(row: dict[str, object]) -> int:
    value = parse_int(str(row.get("dynasty_rank", "")))
    return value if value > 0 else 999999


def adp_value(row: dict[str, object]) -> float:
    value = parse_float(str(row.get("adp", "")))
    return value if value > 0 else 999999.0


def prospect_rank_value(row: dict[str, object]) -> int:
    value = parse_int(str(row.get("prospect_rank", "")))
    return value if value > 0 else 999999


def player_projection_value(player: dict[str, object]) -> float:
    if is_pitcher(player) and not is_hitter(player):
        return pitcher_value(player)
    if is_hitter(player) and not is_pitcher(player):
        return hitter_value(player)
    return max(hitter_value(player), pitcher_value(player))


def merge_roster_with_board(roster_row: dict[str, str], board_index: dict[str, dict[str, str]]) -> dict[str, object]:
    joined = dict(board_index.get(player_key(roster_row), {}))
    joined.update(roster_row)
    joined["mlbam_id"] = clean_value(str(joined.get("mlbam_id", "")))
    joined["player_name"] = clean_value(str(joined.get("player_name", "")))
    joined["player_type"] = clean_value(str(joined.get("player_type", "")))
    joined["roster_bucket"] = clean_value(str(joined.get("roster_bucket", "")))
    joined["current_level"] = clean_value(str(joined.get("current_level", "")))
    joined["mlb_team"] = clean_value(str(joined.get("mlb_team", ""))) or clean_value(str(joined.get("proj_team", "")))
    return joined


def career_snapshot(player: dict[str, object], hitting_map: dict[str, dict], pitching_map: dict[str, dict]) -> dict[str, object]:
    mlbam_id = clean_value(str(player.get("mlbam_id", "")))
    hitting_row = hitting_map.get(mlbam_id, {}) if mlbam_id else {}
    pitching_row = pitching_map.get(mlbam_id, {}) if mlbam_id else {}
    hitting_stat = hitting_row.get("stat", {})
    pitching_stat = pitching_row.get("stat", {})
    career_ab = parse_int(str(hitting_stat.get("atBats", "")))
    career_pa = parse_int(str(hitting_stat.get("plateAppearances", "")))
    career_outs = parse_innings_to_outs(str(pitching_stat.get("inningsPitched", "")))
    career_ip = outs_to_display_innings(career_outs) if career_outs else "0.0"
    actual_team = clean_value(str(hitting_row.get("team", {}).get("abbreviation", ""))) or clean_value(str(pitching_row.get("team", {}).get("abbreviation", "")))
    player_type = clean_value(str(player.get("player_type", "")))
    exceeds_hitter = career_ab >= HITTER_AB_THRESHOLD
    exceeds_pitcher = career_outs >= PITCHER_OUT_THRESHOLD
    if player_type == "pitcher":
        ineligible = exceeds_pitcher
        reason = f"Exceeded pitching threshold with {career_ip} MLB innings ({career_outs} outs)." if ineligible else "Still under the 50 MLB inning limit."
    elif player_type == "hitter":
        ineligible = exceeds_hitter
        reason = f"Exceeded hitter threshold with {career_ab} MLB at-bats." if ineligible else "Still under the 130 MLB at-bat limit."
    else:
        ineligible = exceeds_hitter or exceeds_pitcher
        if ineligible:
            pieces = []
            if exceeds_hitter:
                pieces.append(f"{career_ab} MLB at-bats")
            if exceeds_pitcher:
                pieces.append(f"{career_ip} MLB innings")
            reason = "Exceeded minor-league eligibility threshold with " + " and ".join(pieces) + "."
        else:
            reason = "Still under both the hitter and pitcher MLB thresholds."
    return {
        "career_ab": career_ab,
        "career_pa": career_pa,
        "career_ip": career_ip,
        "career_outs": career_outs,
        "career_team": actual_team,
        "ineligible_for_minors": ineligible,
        "reason": reason,
    }


def is_minor_roster_player(player: dict[str, object]) -> bool:
    return clean_value(str(player.get("roster_bucket", ""))).upper() == "MINORS"


def is_acquired_by_org(row: dict[str, object]) -> bool:
    if not clean_value(str(row.get("mlbam_id", ""))):
        return False
    if clean_value(str(row.get("parent_org_name", ""))) or clean_value(str(row.get("affiliated_team", ""))):
        return True
    team = clean_value(str(row.get("team", ""))).upper()
    mlb_team = clean_value(str(row.get("mlb_team", ""))).upper()
    return team not in {"", "FA"} or mlb_team not in {"", "FA"}


def minor_add_sort_key(row: dict[str, object]) -> tuple[object, ...]:
    player_stage = clean_value(str(row.get("player_stage", ""))).upper()
    return (
        0 if player_stage == "PROSPECT" else 1,
        dynasty_rank_value(row),
        prospect_rank_value(row),
        adp_value(row),
        -current_level_priority(str(row.get("current_level", ""))),
        parse_float(str(row.get("age", 99.0))) or 99.0,
        clean_value(str(row.get("player_name", ""))),
    )


def build_minor_add_candidates(
    board_rows: list[dict[str, str]],
    rostered_keys: set[str],
    hitting_map: dict[str, dict],
    pitching_map: dict[str, dict],
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for board_row in dedupe_rows(board_rows):
        key = player_key(board_row)
        if not key or key in rostered_keys:
            continue
        if not is_acquired_by_org(board_row):
            continue
        merged = dict(board_row)
        snapshot = career_snapshot(merged, hitting_map, pitching_map)
        if snapshot["ineligible_for_minors"]:
            continue
        merged.update(snapshot)
        candidates.append(merged)
    candidates.sort(key=minor_add_sort_key)
    return candidates


def drop_candidate_sort_key(player: dict[str, object]) -> tuple[object, ...]:
    projected_role = clean_value(str(player.get("projected_role", "")))
    return (
        0 if projected_role == "Reserve" else 1,
        player_projection_value(player),
        dynasty_rank_value(player),
        adp_value(player),
        -(parse_float(str(player.get("age", 0.0))) or 0.0),
        clean_value(str(player.get("player_name", ""))),
    )


def build_drop_candidates(team_players: list[dict[str, object]], excluded_keys: set[str]) -> list[dict[str, object]]:
    mlb_players = [player for player in team_players if not is_minor_roster_player(player) and player_key(player) not in excluded_keys]
    active_keys = projected_active_key_set(mlb_players)
    for player in mlb_players:
        player["projected_role"] = "Active" if player_key(player) in active_keys else "Reserve"
    mlb_players.sort(key=drop_candidate_sort_key)
    return mlb_players[:TOP_DROP_CANDIDATES]


def evaluate_offender_action(offender: dict[str, object], team_players: list[dict[str, object]], excluded_keys: set[str]) -> dict[str, object]:
    mlb_players = [player for player in team_players if not is_minor_roster_player(player) and player_key(player) not in excluded_keys]
    promoted_offender = dict(offender)
    promoted_offender["roster_bucket"] = "MLB"
    optimized = optimize_roster(mlb_players + [promoted_offender])

    active_role_map: dict[str, str] = {}
    for player in optimized["active_hitters"]:
        active_role_map[player_key(player)] = clean_value(str(player.get("lineup_slot", ""))) or "Active"
    for player in optimized["active_pitchers"]:
        active_role_map[player_key(player)] = clean_value(str(player.get("lineup_slot", ""))) or "Active"
    for player in optimized["bench_players"]:
        active_role_map[player_key(player)] = "Bench"

    offender_key = player_key(promoted_offender)
    offender_role = active_role_map.get(offender_key, "Bench")
    offender_is_starter = offender_role != "Bench"

    drop_candidates = build_drop_candidates(team_players, excluded_keys)
    best_drop = drop_candidates[0] if drop_candidates else None
    offender_value = round(player_projection_value(promoted_offender), 1)
    best_drop_value = round(player_projection_value(best_drop), 1) if best_drop else 0.0

    if offender_is_starter:
        recommended_action = "Promote to MLB roster as starter"
        rationale = f"Would enter the active lineup at {offender_role} under the current optimizer."
    elif best_drop and player_projection_value(promoted_offender) > player_projection_value(best_drop):
        recommended_action = "Promote to MLB roster as bench player"
        rationale = "Profiles as a better MLB-bucket hold than the weakest current MLB roster player, even though the player would open on the fantasy bench."
    else:
        recommended_action = "Drop from minor league roster"
        rationale = "Does not currently project better than the weakest MLB-bucket alternative, so the cleaner forced-move path is to cut the offender and refill the minors slot."

    return {
        "recommended_action": recommended_action,
        "projected_role_if_promoted": "Starter" if offender_is_starter else "Bench",
        "projected_slot_if_promoted": offender_role if offender_is_starter else "",
        "offender_projection_value": offender_value,
        "suggested_mlb_drop": {
            "player_name": clean_value(str(best_drop.get("player_name", ""))) if best_drop else "",
            "mlb_team": clean_value(str(best_drop.get("mlb_team", ""))) if best_drop else "",
            "player_type": clean_value(str(best_drop.get("player_type", ""))) if best_drop else "",
            "projected_role": clean_value(str(best_drop.get("projected_role", ""))) if best_drop else "",
            "projection_value": best_drop_value,
        },
        "decision_rationale": rationale,
    }


def build_team_report(
    team_name: str,
    team_players: list[dict[str, object]],
    hitting_map: dict[str, dict],
    pitching_map: dict[str, dict],
    minor_add_candidates: list[dict[str, object]],
) -> dict[str, object]:
    minors = [player for player in team_players if is_minor_roster_player(player)]
    offenders: list[dict[str, object]] = []
    unevaluated: list[str] = []

    for player in minors:
        if not clean_value(str(player.get("mlbam_id", ""))):
            unevaluated.append(clean_value(str(player.get("player_name", ""))))
            continue
        snapshot = career_snapshot(player, hitting_map, pitching_map)
        player_report = {
            "player_name": clean_value(str(player.get("player_name", ""))),
            "mlbam_id": clean_value(str(player.get("mlbam_id", ""))),
            "player_type": clean_value(str(player.get("player_type", ""))),
            "mlb_team": clean_value(str(player.get("mlb_team", ""))) or clean_value(str(snapshot.get("career_team", ""))),
            "current_level": clean_value(str(player.get("current_level", ""))),
            "dynasty_rank": clean_value(str(player.get("dynasty_rank", ""))),
            "adp": clean_value(str(player.get("adp", ""))),
            "career_ab": int(snapshot["career_ab"]),
            "career_pa": int(snapshot["career_pa"]),
            "career_ip": clean_value(str(snapshot["career_ip"])),
            "career_outs": int(snapshot["career_outs"]),
            "reason": clean_value(str(snapshot["reason"])),
            "resolution_paths": [
                "Drop this player, then add a new eligible minor leaguer to restore the 15-player minors list.",
                "Promote this player to the MLB bucket, drop one MLB player, then add a new eligible minor leaguer.",
            ],
        }
        if snapshot["ineligible_for_minors"]:
            offenders.append(player_report)

    offender_keys = {clean_value(str(item.get("mlbam_id", ""))) or normalize_name(str(item.get("player_name", ""))) for item in offenders}
    drop_candidates = build_drop_candidates(team_players, offender_keys)
    offender_lookup = {player_key(player): player for player in minors}
    for offender in offenders:
        decision = evaluate_offender_action(offender_lookup[player_key(offender)], team_players, offender_keys)
        offender.update(decision)
    team_add_candidates = minor_add_candidates[:TOP_MINOR_ADD_CANDIDATES]
    notes = []
    if offenders:
        notes.append(
            f"{len(offenders)} minor leaguer(s) lost eligibility. Each resolution requires the minors slot to be refilled with a new eligible player."
        )
        notes.append("Offender-level recommendations classify each forced move as a promotion to the MLB roster or a direct drop from the minors list based on the current lineup optimizer.")
    if unevaluated:
        notes.append("Unable to evaluate these minors because no MLBAM ID was available: " + ", ".join(sorted(unevaluated)))

    return {
        "team": team_name,
        "roster_count": len(team_players),
        "mlb_bucket_count": len([player for player in team_players if not is_minor_roster_player(player)]),
        "minor_bucket_count": len(minors),
        "offender_count": len(offenders),
        "requires_action": bool(offenders),
        "offenders": offenders,
        "suggested_mlb_drops": [
            {
                "player_name": clean_value(str(player.get("player_name", ""))),
                "mlb_team": clean_value(str(player.get("mlb_team", ""))),
                "player_type": clean_value(str(player.get("player_type", ""))),
                "projected_role": clean_value(str(player.get("projected_role", ""))),
                "current_level": clean_value(str(player.get("current_level", ""))),
                "dynasty_rank": clean_value(str(player.get("dynasty_rank", ""))),
                "adp": clean_value(str(player.get("adp", ""))),
                "projection_value": round(player_projection_value(player), 1),
            }
            for player in drop_candidates
        ],
        "suggested_minor_adds": [
            {
                "player_name": clean_value(str(player.get("player_name", ""))),
                "mlb_team": clean_value(str(player.get("mlb_team", ""))) or clean_value(str(player.get("team", ""))),
                "player_type": clean_value(str(player.get("player_type", ""))),
                "current_level": clean_value(str(player.get("current_level", ""))),
                "player_stage": clean_value(str(player.get("player_stage", ""))),
                "dynasty_rank": clean_value(str(player.get("dynasty_rank", ""))),
                "prospect_rank": clean_value(str(player.get("prospect_rank", ""))),
                "adp": clean_value(str(player.get("adp", ""))),
                "career_ab": int(player.get("career_ab", 0)),
                "career_ip": clean_value(str(player.get("career_ip", "0.0"))),
            }
            for player in team_add_candidates
        ],
        "notes": notes,
    }


def build_report(board_rows: list[dict[str, str]], hitting_map: dict[str, dict], pitching_map: dict[str, dict]) -> dict[str, object]:
    settings = read_settings()
    board_index = board_index_rows(board_rows)
    team_reports = []
    rostered_keys: set[str] = set()
    team_players_by_name: dict[str, list[dict[str, object]]] = {}

    for roster_path in roster_order(settings):
        team_name = clean_value(roster_path.stem.replace("-roster", "").replace("-", " ")).title()
        players = [merge_roster_with_board(row, board_index) for row in read_csv_rows(roster_path)]
        team_players_by_name[team_name] = players
        for player in players:
            key = player_key(player)
            if key:
                rostered_keys.add(key)

    minor_add_candidates = build_minor_add_candidates(board_rows, rostered_keys, hitting_map, pitching_map)

    for team_name in team_players_by_name:
        team_reports.append(build_team_report(team_name, team_players_by_name[team_name], hitting_map, pitching_map, minor_add_candidates))

    teams_requiring_action = [team for team in team_reports if team["requires_action"]]
    total_offenders = sum(int(team["offender_count"]) for team in team_reports)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "season": 2026,
        "thresholds": {
            "hitters_at_bats": HITTER_AB_THRESHOLD,
            "pitchers_innings_pitched": 50,
            "pitchers_outs": PITCHER_OUT_THRESHOLD,
        },
        "sources": {
            "rosters": "manager-rosters/*.csv",
            "draft_board": workspace_relative_path(BOARD_PATH),
            "career_stats": "MLB Stats API career totals",
        },
        "summary": {
            "teams_checked": len(team_reports),
            "teams_requiring_action": len(teams_requiring_action),
            "total_ineligible_minor_leaguers": total_offenders,
            "replacement_minor_pool_size": len(minor_add_candidates),
        },
        "teams": team_reports,
        "output_files": {
            "json": workspace_relative_path(OUTPUT_JSON_PATH),
            "csv": workspace_relative_path(OUTPUT_CSV_PATH),
        },
    }


def build_csv_rows(report: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for team in report.get("teams", []):
        drop_names = "; ".join(candidate["player_name"] for candidate in team.get("suggested_mlb_drops", []))
        add_names = "; ".join(candidate["player_name"] for candidate in team.get("suggested_minor_adds", []))
        for offender in team.get("offenders", []):
            suggested_drop = offender.get("suggested_mlb_drop", {})
            rows.append(
                {
                    "team": team.get("team", ""),
                    "player_name": offender.get("player_name", ""),
                    "mlbam_id": offender.get("mlbam_id", ""),
                    "player_type": offender.get("player_type", ""),
                    "mlb_team": offender.get("mlb_team", ""),
                    "current_level": offender.get("current_level", ""),
                    "career_ab": offender.get("career_ab", 0),
                    "career_ip": offender.get("career_ip", "0.0"),
                    "career_outs": offender.get("career_outs", 0),
                    "reason": offender.get("reason", ""),
                    "recommended_action": offender.get("recommended_action", ""),
                    "projected_role_if_promoted": offender.get("projected_role_if_promoted", ""),
                    "projected_slot_if_promoted": offender.get("projected_slot_if_promoted", ""),
                    "offender_projection_value": offender.get("offender_projection_value", 0.0),
                    "decision_rationale": offender.get("decision_rationale", ""),
                    "suggested_single_mlb_drop": suggested_drop.get("player_name", ""),
                    "drop_offender_path": "Drop offender, then add a new eligible minor leaguer.",
                    "promotion_path": "Promote offender, drop one MLB player, then add a new eligible minor leaguer.",
                    "suggested_mlb_drop_candidates": drop_names,
                    "suggested_minor_add_candidates": add_names,
                }
            )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check rostered minor leaguers for lost eligibility and suggest the downstream roster moves required to regain compliance."
    )
    parser.add_argument("--output-json", default=str(OUTPUT_JSON_PATH), help="Path for the JSON report output")
    parser.add_argument("--output-csv", default=str(OUTPUT_CSV_PATH), help="Path for the CSV report output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    board_rows = read_csv_rows(BOARD_PATH)
    hitting_map = build_stat_map("hitting")
    pitching_map = build_stat_map("pitching")
    report = build_report(board_rows, hitting_map, pitching_map)

    output_json_path = Path(args.output_json)
    output_csv_path = Path(args.output_csv)
    write_json(output_json_path, report)
    write_csv(
        output_csv_path,
        [
            "team",
            "player_name",
            "mlbam_id",
            "player_type",
            "mlb_team",
            "current_level",
            "career_ab",
            "career_ip",
            "career_outs",
            "reason",
            "recommended_action",
            "projected_role_if_promoted",
            "projected_slot_if_promoted",
            "offender_projection_value",
            "decision_rationale",
            "suggested_single_mlb_drop",
            "drop_offender_path",
            "promotion_path",
            "suggested_mlb_drop_candidates",
            "suggested_minor_add_candidates",
        ],
        build_csv_rows(report),
    )

    summary = report["summary"]
    print(f"Wrote minor-league eligibility JSON report to {output_json_path}")
    print(f"Wrote minor-league eligibility CSV report to {output_csv_path}")
    print(
        "Teams requiring action: "
        f"{summary['teams_requiring_action']} / {summary['teams_checked']}"
    )
    print(f"Total ineligible minor leaguers: {summary['total_ineligible_minor_leaguers']}")
    for team in report["teams"]:
        if not team["requires_action"]:
            continue
        names = ", ".join(player["player_name"] for player in team["offenders"])
        print(f"- {team['team']}: {team['offender_count']} offender(s) -> {names}")


if __name__ == "__main__":
    main()