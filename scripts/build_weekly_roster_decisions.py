from __future__ import annotations

import argparse
import json
from itertools import product
from pathlib import Path

from build_weekly_lineup_snapshot import (
    BOARD_PATH,
    OUTPUT_DIR as LINEUP_DIR,
    ROSTERS_DIR,
    assign_best_hitter_lineup,
    assign_pitchers,
    board_index_rows,
    build_lineup_rows,
    clean_value,
    hitter_value,
    is_hitter,
    is_pitcher,
    parse_float,
    parse_int,
    pitcher_value,
    player_key,
    read_csv_rows,
    read_settings,
    roster_order,
    write_csv,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = WORKSPACE_ROOT / "data"
DECISION_DIR = DATA_DIR / "weekly-decisions"


def workspace_relative_path(path: Path) -> str:
    return str(path.relative_to(WORKSPACE_ROOT)).replace("\\", "/")


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def merge_roster_rows(roster_rows: list[dict[str, str]], board_index: dict[str, dict[str, str]]) -> list[dict[str, object]]:
    roster: list[dict[str, object]] = []
    for roster_row in roster_rows:
        joined = dict(board_index.get(player_key(roster_row), {}))
        joined.update(roster_row)
        joined["mlb_team"] = clean_value(str(joined.get("mlb_team", ""))) or clean_value(str(joined.get("proj_team", "")))
        roster.append(joined)
    return roster


def team_name_from_path(roster_path: Path) -> str:
    return clean_value(roster_path.stem.replace("-roster", "").replace("-", " ")).title()


def player_value(player: dict[str, object]) -> float:
    hitter_score = hitter_value(player) if is_hitter(player) else float("-inf")
    pitcher_score = pitcher_value(player) if is_pitcher(player) else float("-inf")
    best = max(hitter_score, pitcher_score)
    return 0.0 if best == float("-inf") else best


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
            parse_int(str(player.get("dynasty_rank", 0))),
            clean_value(str(player.get("player_name", ""))),
        )

    return min(eligible, key=sort_key)


def evaluate_minor_promotion(candidate: dict[str, object], current_mlb_roster: list[dict[str, object]]) -> dict[str, object]:
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
    improvement = round(candidate_value - drop_value, 1)

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
            "current_projected_role": projected_role_map(current_mlb_roster).get(player_key(drop_candidate), "") if drop_candidate else "",
            "roster_value": drop_value,
        },
        "improvement": improvement,
        "rationale": rationale,
    }


def summarize_player(player: dict[str, object]) -> dict[str, object]:
    return {
        "player_name": clean_value(str(player.get("player_name", ""))),
        "player_type": clean_value(str(player.get("player_type", ""))),
        "eligible_positions": clean_value(str(player.get("eligible_positions", ""))),
        "mlb_team": clean_value(str(player.get("mlb_team", ""))),
        "current_level": clean_value(str(player.get("current_level", ""))),
        "lineup_slot": clean_value(str(player.get("lineup_slot", ""))),
        "projection_value": round(player_value(player), 1),
    }


def build_team_report(
    week: str,
    team_name: str,
    roster_rows: list[dict[str, str]],
    board_index: dict[str, dict[str, str]],
) -> tuple[list[dict[str, str]], dict[str, object]]:
    roster = merge_roster_rows(roster_rows, board_index)
    mlb_roster = [player for player in roster if clean_value(str(player.get("roster_bucket", ""))) != "Minors"]
    minors = [player for player in roster if clean_value(str(player.get("roster_bucket", ""))) == "Minors"]
    optimized = optimize_roster(mlb_roster)
    lineup_rows = build_lineup_rows(team_name, roster_rows, board_index, week)

    recommendations = []
    for candidate in minors:
        evaluation = evaluate_minor_promotion(candidate, mlb_roster)
        if evaluation["recommendation"].startswith("Move to MLB roster"):
            recommendations.append(
                {
                    "player_name": clean_value(str(candidate.get("player_name", ""))),
                    "player_type": clean_value(str(candidate.get("player_type", ""))),
                    "eligible_positions": clean_value(str(candidate.get("eligible_positions", ""))),
                    "mlb_team": clean_value(str(candidate.get("mlb_team", ""))),
                    "current_level": clean_value(str(candidate.get("current_level", ""))),
                    **evaluation,
                }
            )

    recommendations.sort(
        key=lambda row: (
            0 if row["projected_role_if_promoted"] == "Starter" else 1,
            -float(row["improvement"]),
            -float(row["candidate_projection_value"]),
            row["player_name"],
        )
    )

    return lineup_rows, {
        "team": team_name,
        "week": week,
        "mlb_bucket_count": len(mlb_roster),
        "minor_bucket_count": len(minors),
        "active_hitter_count": len(optimized["active_hitters"]),
        "active_pitcher_count": len(optimized["active_pitchers"]),
        "bench_count": len(optimized["bench_players"]),
        "active_hitters": [summarize_player(player) for player in optimized["active_hitters"]],
        "active_pitchers": [summarize_player(player) for player in optimized["active_pitchers"]],
        "bench": [summarize_player(player) for player in optimized["bench_players"]],
        "recommended_minor_promotions": recommendations,
    }


def build_report(week: str) -> tuple[list[dict[str, str]], dict[str, object]]:
    settings = read_settings()
    board_rows = read_csv_rows(BOARD_PATH)
    board_index = board_index_rows(board_rows)
    lineup_rows: list[dict[str, str]] = []
    teams: list[dict[str, object]] = []

    for roster_path in roster_order(ROSTERS_DIR, settings):
        team_name = team_name_from_path(roster_path)
        team_lineup_rows, team_report = build_team_report(week, team_name, read_csv_rows(roster_path), board_index)
        lineup_rows.extend(team_lineup_rows)
        teams.append(team_report)

    teams_with_promotions = [team for team in teams if team["recommended_minor_promotions"]]
    total_recommendations = sum(len(team["recommended_minor_promotions"]) for team in teams)

    return lineup_rows, {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
        "week": week,
        "summary": {
            "teams_checked": len(teams),
            "teams_with_recommended_promotions": len(teams_with_promotions),
            "total_promotion_recommendations": total_recommendations,
        },
        "teams": teams,
    }


def build_csv_rows(report: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for team in report.get("teams", []):
        recommendations = team.get("recommended_minor_promotions", [])
        if not recommendations:
            rows.append(
                {
                    "week": report.get("week", ""),
                    "team": team.get("team", ""),
                    "recommendation": "No change recommended",
                    "player_name": "",
                    "player_type": "",
                    "eligible_positions": "",
                    "current_level": "",
                    "projected_role_if_promoted": "",
                    "projected_slot_if_promoted": "",
                    "candidate_projection_value": "",
                    "drop_candidate_name": "",
                    "drop_candidate_role": "",
                    "drop_candidate_value": "",
                    "improvement": "",
                    "rationale": "Current MLB bucket already optimizes above all rostered minor-league alternatives.",
                }
            )
            continue
        for recommendation in recommendations:
            drop_candidate = recommendation.get("drop_candidate", {})
            rows.append(
                {
                    "week": report.get("week", ""),
                    "team": team.get("team", ""),
                    "recommendation": recommendation.get("recommendation", ""),
                    "player_name": recommendation.get("player_name", ""),
                    "player_type": recommendation.get("player_type", ""),
                    "eligible_positions": recommendation.get("eligible_positions", ""),
                    "current_level": recommendation.get("current_level", ""),
                    "projected_role_if_promoted": recommendation.get("projected_role_if_promoted", ""),
                    "projected_slot_if_promoted": recommendation.get("projected_slot_if_promoted", ""),
                    "candidate_projection_value": recommendation.get("candidate_projection_value", ""),
                    "drop_candidate_name": drop_candidate.get("player_name", ""),
                    "drop_candidate_role": drop_candidate.get("current_projected_role", ""),
                    "drop_candidate_value": drop_candidate.get("roster_value", ""),
                    "improvement": recommendation.get("improvement", ""),
                    "rationale": recommendation.get("rationale", ""),
                }
            )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the weekly lineup snapshot plus a current-state active-roster decision report."
    )
    parser.add_argument("--week", required=True, help="Week key such as 2026-week-01")
    parser.add_argument("--lineup-output", help="Optional explicit weekly lineup snapshot path")
    parser.add_argument("--report-json", help="Optional explicit weekly decision JSON path")
    parser.add_argument("--report-csv", help="Optional explicit weekly decision CSV path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    lineup_output = Path(args.lineup_output) if args.lineup_output else LINEUP_DIR / f"{args.week}.csv"
    report_json = Path(args.report_json) if args.report_json else DECISION_DIR / f"{args.week}.json"
    report_csv = Path(args.report_csv) if args.report_csv else DECISION_DIR / f"{args.week}.csv"

    lineup_rows, report = build_report(args.week)
    report["output_files"] = {
        "lineup_snapshot": workspace_relative_path(lineup_output),
        "decision_json": workspace_relative_path(report_json),
        "decision_csv": workspace_relative_path(report_csv),
    }

    write_csv(
        lineup_output,
        [
            "week",
            "team",
            "lineup_status",
            "lineup_slot",
            "mlbam_id",
            "player_name",
            "player_type",
            "eligible_positions",
            "mlb_team",
            "current_level",
        ],
        lineup_rows,
    )
    write_json(report_json, report)
    write_csv(
        report_csv,
        [
            "week",
            "team",
            "recommendation",
            "player_name",
            "player_type",
            "eligible_positions",
            "current_level",
            "projected_role_if_promoted",
            "projected_slot_if_promoted",
            "candidate_projection_value",
            "drop_candidate_name",
            "drop_candidate_role",
            "drop_candidate_value",
            "improvement",
            "rationale",
        ],
        build_csv_rows(report),
    )

    summary = report["summary"]
    print(f"Wrote weekly lineup snapshot to {lineup_output}")
    print(f"Wrote weekly decision JSON report to {report_json}")
    print(f"Wrote weekly decision CSV report to {report_csv}")
    print(
        "Teams with recommended promotions: "
        f"{summary['teams_with_recommended_promotions']} / {summary['teams_checked']}"
    )
    print(f"Total promotion recommendations: {summary['total_promotion_recommendations']}")


if __name__ == "__main__":
    main()