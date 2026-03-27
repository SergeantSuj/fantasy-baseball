from __future__ import annotations

import argparse
import csv
from itertools import product
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = WORKSPACE_ROOT / "data"
ROSTERS_DIR = WORKSPACE_ROOT / "manager-rosters"
SETTINGS_PATH = DATA_DIR / "startup-draft-settings-2026.json"
BOARD_PATH = DATA_DIR / "draft-board-input-2026.csv"
OUTPUT_DIR = DATA_DIR / "weekly-lineups"

ACTIVE_HITTER_SLOTS = ["C", "1B", "2B", "3B", "SS", "CI", "MI", "OF", "OF", "OF", "OF", "OF", "UTIL"]
PITCHER_SLOTS = 9
IL_ROSTER_BUCKETS = {"IL", "INJURY LIST", "INJURED LIST"}
IL_STATUS_TERMS = ("7-DAY IL", "10-DAY IL", "15-DAY IL", "60-DAY IL", "INJURED LIST", "DISABLED LIST")


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


def merge_player_rows(base_row: dict[str, str], override_row: dict[str, str]) -> dict[str, str]:
    merged = dict(base_row)
    for field, value in override_row.items():
        if field not in merged or clean_value(value):
            merged[field] = value
    return merged


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def read_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    import json

    return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))


def player_key(row: dict[str, str] | dict[str, object]) -> str:
    mlbam_id = clean_value(str(row.get("mlbam_id", "")))
    return mlbam_id or normalize_name(str(row.get("player_name", "")))


def roster_bucket_value(player: dict[str, str] | dict[str, object]) -> str:
    return clean_value(str(player.get("roster_bucket", "")))


def is_minor_roster_bucket(player: dict[str, str] | dict[str, object]) -> bool:
    return roster_bucket_value(player).upper() == "MINORS"


def is_il_roster_bucket(player: dict[str, str] | dict[str, object]) -> bool:
    return roster_bucket_value(player).upper() in IL_ROSTER_BUCKETS


def injury_status_summary(player: dict[str, str] | dict[str, object]) -> str:
    injury_status = clean_value(str(player.get("injury_status", "")))
    transaction_status = clean_value(str(player.get("transaction_status", "")))
    return injury_status or transaction_status


def is_injured_list_status(value: str | None) -> bool:
    normalized = clean_value(value).upper()
    return any(term in normalized for term in IL_STATUS_TERMS)


def is_injured_list_player(player: dict[str, str] | dict[str, object]) -> bool:
    return is_il_roster_bucket(player) or is_injured_list_status(injury_status_summary(player))


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


def build_lineup_rows(team_name: str, roster_rows: list[dict[str, str]], board_index: dict[str, dict[str, str]], week: str) -> list[dict[str, str]]:
    roster: list[dict[str, object]] = []
    for roster_row in roster_rows:
        joined = merge_player_rows(board_index.get(player_key(roster_row), {}), roster_row)
        joined["mlb_team"] = clean_value(joined.get("mlb_team")) or clean_value(joined.get("proj_team"))
        roster.append(joined)

    mlb_roster = [player for player in roster if not is_minor_roster_bucket(player) and not is_injured_list_player(player)]
    two_way_players = [player for player in mlb_roster if clean_value(str(player.get("player_type", ""))) == "two-way"]
    scenario_results: list[dict[str, object]] = []
    scenario_labels = ["hitter", "pitcher"] if two_way_players else [""]

    for choices in product(scenario_labels, repeat=len(two_way_players)):
        choice_map = {player_key(player): choice for player, choice in zip(two_way_players, choices)}
        hitters = []
        pitchers = []
        for player in mlb_roster:
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
        scenario_results.append(
            {
                "score": score,
                "active_hitters": active_hitters,
                "active_pitchers": active_pitchers,
            }
        )

    best = max(scenario_results, key=lambda item: float(item["score"]))
    active_lookup = {player_key(player): player for player in [*best["active_hitters"], *best["active_pitchers"]]}
    rows: list[dict[str, str]] = []
    for player in sorted(roster, key=lambda item: parse_int(str(item.get("pick_number", 0)))):
        active_player = active_lookup.get(player_key(player))
        if active_player:
            lineup_status = "ACTIVE"
        elif is_injured_list_player(player):
            lineup_status = "IL"
        else:
            lineup_status = "BENCH"
        rows.append(
            {
                "week": week,
                "team": team_name,
                "lineup_status": lineup_status,
                "lineup_slot": clean_value(str(active_player.get("lineup_slot", ""))) if active_player else "",
                "mlbam_id": clean_value(str(player.get("mlbam_id", ""))),
                "player_name": clean_value(str(player.get("player_name", ""))),
                "player_type": clean_value(str(player.get("player_type", ""))),
                "eligible_positions": clean_value(str(player.get("eligible_positions", ""))),
                "mlb_team": clean_value(str(player.get("mlb_team", ""))),
                "current_level": clean_value(str(player.get("current_level", ""))),
                "roster_bucket": roster_bucket_value(player),
                "injury_status": clean_value(str(player.get("injury_status", ""))),
                "transaction_status": clean_value(str(player.get("transaction_status", ""))),
            }
        )
    return rows


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a weekly lineup snapshot CSV for later Monday stat imports.")
    parser.add_argument("--week", required=True, help="Week key such as 2026-week-01")
    parser.add_argument("--output", help="Optional explicit output CSV path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = read_settings()
    board_rows = read_csv_rows(BOARD_PATH)
    board_index = board_index_rows(board_rows)

    rows: list[dict[str, str]] = []
    for roster_path in roster_order(ROSTERS_DIR, settings):
        team_name = clean_value(roster_path.stem.replace("-roster", "").replace("-", " ")).title()
        rows.extend(build_lineup_rows(team_name, read_csv_rows(roster_path), board_index, args.week))

    output_path = Path(args.output) if args.output else OUTPUT_DIR / f"{args.week}.csv"
    write_csv(
        output_path,
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
        rows,
    )
    print(f"Wrote weekly lineup snapshot to {output_path}")
    print("Review the lineup_status and lineup_slot fields before the scoring week locks.")


if __name__ == "__main__":
    main()