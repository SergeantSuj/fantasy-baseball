from __future__ import annotations

import csv
import json
import urllib.request
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = WORKSPACE_ROOT / "data"

PLAYER_POOL_PATH = DATA_DIR / "player-pool-2026.csv"
OUTPUT_PATH = DATA_DIR / "player-stats-2025.csv"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0 Safari/537.36"

HITTING_URL = "https://statsapi.mlb.com/api/v1/stats?stats=season&group=hitting&season=2025&playerPool=ALL&limit=10000"
PITCHING_URL = "https://statsapi.mlb.com/api/v1/stats?stats=season&group=pitching&season=2025&playerPool=ALL&limit=10000"


def clean_value(value: str | None) -> str:
    return (value or "").strip()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def dedupe_player_pool(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    merged_by_key: dict[str, dict[str, str]] = {}
    order: list[str] = []

    for row in rows:
        key = clean_value(row.get("mlbam_id")) or clean_value(row.get("player_name"))
        if key not in merged_by_key:
            merged_by_key[key] = dict(row)
            order.append(key)
            continue

        existing = merged_by_key[key]
        for field, value in row.items():
            if not clean_value(existing.get(field)) and clean_value(value):
                existing[field] = value

    return [merged_by_key[key] for key in order]


def stat_text(stat: dict, field: str) -> str:
    value = stat.get(field, "")
    return "" if value is None else str(value)


def build_stat_map(url: str) -> dict[str, dict]:
    payload = fetch_json(url)
    splits = payload.get("stats", [{}])[0].get("splits", [])
    return {str(split.get("player", {}).get("id", "")): split for split in splits if split.get("player", {}).get("id")}


def build_output_rows(player_rows: list[dict[str, str]], hitting_map: dict[str, dict], pitching_map: dict[str, dict]) -> list[dict[str, str]]:
    output_rows: list[dict[str, str]] = []
    for row in player_rows:
        mlbam_id = clean_value(row.get("mlbam_id"))
        hitting_row = hitting_map.get(mlbam_id, {})
        pitching_row = pitching_map.get(mlbam_id, {})
        hitting_stat = hitting_row.get("stat", {})
        pitching_stat = pitching_row.get("stat", {})

        actual_team = (
            clean_value(hitting_row.get("team", {}).get("abbreviation"))
            or clean_value(pitching_row.get("team", {}).get("abbreviation"))
            or clean_value(row.get("mlb_team"))
            or clean_value(row.get("team"))
        )

        output_rows.append(
            {
                "source": "MLB Stats API 2025 season stats",
                "season": "2025",
                "mlbam_id": mlbam_id,
                "player_name": clean_value(row.get("player_name")),
                "team": actual_team,
                "player_type": clean_value(row.get("player_type")),
                "actual_2025_g": stat_text(hitting_stat or pitching_stat, "gamesPlayed"),
                "actual_2025_pa": stat_text(hitting_stat, "plateAppearances"),
                "actual_2025_ab": stat_text(hitting_stat, "atBats"),
                "actual_2025_r": stat_text(hitting_stat, "runs"),
                "actual_2025_hr": stat_text(hitting_stat, "homeRuns"),
                "actual_2025_rbi": stat_text(hitting_stat, "rbi"),
                "actual_2025_sb": stat_text(hitting_stat, "stolenBases"),
                "actual_2025_h": stat_text(hitting_stat, "hits"),
                "actual_2025_bb": stat_text(hitting_stat, "baseOnBalls"),
                "actual_2025_so": stat_text(hitting_stat, "strikeOuts"),
                "actual_2025_avg": stat_text(hitting_stat, "avg"),
                "actual_2025_obp": stat_text(hitting_stat, "obp"),
                "actual_2025_slg": stat_text(hitting_stat, "slg"),
                "actual_2025_ops": stat_text(hitting_stat, "ops"),
                "actual_2025_pitch_g": stat_text(pitching_stat, "gamesPlayed"),
                "actual_2025_gs": stat_text(pitching_stat, "gamesStarted"),
                "actual_2025_ip": stat_text(pitching_stat, "inningsPitched"),
                "actual_2025_w": stat_text(pitching_stat, "wins"),
                "actual_2025_l": stat_text(pitching_stat, "losses"),
                "actual_2025_sv": stat_text(pitching_stat, "saves"),
                "actual_2025_hld": stat_text(pitching_stat, "holds"),
                "actual_2025_qs": stat_text(pitching_stat, "qualityStarts"),
                "actual_2025_pitch_h": stat_text(pitching_stat, "hits"),
                "actual_2025_pitch_bb": stat_text(pitching_stat, "baseOnBalls"),
                "actual_2025_pitch_hr": stat_text(pitching_stat, "homeRuns"),
                "actual_2025_k": stat_text(pitching_stat, "strikeOuts"),
                "actual_2025_era": stat_text(pitching_stat, "era"),
                "actual_2025_whip": stat_text(pitching_stat, "whip"),
            }
        )

    return output_rows


def main() -> None:
    player_rows = dedupe_player_pool(read_csv_rows(PLAYER_POOL_PATH))
    hitting_map = build_stat_map(HITTING_URL)
    pitching_map = build_stat_map(PITCHING_URL)
    output_rows = build_output_rows(player_rows, hitting_map, pitching_map)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(
        OUTPUT_PATH,
        [
            "source",
            "season",
            "mlbam_id",
            "player_name",
            "team",
            "player_type",
            "actual_2025_g",
            "actual_2025_pa",
            "actual_2025_ab",
            "actual_2025_r",
            "actual_2025_hr",
            "actual_2025_rbi",
            "actual_2025_sb",
            "actual_2025_h",
            "actual_2025_bb",
            "actual_2025_so",
            "actual_2025_avg",
            "actual_2025_obp",
            "actual_2025_slg",
            "actual_2025_ops",
            "actual_2025_pitch_g",
            "actual_2025_gs",
            "actual_2025_ip",
            "actual_2025_w",
            "actual_2025_l",
            "actual_2025_sv",
            "actual_2025_hld",
            "actual_2025_qs",
            "actual_2025_pitch_h",
            "actual_2025_pitch_bb",
            "actual_2025_pitch_hr",
            "actual_2025_k",
            "actual_2025_era",
            "actual_2025_whip",
        ],
        output_rows,
    )

    covered_rows = sum(1 for row in output_rows if clean_value(row.get("actual_2025_pa")) or clean_value(row.get("actual_2025_ip")))
    print(f"Wrote {len(output_rows)} rows to {OUTPUT_PATH}")
    print(f"Rows with 2025 MLB stats: {covered_rows}")


if __name__ == "__main__":
    main()