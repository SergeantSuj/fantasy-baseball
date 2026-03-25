from __future__ import annotations

import csv
import json
import re
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from bs4 import BeautifulSoup


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = WORKSPACE_ROOT / "data"
CACHE_PATH = DATA_DIR / "mlb_search_cache.json"
OUTPUT_PATH = DATA_DIR / "player-pool-2026.csv"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0 Safari/537.36"

RAZZBALL_SOURCES = {
    "hitter": "https://razzball.com/steamer-hitter-projections/",
    "pitcher": "https://razzball.com/steamer-pitcher-projections/",
}

MLB_PLAYER_SOURCE_URLS = [
    "https://statsapi.mlb.com/api/v1/sports/1/players?season=2026",
    "https://statsapi.mlb.com/api/v1/sports/11/players",
    "https://statsapi.mlb.com/api/v1/sports/12/players",
    "https://statsapi.mlb.com/api/v1/sports/13/players",
    "https://statsapi.mlb.com/api/v1/sports/14/players",
    "https://statsapi.mlb.com/api/v1/sports/16/players",
]
MLB_TEAMS_URL = "https://statsapi.mlb.com/api/v1/teams?sportId=1&season=2026"
MLB_SEARCH_URL = "https://statsapi.mlb.com/api/v1/people/search?names={name}"


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_json(url: str) -> dict:
    return json.loads(fetch_text(url))


def normalize_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().replace(".", " ").replace("-", " ")
    normalized = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", " ", normalized)
    normalized = re.sub(r"[^a-z0-9 ]+", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = re.sub(r"\b([a-z]) ([a-z])\b", r"\1\2", normalized)
    return normalized


def split_positions(value: str) -> list[str]:
    positions: list[str] = []
    for token in re.split(r"[,/]+", value or ""):
        token = token.strip().upper()
        if token and token not in positions:
            positions.append(token)
    return positions


def merge_positions(*position_lists: list[str]) -> str:
    merged: list[str] = []
    for position_list in position_lists:
        for position in position_list:
            if position not in merged:
                merged.append(position)
    return "/".join(merged)


def parse_razzball_table(url: str, player_type: str) -> list[dict]:
    soup = BeautifulSoup(fetch_text(url), "lxml")
    tables = soup.find_all("table")
    if len(tables) < 3:
        raise RuntimeError(f"Projection table not found at {url}")

    table = tables[2]
    rows = table.find_all("tr")
    headers = [cell.get_text(" ", strip=True) for cell in rows[0].find_all(["th", "td"])]

    parsed_rows: list[dict] = []
    for row in rows[1:]:
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all("td")]
        if len(cells) != len(headers):
            continue

        record = dict(zip(headers, cells))
        name = record.get("Name", "").strip()
        team = record.get("Team", "").strip().upper()
        if not name:
            continue

        espn_positions = split_positions(record.get("ESPN", ""))
        yahoo_positions = split_positions(record.get("YAHOO", ""))
        pos_positions = split_positions(record.get("POS", ""))

        eligible_positions = merge_positions(espn_positions, yahoo_positions, pos_positions)
        if not eligible_positions:
            eligible_positions = "P" if player_type == "pitcher" else ""

        output = {
            "player_name": name,
            "player_type": player_type,
            "team": team,
            "eligible_positions": eligible_positions,
            "source_positions_espn": "/".join(espn_positions),
            "source_positions_yahoo": "/".join(yahoo_positions),
            "source_positions_razzball": "/".join(pos_positions),
            "projection_source": "Razzball Steamer 2026",
        }

        for key, value in record.items():
            if key == "#":
                continue
            column_name = f"proj_{key.strip().lower().replace('%', 'pct').replace('/', '_').replace(' ', '_')}"
            output[column_name] = value

        parsed_rows.append(output)

    return parsed_rows


def build_team_map() -> dict[int, str]:
    payload = fetch_json(MLB_TEAMS_URL)
    return {team["id"]: team.get("abbreviation", "") for team in payload.get("teams", [])}


def load_search_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def save_search_cache(cache: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")


def search_player(name: str) -> dict | None:
    encoded_name = urllib.parse.quote(name)
    payload = fetch_json(MLB_SEARCH_URL.format(name=encoded_name))
    people = payload.get("people", [])
    normalized_target = normalize_name(name)

    exact = [person for person in people if normalize_name(person.get("fullName", "")) == normalized_target]
    if exact:
        exact.sort(key=lambda person: (not person.get("active", False), person.get("id", 0)))
        return exact[0]

    return None


def fetch_metadata(rows: list[dict]) -> tuple[dict[str, dict], list[str]]:
    team_map = build_team_map()
    people_by_name: dict[str, dict] = {}
    for url in MLB_PLAYER_SOURCE_URLS:
        for person in fetch_json(url).get("people", []):
            normalized_name = normalize_name(person.get("fullName", ""))
            existing = people_by_name.get(normalized_name)
            if existing is None:
                people_by_name[normalized_name] = person
                continue

            existing_has_debut = bool(existing.get("mlbDebutDate"))
            candidate_has_debut = bool(person.get("mlbDebutDate"))
            if candidate_has_debut and not existing_has_debut:
                people_by_name[normalized_name] = person
    cache = load_search_cache()

    missing_names = sorted({row["player_name"] for row in rows if normalize_name(row["player_name"]) not in people_by_name})

    unresolved: list[str] = []

    def resolve_missing_name(name: str) -> tuple[str, dict | None]:
        normalized = normalize_name(name)
        cached = cache.get(normalized)
        if cached is not None:
            return normalized, cached
        person = search_player(name)
        return normalized, person

    if missing_names:
        with ThreadPoolExecutor(max_workers=12) as executor:
            futures = {executor.submit(resolve_missing_name, name): name for name in missing_names}
            for future in as_completed(futures):
                normalized_name, person = future.result()
                cache[normalized_name] = person

    for normalized_name, person in cache.items():
        if person and normalized_name not in people_by_name:
            people_by_name[normalized_name] = person

    for name in missing_names:
        if normalize_name(name) not in people_by_name:
            unresolved.append(name)

    save_search_cache(cache)

    metadata_by_name: dict[str, dict] = {}
    for normalized_name, person in people_by_name.items():
        current_team = person.get("currentTeam", {})
        metadata_by_name[normalized_name] = {
            "mlbam_id": person.get("id", ""),
            "birth_date": person.get("birthDate", ""),
            "age": person.get("currentAge", ""),
            "bat_side": person.get("batSide", {}).get("code", ""),
            "pitch_hand": person.get("pitchHand", {}).get("code", ""),
            "primary_position": person.get("primaryPosition", {}).get("abbreviation", ""),
            "mlb_team": team_map.get(current_team.get("id"), ""),
            "active": person.get("active", ""),
        }

    return metadata_by_name, unresolved


def enrich_rows(rows: list[dict], metadata_by_name: dict[str, dict]) -> list[dict]:
    enriched: list[dict] = []
    for row in rows:
        metadata = metadata_by_name.get(normalize_name(row["player_name"]), {})
        output = {
            "player_name": row["player_name"],
            "player_type": row["player_type"],
            "team": row["team"],
            "mlb_team": metadata.get("mlb_team", ""),
            "mlbam_id": metadata.get("mlbam_id", ""),
            "birth_date": metadata.get("birth_date", ""),
            "age": metadata.get("age", ""),
            "bat_side": metadata.get("bat_side", ""),
            "pitch_hand": metadata.get("pitch_hand", ""),
            "primary_position": metadata.get("primary_position", ""),
            "eligible_positions": row["eligible_positions"] or metadata.get("primary_position", ""),
            "source_positions_espn": row["source_positions_espn"],
            "source_positions_yahoo": row["source_positions_yahoo"],
            "source_positions_razzball": row["source_positions_razzball"],
            "projection_source": row["projection_source"],
        }

        for key, value in row.items():
            if key in output:
                continue
            output[key] = value

        enriched.append(output)

    enriched.sort(key=lambda row: (row["player_type"], row["player_name"]))
    return enriched


def write_csv(rows: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for field in row:
            if field not in fieldnames:
                fieldnames.append(field)

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    rows = []
    for player_type, url in RAZZBALL_SOURCES.items():
        rows.extend(parse_razzball_table(url, player_type))

    metadata_by_name, unresolved = fetch_metadata(rows)
    enriched_rows = enrich_rows(rows, metadata_by_name)
    write_csv(enriched_rows)

    print(f"Wrote {len(enriched_rows)} rows to {OUTPUT_PATH}")
    print(f"Unique players: {len({row['player_name'] for row in enriched_rows})}")
    print(f"Unresolved ages/metadata: {len(unresolved)}")
    if unresolved:
        print("Sample unresolved names:")
        for name in unresolved[:25]:
            print(f"- {name}")
    print(f"Generated at: {datetime.now(UTC).isoformat()}")


if __name__ == "__main__":
    main()