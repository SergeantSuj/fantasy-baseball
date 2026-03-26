from __future__ import annotations

import csv
import json
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = WORKSPACE_ROOT / "data"
ROSTERS_DIR = WORKSPACE_ROOT / "manager-rosters"
BOARD_PATH = DATA_DIR / "draft-board-input-2026.csv"
OPENING_DAY_ROSTERS_PATH = DATA_DIR / "mlb-opening-day-rosters-2026.csv"
OUTPUT_JSON_PATH = DATA_DIR / "minor-leaguers-on-opening-day-rosters-2026.json"
OUTPUT_CSV_PATH = DATA_DIR / "minor-leaguers-on-opening-day-rosters-2026.csv"


def clean_value(value: str | None) -> str:
    return (value or "").strip()


def normalize_name(name: str) -> str:
    return " ".join(clean_value(name).lower().replace(".", " ").replace("-", " ").split())


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def write_csv_rows(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def workspace_relative_path(path: Path) -> str:
    return str(path.relative_to(WORKSPACE_ROOT)).replace("\\", "/")


def player_key(row: dict[str, str] | dict[str, object]) -> str:
    mlbam_id = clean_value(str(row.get("mlbam_id", "")))
    if mlbam_id:
        return mlbam_id
    return normalize_name(str(row.get("player_name", "")))


def dedupe_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    merged_by_key: dict[str, dict[str, str]] = {}
    ordered_keys: list[str] = []
    for row in rows:
        key = player_key(row)
        if not key:
            continue
        if key not in merged_by_key:
            merged_by_key[key] = dict(row)
            ordered_keys.append(key)
            continue
        existing = merged_by_key[key]
        for field, value in row.items():
            if not clean_value(existing.get(field)) and clean_value(value):
                existing[field] = value
    return [merged_by_key[key] for key in ordered_keys]


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


def opening_day_index_rows(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for row in rows:
        mlbam_id = clean_value(row.get("mlbam_id"))
        if mlbam_id:
            index[mlbam_id] = row
        name_key = normalize_name(row.get("player_name", ""))
        if name_key and name_key not in index:
            index[name_key] = row
    return index


def team_name_from_path(path: Path) -> str:
    return clean_value(path.stem.replace("-roster", "").replace("-", " ")).title()


def build_team_report(
    team_name: str,
    roster_rows: list[dict[str, str]],
    board_index: dict[str, dict[str, str]],
    opening_day_index: dict[str, dict[str, str]],
) -> dict[str, object]:
    matches: list[dict[str, object]] = []
    unmatched_minor_rows = 0

    for roster_row in roster_rows:
        if clean_value(roster_row.get("roster_bucket")) != "Minors":
            continue

        lookup_keys = []
        name_key = normalize_name(roster_row.get("player_name", ""))
        if name_key:
            lookup_keys.append(name_key)

        board_row = None
        for lookup_key in lookup_keys:
            if lookup_key in board_index:
                board_row = board_index[lookup_key]
                break

        if board_row is None:
            unmatched_minor_rows += 1
            continue

        mlbam_id = clean_value(board_row.get("mlbam_id"))
        opening_day_row = None
        if mlbam_id and mlbam_id in opening_day_index:
            opening_day_row = opening_day_index[mlbam_id]
        elif name_key and name_key in opening_day_index:
            opening_day_row = opening_day_index[name_key]

        if opening_day_row is None:
            continue

        matches.append(
            {
                "player_name": clean_value(board_row.get("player_name")) or clean_value(roster_row.get("player_name")),
                "mlbam_id": mlbam_id,
                "fantasy_team": team_name,
                "fantasy_roster_bucket": clean_value(roster_row.get("roster_bucket")),
                "eligible_positions": clean_value(board_row.get("eligible_positions")) or clean_value(roster_row.get("eligible_positions")),
                "player_type": clean_value(board_row.get("player_type")) or clean_value(roster_row.get("player_type")),
                "real_team": clean_value(opening_day_row.get("team_abbreviation")),
                "real_team_name": clean_value(opening_day_row.get("team_name")),
                "opening_day": clean_value(opening_day_row.get("opening_day")),
                "roster_type": clean_value(opening_day_row.get("roster_type")),
                "position_abbreviation": clean_value(opening_day_row.get("position_abbreviation")),
                "status_description": clean_value(opening_day_row.get("status_description")),
                "dynasty_rank": clean_value(board_row.get("dynasty_rank")),
                "adp": clean_value(board_row.get("adp")),
                "transaction_status": clean_value(roster_row.get("transaction_status")),
                "current_level": clean_value(roster_row.get("current_level")),
            }
        )

    matches.sort(key=lambda item: item["player_name"])
    return {
        "team": team_name,
        "minor_leaguers_on_opening_day_roster": len(matches),
        "unmatched_minor_rows": unmatched_minor_rows,
        "players": matches,
    }


def build_csv_rows(report: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for team in report.get("teams", []):
        for player in team.get("players", []):
            rows.append(player)
    return rows


def build_report() -> dict[str, object]:
    board_index = board_index_rows(read_csv_rows(BOARD_PATH))
    opening_day_rows = read_csv_rows(OPENING_DAY_ROSTERS_PATH)
    opening_day_index = opening_day_index_rows(opening_day_rows)

    teams = []
    for roster_path in sorted(ROSTERS_DIR.glob("*-roster.csv")):
        team_report = build_team_report(
            team_name_from_path(roster_path),
            read_csv_rows(roster_path),
            board_index,
            opening_day_index,
        )
        teams.append(team_report)

    teams.sort(key=lambda item: item["team"])
    total_players = sum(int(team["minor_leaguers_on_opening_day_roster"]) for team in teams)
    opening_day = clean_value(opening_day_rows[0].get("opening_day")) if opening_day_rows else ""

    return {
        "season": 2026,
        "opening_day": opening_day,
        "source": "MLB Stats API Opening Day active rosters",
        "summary": {
            "teams_checked": len(teams),
            "teams_with_break_camp_players": sum(1 for team in teams if team["minor_leaguers_on_opening_day_roster"] > 0),
            "total_minor_leaguers_on_opening_day_rosters": total_players,
        },
        "teams": teams,
        "output_files": {
            "json": workspace_relative_path(OUTPUT_JSON_PATH),
            "csv": workspace_relative_path(OUTPUT_CSV_PATH),
        },
    }


def main() -> None:
    report = build_report()
    write_json(OUTPUT_JSON_PATH, report)
    write_csv_rows(
        OUTPUT_CSV_PATH,
        [
            "player_name",
            "mlbam_id",
            "fantasy_team",
            "fantasy_roster_bucket",
            "eligible_positions",
            "player_type",
            "real_team",
            "real_team_name",
            "opening_day",
            "roster_type",
            "position_abbreviation",
            "status_description",
            "dynasty_rank",
            "adp",
            "transaction_status",
            "current_level",
        ],
        build_csv_rows(report),
    )
    print(f"Opening Day report date: {report['opening_day']}")
    print(f"Teams checked: {report['summary']['teams_checked']}")
    print(f"Matched players: {report['summary']['total_minor_leaguers_on_opening_day_rosters']}")
    print(f"Wrote JSON report to {OUTPUT_JSON_PATH}")
    print(f"Wrote CSV report to {OUTPUT_CSV_PATH}")


if __name__ == "__main__":
    main()