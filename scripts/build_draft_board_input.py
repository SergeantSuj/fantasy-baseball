from __future__ import annotations

import csv
import json
import unicodedata
from datetime import UTC, datetime
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
DYNASTY_RANKINGS_PATH = DATA_DIR / "dynasty-rankings-2026.csv"
PROSPECT_RANKINGS_PATH = DATA_DIR / "prospect-rankings-2026.csv"
MARKET_ADP_PATH = DATA_DIR / "market-adp-2026.csv"
PLAYER_CONTEXT_PATH = DATA_DIR / "player-context-2026.csv"
PLAYER_INJURIES_PATH = DATA_DIR / "player-injuries-2026.csv"
PLAYER_TRANSACTIONS_PATH = DATA_DIR / "player-transactions-2026.csv"
SKILL_METRICS_PATH = DATA_DIR / "skill-metrics-2026.csv"
ACTUAL_STATS_PATH = DATA_DIR / "player-stats-2025.csv"
SETTINGS_PATH = DATA_DIR / "startup-draft-settings-2026.json"

OUTPUT_PATH = DATA_DIR / "draft-board-input-2026.csv"
SUMMARY_PATH = DATA_DIR / "draft-board-input-summary-2026.json"


def normalize_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().replace(".", " ").replace("-", " ")
    normalized = " ".join(normalized.split())
    return normalized


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
        reader = csv.DictReader(csv_file)
        return [{key: value or "" for key, value in row.items()} for row in reader]


def read_settings(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def merge_positions(*values: str) -> str:
    merged: list[str] = []
    for value in values:
        for position in (value or "").split("/"):
            position = position.strip().upper()
            if position and position not in merged:
                merged.append(position)
    return "/".join(merged)


def dedupe_base_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
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

        existing["eligible_positions"] = merge_positions(existing.get("eligible_positions", ""), row.get("eligible_positions", ""))
        existing["source_positions_espn"] = merge_positions(existing.get("source_positions_espn", ""), row.get("source_positions_espn", ""))
        existing["source_positions_yahoo"] = merge_positions(existing.get("source_positions_yahoo", ""), row.get("source_positions_yahoo", ""))
        existing["source_positions_razzball"] = merge_positions(existing.get("source_positions_razzball", ""), row.get("source_positions_razzball", ""))

        player_types = {clean_value(existing.get("player_type")), clean_value(row.get("player_type"))}
        if "hitter" in player_types and "pitcher" in player_types:
            existing["player_type"] = "two-way"
            if not clean_value(existing.get("primary_position")):
                existing["primary_position"] = "TWP"

    return [merged_by_key[key] for key in order]


def build_match_keys(row: dict[str, str]) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []

    mlbam_id = clean_value(row.get("mlbam_id"))
    if mlbam_id:
        keys.append(("mlbam_id", mlbam_id))

    player_name = clean_value(row.get("player_name"))
    if not player_name:
        return keys

    name_variants = {normalize_lookup_name(player_name), normalize_lookup_name_without_suffix(player_name)}
    team = clean_team(
        row.get("mlb_team")
        or row.get("team")
        or row.get("org")
        or row.get("organization")
    )
    for normalized_name in name_variants:
        if not normalized_name:
            continue
        if team:
            keys.append(("name_team", f"{normalized_name}|{team}"))
        keys.append(("name_only", normalized_name))
    return keys


def index_rows(rows: list[dict[str, str]]) -> dict[str, dict[str, dict[str, str]]]:
    index = {
        "mlbam_id": {},
        "name_team": {},
        "name_only": {},
    }
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


def derive_dynasty_tier(rank_text: str | None, explicit_tier: str | None) -> str:
    explicit = clean_value(explicit_tier)
    if explicit:
        return explicit

    rank = parse_int(rank_text)
    if rank is None:
        return ""
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


def derive_market_timing(adp_text: str | None, explicit_bucket: str | None) -> str:
    explicit = clean_value(explicit_bucket)
    if explicit:
        return explicit

    adp = parse_float(adp_text)
    if adp is None:
        return ""
    if adp <= 24:
        return "Rounds 1-2"
    if adp <= 60:
        return "Rounds 3-5"
    if adp <= 120:
        return "Rounds 6-10"
    if adp <= 180:
        return "Rounds 11-15"
    if adp <= 300:
        return "Rounds 16-25"
    return "Reserve / Late"


def derive_player_stage(base_row: dict[str, str], prospect_row: dict[str, str], context_row: dict[str, str]) -> str:
    current_level = clean_value(context_row.get("current_level"))
    if current_level:
        if current_level.upper() in {"MLB", "MAJORS"}:
            return "MLB"
        return "Prospect"

    if clean_value(prospect_row.get("prospect_rank")):
        return "Prospect"

    mlb_team = clean_value(base_row.get("mlb_team"))
    if mlb_team:
        return "MLB"
    return "Unknown"


def derive_current_level(base_row: dict[str, str], prospect_row: dict[str, str], context_row: dict[str, str], transaction_row: dict[str, str]) -> str:
    current_level = clean_value(context_row.get("current_level")) or clean_value(transaction_row.get("current_level"))
    if current_level:
        return current_level
    if clean_value(prospect_row.get("prospect_rank")):
        return "Prospect"
    if clean_value(base_row.get("mlb_team")):
        return "MLB"
    return ""


def derive_risk_flag(base_row: dict[str, str], prospect_row: dict[str, str], context_row: dict[str, str]) -> str:
    explicit = clean_value(context_row.get("risk_flag"))
    if explicit:
        return explicit

    injury_status = clean_value(context_row.get("injury_status")).lower()
    role_security = clean_value(context_row.get("role_security")).lower()
    prospect_risk = clean_value(prospect_row.get("prospect_risk")).lower()

    high_injury_terms = ("60-day", "out", "surgery", "indefinite", "doubtful")
    if any(term in injury_status for term in high_injury_terms):
        return "high"

    if prospect_risk in {"high", "extreme"}:
        return "high"

    medium_role_terms = {"platoon", "committee", "uncertain", "fragile"}
    if role_security in medium_role_terms:
        return "medium"

    if injury_status or role_security or prospect_risk in {"medium", "moderate"}:
        return "medium"

    return "low"


def derive_skill_flag(skill_row: dict[str, str]) -> str:
    explicit = clean_value(skill_row.get("skill_flag"))
    if explicit:
        return explicit

    xwoba = parse_float(skill_row.get("xwoba"))
    barrel_rate = parse_float(skill_row.get("barrel_rate"))
    whiff_rate = parse_float(skill_row.get("whiff_rate"))

    if xwoba is not None and xwoba >= 0.360:
        return "impact"
    if barrel_rate is not None and barrel_rate >= 12:
        return "impact"
    if whiff_rate is not None and whiff_rate >= 30:
        return "swing-miss"
    return ""


def infer_injury_status_from_transaction(transaction_row: dict[str, str]) -> str:
    status = clean_value(transaction_row.get("transaction_status")).lower()
    notes = clean_value(transaction_row.get("notes")).lower()
    text = f"{status} {notes}"

    if "activated" in text or "reinstated" in text:
        return ""
    if "60-day injured list" in text:
        return "60-day IL"
    if "15-day injured list" in text:
        return "15-day IL"
    if "10-day injured list" in text:
        return "10-day IL"
    if "7-day injured list" in text:
        return "7-day IL"
    if "injured list" in text or "il" in status:
        return "Injured List"
    return ""


def derive_pitcher_role(base_row: dict[str, str], context_row: dict[str, str], actual_stats_row: dict[str, str]) -> str:
    if clean_value(base_row.get("player_type")) not in {"pitcher", "two-way"}:
        return ""

    explicit_rotation = clean_value(context_row.get("rotation_role"))
    explicit_bullpen = clean_value(context_row.get("bullpen_role"))
    if explicit_rotation and not explicit_bullpen:
        return "starter"
    if explicit_bullpen and not explicit_rotation:
        return "reliever"

    proj_gs = parse_float(base_row.get("proj_gs")) or 0.0
    actual_gs = parse_float(actual_stats_row.get("actual_2025_gs")) or 0.0
    gs_signal = max(proj_gs, actual_gs)

    if gs_signal >= 5:
        return "starter"
    if gs_signal <= 1:
        return "reliever"
    return "swing"


def merge_player_row(
    base_row: dict[str, str],
    dynasty_row: dict[str, str],
    prospect_row: dict[str, str],
    adp_row: dict[str, str],
    context_row: dict[str, str],
    injury_row: dict[str, str],
    transaction_row: dict[str, str],
    skill_row: dict[str, str],
    actual_stats_row: dict[str, str],
) -> dict[str, str]:
    output = dict(base_row)

    output["dynasty_source"] = clean_value(dynasty_row.get("source"))
    output["dynasty_rank"] = clean_value(dynasty_row.get("dynasty_rank"))
    output["dynasty_tier"] = derive_dynasty_tier(dynasty_row.get("dynasty_rank"), dynasty_row.get("dynasty_tier"))
    output["dynasty_notes"] = clean_value(dynasty_row.get("notes"))

    output["prospect_source"] = clean_value(prospect_row.get("source"))
    output["prospect_rank"] = clean_value(prospect_row.get("prospect_rank"))
    output["org_rank"] = clean_value(prospect_row.get("org_rank"))
    output["current_level"] = derive_current_level(base_row, prospect_row, context_row, transaction_row) or clean_value(prospect_row.get("current_level"))
    output["eta"] = clean_value(prospect_row.get("eta"))
    output["prospect_fv"] = clean_value(prospect_row.get("prospect_fv"))
    output["prospect_risk"] = clean_value(prospect_row.get("prospect_risk"))
    output["prospect_notes"] = clean_value(prospect_row.get("notes"))

    output["adp_source"] = clean_value(adp_row.get("source"))
    output["adp"] = clean_value(adp_row.get("adp"))
    output["overall_market_rank"] = clean_value(adp_row.get("overall_rank"))
    output["market_timing_estimate"] = derive_market_timing(adp_row.get("adp"), adp_row.get("market_timing_estimate"))
    output["market_notes"] = clean_value(adp_row.get("notes"))

    pitcher_role_estimate = derive_pitcher_role(base_row, context_row, actual_stats_row)
    output["pitcher_role_estimate"] = pitcher_role_estimate
    output["rotation_role"] = clean_value(context_row.get("rotation_role")) or ("rotation" if pitcher_role_estimate == "starter" else "")
    output["bullpen_role"] = clean_value(context_row.get("bullpen_role")) or ("bullpen" if pitcher_role_estimate == "reliever" else "")
    output["closer_role"] = clean_value(context_row.get("closer_role"))
    output["role_security"] = clean_value(context_row.get("role_security"))
    inferred_injury_status = infer_injury_status_from_transaction(transaction_row)
    output["injury_tracking_source"] = clean_value(injury_row.get("source")) or (clean_value(transaction_row.get("source")) if inferred_injury_status else "")
    output["injury_status"] = clean_value(injury_row.get("injury_status") or context_row.get("injury_status") or inferred_injury_status)
    output["expected_return"] = clean_value(injury_row.get("expected_return") or context_row.get("expected_return"))
    output["injury_last_updated"] = clean_value(injury_row.get("last_updated"))
    output["transaction_source"] = clean_value(transaction_row.get("source"))
    output["transaction_status"] = clean_value(transaction_row.get("transaction_status") or context_row.get("transaction_status"))
    output["transaction_date"] = clean_value(transaction_row.get("transaction_date"))
    output["context_notes"] = clean_value(context_row.get("notes"))
    output["injury_notes"] = clean_value(injury_row.get("notes"))
    output["transaction_notes"] = clean_value(transaction_row.get("notes"))

    output["skill_source"] = clean_value(skill_row.get("source"))
    output["avg_exit_velocity"] = clean_value(skill_row.get("avg_exit_velocity"))
    output["barrel_rate"] = clean_value(skill_row.get("barrel_rate"))
    output["xwoba"] = clean_value(skill_row.get("xwoba"))
    output["sprint_speed"] = clean_value(skill_row.get("sprint_speed"))
    output["whiff_rate"] = clean_value(skill_row.get("whiff_rate"))
    output["chase_rate"] = clean_value(skill_row.get("chase_rate"))
    output["ivb"] = clean_value(skill_row.get("ivb"))
    output["hb"] = clean_value(skill_row.get("hb"))
    output["skill_flag"] = derive_skill_flag(skill_row)
    output["skill_notes"] = clean_value(skill_row.get("notes"))

    output["actual_stats_source"] = clean_value(actual_stats_row.get("source"))
    output["actual_stats_season"] = clean_value(actual_stats_row.get("season"))
    output["actual_2025_team"] = clean_value(actual_stats_row.get("team"))
    output["actual_2025_g"] = clean_value(actual_stats_row.get("actual_2025_g"))
    output["actual_2025_pa"] = clean_value(actual_stats_row.get("actual_2025_pa"))
    output["actual_2025_ab"] = clean_value(actual_stats_row.get("actual_2025_ab"))
    output["actual_2025_r"] = clean_value(actual_stats_row.get("actual_2025_r"))
    output["actual_2025_hr"] = clean_value(actual_stats_row.get("actual_2025_hr"))
    output["actual_2025_rbi"] = clean_value(actual_stats_row.get("actual_2025_rbi"))
    output["actual_2025_sb"] = clean_value(actual_stats_row.get("actual_2025_sb"))
    output["actual_2025_h"] = clean_value(actual_stats_row.get("actual_2025_h"))
    output["actual_2025_bb"] = clean_value(actual_stats_row.get("actual_2025_bb"))
    output["actual_2025_so"] = clean_value(actual_stats_row.get("actual_2025_so"))
    output["actual_2025_avg"] = clean_value(actual_stats_row.get("actual_2025_avg"))
    output["actual_2025_obp"] = clean_value(actual_stats_row.get("actual_2025_obp"))
    output["actual_2025_slg"] = clean_value(actual_stats_row.get("actual_2025_slg"))
    output["actual_2025_ops"] = clean_value(actual_stats_row.get("actual_2025_ops"))
    output["actual_2025_pitch_g"] = clean_value(actual_stats_row.get("actual_2025_pitch_g"))
    output["actual_2025_gs"] = clean_value(actual_stats_row.get("actual_2025_gs"))
    output["actual_2025_ip"] = clean_value(actual_stats_row.get("actual_2025_ip"))
    output["actual_2025_w"] = clean_value(actual_stats_row.get("actual_2025_w"))
    output["actual_2025_l"] = clean_value(actual_stats_row.get("actual_2025_l"))
    output["actual_2025_sv"] = clean_value(actual_stats_row.get("actual_2025_sv"))
    output["actual_2025_hld"] = clean_value(actual_stats_row.get("actual_2025_hld"))
    output["actual_2025_qs"] = clean_value(actual_stats_row.get("actual_2025_qs"))
    output["actual_2025_pitch_h"] = clean_value(actual_stats_row.get("actual_2025_pitch_h"))
    output["actual_2025_pitch_bb"] = clean_value(actual_stats_row.get("actual_2025_pitch_bb"))
    output["actual_2025_pitch_hr"] = clean_value(actual_stats_row.get("actual_2025_pitch_hr"))
    output["actual_2025_k"] = clean_value(actual_stats_row.get("actual_2025_k"))
    output["actual_2025_era"] = clean_value(actual_stats_row.get("actual_2025_era"))
    output["actual_2025_whip"] = clean_value(actual_stats_row.get("actual_2025_whip"))

    output["player_stage"] = derive_player_stage(base_row, prospect_row, context_row)
    output["risk_flag"] = derive_risk_flag(base_row, prospect_row, context_row)
    output["draft_ready"] = "yes" if output["dynasty_rank"] and output["market_timing_estimate"] else "partial"

    return output


def write_csv(rows: list[dict[str, str]], path: Path) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for field in row:
            if field not in fieldnames:
                fieldnames.append(field)

    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_summary(rows: list[dict[str, str]], supplemental_counts: dict[str, int], settings: dict) -> dict:
    total_players = len(rows)
    require_prospect_rankings = settings.get("require_prospect_rankings_for_initial_prep", True)

    def count_present(field: str) -> int:
        return sum(1 for row in rows if clean_value(row.get(field)))

    coverage = {
        "total_players": total_players,
        "with_dynasty_rank": count_present("dynasty_rank"),
        "with_prospect_rank": count_present("prospect_rank"),
        "with_adp": count_present("adp"),
        "with_market_timing_estimate": count_present("market_timing_estimate"),
        "with_injury_status": count_present("injury_status"),
        "with_transaction_status": count_present("transaction_status"),
        "with_role_security": count_present("role_security"),
        "with_skill_flag": count_present("skill_flag"),
        "with_actual_2025_stats": sum(1 for row in rows if clean_value(row.get("actual_2025_pa")) or clean_value(row.get("actual_2025_ip"))),
        "with_source_specific_dynasty_rank": sum(1 for row in rows if clean_value(row.get("dynasty_source")) and clean_value(row.get("dynasty_source")) != "workspace-baseline-2026"),
        "with_source_specific_market_adp": sum(1 for row in rows if clean_value(row.get("adp_source")) and clean_value(row.get("adp_source")) != "workspace-baseline-2026"),
        "draft_ready_rows": sum(1 for row in rows if row.get("draft_ready") == "yes"),
    }

    blocking_items: list[str] = []
    deferred_items: list[str] = []
    advisory_items: list[str] = []
    if coverage["with_dynasty_rank"] == 0:
        blocking_items.append("Load dynasty rankings into data/dynasty-rankings-2026.csv")
    if coverage["with_adp"] == 0:
        blocking_items.append("Load market ADP into data/market-adp-2026.csv")
    if require_prospect_rankings and coverage["with_prospect_rank"] == 0:
        blocking_items.append("Load prospect rankings into data/prospect-rankings-2026.csv")
    if not require_prospect_rankings and coverage["with_prospect_rank"] == 0:
        deferred_items.append("Prospect rankings remain deferred for a later draft-prep pass")
    if not settings.get("draft_order"):
        blocking_items.append("Set startup draft order in data/startup-draft-settings-2026.json")
    if coverage["with_source_specific_dynasty_rank"] == 0:
        advisory_items.append("Load FantraxHQ rows into data/dynasty-rankings-fantraxhq-2026.csv to replace dynasty baseline fallback rows")
    if coverage["with_source_specific_market_adp"] == 0:
        advisory_items.append("Load FantasyPros and/or RotoWire rows into data/market-adp-fantasypros-2026.csv and data/market-adp-rotowire-2026.csv to replace market baseline fallback rows")

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "supplemental_file_rows": supplemental_counts,
        "settings": {
            "draft_order_confirmed": settings.get("draft_order_confirmed", False),
            "third_round_reversal": settings.get("third_round_reversal"),
            "startup_draft_rounds": settings.get("startup_draft_rounds"),
            "require_prospect_rankings_for_initial_prep": require_prospect_rankings,
        },
        "coverage": coverage,
        "blocking_items": blocking_items,
        "deferred_items": deferred_items,
        "advisory_items": advisory_items,
    }


def main() -> None:
    base_rows = dedupe_base_rows(read_csv_rows(PLAYER_POOL_PATH))
    dynasty_rows = read_csv_rows(DYNASTY_RANKINGS_PATH)
    prospect_rows = read_csv_rows(PROSPECT_RANKINGS_PATH)
    adp_rows = read_csv_rows(MARKET_ADP_PATH)
    context_rows = read_csv_rows(PLAYER_CONTEXT_PATH)
    injury_rows = read_csv_rows(PLAYER_INJURIES_PATH)
    transaction_rows = read_csv_rows(PLAYER_TRANSACTIONS_PATH)
    skill_rows = read_csv_rows(SKILL_METRICS_PATH)
    actual_stats_rows = read_csv_rows(ACTUAL_STATS_PATH)
    settings = read_settings(SETTINGS_PATH)

    dynasty_index = index_rows(dynasty_rows)
    prospect_index = index_rows(prospect_rows)
    adp_index = index_rows(adp_rows)
    context_index = index_rows(context_rows)
    injury_index = index_rows(injury_rows)
    transaction_index = index_rows(transaction_rows)
    skill_index = index_rows(skill_rows)
    actual_stats_index = index_rows(actual_stats_rows)

    merged_rows = []
    for base_row in base_rows:
        merged_rows.append(
            merge_player_row(
                base_row,
                match_row(dynasty_index, base_row),
                match_row(prospect_index, base_row),
                match_row(adp_index, base_row),
                match_row(context_index, base_row),
                match_row(injury_index, base_row),
                match_row(transaction_index, base_row),
                match_row(skill_index, base_row),
                match_row(actual_stats_index, base_row),
            )
        )

    write_csv(merged_rows, OUTPUT_PATH)

    summary = build_summary(
        merged_rows,
        {
            "dynasty_rankings": len(dynasty_rows),
            "prospect_rankings": len(prospect_rows),
            "market_adp": len(adp_rows),
            "player_context": len(context_rows),
            "player_injuries": len(injury_rows),
            "player_transactions": len(transaction_rows),
            "skill_metrics": len(skill_rows),
            "actual_stats_2025": len(actual_stats_rows),
        },
        settings,
    )
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Wrote {len(merged_rows)} rows to {OUTPUT_PATH}")
    print(f"Wrote draft prep summary to {SUMMARY_PATH}")
    if summary["blocking_items"]:
        print("Blocking items:")
        for item in summary["blocking_items"]:
            print(f"- {item}")


if __name__ == "__main__":
    main()