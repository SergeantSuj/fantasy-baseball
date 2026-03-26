from __future__ import annotations

import csv
import html
import json
import re
import urllib.request
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = WORKSPACE_ROOT / "data"
OUTPUT_PATH = DATA_DIR / "prospect-rankings-2026.csv"

PIPELINE_URL = "https://www.mlb.com/milb/prospects"
TOP_100_NEEDLE = 'getPlayerRankingsFromSelection({\\"limit\\":100,\\"slug\\":\\"sel-pr-2026-top100\\"})":'
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0 Safari/537.36"

SPORT_LEVELS = {
    1: "MLB",
    11: "AAA",
    12: "AA",
    13: "High-A",
    14: "Single-A",
    16: "Rookie",
}

FIELDNAMES = [
    "source",
    "mlbam_id",
    "fg_id",
    "player_name",
    "org",
    "prospect_rank",
    "org_rank",
    "current_level",
    "eta",
    "prospect_fv",
    "prospect_risk",
    "notes",
]


def clean_value(value: str | None) -> str:
    return (value or "").strip()


def normalize_name(name: str) -> str:
    normalized = clean_value(name).lower().replace(".", " ").replace("-", " ")
    return " ".join(normalized.split())


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_json(url: str) -> dict:
    return json.loads(fetch_text(url))


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def write_csv_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def extract_top_100_payload(page_html: str) -> list[dict]:
    decoded = html.unescape(page_html)
    index = decoded.find(TOP_100_NEEDLE)
    if index < 0:
        raise RuntimeError("Could not find MLB Pipeline Top 100 payload in page HTML")
    payload_text = decoded[index + len(TOP_100_NEEDLE):]
    payload, _ = json.JSONDecoder().raw_decode(payload_text)
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected MLB Pipeline payload shape")
    return payload


def extract_reference_object(decoded_html: str, reference_key: str) -> dict:
    needle = f'"{reference_key}":'
    index = decoded_html.find(needle)
    if index < 0:
        return {}
    try:
        payload, _ = json.JSONDecoder().raw_decode(decoded_html[index + len(needle):])
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def parse_overall_grade(bio_rows: list[dict]) -> str:
    best_grade = ""
    for bio_row in bio_rows or []:
        content = clean_value(bio_row.get("contentText"))
        match = re.search(r"Overall:\s*(\d+)", content)
        if match:
            best_grade = match.group(1)
    return best_grade


def build_mlb_org_map() -> dict[str, str]:
    payload = fetch_json("https://statsapi.mlb.com/api/v1/teams?sportId=1&season=2026")
    mapping: dict[str, str] = {}
    for team in payload.get("teams", []):
        team_id = str(team.get("id") or "")
        abbreviation = clean_value(team.get("abbreviation"))
        if team_id and abbreviation:
            mapping[team_id] = abbreviation
    return mapping


def build_pipeline_rank_rows() -> list[dict[str, str]]:
    page_html = fetch_text(PIPELINE_URL)
    decoded_html = html.unescape(page_html)
    payload_rows = extract_top_100_payload(page_html)

    mlb_org_map = build_mlb_org_map()

    parsed_rows: list[dict[str, str]] = []
    for payload_row in sorted(payload_rows, key=lambda row: row.get("rank", 9999)):
        rank = str(payload_row.get("rank") or "")
        player_entity = payload_row.get("playerEntity") or {}
        player_id = player_entity.get("player", {}).get("__ref", "").split(":", 1)[1]
        person_row = extract_reference_object(decoded_html, f"Person:{player_id}")
        team_reference = clean_value((person_row.get("activeRoster") or {}).get("__ref")) or clean_value((person_row.get("activeRosterMLB") or {}).get("__ref"))
        team_row = extract_reference_object(decoded_html, team_reference) if team_reference else {}
        sport_reference = clean_value((team_row.get("sport") or {}).get("__ref"))
        sport_row = extract_reference_object(decoded_html, sport_reference) if sport_reference else {}
        sport_id = clean_value(sport_row.get("id"))
        parent_org_id = str(team_row.get("parentOrgId") or "")
        current_level = SPORT_LEVELS.get(int(sport_id), "") if sport_id.isdigit() else ""
        team_id = str(team_row.get("id") or "")
        org = mlb_org_map.get(parent_org_id) or mlb_org_map.get(team_id, "")
        position = clean_value(player_entity.get("position"))
        eta = clean_value(player_entity.get("eta"))
        overall_grade = parse_overall_grade(player_entity.get("prospectBio") or [])
        player_name = f"{clean_value(person_row.get('useName'))} {clean_value(person_row.get('useLastName'))}".strip()

        notes_parts = [f"MLB Pipeline Top 100 rank {rank}"]
        if position:
            notes_parts.append(f"position {position}")
        if current_level:
            notes_parts.append(f"current level {current_level}")
        if eta:
            notes_parts.append(f"ETA {eta}")
        if overall_grade:
            notes_parts.append(f"Pipeline overall grade {overall_grade}")

        parsed_rows.append(
            {
                "source": "MLB Pipeline Top 100 2026",
                "mlbam_id": player_id,
                "fg_id": "",
                "player_name": player_name,
                "org": org,
                "prospect_rank": rank,
                "org_rank": "",
                "current_level": current_level,
                "eta": eta,
                "prospect_fv": overall_grade,
                "prospect_risk": "",
                "notes": "; ".join(notes_parts),
            }
        )

    return parsed_rows


def append_note(existing_note: str, new_note: str) -> str:
    existing = clean_value(existing_note)
    new = clean_value(new_note)
    if not existing:
        return new

    parts: list[str] = []
    seen: set[str] = set()
    for chunk in [new, existing]:
        for part in [item.strip() for item in chunk.split(";") if item.strip()]:
            if part in seen:
                continue
            seen.add(part)
            parts.append(part)
    return "; ".join(parts)


def merge_pipeline_rows(existing_rows: list[dict[str, str]], pipeline_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    existing_by_id = {clean_value(row.get("mlbam_id")): dict(row) for row in existing_rows if clean_value(row.get("mlbam_id"))}
    existing_by_name = {normalize_name(row.get("player_name", "")): dict(row) for row in existing_rows if clean_value(row.get("player_name"))}

    top_100_rows: list[dict[str, str]] = []
    used_ids: set[str] = set()

    for pipeline_row in sorted(pipeline_rows, key=lambda row: int(row["prospect_rank"])):
        player_id = clean_value(pipeline_row.get("mlbam_id"))
        existing = existing_by_id.get(player_id)
        if existing is None:
            existing = existing_by_name.get(normalize_name(pipeline_row.get("player_name", "")), {})

        merged = {field: clean_value(existing.get(field)) for field in FIELDNAMES}
        for field in FIELDNAMES:
            if clean_value(pipeline_row.get(field)):
                merged[field] = clean_value(pipeline_row.get(field))

        merged["source"] = "MLB Pipeline Top 100 2026"
        merged["notes"] = append_note(existing.get("notes", ""), pipeline_row.get("notes", ""))
        if not clean_value(merged.get("org_rank")):
            merged["org_rank"] = clean_value(existing.get("org_rank"))

        top_100_rows.append(merged)
        if player_id:
            used_ids.add(player_id)

    remaining_rows = []
    for row in existing_rows:
        player_id = clean_value(row.get("mlbam_id"))
        if player_id and player_id in used_ids:
            continue
        remaining_rows.append(dict(row))

    remaining_rows.sort(key=lambda row: (int(clean_value(row.get("prospect_rank")) or "999999"), clean_value(row.get("player_name"))))

    next_rank = 101
    for row in remaining_rows:
        row["prospect_rank"] = str(next_rank)
        next_rank += 1

    combined_rows = top_100_rows + remaining_rows
    normalized_rows: list[dict[str, str]] = []
    for row in combined_rows:
        normalized_rows.append({field: clean_value(row.get(field)) for field in FIELDNAMES})
    return normalized_rows


def main() -> None:
    existing_rows = read_csv_rows(OUTPUT_PATH)
    pipeline_rows = build_pipeline_rank_rows()
    merged_rows = merge_pipeline_rows(existing_rows, pipeline_rows)
    write_csv_rows(OUTPUT_PATH, merged_rows)

    print(f"Loaded {len(pipeline_rows)} MLB Pipeline Top 100 rows")
    print(f"Wrote {len(merged_rows)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()