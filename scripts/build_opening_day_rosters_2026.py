from __future__ import annotations

import csv
import json
import urllib.parse
import urllib.request
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = WORKSPACE_ROOT / "data"
OUTPUT_CSV_PATH = DATA_DIR / "mlb-opening-day-rosters-2026.csv"
OUTPUT_JSON_PATH = DATA_DIR / "mlb-opening-day-rosters-2026.json"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0 Safari/537.36"


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def write_csv_rows(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def clean_value(value: str | None) -> str:
    return (value or "").strip()


def schedule_url(start_date: str, end_date: str, season: int) -> str:
    query = urllib.parse.urlencode(
        {
            "sportId": 1,
            "gameType": "R",
            "season": season,
            "startDate": start_date,
            "endDate": end_date,
        }
    )
    return f"https://statsapi.mlb.com/api/v1/schedule?{query}"


def teams_url(season: int) -> str:
    query = urllib.parse.urlencode({"sportId": 1, "season": season})
    return f"https://statsapi.mlb.com/api/v1/teams?{query}"


def roster_url(team_id: int, roster_type: str, roster_date: str) -> str:
    query = urllib.parse.urlencode({"rosterType": roster_type, "date": roster_date})
    return f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster?{query}"


def find_opening_day(season: int) -> tuple[str, int]:
    payload = fetch_json(schedule_url(f"{season}-03-01", f"{season}-04-15", season))
    for day in payload.get("dates", []):
        total_games = int(day.get("totalGames") or 0)
        if total_games > 0:
            return clean_value(day.get("date")), total_games
    raise RuntimeError(f"Could not determine Opening Day for {season}")


def fetch_teams(season: int) -> list[dict[str, object]]:
    payload = fetch_json(teams_url(season))
    teams = []
    for team in payload.get("teams", []):
        if not team.get("active", False):
            continue
        if int(team.get("sport", {}).get("id", 0) or 0) != 1:
            continue
        teams.append(team)
    return sorted(teams, key=lambda item: clean_value(item.get("name")))


def flatten_roster_rows(team: dict[str, object], roster_payload: dict[str, object], opening_day: str, roster_type: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for player in roster_payload.get("roster", []):
        person = player.get("person", {})
        position = player.get("position", {})
        status = player.get("status", {})
        rows.append(
            {
                "season": 2026,
                "opening_day": opening_day,
                "roster_type": roster_type,
                "team_id": int(team.get("id") or 0),
                "team_name": clean_value(team.get("name")),
                "team_abbreviation": clean_value(team.get("abbreviation")),
                "team_location": clean_value(team.get("locationName")),
                "player_name": clean_value(person.get("fullName")),
                "mlbam_id": clean_value(str(person.get("id", ""))),
                "jersey_number": clean_value(player.get("jerseyNumber")),
                "position_code": clean_value(position.get("code")),
                "position_name": clean_value(position.get("name")),
                "position_type": clean_value(position.get("type")),
                "position_abbreviation": clean_value(position.get("abbreviation")),
                "status_code": clean_value(status.get("code")),
                "status_description": clean_value(status.get("description")),
            }
        )
    return rows


def build_snapshot(season: int = 2026, roster_type: str = "active") -> dict[str, object]:
    opening_day, opening_day_games = find_opening_day(season)
    teams = fetch_teams(season)

    roster_rows: list[dict[str, object]] = []
    team_summaries: list[dict[str, object]] = []
    for team in teams:
        team_id = int(team.get("id") or 0)
        roster_payload = fetch_json(roster_url(team_id, roster_type, opening_day))
        team_rows = flatten_roster_rows(team, roster_payload, opening_day, roster_type)
        roster_rows.extend(team_rows)
        team_summaries.append(
            {
                "team_id": team_id,
                "team_name": clean_value(team.get("name")),
                "team_abbreviation": clean_value(team.get("abbreviation")),
                "roster_count": len(team_rows),
            }
        )

    team_summaries.sort(key=lambda item: item["team_name"])
    roster_rows.sort(key=lambda item: (item["team_name"], item["player_name"]))

    return {
        "season": season,
        "opening_day": opening_day,
        "opening_day_games": opening_day_games,
        "roster_type": roster_type,
        "source": "MLB Stats API",
        "team_count": len(team_summaries),
        "player_count": len(roster_rows),
        "teams": team_summaries,
        "rosters": roster_rows,
        "output_files": {
            "csv": str(OUTPUT_CSV_PATH.relative_to(WORKSPACE_ROOT)).replace("\\", "/"),
            "json": str(OUTPUT_JSON_PATH.relative_to(WORKSPACE_ROOT)).replace("\\", "/"),
        },
    }


def main() -> None:
    snapshot = build_snapshot()
    write_csv_rows(
        OUTPUT_CSV_PATH,
        [
            "season",
            "opening_day",
            "roster_type",
            "team_id",
            "team_name",
            "team_abbreviation",
            "team_location",
            "player_name",
            "mlbam_id",
            "jersey_number",
            "position_code",
            "position_name",
            "position_type",
            "position_abbreviation",
            "status_code",
            "status_description",
        ],
        snapshot["rosters"],
    )
    write_json(OUTPUT_JSON_PATH, snapshot)
    print(f"Opening Day: {snapshot['opening_day']} ({snapshot['opening_day_games']} games)")
    print(f"Wrote {snapshot['player_count']} roster rows to {OUTPUT_CSV_PATH}")
    print(f"Wrote JSON snapshot to {OUTPUT_JSON_PATH}")


if __name__ == "__main__":
    main()