from __future__ import annotations

import csv
import json
from itertools import product
from pathlib import Path

from build_league_site import (
    ACTIVE_HITTER_SLOTS,
    BOARD_PATH,
    PITCHER_SLOTS,
    ROSTERS_DIR,
    SETTINGS_PATH,
    assign_best_hitter_lineup,
    assign_pitchers,
    board_index_rows,
    clean_value,
    hitter_value,
    is_hitter,
    is_pitcher,
    normalize_name,
    parse_float,
    player_key,
    read_csv_rows,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = WORKSPACE_ROOT / "data"
BREAK_CAMP_REPORT_PATH = DATA_DIR / "minor-leaguers-on-opening-day-rosters-2026.json"
OUTPUT_JSON_PATH = DATA_DIR / "break-camp-promotion-recommendations-2026.json"
OUTPUT_CSV_PATH = DATA_DIR / "break-camp-promotion-recommendations-2026.csv"


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_csv_rows(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def workspace_relative_path(path: Path) -> str:
    return str(path.relative_to(WORKSPACE_ROOT)).replace("\\", "/")


def read_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))


def roster_order(path: Path, settings: dict) -> list[Path]:
    configured_order = settings.get("draft_order") or []
    file_by_name = {clean_value(item.stem.replace("-roster", "").replace("-", " ")).title(): item for item in sorted(path.glob("*-roster.csv"))}
    ordered_files: list[Path] = []
    for team_name in configured_order:
        slug_key = clean_value(team_name)
        for display_name, file_path in file_by_name.items():
            if normalize_name(display_name) == normalize_name(slug_key):
                ordered_files.append(file_path)
                break
    remaining = [item for item in sorted(path.glob("*-roster.csv")) if item not in ordered_files]
    return ordered_files + remaining


def pitcher_value(player: dict[str, object]) -> float:
    return (
        parse_float(str(player.get("proj_w", 0.0))) * 4.0
        + parse_float(str(player.get("proj_k", 0.0))) * 0.85
        + parse_float(str(player.get("proj_sv", 0.0))) * 5.0
        + max(4.2 - parse_float(str(player.get("proj_era", 9.99))), 0.0) * 30.0
        + max(1.3 - parse_float(str(player.get("proj_whip", 9.99))), 0.0) * 100.0
    )


def player_value(player: dict[str, object]) -> float:
    hitter_score = hitter_value(player) if is_hitter(player) else float("-inf")
    pitcher_score = pitcher_value(player) if is_pitcher(player) else float("-inf")
    best = max(hitter_score, pitcher_score)
    return 0.0 if best == float("-inf") else best


def enrich_roster_rows(roster_rows: list[dict[str, str]], board_index: dict[str, dict[str, str]]) -> list[dict[str, object]]:
    roster: list[dict[str, object]] = []
    for roster_row in roster_rows:
        joined = dict(board_index.get(player_key(roster_row), {}))
        joined.update(roster_row)
        joined["mlb_team"] = clean_value(str(joined.get("mlb_team", ""))) or clean_value(str(joined.get("proj_team", "")))
        roster.append(joined)
    return roster


def optimize_roster(players: list[dict[str, object]]) -> dict[str, object]:
    two_way_players = [player for player in players if clean_value(str(player.get("player_type", ""))) == "two-way"]
    scenario_labels = ["hitter", "pitcher"] if two_way_players else [""]
    scenario_results: list[dict[str, object]] = []

    for choices in product(scenario_labels, repeat=len(two_way_players)):
        choice_map = {player_key(player): choice for player, choice in zip(two_way_players, choices)}
        hitters = []
        pitchers = []
        for player in players:
            key = player_key(player)
            choice = choice_map.get(key)
            if clean_value(str(player.get("player_type", ""))) == "two-way":
                if choice == "pitcher":
                    pitchers.append(player)
                else:
                    hitters.append(player)
                continue
            if is_hitter(player):
                hitters.append(player)
            if is_pitcher(player):
                pitchers.append(player)

        active_hitters, _ = assign_best_hitter_lineup(hitters)
        active_pitchers, _ = assign_pitchers(pitchers)
        active_keys = {player_key(player) for player in [*active_hitters, *active_pitchers]}
        bench_players = [dict(player) for player in players if player_key(player) not in active_keys]
        score = sum(hitter_value(player) for player in active_hitters) + sum(pitcher_value(player) for player in active_pitchers)
        scenario_results.append(
            {
                "score": score,
                "active_hitters": active_hitters,
                "active_pitchers": active_pitchers,
                "bench_players": bench_players,
            }
        )

    return max(scenario_results, key=lambda item: float(item["score"]))


def projected_role_map(players: list[dict[str, object]]) -> dict[str, str]:
    optimized = optimize_roster(players)
    role_map: dict[str, str] = {}
    for player in optimized["active_hitters"]:
        role_map[player_key(player)] = clean_value(str(player.get("lineup_slot", ""))) or "Active"
    for player in optimized["active_pitchers"]:
        role_map[player_key(player)] = clean_value(str(player.get("lineup_slot", ""))) or "Active"
    for player in optimized["bench_players"]:
        role_map[player_key(player)] = "Bench"
    return role_map


def weakest_drop_candidate(players: list[dict[str, object]], exclude_keys: set[str]) -> dict[str, object] | None:
    role_map = projected_role_map(players)
    eligible = [player for player in players if player_key(player) not in exclude_keys]
    if not eligible:
        return None

    def sort_key(player: dict[str, object]) -> tuple[object, ...]:
        role = role_map.get(player_key(player), "Bench")
        role_priority = 0 if role == "Bench" else 1
        return (
            role_priority,
            player_value(player),
            clean_value(str(player.get("dynasty_rank", "999999"))),
            clean_value(str(player.get("player_name", ""))),
        )

    return min(eligible, key=sort_key)


def promote_candidate_evaluation(candidate: dict[str, object], current_mlb_roster: list[dict[str, object]]) -> dict[str, object]:
    promoted_candidate = dict(candidate)
    promoted_candidate["roster_bucket"] = "MLB"

    promoted_roster = [dict(player) for player in current_mlb_roster] + [promoted_candidate]
    optimized = optimize_roster(promoted_roster)
    active_keys = {player_key(player) for player in [*optimized["active_hitters"], *optimized["active_pitchers"]]}
    candidate_key = player_key(promoted_candidate)
    candidate_role = "Bench"
    candidate_slot = ""
    if candidate_key in active_keys:
        candidate_role = "Starter"
        for player in [*optimized["active_hitters"], *optimized["active_pitchers"]]:
            if player_key(player) == candidate_key:
                candidate_slot = clean_value(str(player.get("lineup_slot", "")))
                break

    drop_candidate = weakest_drop_candidate(promoted_roster, {candidate_key})
    candidate_value = round(player_value(promoted_candidate), 1)
    drop_value = round(player_value(drop_candidate), 1) if drop_candidate else 0.0

    if candidate_role == "Starter":
        recommendation = "Move to MLB roster as starter"
        rationale = f"Would crack the active lineup at {candidate_slot or 'an active slot'} under the current optimizer."
    elif drop_candidate and player_value(promoted_candidate) > player_value(drop_candidate):
        recommendation = "Move to MLB roster as bench player"
        rationale = "Improves the 30-man MLB bucket even though the player would open on the fantasy bench."
    else:
        recommendation = "Keep in minors for now"
        rationale = "Does not currently beat the weakest projected MLB roster player on the fantasy roster."

    return {
        "recommendation": recommendation,
        "projected_role_if_promoted": candidate_role,
        "projected_slot_if_promoted": candidate_slot,
        "candidate_projection_value": candidate_value,
        "drop_candidate": {
            "player_name": clean_value(str(drop_candidate.get("player_name", ""))) if drop_candidate else "",
            "player_type": clean_value(str(drop_candidate.get("player_type", ""))) if drop_candidate else "",
            "eligible_positions": clean_value(str(drop_candidate.get("eligible_positions", ""))) if drop_candidate else "",
            "roster_value": drop_value,
            "current_projected_role": projected_role_map(current_mlb_roster).get(player_key(drop_candidate), "") if drop_candidate else "",
        },
        "rationale": rationale,
    }


def build_report() -> dict[str, object]:
    board_index = board_index_rows(read_csv_rows(BOARD_PATH))
    break_camp_report = read_json(BREAK_CAMP_REPORT_PATH)
    settings = read_settings()
    team_break_camp_index = {clean_value(str(team.get("team", ""))): team for team in break_camp_report.get("teams", [])}

    teams: list[dict[str, object]] = []
    for roster_path in roster_order(ROSTERS_DIR, settings):
        team_name = clean_value(roster_path.stem.replace("-roster", "").replace("-", " ")).title()
        roster_rows = read_csv_rows(roster_path)
        roster = enrich_roster_rows(roster_rows, board_index)
        current_mlb_roster = [player for player in roster if clean_value(str(player.get("roster_bucket", ""))) != "Minors"]
        team_break_camp = team_break_camp_index.get(team_name, {})
        evaluations: list[dict[str, object]] = []

        for player in team_break_camp.get("players", []):
            candidate = dict(board_index.get(clean_value(str(player.get("mlbam_id", ""))), board_index.get(normalize_name(str(player.get("player_name", ""))), {})))
            if not candidate:
                continue
            candidate["player_name"] = clean_value(str(player.get("player_name", "")))
            candidate["mlb_team"] = clean_value(str(player.get("real_team", ""))) or clean_value(str(candidate.get("mlb_team", "")))
            candidate["eligible_positions"] = clean_value(str(player.get("eligible_positions", ""))) or clean_value(str(candidate.get("eligible_positions", "")))
            candidate["player_type"] = clean_value(str(player.get("player_type", ""))) or clean_value(str(candidate.get("player_type", "")))
            candidate["roster_bucket"] = "Minors"

            evaluation = promote_candidate_evaluation(candidate, current_mlb_roster)
            evaluations.append(
                {
                    "player_name": clean_value(str(player.get("player_name", ""))),
                    "real_team": clean_value(str(player.get("real_team", ""))),
                    "eligible_positions": clean_value(str(player.get("eligible_positions", ""))),
                    "player_type": clean_value(str(player.get("player_type", ""))),
                    "dynasty_rank": clean_value(str(player.get("dynasty_rank", ""))),
                    "adp": clean_value(str(player.get("adp", ""))),
                    **evaluation,
                }
            )

        teams.append(
            {
                "team": team_name,
                "players": evaluations,
            }
        )

    summary_counts = {"starter": 0, "bench": 0, "stay_minors": 0}
    for team in teams:
        for player in team["players"]:
            recommendation = player["recommendation"]
            if recommendation.endswith("starter"):
                summary_counts["starter"] += 1
            elif recommendation.endswith("bench player"):
                summary_counts["bench"] += 1
            else:
                summary_counts["stay_minors"] += 1

    return {
        "season": 2026,
        "opening_day": break_camp_report.get("opening_day", ""),
        "source": "MLB Stats API Opening Day active rosters + fantasy lineup optimizer",
        "summary": {
            "teams_checked": len(teams),
            "starters": summary_counts["starter"],
            "bench_promotions": summary_counts["bench"],
            "keep_in_minors": summary_counts["stay_minors"],
        },
        "teams": teams,
        "output_files": {
            "json": workspace_relative_path(OUTPUT_JSON_PATH),
            "csv": workspace_relative_path(OUTPUT_CSV_PATH),
        },
    }


def build_csv_rows(report: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for team in report.get("teams", []):
        for player in team.get("players", []):
            row = {"fantasy_team": team["team"]}
            row.update(player)
            drop_candidate = row.pop("drop_candidate", {})
            row["drop_candidate_name"] = drop_candidate.get("player_name", "")
            row["drop_candidate_role"] = drop_candidate.get("current_projected_role", "")
            row["drop_candidate_value"] = drop_candidate.get("roster_value", "")
            rows.append(row)
    return rows


def main() -> None:
    report = build_report()
    write_json(OUTPUT_JSON_PATH, report)
    write_csv_rows(
        OUTPUT_CSV_PATH,
        [
            "fantasy_team",
            "player_name",
            "real_team",
            "eligible_positions",
            "player_type",
            "dynasty_rank",
            "adp",
            "recommendation",
            "projected_role_if_promoted",
            "projected_slot_if_promoted",
            "candidate_projection_value",
            "drop_candidate_name",
            "drop_candidate_role",
            "drop_candidate_value",
            "rationale",
        ],
        build_csv_rows(report),
    )
    print(f"Opening Day report date: {report['opening_day']}")
    print(f"Starters: {report['summary']['starters']}")
    print(f"Bench promotions: {report['summary']['bench_promotions']}")
    print(f"Keep in minors: {report['summary']['keep_in_minors']}")
    print(f"Wrote JSON report to {OUTPUT_JSON_PATH}")
    print(f"Wrote CSV report to {OUTPUT_CSV_PATH}")


if __name__ == "__main__":
    main()