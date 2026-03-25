from __future__ import annotations

import csv
import json
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = WORKSPACE_ROOT / "data"

PLAYER_POOL_PATH = DATA_DIR / "player-pool-2026.csv"
OUTPUT_PATH = DATA_DIR / "player-transactions-2026.csv"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0 Safari/537.36"

SPORT_LEVELS = {
    1: "MLB",
    11: "AAA",
    12: "AA",
    13: "High-A",
    14: "Single-A",
    16: "Rookie",
}


def clean_value(value: str | None) -> str:
    return (value or "").strip()


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


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def build_url(sport_id: int, start_date: str, end_date: str) -> str:
    query = urllib.parse.urlencode({
        "startDate": start_date,
        "endDate": end_date,
        "sportId": sport_id,
        "limit": 5000,
    })
    return f"https://statsapi.mlb.com/api/v1/transactions?{query}"


def parse_sort_key(row: dict) -> tuple[str, str, int]:
    effective = clean_value(row.get("effectiveDate")) or clean_value(row.get("date")) or clean_value(row.get("resolutionDate"))
    created = clean_value(row.get("date"))
    return effective, created, int(row.get("id", 0) or 0)


def fetch_latest_transactions(start_date: str, end_date: str) -> dict[str, dict]:
    latest_by_player: dict[str, dict] = {}
    for sport_id, level in SPORT_LEVELS.items():
        payload = fetch_json(build_url(sport_id, start_date, end_date))
        for transaction in payload.get("transactions", []):
            person = transaction.get("person", {})
            mlbam_id = str(person.get("id", ""))
            if not mlbam_id:
                continue

            candidate = {
                "source": "MLB Stats API transactions",
                "mlbam_id": mlbam_id,
                "player_name": clean_value(person.get("fullName")),
                "team": clean_value(transaction.get("toTeam", {}).get("abbreviation") or transaction.get("fromTeam", {}).get("abbreviation")),
                "current_level": level,
                "transaction_status": clean_value(transaction.get("typeDesc")),
                "transaction_date": clean_value(transaction.get("effectiveDate") or transaction.get("date") or transaction.get("resolutionDate")),
                "notes": clean_value(transaction.get("description")),
                "transaction_id": str(transaction.get("id", "")),
            }

            existing = latest_by_player.get(mlbam_id)
            if existing is None or parse_sort_key(transaction) >= (
                clean_value(existing.get("transaction_date")),
                clean_value(existing.get("transaction_date")),
                int(existing.get("transaction_id", "0") or 0),
            ):
                latest_by_player[mlbam_id] = candidate

    return latest_by_player


def main() -> None:
    season_start = date(2026, 1, 1).isoformat()
    today = datetime.now(UTC).date().isoformat()
    latest_transactions = fetch_latest_transactions(season_start, today)

    player_rows = read_csv_rows(PLAYER_POOL_PATH)
    seen: set[str] = set()
    output_rows: list[dict[str, str]] = []
    for row in player_rows:
        mlbam_id = clean_value(row.get("mlbam_id"))
        if not mlbam_id or mlbam_id in seen:
            continue
        seen.add(mlbam_id)
        if mlbam_id not in latest_transactions:
            continue
        output_rows.append(latest_transactions[mlbam_id])

    output_rows.sort(key=lambda row: (clean_value(row.get("player_name")), clean_value(row.get("team"))))
    write_csv_rows(
        OUTPUT_PATH,
        ["source", "mlbam_id", "player_name", "team", "current_level", "transaction_status", "transaction_date", "notes", "transaction_id"],
        output_rows,
    )
    print(f"Wrote {len(output_rows)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()