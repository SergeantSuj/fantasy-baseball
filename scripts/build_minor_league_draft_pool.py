from __future__ import annotations

import csv
import json
import re
import unicodedata
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = WORKSPACE_ROOT / "data"
ROSTERS_DIR = WORKSPACE_ROOT / "manager-rosters"

OUTPUT_PATH = DATA_DIR / "minor-league-draft-pool-2026.csv"
SUMMARY_PATH = DATA_DIR / "minor-league-draft-pool-summary-2026.json"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0 Safari/537.36"

SPORT_LEVELS = {
    11: "AAA",
    12: "AA",
    13: "High-A",
    14: "Single-A",
    16: "Rookie",
}

LEVEL_PRIORITY = {
    "AAA": 1,
    "AA": 2,
    "High-A": 3,
    "Single-A": 4,
    "Rookie": 5,
}


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def clean_value(value: str | None) -> str:
    return (value or "").strip()


def normalize_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().replace(".", " ").replace("-", " ")
    normalized = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", " ", normalized)
    normalized = re.sub(r"[^a-z0-9 ]+", "", normalized)
    return " ".join(normalized.split())


def split_positions(value: str | None) -> list[str]:
    positions: list[str] = []
    for token in re.split(r"[,/]+", clean_value(value).upper()):
        if token and token not in positions:
            positions.append(token)
    return positions


def split_tokens(value: str | None) -> list[str]:
    tokens: list[str] = []
    for token in re.split(r"[,/]+", clean_value(value)):
        if token and token not in tokens:
            tokens.append(token)
    return tokens


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def read_rostered_names() -> tuple[set[str], dict[str, str]]:
    rostered_names: set[str] = set()
    rostered_by_name: dict[str, str] = {}
    for roster_path in sorted(ROSTERS_DIR.glob("*-roster.csv")):
        rows = read_csv_rows(roster_path)
        for row in rows:
            player_name = clean_value(row.get("player_name"))
            team_name = clean_value(row.get("team"))
            if not player_name:
                continue
            normalized = normalize_name(player_name)
            rostered_names.add(normalized)
            rostered_by_name[normalized] = team_name
    return rostered_names, rostered_by_name


def fetch_people_for_sport(sport_id: int) -> list[dict]:
    url = f"https://statsapi.mlb.com/api/v1/sports/{sport_id}/players"
    payload = fetch_json(url)
    return payload.get("people", [])


def choose_better_record(existing: dict, candidate: dict) -> dict:
    existing_level = clean_value(existing.get("current_level"))
    candidate_level = clean_value(candidate.get("current_level"))
    existing_priority = LEVEL_PRIORITY.get(existing_level, 99)
    candidate_priority = LEVEL_PRIORITY.get(candidate_level, 99)

    if candidate_priority < existing_priority:
        return candidate
    if candidate_priority > existing_priority:
        return existing

    existing_team_id = clean_value(existing.get("affiliated_team_id"))
    candidate_team_id = clean_value(candidate.get("affiliated_team_id"))
    if candidate_team_id and not existing_team_id:
        return candidate
    return existing


def collect_affiliated_players() -> tuple[list[dict[str, str]], dict[str, int], set[int]]:
    merged_by_id: dict[str, dict[str, str]] = {}
    counts_by_level: dict[str, int] = {label: 0 for label in SPORT_LEVELS.values()}
    team_ids: set[int] = set()

    for sport_id, level in SPORT_LEVELS.items():
        people = fetch_people_for_sport(sport_id)
        counts_by_level[level] = len(people)
        for person in people:
            mlbam_id = str(person.get("id", "") or "")
            if not mlbam_id:
                continue

            current_team = person.get("currentTeam", {}) or {}
            team_id = current_team.get("id")
            if team_id:
                team_ids.add(int(team_id))

            candidate = {
                "source": "MLB Stats API affiliated player feeds",
                "mlbam_id": mlbam_id,
                "player_name": clean_value(person.get("fullName")),
                "current_level": level,
                "levels_seen": level,
                "source_sport_ids": str(sport_id),
                "affiliated_team_id": str(team_id or ""),
                "birth_date": clean_value(person.get("birthDate")),
                "age": str(person.get("currentAge", "") or ""),
                "bat_side": clean_value((person.get("batSide") or {}).get("code")),
                "pitch_hand": clean_value((person.get("pitchHand") or {}).get("code")),
                "primary_position": clean_value((person.get("primaryPosition") or {}).get("abbreviation")),
                "position_type": clean_value((person.get("primaryPosition") or {}).get("type")),
                "draft_year": str(person.get("draftYear", "") or ""),
                "active": str(person.get("active", "") or ""),
            }

            existing = merged_by_id.get(mlbam_id)
            if existing is None:
                merged_by_id[mlbam_id] = candidate
                continue

            existing_levels = split_tokens(existing.get("levels_seen"))
            if level not in existing_levels:
                existing_levels.append(level)
            existing["levels_seen"] = "/".join(existing_levels)

            source_ids = split_tokens(existing.get("source_sport_ids"))
            sport_id_text = str(sport_id)
            if sport_id_text not in source_ids:
                source_ids.append(sport_id_text)
            existing["source_sport_ids"] = "/".join(source_ids)

            preferred = choose_better_record(existing, candidate)
            if preferred is candidate:
                candidate["levels_seen"] = existing["levels_seen"]
                candidate["source_sport_ids"] = existing["source_sport_ids"]
                merged_by_id[mlbam_id] = candidate

    return list(merged_by_id.values()), counts_by_level, team_ids


def fetch_team_details(team_id: int) -> tuple[int, dict[str, str]]:
    payload = fetch_json(f"https://statsapi.mlb.com/api/v1/teams/{team_id}")
    team = (payload.get("teams") or [{}])[0]
    return team_id, {
        "affiliated_team": clean_value(team.get("name")),
        "affiliated_team_abbr": clean_value(team.get("abbreviation")),
        "league_name": clean_value((team.get("league") or {}).get("name")),
        "parent_org_id": str(team.get("parentOrgId", "") or ""),
        "parent_org_name": clean_value(team.get("parentOrgName")),
    }


def build_team_lookup(team_ids: set[int]) -> dict[int, dict[str, str]]:
    lookup: dict[int, dict[str, str]] = {}
    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = {executor.submit(fetch_team_details, team_id): team_id for team_id in sorted(team_ids)}
        for future in as_completed(futures):
            team_id, details = future.result()
            lookup[team_id] = details
    return lookup


def write_csv_rows(path: Path, rows: list[dict[str, str]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    rostered_names, rostered_by_name = read_rostered_names()
    affiliated_players, api_counts_by_level, team_ids = collect_affiliated_players()
    team_lookup = build_team_lookup(team_ids)

    output_rows: list[dict[str, str]] = []
    excluded_rows: list[dict[str, str]] = []
    counts_by_parent_org: dict[str, int] = {}
    counts_by_level: dict[str, int] = {label: 0 for label in SPORT_LEVELS.values()}

    for row in affiliated_players:
        team_id_text = clean_value(row.get("affiliated_team_id"))
        team_details = team_lookup.get(int(team_id_text), {}) if team_id_text else {}
        normalized_name = normalize_name(row.get("player_name", ""))
        if normalized_name in rostered_names:
            excluded_rows.append(
                {
                    "player_name": clean_value(row.get("player_name")),
                    "mlbam_id": clean_value(row.get("mlbam_id")),
                    "current_level": clean_value(row.get("current_level")),
                    "rostered_by": rostered_by_name.get(normalized_name, ""),
                }
            )
            continue

        output = dict(row)
        output.update(team_details)
        output_rows.append(output)

        level = clean_value(output.get("current_level"))
        parent_org = clean_value(output.get("parent_org_name")) or "Unknown"
        counts_by_level[level] = counts_by_level.get(level, 0) + 1
        counts_by_parent_org[parent_org] = counts_by_parent_org.get(parent_org, 0) + 1

    output_rows.sort(
        key=lambda row: (
            LEVEL_PRIORITY.get(clean_value(row.get("current_level")), 99),
            clean_value(row.get("parent_org_name")),
            clean_value(row.get("player_name")),
        )
    )
    excluded_rows.sort(key=lambda row: (clean_value(row.get("rostered_by")), clean_value(row.get("player_name"))))

    write_csv_rows(OUTPUT_PATH, output_rows)

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "MLB Stats API affiliated player feeds and team endpoints",
        "eligibility_rule": "all unrostered affiliated minor leaguers",
        "sport_levels": SPORT_LEVELS,
        "api_counts_by_level": api_counts_by_level,
        "deduplicated_affiliated_players": len(affiliated_players),
        "fantasy_rostered_name_count": len(rostered_names),
        "excluded_rostered_players_found_in_affiliated_pool": len(excluded_rows),
        "draft_pool_count": len(output_rows),
        "pool_counts_by_level": counts_by_level,
        "top_parent_org_counts": [
            {"parent_org_name": parent_org, "count": count}
            for parent_org, count in sorted(counts_by_parent_org.items(), key=lambda item: (-item[1], item[0]))[:15]
        ],
        "sample_excluded_players": excluded_rows[:15],
        "output_file": str(OUTPUT_PATH),
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Wrote {len(output_rows)} rows to {OUTPUT_PATH}")
    print(f"Summary written to {SUMMARY_PATH}")
    print(f"Deduplicated affiliated players: {len(affiliated_players)}")
    print(f"Excluded rostered players found in pool: {len(excluded_rows)}")


if __name__ == "__main__":
    main()