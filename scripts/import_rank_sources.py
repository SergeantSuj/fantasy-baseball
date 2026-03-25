from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = WORKSPACE_ROOT / "data"
IMPORTS_DIR = DATA_DIR / "imports"

TEAM_ALIASES = {
    "ARI": "AZ",
    "AZ": "AZ",
    "CHW": "CWS",
    "CWS": "CWS",
    "KCR": "KC",
    "KC": "KC",
    "OAK": "ATH",
    "ATH": "ATH",
    "SDP": "SD",
    "SD": "SD",
    "SFG": "SF",
    "SF": "SF",
    "TBR": "TB",
    "TB": "TB",
    "WSN": "WSH",
    "WSH": "WSH",
}

MLB_TEAMS = {
    "AZ", "ARI", "ATL", "BAL", "BOS", "CHC", "CIN", "CLE", "COL", "CWS", "DET", "HOU", "KC", "LAA", "LAD",
    "MIA", "MIL", "MIN", "NYM", "NYY", "ATH", "PHI", "PIT", "SD", "SEA", "SF", "STL", "TB", "TEX", "TOR", "WSH",
}

NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
POSITION_TAGS = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "OF", "SP", "RP", "P", "DH", "UT", "UTIL", "TWP"}
STATUS_TAG_PATTERN = re.compile(r"\s+(?:NRI|OUT|DTD|NA|IL10|IL15|IL60|D10|D15|D60|SUSP)\s*$", re.IGNORECASE)

PLAYER_POOL_PATH = DATA_DIR / "player-pool-2026.csv"
CHADWICK_REGISTER_PATH = DATA_DIR / "chadwick-register-2026.csv"

FANTRAX_INPUT_PATH = IMPORTS_DIR / "fantraxhq-dynasty-2026.csv"
FANTRAX_ALTERNATE_INPUT_PATH = IMPORTS_DIR / "fantraxhq-adp-2026.csv"
FANTASYPROS_INPUT_PATH = IMPORTS_DIR / "fantasypros-adp-2026.csv"
ROTOWIRE_INPUT_PATH = IMPORTS_DIR / "rotowire-adp-2026.csv"

FANTRAX_OUTPUT_PATH = DATA_DIR / "dynasty-rankings-fantraxhq-2026.csv"
FANTASYPROS_OUTPUT_PATH = DATA_DIR / "market-adp-fantasypros-2026.csv"
ROTOWIRE_OUTPUT_PATH = DATA_DIR / "market-adp-rotowire-2026.csv"


def normalize_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().replace(".", " ").replace("-", " ")
    normalized = " ".join(normalized.split())
    return normalized


def clean_import_text(value: str | None) -> str:
    text = clean_value(value)
    text = text.replace("\ufffd", "")
    text = text.replace("\xa0", " ")
    return " ".join(text.split())


def clean_value(value: str | None) -> str:
    return (value or "").strip()


def clean_team(value: str | None) -> str:
    team = clean_value(value).upper()
    return TEAM_ALIASES.get(team, team)


def normalize_lookup_name(name: str) -> str:
    return normalize_name(name)


def normalize_lookup_name_without_suffix(name: str) -> str:
    parts = normalize_lookup_name(name).split()
    while parts and parts[-1] in NAME_SUFFIXES:
        parts.pop()
    return " ".join(parts)


def parse_float(value: str | None) -> float | None:
    text = clean_value(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_int(value: str | None) -> int | None:
    number = parse_float(value)
    if number is None:
        return None
    return int(number)


def normalize_header(header: str) -> str:
    return normalize_name(header).replace(" ", "_")


def sniff_dialect(path: Path) -> csv.Dialect:
    sample = read_source_text(path)[:4096]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;")
    except csv.Error:
        return csv.get_dialect("excel")


def read_source_text(path: Path) -> str:
    for encoding in ["utf-8-sig", "cp1252", "latin-1"]:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8-sig", errors="replace")


def read_input_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    dialect = sniff_dialect(path)
    source_text = read_source_text(path)
    from io import StringIO

    lines = source_text.splitlines()
    header_index = 0
    for index, line in enumerate(lines):
        normalized_line = normalize_header(line)
        if "player_name" in normalized_line or ",name," in f",{normalized_line}," or normalized_line.startswith("rank,name"):
            header_index = index
            break

    csv_file = StringIO("\n".join(lines[header_index:]))
    try:
        reader = csv.DictReader(csv_file, dialect=dialect)
        rows: list[dict[str, str]] = []
        for row in reader:
            normalized_row = {normalize_header(key): value or "" for key, value in row.items() if key is not None}
            rows.append(normalized_row)
        return rows
    finally:
        csv_file.close()


def read_fantrax_input_rows() -> list[dict[str, str]]:
    primary_rows = read_input_rows(FANTRAX_INPUT_PATH)
    if primary_rows:
        return primary_rows
    return read_input_rows(FANTRAX_ALTERNATE_INPUT_PATH)


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


def build_match_keys(row: dict[str, str]) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []

    mlbam_id = clean_value(row.get("mlbam_id"))
    if mlbam_id:
        keys.append(("mlbam_id", mlbam_id))

    fg_id = clean_value(row.get("fg_id"))
    if fg_id:
        keys.append(("fg_id", fg_id))

    player_name = clean_value(row.get("player_name"))
    if not player_name:
        return keys

    name_variants = {normalize_lookup_name(player_name), normalize_lookup_name_without_suffix(player_name)}
    team = clean_team(row.get("team") or row.get("mlb_team") or row.get("org") or row.get("organization"))
    for normalized_name in name_variants:
        if not normalized_name:
            continue
        if team:
            keys.append(("name_team", f"{normalized_name}|{team}"))
        keys.append(("name_only", normalized_name))
    return keys


def index_rows(rows: list[dict[str, str]]) -> dict[str, dict[str, dict[str, str]]]:
    index = {"mlbam_id": {}, "fg_id": {}, "name_team": {}, "name_only": {}}
    for row in rows:
        for key_type, key in build_match_keys(row):
            index[key_type].setdefault(key, row)
    return index


def match_row(index: dict[str, dict[str, dict[str, str]]], row: dict[str, str]) -> dict[str, str]:
    for key_type, key in build_match_keys(row):
        match = index[key_type].get(key)
        if match:
            return match
    return {}


def dedupe_player_pool(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    merged_by_key: dict[str, dict[str, str]] = {}
    order: list[str] = []

    for row in rows:
        key = clean_value(row.get("mlbam_id")) or normalize_name(clean_value(row.get("player_name")))
        if key not in merged_by_key:
            merged_by_key[key] = dict(row)
            order.append(key)
            continue

        existing = merged_by_key[key]
        for field, value in row.items():
            if not clean_value(existing.get(field)) and clean_value(value):
                existing[field] = value

    return [merged_by_key[key] for key in order]


def lookup_field(row: dict[str, str], candidates: list[str]) -> str:
    for field in candidates:
        value = clean_import_text(row.get(field))
        if value:
            return value
    return ""


def lookup_int(row: dict[str, str], candidates: list[str]) -> int | None:
    for field in candidates:
        value = parse_int(row.get(field))
        if value is not None:
            return value
    return None


def lookup_float(row: dict[str, str], candidates: list[str]) -> float | None:
    for field in candidates:
        value = parse_float(row.get(field))
        if value is not None:
            return value
    return None


def split_embedded_team(player_name: str, fallback_team: str) -> tuple[str, str]:
    cleaned_name = clean_import_text(player_name)
    cleaned_team = clean_team(fallback_team)

    while True:
        updated_name = STATUS_TAG_PATTERN.sub("", cleaned_name).strip()
        if updated_name != cleaned_name:
            cleaned_name = updated_name
            continue

        match = re.search(r"\s*\(([^()]+)\)\s*$", cleaned_name)
        if not match:
            break

        tag = clean_value(match.group(1)).upper()
        alias_tag = TEAM_ALIASES.get(tag, tag)
        if tag in TEAM_ALIASES or alias_tag in MLB_TEAMS or alias_tag == "FA":
            if not cleaned_team:
                cleaned_team = alias_tag
            cleaned_name = cleaned_name[:match.start()].strip()
            continue

        if tag in POSITION_TAGS:
            cleaned_name = cleaned_name[:match.start()].strip()
            continue

        break

    return cleaned_name, cleaned_team


def enrich_with_ids(row: dict[str, str], player_index: dict[str, dict[str, dict[str, str]]], chadwick_index: dict[str, dict[str, dict[str, str]]]) -> dict[str, str]:
    raw_player_name = lookup_field(row, ["player_name", "player", "player_name_team", "name"])
    raw_team = lookup_field(row, ["team", "tm", "org", "organization"])
    player_name, embedded_team = split_embedded_team(raw_player_name, raw_team)

    candidate = {
        "mlbam_id": lookup_field(row, ["mlbam_id", "mlb_id", "mlbam", "playerid_mlbam"]),
        "fg_id": lookup_field(row, ["fg_id", "fangraphs_id", "playerid_fangraphs"]),
        "player_name": player_name,
        "team": embedded_team,
    }

    chadwick_match = match_row(chadwick_index, candidate)
    player_match = match_row(player_index, {**candidate, **chadwick_match})

    enriched = dict(row)
    enriched["player_name"] = candidate["player_name"] or clean_value(chadwick_match.get("player_name")) or clean_value(player_match.get("player_name"))
    enriched["team"] = clean_team(candidate["team"] or chadwick_match.get("team") or player_match.get("mlb_team") or player_match.get("team"))
    enriched["mlbam_id"] = candidate["mlbam_id"] or clean_value(chadwick_match.get("mlbam_id")) or clean_value(player_match.get("mlbam_id"))
    enriched["fg_id"] = candidate["fg_id"] or clean_value(chadwick_match.get("fg_id")) or clean_value(player_match.get("fg_id")) or clean_value(player_match.get("proj_razzid"))
    return enriched


def convert_fantrax_rows(rows: list[dict[str, str]], player_index: dict[str, dict[str, dict[str, str]]], chadwick_index: dict[str, dict[str, dict[str, str]]]) -> list[dict[str, str]]:
    converted: list[dict[str, str]] = []
    for row in rows:
        enriched = enrich_with_ids(row, player_index, chadwick_index)
        player_name = clean_value(enriched.get("player_name"))
        dynasty_rank = lookup_int(row, ["dynasty_rank", "roto", "rank", "overall_rank", "overall", "points"])
        if not player_name or dynasty_rank is None:
            continue
        converted.append(
            {
                "source": lookup_field(row, ["source"]) or "FantraxHQ 2026 dynasty rankings",
                "mlbam_id": clean_value(enriched.get("mlbam_id")),
                "fg_id": clean_value(enriched.get("fg_id")),
                "player_name": player_name,
                "team": clean_team(enriched.get("team")),
                "dynasty_rank": str(dynasty_rank),
                "dynasty_tier": lookup_field(row, ["dynasty_tier", "tier"]),
                "notes": lookup_field(row, ["notes", "comment", "comments"]),
            }
        )
    converted.sort(key=lambda row: (parse_int(row.get("dynasty_rank")) or 999999, row.get("player_name", "")))
    return converted


def convert_adp_rows(rows: list[dict[str, str]], player_index: dict[str, dict[str, dict[str, str]]], chadwick_index: dict[str, dict[str, dict[str, str]]], default_source: str) -> list[dict[str, str]]:
    converted: list[dict[str, str]] = []
    for row in rows:
        enriched = enrich_with_ids(row, player_index, chadwick_index)
        player_name = clean_value(enriched.get("player_name"))
        adp = lookup_float(row, ["adp", "avg", "avg_pick", "average_pick", "average_pick_overall", "overall_adp", "avg_", "avg_adp"])
        overall_rank = lookup_int(row, ["overall_rank", "rank", "overall", "rk"])
        if not player_name or adp is None:
            continue
        converted.append(
            {
                "source": lookup_field(row, ["source"]) or default_source,
                "mlbam_id": clean_value(enriched.get("mlbam_id")),
                "fg_id": clean_value(enriched.get("fg_id")),
                "player_name": player_name,
                "team": clean_team(enriched.get("team")),
                "adp": f"{adp:.1f}",
                "overall_rank": str(overall_rank) if overall_rank is not None else "",
                "format": lookup_field(row, ["format", "league_format", "scoring_format"]) or "10-team dynasty startup snake",
                "notes": lookup_field(row, ["notes", "comment", "comments"]),
            }
        )
    converted.sort(key=lambda row: (parse_float(row.get("adp")) or 999999.0, row.get("player_name", "")))
    return converted


def main() -> None:
    player_rows = dedupe_player_pool(read_csv_rows(PLAYER_POOL_PATH))
    chadwick_rows = read_csv_rows(CHADWICK_REGISTER_PATH)
    player_index = index_rows(player_rows)
    chadwick_index = index_rows(chadwick_rows)

    fantrax_rows = convert_fantrax_rows(read_fantrax_input_rows(), player_index, chadwick_index)
    fantasypros_rows = convert_adp_rows(read_input_rows(FANTASYPROS_INPUT_PATH), player_index, chadwick_index, "FantasyPros overall ADP")
    rotowire_rows = convert_adp_rows(read_input_rows(ROTOWIRE_INPUT_PATH), player_index, chadwick_index, "RotoWire ADP")

    write_csv(
        FANTRAX_OUTPUT_PATH,
        ["source", "mlbam_id", "fg_id", "player_name", "team", "dynasty_rank", "dynasty_tier", "notes"],
        fantrax_rows,
    )
    write_csv(
        FANTASYPROS_OUTPUT_PATH,
        ["source", "mlbam_id", "fg_id", "player_name", "team", "adp", "overall_rank", "format", "notes"],
        fantasypros_rows,
    )
    write_csv(
        ROTOWIRE_OUTPUT_PATH,
        ["source", "mlbam_id", "fg_id", "player_name", "team", "adp", "overall_rank", "format", "notes"],
        rotowire_rows,
    )

    print(f"Wrote {len(fantrax_rows)} rows to {FANTRAX_OUTPUT_PATH}")
    print(f"Wrote {len(fantasypros_rows)} rows to {FANTASYPROS_OUTPUT_PATH}")
    print(f"Wrote {len(rotowire_rows)} rows to {ROTOWIRE_OUTPUT_PATH}")


if __name__ == "__main__":
    main()