from __future__ import annotations

import csv
import json
import math
import unicodedata
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = WORKSPACE_ROOT / "data"

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
    "ARI", "ATL", "BAL", "BOS", "CHC", "CIN", "CLE", "COL", "CWS", "DET", "HOU", "KC", "LAA", "LAD",
    "MIA", "MIL", "MIN", "NYM", "NYY", "ATH", "PHI", "PIT", "SD", "SEA", "SF", "STL", "TB", "TEX", "TOR", "WSH",
}

NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

PLAYER_POOL_PATH = DATA_DIR / "player-pool-2026.csv"
SETTINGS_PATH = DATA_DIR / "startup-draft-settings-2026.json"

DYNASTY_RAW_FANTRAX_PATH = DATA_DIR / "dynasty-rankings-fantraxhq-2026.csv"
MARKET_ADP_FANTASYPROS_PATH = DATA_DIR / "market-adp-fantasypros-2026.csv"
MARKET_ADP_ROTOWIRE_PATH = DATA_DIR / "market-adp-rotowire-2026.csv"
CHADWICK_REGISTER_PATH = DATA_DIR / "chadwick-register-2026.csv"

DYNASTY_RANKINGS_PATH = DATA_DIR / "dynasty-rankings-2026.csv"
MARKET_ADP_PATH = DATA_DIR / "market-adp-2026.csv"

BOARD_ORDER = [
    "Bobby Witt Jr.",
    "Shohei Ohtani",
    "Juan Soto",
    "Gunnar Henderson",
    "Elly De La Cruz",
    "Julio Rodriguez",
    "Ronald Acuna Jr.",
    "Kyle Tucker",
    "Jose Ramirez",
    "Aaron Judge",
    "Mookie Betts",
    "Tarik Skubal",
    "Paul Skenes",
    "Corbin Carroll",
    "Vladimir Guerrero Jr.",
    "Jackson Chourio",
    "Fernando Tatis Jr.",
    "Yordan Alvarez",
    "Oneil Cruz",
    "Francisco Lindor",
    "James Wood",
    "Corbin Burnes",
    "Rafael Devers",
    "Jackson Merrill",
    "Garrett Crochet",
    "CJ Abrams",
    "Bryce Harper",
    "Corey Seager",
    "Wyatt Langford",
    "Austin Riley",
    "Trea Turner",
    "Yoshinobu Yamamoto",
    "Matt Olson",
    "Manny Machado",
    "Zack Wheeler",
    "Jackson Holliday",
    "Ketel Marte",
    "Jarren Duran",
    "Mason Miller",
    "Dylan Crews",
]

BOARD_RANKS = {name: index + 1 for index, name in enumerate(BOARD_ORDER)}


def normalize_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().replace(".", " ").replace("-", " ")
    normalized = " ".join(normalized.split())
    return normalized


NORMALIZED_BOARD_RANKS = {normalize_name(name): rank for name, rank in BOARD_RANKS.items()}


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


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def read_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def merge_positions(*values: str) -> str:
    merged: list[str] = []
    for value in values:
        for position in (value or "").split("/"):
            position = position.strip().upper()
            if position and position not in merged:
                merged.append(position)
    return "/".join(merged)


def player_key(row: dict[str, str]) -> str:
    return clean_value(row.get("mlbam_id")) or normalize_name(clean_value(row.get("player_name")))


def dedupe_player_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    merged_by_key: dict[str, dict[str, str]] = {}
    order: list[str] = []

    for row in rows:
        key = player_key(row)
        if key not in merged_by_key:
            merged_by_key[key] = dict(row)
            order.append(key)
            continue

        existing = merged_by_key[key]
        for field, value in row.items():
            if not clean_value(existing.get(field)) and clean_value(value):
                existing[field] = value

        existing["eligible_positions"] = merge_positions(existing.get("eligible_positions", ""), row.get("eligible_positions", ""))
        existing["source_positions_espn"] = merge_positions(existing.get("source_positions_espn", ""), row.get("source_positions_espn", ""))
        existing["source_positions_yahoo"] = merge_positions(existing.get("source_positions_yahoo", ""), row.get("source_positions_yahoo", ""))
        existing["source_positions_razzball"] = merge_positions(existing.get("source_positions_razzball", ""), row.get("source_positions_razzball", ""))

        player_types = {clean_value(existing.get("player_type")), clean_value(row.get("player_type"))}
        if "hitter" in player_types and "pitcher" in player_types:
            existing["player_type"] = "two-way"
            existing["primary_position"] = existing.get("primary_position") or "TWP"

    return [merged_by_key[key] for key in order]


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


def apply_chadwick_register(rows: list[dict[str, str]], chadwick_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    if not chadwick_rows:
        return rows

    chadwick_index = index_rows(chadwick_rows)
    enriched_rows: list[dict[str, str]] = []
    for row in rows:
        matched = match_row(chadwick_index, row)
        merged = dict(row)
        if matched:
            for field in ["fg_id", "bbref_id", "retrosheet_id"]:
                if clean_value(matched.get(field)):
                    merged[field] = clean_value(matched.get(field))
        enriched_rows.append(merged)
    return enriched_rows


def age_bonus(age: int | None, peak_start: int, peak_end: int, decline_rate: float, youth_penalty_rate: float) -> float:
    if age is None:
        return 0.0
    if peak_start <= age <= peak_end:
        return 0.0
    if age < peak_start:
        return -(peak_start - age) * youth_penalty_rate
    return -(age - peak_end) * decline_rate


def hitter_dynasty_score(row: dict[str, str]) -> float:
    hr = parse_float(row.get("proj_hr")) or 0.0
    runs = parse_float(row.get("proj_r")) or 0.0
    rbi = parse_float(row.get("proj_rbi")) or 0.0
    steals = parse_float(row.get("proj_sb")) or 0.0
    obp = parse_float(row.get("proj_obp")) or 0.300
    plate_appearances = parse_float(row.get("proj_pa")) or 0.0
    age = parse_int(row.get("age"))
    eligible_positions = (row.get("eligible_positions") or "").upper().split("/")

    score = 0.0
    score += runs * 1.0
    score += hr * 3.8
    score += rbi * 1.2
    score += steals * 4.2
    score += max(obp - 0.300, 0.0) * 360.0
    score += plate_appearances * 0.06
    score += age_bonus(age, 24, 28, 3.0, 0.4)

    if "C" in eligible_positions:
        score += 8.0
    if "SS" in eligible_positions:
        score += 4.0
    if "2B" in eligible_positions:
        score += 2.0
    if len([position for position in eligible_positions if position]) >= 2:
        score += 2.5
    return score


def pitcher_dynasty_score(row: dict[str, str]) -> float:
    innings = parse_float(row.get("proj_ip")) or 0.0
    wins = parse_float(row.get("proj_w")) or 0.0
    saves = parse_float(row.get("proj_sv")) or 0.0
    strikeouts = parse_float(row.get("proj_k")) or 0.0
    era = parse_float(row.get("proj_era")) or 4.50
    whip = parse_float(row.get("proj_whip")) or 1.35
    starts = parse_float(row.get("proj_gs")) or 0.0
    age = parse_int(row.get("age"))

    score = 0.0
    score += wins * 4.0
    score += strikeouts * 0.85
    score += saves * 5.0
    score += innings * 0.18
    score += max(0.0, 4.20 - era) * 30.0
    score += max(0.0, 1.30 - whip) * 120.0
    score += starts * 1.5
    score += age_bonus(age, 25, 29, 4.0, 0.2)
    score -= 22.0
    return score


def hitter_adp_score(row: dict[str, str]) -> float:
    hr = parse_float(row.get("proj_hr")) or 0.0
    runs = parse_float(row.get("proj_r")) or 0.0
    rbi = parse_float(row.get("proj_rbi")) or 0.0
    steals = parse_float(row.get("proj_sb")) or 0.0
    obp = parse_float(row.get("proj_obp")) or 0.300
    plate_appearances = parse_float(row.get("proj_pa")) or 0.0
    age = parse_int(row.get("age"))

    score = 0.0
    score += runs * 1.05
    score += hr * 4.2
    score += rbi * 1.3
    score += steals * 3.5
    score += max(obp - 0.305, 0.0) * 260.0
    score += plate_appearances * 0.07
    score += age_bonus(age, 25, 30, 1.8, 0.6)
    return score


def pitcher_adp_score(row: dict[str, str]) -> float:
    innings = parse_float(row.get("proj_ip")) or 0.0
    wins = parse_float(row.get("proj_w")) or 0.0
    saves = parse_float(row.get("proj_sv")) or 0.0
    strikeouts = parse_float(row.get("proj_k")) or 0.0
    era = parse_float(row.get("proj_era")) or 4.50
    whip = parse_float(row.get("proj_whip")) or 1.35
    starts = parse_float(row.get("proj_gs")) or 0.0
    age = parse_int(row.get("age"))

    score = 0.0
    score += wins * 4.5
    score += strikeouts * 0.95
    score += saves * 6.2
    score += innings * 0.22
    score += max(0.0, 4.00 - era) * 36.0
    score += max(0.0, 1.28 - whip) * 125.0
    score += starts * 2.0
    score += age_bonus(age, 26, 31, 2.5, 0.4)
    score -= 12.0
    return score


def dynasty_tier(rank: int) -> str:
    if rank <= 12:
        return "Tier 1"
    if rank <= 30:
        return "Tier 2"
    if rank <= 60:
        return "Tier 3"
    if rank <= 120:
        return "Tier 4"
    if rank <= 240:
        return "Tier 5"
    return "Tier 6"


def market_timing(adp_rank: int) -> str:
    if adp_rank <= 24:
        return "Rounds 1-2"
    if adp_rank <= 60:
        return "Rounds 3-5"
    if adp_rank <= 120:
        return "Rounds 6-10"
    if adp_rank <= 180:
        return "Rounds 11-15"
    if adp_rank <= 300:
        return "Rounds 16-25"
    return "Reserve / Late"


def position_group(row: dict[str, str]) -> str:
    if row.get("player_type") in {"pitcher", "two-way"}:
        starts = parse_float(row.get("proj_gs")) or 0.0
        saves = parse_float(row.get("proj_sv")) or 0.0
        if row.get("player_type") == "two-way":
            return "TWP"
        if saves >= 8 and starts < 5:
            return "RP"
        return "SP"

    positions = (row.get("eligible_positions") or row.get("primary_position") or "").upper().split("/")
    for preferred in ["C", "SS", "2B", "3B", "1B", "OF"]:
        if preferred in positions:
            return preferred
    return row.get("primary_position") or "UTIL"


def baseline_sorted_rows(rows: list[dict[str, str]], score_key: str) -> list[dict[str, str]]:
    return sorted(
        rows,
        key=lambda row: (
            0 if normalize_name(row["player_name"]) in NORMALIZED_BOARD_RANKS else 1,
            NORMALIZED_BOARD_RANKS.get(normalize_name(row["player_name"]), math.inf),
            -float(row[score_key]),
            row["player_name"],
        ),
    )


def build_baseline_maps(rows: list[dict[str, str]]) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    scored_rows = []
    for row in rows:
        scored = dict(row)
        if row.get("player_type") == "pitcher":
            scored["dynasty_model_score"] = f"{pitcher_dynasty_score(row):.6f}"
            scored["adp_model_score"] = f"{pitcher_adp_score(row):.6f}"
        else:
            scored["dynasty_model_score"] = f"{hitter_dynasty_score(row):.6f}"
            scored["adp_model_score"] = f"{hitter_adp_score(row):.6f}"
        scored_rows.append(scored)

    dynasty_map: dict[str, dict[str, str]] = {}
    for rank, row in enumerate(baseline_sorted_rows(scored_rows, "dynasty_model_score"), start=1):
        dynasty_map[player_key(row)] = {
            "fallback_dynasty_rank": str(rank),
            "fallback_dynasty_tier": dynasty_tier(rank),
            "position_group": position_group(row),
        }

    adp_map: dict[str, dict[str, str]] = {}
    for rank, row in enumerate(baseline_sorted_rows(scored_rows, "adp_model_score"), start=1):
        adp_map[player_key(row)] = {
            "fallback_adp": f"{float(rank):.1f}",
            "fallback_overall_rank": str(rank),
            "fallback_market_timing_estimate": market_timing(rank),
        }

    return dynasty_map, adp_map


def raw_dynasty_rank(raw_row: dict[str, str]) -> int | None:
    for field in ["dynasty_rank", "fantrax_dynasty_rank", "overall_rank", "rank"]:
        value = parse_int(raw_row.get(field))
        if value is not None:
            return value
    return None


def raw_dynasty_tier(raw_row: dict[str, str]) -> str:
    for field in ["dynasty_tier", "fantrax_tier", "tier"]:
        value = clean_value(raw_row.get(field))
        if value:
            return value
    return ""


def raw_adp_value(raw_row: dict[str, str], fields: list[str]) -> float | None:
    for field in fields:
        value = parse_float(raw_row.get(field))
        if value is not None:
            return value
    return None


def build_dynasty_output(rows: list[dict[str, str]], baseline_map: dict[str, dict[str, str]], fantrax_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    fantrax_index = index_rows(fantrax_rows)
    sortable_rows = []

    for row in rows:
        base = baseline_map[player_key(row)]
        fantrax_row = match_row(fantrax_index, row)
        source_rank = raw_dynasty_rank(fantrax_row)
        sortable_rows.append(
            {
                "base_row": row,
                "fantrax_row": fantrax_row,
                "sort_key": (0, source_rank, int(base["fallback_dynasty_rank"])) if source_rank is not None else (1, int(base["fallback_dynasty_rank"])),
            }
        )

    sortable_rows.sort(key=lambda item: item["sort_key"])

    output = []
    for final_rank, item in enumerate(sortable_rows, start=1):
        row = item["base_row"]
        fantrax_row = item["fantrax_row"]
        base = baseline_map[player_key(row)]
        source_rank = raw_dynasty_rank(fantrax_row)
        source_tier = raw_dynasty_tier(fantrax_row)
        source_name = clean_value(fantrax_row.get("source")) or "FantraxHQ 2026 dynasty rankings"
        final_source = source_name if source_rank is not None else "workspace-baseline-2026"
        output.append(
            {
                "source": final_source,
                "mlbam_id": clean_value(row.get("mlbam_id")),
                "fg_id": clean_value(row.get("fg_id")),
                "player_name": row.get("player_name", ""),
                "team": clean_value(row.get("mlb_team") or row.get("team")),
                "dynasty_rank": str(final_rank),
                "dynasty_tier": source_tier or dynasty_tier(final_rank),
                "position_group": base["position_group"],
                "source_rank": str(source_rank) if source_rank is not None else "",
                "fallback_rank": base["fallback_dynasty_rank"],
                "rank_method": "fantrax-source" if source_rank is not None else "baseline-fallback",
                "notes": clean_value(fantrax_row.get("notes")) or "Source-specific ingest uses FantraxHQ when present and baseline fallback otherwise.",
            }
        )

    return output


def build_market_adp_output(
    rows: list[dict[str, str]],
    baseline_map: dict[str, dict[str, str]],
    fantasypros_rows: list[dict[str, str]],
    rotowire_rows: list[dict[str, str]],
    settings: dict,
) -> list[dict[str, str]]:
    fantasypros_index = index_rows(fantasypros_rows)
    rotowire_index = index_rows(rotowire_rows)

    market_settings = settings.get("market_adp_blend", {})
    fantasypros_weight = float(market_settings.get("fantasypros_weight", 0.6))
    rotowire_weight = float(market_settings.get("rotowire_weight", 0.4))
    total_weight = fantasypros_weight + rotowire_weight or 1.0

    sortable_rows = []
    for row in rows:
        base = baseline_map[player_key(row)]
        fantasypros_row = match_row(fantasypros_index, row)
        rotowire_row = match_row(rotowire_index, row)

        fantasypros_adp = raw_adp_value(fantasypros_row, ["adp", "fantasypros_adp", "overall_adp"])
        rotowire_adp = raw_adp_value(rotowire_row, ["adp", "rotowire_adp", "overall_adp"])
        fallback_adp = parse_float(base["fallback_adp"]) or 9999.0

        if fantasypros_adp is not None and rotowire_adp is not None:
            final_adp = ((fantasypros_adp * fantasypros_weight) + (rotowire_adp * rotowire_weight)) / total_weight
            final_source = "FantasyPros + RotoWire blend"
            adp_method = "weighted-source-blend"
        elif fantasypros_adp is not None:
            final_adp = fantasypros_adp
            final_source = clean_value(fantasypros_row.get("source")) or "FantasyPros overall ADP"
            adp_method = "fantasypros-source"
        elif rotowire_adp is not None:
            final_adp = rotowire_adp
            final_source = clean_value(rotowire_row.get("source")) or "RotoWire ADP"
            adp_method = "rotowire-source"
        else:
            final_adp = fallback_adp
            final_source = "workspace-baseline-2026"
            adp_method = "baseline-fallback"

        sortable_rows.append(
            {
                "base_row": row,
                "fantasypros_row": fantasypros_row,
                "rotowire_row": rotowire_row,
                "fantasypros_adp": fantasypros_adp,
                "rotowire_adp": rotowire_adp,
                "final_adp": final_adp,
                "fallback_adp": fallback_adp,
                "final_source": final_source,
                "adp_method": adp_method,
            }
        )

    sortable_rows.sort(key=lambda item: (item["final_adp"], item["fallback_adp"], item["base_row"]["player_name"]))

    output = []
    for final_rank, item in enumerate(sortable_rows, start=1):
        row = item["base_row"]
        fantasypros_row = item["fantasypros_row"]
        rotowire_row = item["rotowire_row"]
        fantasypros_adp = item["fantasypros_adp"]
        rotowire_adp = item["rotowire_adp"]
        output.append(
            {
                "source": item["final_source"],
                "mlbam_id": clean_value(row.get("mlbam_id")),
                "fg_id": clean_value(row.get("fg_id")),
                "player_name": row.get("player_name", ""),
                "team": clean_value(row.get("mlb_team") or row.get("team")),
                "adp": f"{item['final_adp']:.1f}",
                "overall_rank": str(final_rank),
                "format": "10-team dynasty startup snake",
                "market_timing_estimate": market_timing(final_rank),
                "fantasypros_adp": f"{fantasypros_adp:.1f}" if fantasypros_adp is not None else "",
                "rotowire_adp": f"{rotowire_adp:.1f}" if rotowire_adp is not None else "",
                "fallback_adp": f"{item['fallback_adp']:.1f}",
                "adp_method": item["adp_method"],
                "notes": clean_value(fantasypros_row.get("notes")) or clean_value(rotowire_row.get("notes")) or "Source-specific ingest uses FantasyPros and RotoWire when present and baseline fallback otherwise.",
            }
        )

    return output


def main() -> None:
    settings = read_settings()
    rows = dedupe_player_rows(read_csv_rows(PLAYER_POOL_PATH))
    rows = apply_chadwick_register(rows, read_csv_rows(CHADWICK_REGISTER_PATH))

    baseline_dynasty_map, baseline_adp_map = build_baseline_maps(rows)
    dynasty_output = build_dynasty_output(rows, baseline_dynasty_map, read_csv_rows(DYNASTY_RAW_FANTRAX_PATH))
    market_output = build_market_adp_output(
        rows,
        baseline_adp_map,
        read_csv_rows(MARKET_ADP_FANTASYPROS_PATH),
        read_csv_rows(MARKET_ADP_ROTOWIRE_PATH),
        settings,
    )

    write_csv(
        DYNASTY_RANKINGS_PATH,
        ["source", "mlbam_id", "fg_id", "player_name", "team", "dynasty_rank", "dynasty_tier", "position_group", "source_rank", "fallback_rank", "rank_method", "notes"],
        dynasty_output,
    )
    write_csv(
        MARKET_ADP_PATH,
        ["source", "mlbam_id", "fg_id", "player_name", "team", "adp", "overall_rank", "format", "market_timing_estimate", "fantasypros_adp", "rotowire_adp", "fallback_adp", "adp_method", "notes"],
        market_output,
    )

    print(f"Wrote {len(dynasty_output)} rows to {DYNASTY_RANKINGS_PATH}")
    print(f"Wrote {len(market_output)} rows to {MARKET_ADP_PATH}")


if __name__ == "__main__":
    main()