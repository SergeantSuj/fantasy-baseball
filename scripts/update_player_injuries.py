from __future__ import annotations

import argparse
import csv
import unicodedata
from datetime import UTC, datetime
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = WORKSPACE_ROOT / "data"

PLAYER_POOL_PATH = DATA_DIR / "player-pool-2026.csv"
INJURY_TRACKER_PATH = DATA_DIR / "player-injuries-2026.csv"


def normalize_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().replace(".", " ").replace("-", " ")
    normalized = " ".join(normalized.split())
    return normalized


def clean_value(value: str | None) -> str:
    return (value or "").strip()


def clean_team(value: str | None) -> str:
    return clean_value(value).upper()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def write_csv_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def resolve_player(player_rows: list[dict[str, str]], player_name: str, team: str) -> dict[str, str]:
    normalized_target = normalize_name(player_name)
    cleaned_team = clean_team(team)

    matches = [row for row in player_rows if normalize_name(row.get("player_name", "")) == normalized_target]
    if cleaned_team:
        team_matches = [row for row in matches if clean_team(row.get("mlb_team") or row.get("team")) == cleaned_team]
        if team_matches:
            matches = team_matches

    if len(matches) != 1:
        raise ValueError(f"Expected exactly one player match for '{player_name}', found {len(matches)}")
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Upsert a row in data/player-injuries-2026.csv")
    parser.add_argument("--player", required=True, help="Player name to update")
    parser.add_argument("--team", default="", help="Optional team abbreviation to disambiguate")
    parser.add_argument("--status", default="", help="Current injury status")
    parser.add_argument("--expected-return", default="", help="Expected return text")
    parser.add_argument("--notes", default="", help="Freeform notes")
    parser.add_argument("--source", default="manual injury tracker", help="Source label")
    parser.add_argument("--clear", action="store_true", help="Remove the injury row for this player")
    args = parser.parse_args()

    player_rows = read_csv_rows(PLAYER_POOL_PATH)
    injury_rows = read_csv_rows(INJURY_TRACKER_PATH)
    player = resolve_player(player_rows, args.player, args.team)

    mlbam_id = clean_value(player.get("mlbam_id"))
    player_name = clean_value(player.get("player_name"))
    team = clean_team(player.get("mlb_team") or player.get("team"))

    remaining_rows = [row for row in injury_rows if clean_value(row.get("mlbam_id")) != mlbam_id]

    if args.clear:
        write_csv_rows(
            INJURY_TRACKER_PATH,
            ["source", "mlbam_id", "player_name", "team", "injury_status", "expected_return", "last_updated", "notes"],
            remaining_rows,
        )
        print(f"Cleared injury tracking for {player_name}")
        return

    remaining_rows.append(
        {
            "source": clean_value(args.source) or "manual injury tracker",
            "mlbam_id": mlbam_id,
            "player_name": player_name,
            "team": team,
            "injury_status": clean_value(args.status),
            "expected_return": clean_value(args.expected_return),
            "last_updated": datetime.now(UTC).date().isoformat(),
            "notes": clean_value(args.notes),
        }
    )
    remaining_rows.sort(key=lambda row: (clean_value(row.get("player_name")), clean_value(row.get("team"))))
    write_csv_rows(
        INJURY_TRACKER_PATH,
        ["source", "mlbam_id", "player_name", "team", "injury_status", "expected_return", "last_updated", "notes"],
        remaining_rows,
    )
    print(f"Updated injury tracking for {player_name}")


if __name__ == "__main__":
    main()