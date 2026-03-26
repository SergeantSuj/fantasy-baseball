from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from itertools import product
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = WORKSPACE_ROOT / "data"
ROSTERS_DIR = WORKSPACE_ROOT / "manager-rosters"
SETTINGS_PATH = DATA_DIR / "startup-draft-settings-2026.json"
BOARD_PATH = DATA_DIR / "draft-board-input-2026.csv"
RESULTS_PATH = DATA_DIR / "season-results-2026.json"

OUTPUT_DIR = WORKSPACE_ROOT / "docs"
OUTPUT_DATA_DIR = OUTPUT_DIR / "data"
OUTPUT_JSON_PATH = OUTPUT_DATA_DIR / "league-site-data.json"

ACTIVE_HITTER_SLOTS = ["C", "1B", "2B", "3B", "SS", "CI", "MI", "OF", "OF", "OF", "OF", "OF", "UTIL"]
PITCHER_SLOTS = 9

DISPLAY_COLUMNS = [
    "player_name",
    "mlb_team",
    "eligible_positions",
    "age",
    "dynasty_rank",
    "adp",
    "injury_status",
    "transaction_status",
    "roster_bucket",
]


@dataclass(frozen=True)
class CategoryRule:
    key: str
    higher_is_better: bool
    label: str


CATEGORY_RULES = [
    CategoryRule("runs", True, "R"),
    CategoryRule("home_runs", True, "HR"),
    CategoryRule("rbi", True, "RBI"),
    CategoryRule("stolen_bases", True, "SB"),
    CategoryRule("obp", True, "OBP"),
    CategoryRule("wins", True, "W"),
    CategoryRule("strikeouts", True, "K"),
    CategoryRule("saves", True, "SV"),
    CategoryRule("era", False, "ERA"),
    CategoryRule("whip", False, "WHIP"),
]


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


def round_number(value: float, digits: int = 1) -> float:
    return round(value, digits)


def zero_category_totals() -> dict[str, float]:
    return {
        "runs": 0.0,
        "home_runs": 0.0,
        "rbi": 0.0,
        "stolen_bases": 0.0,
        "obp": 0.0,
        "wins": 0.0,
        "strikeouts": 0.0,
        "saves": 0.0,
        "era": 0.0,
        "whip": 0.0,
    }


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def read_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))


def player_key(row: dict[str, str]) -> str:
    mlbam_id = clean_value(row.get("mlbam_id"))
    return mlbam_id or normalize_name(row.get("player_name", ""))


def board_index_rows(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for row in rows:
        mlbam_id = clean_value(row.get("mlbam_id"))
        if mlbam_id:
            index[mlbam_id] = row
        index[normalize_name(row.get("player_name", ""))] = row
    return index


def eligible_positions(player: dict[str, object]) -> list[str]:
    value = clean_value(str(player.get("eligible_positions", "")))
    return [position for position in value.split("/") if position]


def is_pitcher(player: dict[str, object]) -> bool:
    return clean_value(str(player.get("player_type", ""))) in {"pitcher", "two-way"} and bool(parse_float(str(player.get("proj_ip", 0.0))))


def is_hitter(player: dict[str, object]) -> bool:
    return clean_value(str(player.get("player_type", ""))) in {"hitter", "two-way"} and bool(parse_float(str(player.get("proj_pa", 0.0))))


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


def roster_order(path: Path, settings: dict) -> list[Path]:
    configured_order = settings.get("draft_order") or []
    file_by_name = {clean_value(item.stem.replace("-roster", "").replace("-", " ")).title(): item for item in sorted(path.glob("*-roster.csv"))}
    ordered_files: list[Path] = []
    for team_name in configured_order:
        slug_key = clean_value(team_name)
        for display_name, file_path in file_by_name.items():
            if normalize_name(display_name) == normalize_name(slug_key):
                ordered_files.append(file_path)
                break
    remaining = [item for item in sorted(path.glob("*-roster.csv")) if item not in ordered_files]
    return ordered_files + remaining


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


def aggregate_hitting(players: list[dict[str, object]]) -> dict[str, float]:
    totals = {
        "runs": 0.0,
        "home_runs": 0.0,
        "rbi": 0.0,
        "stolen_bases": 0.0,
        "hits": 0.0,
        "walks": 0.0,
        "hbp": 0.0,
        "at_bats": 0.0,
        "sac_flies": 0.0,
        "plate_appearances": 0.0,
    }
    for player in players:
        totals["runs"] += parse_float(str(player.get("proj_r", 0.0)))
        totals["home_runs"] += parse_float(str(player.get("proj_hr", 0.0)))
        totals["rbi"] += parse_float(str(player.get("proj_rbi", 0.0)))
        totals["stolen_bases"] += parse_float(str(player.get("proj_sb", 0.0)))
        totals["hits"] += parse_float(str(player.get("proj_h", 0.0)))
        totals["walks"] += parse_float(str(player.get("proj_bb", 0.0)))
        totals["hbp"] += parse_float(str(player.get("proj_hbp", 0.0)))
        totals["at_bats"] += parse_float(str(player.get("proj_ab", 0.0)))
        totals["sac_flies"] += parse_float(str(player.get("proj_sf", 0.0)))
        totals["plate_appearances"] += parse_float(str(player.get("proj_pa", 0.0)))
    denominator = totals["at_bats"] + totals["walks"] + totals["hbp"] + totals["sac_flies"]
    totals["obp"] = ((totals["hits"] + totals["walks"] + totals["hbp"]) / denominator) if denominator else 0.0
    return totals


def aggregate_pitching(players: list[dict[str, object]]) -> dict[str, float]:
    totals = {
        "wins": 0.0,
        "strikeouts": 0.0,
        "saves": 0.0,
        "innings_pitched": 0.0,
        "earned_runs": 0.0,
        "whip_numerator": 0.0,
    }
    for player in players:
        innings = parse_float(str(player.get("proj_ip", 0.0)))
        projected_era = parse_float(str(player.get("proj_era", 0.0)))
        projected_er = parse_float(str(player.get("proj_er", 0.0)))
        projected_whip = parse_float(str(player.get("proj_whip", 0.0)))
        totals["wins"] += parse_float(str(player.get("proj_w", 0.0)))
        totals["strikeouts"] += parse_float(str(player.get("proj_k", 0.0)))
        totals["saves"] += parse_float(str(player.get("proj_sv", 0.0)))
        totals["innings_pitched"] += innings
        totals["earned_runs"] += projected_er if projected_er else (projected_era * innings / 9.0 if innings else 0.0)
        totals["whip_numerator"] += projected_whip * innings if innings else 0.0

    innings = totals["innings_pitched"]
    totals["era"] = ((totals["earned_runs"] * 9.0) / innings) if innings else 0.0
    totals["whip"] = (totals["whip_numerator"] / innings) if innings else 0.0
    return totals


def roster_player_payload(player: dict[str, object]) -> dict[str, object]:
    payload = {column: clean_value(str(player.get(column, ""))) for column in DISPLAY_COLUMNS}
    payload.update(
        {
            "lineup_slot": clean_value(str(player.get("lineup_slot", ""))),
            "current_level": clean_value(str(player.get("current_level", ""))),
            "projection": {
                "runs": round_number(parse_float(str(player.get("proj_r", 0.0)))),
                "home_runs": round_number(parse_float(str(player.get("proj_hr", 0.0)))),
                "rbi": round_number(parse_float(str(player.get("proj_rbi", 0.0)))),
                "stolen_bases": round_number(parse_float(str(player.get("proj_sb", 0.0)))),
                "obp": round_number(parse_float(str(player.get("proj_obp", 0.0))), 3),
                "wins": round_number(parse_float(str(player.get("proj_w", 0.0)))),
                "strikeouts": round_number(parse_float(str(player.get("proj_k", 0.0)))),
                "saves": round_number(parse_float(str(player.get("proj_sv", 0.0)))),
                "era": round_number(parse_float(str(player.get("proj_era", 0.0))), 2),
                "whip": round_number(parse_float(str(player.get("proj_whip", 0.0))), 2),
                "innings_pitched": round_number(parse_float(str(player.get("proj_ip", 0.0)))),
                "plate_appearances": round_number(parse_float(str(player.get("proj_pa", 0.0)))),
            },
            "actual_2025": {
                "runs": parse_int(str(player.get("actual_2025_r", 0))),
                "home_runs": parse_int(str(player.get("actual_2025_hr", 0))),
                "rbi": parse_int(str(player.get("actual_2025_rbi", 0))),
                "stolen_bases": parse_int(str(player.get("actual_2025_sb", 0))),
                "obp": clean_value(str(player.get("actual_2025_obp", ""))),
                "wins": parse_int(str(player.get("actual_2025_w", 0))),
                "strikeouts": parse_int(str(player.get("actual_2025_k", 0))),
                "saves": parse_int(str(player.get("actual_2025_sv", 0))),
                "era": clean_value(str(player.get("actual_2025_era", ""))),
                "whip": clean_value(str(player.get("actual_2025_whip", ""))),
            },
        }
    )
    return payload


def roto_points(values: list[tuple[str, float]], higher_is_better: bool) -> dict[str, float]:
    sorted_values = sorted(values, key=lambda item: item[1], reverse=higher_is_better)
    team_count = len(sorted_values)
    points: dict[str, float] = {}
    index = 0
    while index < team_count:
        next_index = index + 1
        while next_index < team_count and abs(sorted_values[next_index][1] - sorted_values[index][1]) < 1e-9:
            next_index += 1
        slot_points = [team_count - position for position in range(index, next_index)]
        average_points = sum(slot_points) / len(slot_points)
        for team_name, _ in sorted_values[index:next_index]:
            points[team_name] = round_number(average_points, 2)
        index = next_index
    return points


def build_standings(teams: list[dict[str, object]]) -> list[dict[str, object]]:
    standings = []
    for team in teams:
        standings.append(
            {
                "name": str(team["name"]),
                "rank": 0,
                "total_points": 0.0,
                "hitting_points": 0.0,
                "pitching_points": 0.0,
                "category_points": zero_category_totals(),
                "season_totals": zero_category_totals(),
            }
        )
    return standings


def default_league_leaders(_: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    return {
        "home_runs": [],
        "stolen_bases": [],
        "strikeouts": [],
        "saves": [],
    }


def contribution_payload(contribution: dict[str, object] | None) -> dict[str, object]:
    if not contribution:
        return {
            "weeks_active": 0,
            "runs": 0,
            "home_runs": 0,
            "rbi": 0,
            "stolen_bases": 0,
            "obp": 0.0,
            "wins": 0,
            "strikeouts": 0,
            "saves": 0,
            "era": 0.0,
            "whip": 0.0,
            "at_bats": 0,
            "hits": 0,
            "walks": 0,
            "hit_by_pitch": 0,
            "sac_flies": 0,
            "innings_pitched": "0.0",
            "outs_pitched": 0,
            "earned_runs": 0,
            "hits_allowed": 0,
            "walks_allowed": 0,
        }
    return {
        "weeks_active": parse_int(str(contribution.get("weeks_active", 0))),
        "runs": parse_int(str(contribution.get("runs", 0))),
        "home_runs": parse_int(str(contribution.get("home_runs", 0))),
        "rbi": parse_int(str(contribution.get("rbi", 0))),
        "stolen_bases": parse_int(str(contribution.get("stolen_bases", 0))),
        "obp": round_number(parse_float(str(contribution.get("obp", 0.0))), 3),
        "wins": parse_int(str(contribution.get("wins", 0))),
        "strikeouts": parse_int(str(contribution.get("strikeouts", 0))),
        "saves": parse_int(str(contribution.get("saves", 0))),
        "era": round_number(parse_float(str(contribution.get("era", 0.0))), 2),
        "whip": round_number(parse_float(str(contribution.get("whip", 0.0))), 2),
        "at_bats": parse_int(str(contribution.get("at_bats", 0))),
        "hits": parse_int(str(contribution.get("hits", 0))),
        "walks": parse_int(str(contribution.get("walks", 0))),
        "hit_by_pitch": parse_int(str(contribution.get("hit_by_pitch", 0))),
        "sac_flies": parse_int(str(contribution.get("sac_flies", 0))),
        "innings_pitched": clean_value(str(contribution.get("innings_pitched", "0.0"))),
        "outs_pitched": parse_int(str(contribution.get("outs_pitched", 0))),
        "earned_runs": parse_int(str(contribution.get("earned_runs", 0))),
        "hits_allowed": parse_int(str(contribution.get("hits_allowed", 0))),
        "walks_allowed": parse_int(str(contribution.get("walks_allowed", 0))),
    }


def build_player_contribution_index(team_result: dict[str, object] | None) -> dict[str, dict[str, object]]:
    if not team_result:
        return {}
    index: dict[str, dict[str, object]] = {}
    for contribution in team_result.get("player_contributions", []):
        contribution_dict = dict(contribution)
        key = clean_value(str(contribution_dict.get("mlbam_id"))) or normalize_name(str(contribution_dict.get("player_name", "")))
        if key:
            index[key] = contribution_dict
    return index


def enrich_player_payload(player: dict[str, object], contribution_index: dict[str, dict[str, object]]) -> dict[str, object]:
    payload = roster_player_payload(player)
    payload["season_contribution"] = contribution_payload(contribution_index.get(player_key(player)))
    return payload


def build_team_payload(
    team_name: str,
    roster_rows: list[dict[str, str]],
    board_index: dict[str, dict[str, str]],
    season_team_result: dict[str, object] | None = None,
) -> dict[str, object]:
    roster = []
    for roster_row in roster_rows:
        joined = dict(board_index.get(player_key(roster_row), {}))
        joined.update(roster_row)
        joined["mlb_team"] = clean_value(joined.get("mlb_team")) or clean_value(joined.get("proj_team"))
        roster.append(joined)

    mlb_roster = [player for player in roster if clean_value(player.get("roster_bucket")) != "Minors"]
    two_way_players = [player for player in mlb_roster if clean_value(player.get("player_type")) == "two-way"]
    scenario_results: list[dict[str, object]] = []
    scenario_labels = ["hitter", "pitcher"] if two_way_players else [""]

    for choices in product(scenario_labels, repeat=len(two_way_players)):
        choice_map = {player_key(player): choice for player, choice in zip(two_way_players, choices)}
        hitters = []
        pitchers = []
        for player in mlb_roster:
            key = player_key(player)
            choice = choice_map.get(key)
            if clean_value(player.get("player_type")) == "two-way":
                if choice == "pitcher":
                    pitchers.append(player)
                else:
                    hitters.append(player)
                continue
            if is_hitter(player):
                hitters.append(player)
            if is_pitcher(player):
                pitchers.append(player)

        active_hitters, bench_hitters = assign_best_hitter_lineup(hitters)
        active_pitchers, bench_pitchers = assign_pitchers(pitchers)
        active_keys = {player_key(player) for player in active_hitters + active_pitchers}
        bench_players = [dict(player) for player in mlb_roster if player_key(player) not in active_keys]
        projected_hitting = aggregate_hitting(active_hitters)
        projected_pitching = aggregate_pitching(active_pitchers)
        projected_totals = {
            "runs": round_number(projected_hitting["runs"]),
            "home_runs": round_number(projected_hitting["home_runs"]),
            "rbi": round_number(projected_hitting["rbi"]),
            "stolen_bases": round_number(projected_hitting["stolen_bases"]),
            "obp": round_number(projected_hitting["obp"], 3),
            "wins": round_number(projected_pitching["wins"]),
            "strikeouts": round_number(projected_pitching["strikeouts"]),
            "saves": round_number(projected_pitching["saves"]),
            "era": round_number(projected_pitching["era"], 2),
            "whip": round_number(projected_pitching["whip"], 2),
        }
        score = sum(hitter_value(player) for player in active_hitters) + sum(pitcher_value(player) for player in active_pitchers)
        scenario_results.append(
            {
                "score": score,
                "choice_map": choice_map,
                "active_hitters": active_hitters,
                "active_pitchers": active_pitchers,
                "bench_players": bench_players,
                "projected_totals": projected_totals,
            }
        )

    best = max(scenario_results, key=lambda item: float(item["score"]))
    contribution_index = build_player_contribution_index(season_team_result)
    season_totals = dict(season_team_result.get("season_totals", zero_category_totals())) if season_team_result else zero_category_totals()
    return {
        "name": team_name,
        "roster_count": len(roster),
        "active_hitters": [enrich_player_payload(player, contribution_index) for player in best["active_hitters"]],
        "active_pitchers": [enrich_player_payload(player, contribution_index) for player in best["active_pitchers"]],
        "bench": [enrich_player_payload(player, contribution_index) for player in sorted(best["bench_players"], key=lambda item: (clean_value(item.get("player_type")), clean_value(item.get("player_name"))))],
        "roster": [enrich_player_payload(player, contribution_index) for player in sorted(roster, key=lambda item: parse_int(item.get("pick_number")))],
        "projected_totals": best["projected_totals"],
        "season_totals": season_totals,
    }


def main() -> None:
    settings = read_settings()
    board_rows = read_csv_rows(BOARD_PATH)
    board_index = board_index_rows(board_rows)
    season_results = read_json_file(RESULTS_PATH)
    season_team_index = {clean_value(item.get("name")): item for item in season_results.get("teams", [])}

    teams = []
    for roster_path in roster_order(ROSTERS_DIR, settings):
        team_name = clean_value(roster_path.stem.replace("-roster", "").replace("-", " ")).title()
        teams.append(build_team_payload(team_name, read_csv_rows(roster_path), board_index, season_team_index.get(team_name)))

    standings = season_results.get("standings") or build_standings(teams)
    standings_by_team = {item["name"]: item for item in standings}
    for team in teams:
        summary = standings_by_team[team["name"]]
        team["standings"] = {
            "rank": summary["rank"],
            "total_points": summary["total_points"],
            "hitting_points": summary["hitting_points"],
            "pitching_points": summary["pitching_points"],
            "category_points": summary["category_points"],
        }

    payload = {
        "title": "Boz Cup Baseball Hub",
        "generated_from": season_results.get("generated_from") or "draft-board-input-2026.csv and manager-rosters/*.csv",
        "standings_note": season_results.get("standings_note") or "Standings and league leaders are set to zero until real 2026 season data is available.",
        "teams": teams,
        "standings": standings,
        "leaders": season_results.get("leaders") or default_league_leaders(teams),
    }

    OUTPUT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote league site payload to {OUTPUT_JSON_PATH}")


if __name__ == "__main__":
    main()