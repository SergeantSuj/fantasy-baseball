from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from build_weekly_lineup_snapshot import (
    BOARD_PATH,
    ROSTERS_DIR,
    board_index_rows,
    clean_value,
    is_hitter,
    is_minor_roster_bucket,
    is_pitcher,
    merge_player_rows,
    parse_int,
    player_key,
    read_csv_rows,
    read_settings,
    roster_order,
)
from build_weekly_roster_decisions import (
    adp_value,
    dynasty_rank_value,
    optimize_roster,
    player_value,
    team_name_from_path,
    write_json,
    write_roster_csv,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = WORKSPACE_ROOT / "data"
RESULTS_PATH = DATA_DIR / "season-results-2026.json"
OUTPUT_JSON_PATH = DATA_DIR / "offseason-rosters-2026.json"
OUTPUT_CSV_PATH = DATA_DIR / "offseason-rosters-2026.csv"
SUMMARY_PATH = WORKSPACE_ROOT / "offseason-summary-2026.md"
MLB_KEEPER_LIMIT = 25
MINOR_KEEPER_LIMIT = 15

CATEGORY_LABELS = {
    "runs": "Runs",
    "home_runs": "Home Runs",
    "rbi": "RBI",
    "stolen_bases": "Stolen Bases",
    "obp": "OBP",
    "wins": "Wins",
    "strikeouts": "Strikeouts",
    "saves": "Saves",
    "era": "ERA",
    "whip": "WHIP",
}

YOUTH_LEAN = {"Paul": 14.0, "Josh V": 14.0, "Josh M": 8.0, "Shane": 5.0}
VETERAN_LEAN = {"Greg": 5.0, "Wendell": 5.0}


def merge_roster_player(row: dict[str, str], board_index: dict[str, dict[str, str]]) -> dict[str, object]:
    return merge_player_rows(board_index.get(player_key(row), {}), row)


def canonical_roster_key(row: dict[str, str], board_index: dict[str, dict[str, str]]) -> str:
    return player_key(merge_roster_player(row, board_index))


def build_keeper_roster_row(
    keeper: dict[str, object],
    board_index: dict[str, dict[str, str]],
    team_name: str,
    fieldnames: list[str],
) -> dict[str, str]:
    keeper_key = clean_value(str(keeper.get("mlbam_id", ""))) or clean_value(str(keeper.get("player_name", "")))
    board_player = board_index.get(keeper_key, {})
    eligible_positions = clean_value(str(keeper.get("eligible_positions", ""))) or clean_value(
        board_player.get("eligible_positions", "")
    )
    values = {
        "pick_number": "KEEPER",
        "round": "2026",
        "pick_in_round": "",
        "team": team_name,
        "player_name": clean_value(str(keeper.get("player_name", ""))),
        "player_type": clean_value(str(keeper.get("player_type", ""))),
        "position_bucket": clean_value(board_player.get("primary_position", "")) or eligible_positions.split("/")[0],
        "eligible_positions": eligible_positions,
        "roster_bucket": clean_value(str(keeper.get("roster_bucket", ""))) or "MLB",
        "current_level": clean_value(board_player.get("current_level", "")) or "MLB",
        "dynasty_rank": str(keeper.get("dynasty_rank", "")),
        "adp": str(keeper.get("adp", "")),
        "injury_status": clean_value(str(keeper.get("injury_status", ""))),
        "transaction_status": clean_value(board_player.get("transaction_status", "")),
        "rationale": "Retained in the 2026 offseason 25-player MLB keeper declaration.",
    }
    return {field: values.get(field, "") for field in fieldnames}


def keeper_score(player: dict[str, object], team_name: str) -> float:
    score = player_value(player)
    dynasty_rank = dynasty_rank_value(player)
    if dynasty_rank <= 500:
        score += 120.0 * (501 - dynasty_rank) / 500.0

    adp = adp_value(player)
    if adp <= 500:
        score += 40.0 * (501 - adp) / 500.0

    age = parse_int(str(player.get("age", "")))
    if 0 < age <= 26:
        score += 10.0
    if 0 < age <= 23:
        score += 8.0
    if team_name in YOUTH_LEAN and 0 < age <= 26:
        score += YOUTH_LEAN[team_name]
    if team_name in VETERAN_LEAN and age >= 28:
        score += VETERAN_LEAN[team_name]
    return round(score, 3)


def active_counts(players: list[dict[str, object]]) -> tuple[int, int]:
    optimized = optimize_roster(players)
    return len(optimized["active_hitters"]), len(optimized["active_pitchers"])


def select_keepers(players: list[dict[str, object]], team_name: str) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    ranked = sorted(
        players,
        key=lambda player: (
            -keeper_score(player, team_name),
            dynasty_rank_value(player),
            adp_value(player),
            clean_value(str(player.get("player_name", ""))),
        ),
    )
    optimized = optimize_roster(players)
    active_players = [*optimized["active_hitters"], *optimized["active_pitchers"]]
    active_keys = {player_key(player) for player in active_players}
    if len(optimized["active_hitters"]) < 13 or len(optimized["active_pitchers"]) < 9:
        raise RuntimeError(f"Could not build a viable active lineup from {team_name}'s full roster")

    selected = [player for player in ranked if player_key(player) in active_keys]
    selected_keys = {player_key(player) for player in selected}
    for player in ranked:
        if len(selected) >= MLB_KEEPER_LIMIT:
            break
        if player_key(player) not in selected_keys:
            selected.append(player)
            selected_keys.add(player_key(player))
    unselected = [player for player in ranked if player_key(player) not in selected_keys]

    selected.sort(key=lambda player: (-keeper_score(player, team_name), clean_value(str(player.get("player_name", "")))))
    unselected.sort(key=lambda player: (keeper_score(player, team_name), clean_value(str(player.get("player_name", "")))))
    return selected, unselected


def player_summary(player: dict[str, object], team_name: str) -> dict[str, object]:
    return {
        "player_name": clean_value(str(player.get("player_name", ""))),
        "mlbam_id": clean_value(str(player.get("mlbam_id", ""))),
        "player_type": clean_value(str(player.get("player_type", ""))),
        "eligible_positions": clean_value(str(player.get("eligible_positions", ""))),
        "mlb_team": clean_value(str(player.get("mlb_team", ""))),
        "age": parse_int(str(player.get("age", ""))),
        "roster_bucket": clean_value(str(player.get("roster_bucket", ""))),
        "injury_status": clean_value(str(player.get("injury_status", ""))),
        "dynasty_rank": dynasty_rank_value(player),
        "adp": round(adp_value(player), 1),
        "projection_value": round(player_value(player), 1),
        "keeper_score": keeper_score(player, team_name),
    }


def category_list(standing: dict[str, object], reverse: bool) -> list[dict[str, object]]:
    category_points = standing.get("category_points", {})
    rows = [
        {"category": CATEGORY_LABELS.get(category, category), "points": float(points)}
        for category, points in category_points.items()
    ]
    return sorted(rows, key=lambda row: (float(row["points"]), str(row["category"])), reverse=reverse)[:3]


def performance_label(rank: int) -> str:
    if rank == 1:
        return "League champion"
    if rank <= 3:
        return "Title contender"
    if rank <= 6:
        return "Middle-of-the-table finisher"
    return "Rebuilding-range finisher"


def build_team_outlook(
    standing: dict[str, object],
    keepers: list[dict[str, object]],
    minors: list[dict[str, object]],
    team_name: str,
) -> dict[str, object]:
    rank = int(standing.get("rank", 0) or 0)
    strengths = category_list(standing, True)
    weaknesses = category_list(standing, False)
    young_keeper_count = sum(1 for player in keepers if 0 < parse_int(str(player.get("age", ""))) <= 26)
    core = sorted(keepers, key=lambda player: -keeper_score(player, team_name))[:3]
    weak_names = ", ".join(str(row["category"]) for row in weaknesses)
    core_names = ", ".join(clean_value(str(player.get("player_name", ""))) for player in core)
    outlook = (
        f"The retained core is led by {core_names}. With {young_keeper_count} MLB keepers age 26 or younger "
        f"and {len(minors)} retained minor leaguers, the main 2027 priority is improving {weak_names}."
    )
    return {
        "performance": performance_label(rank),
        "strengths": strengths,
        "weaknesses": weaknesses,
        "keeper_core": [clean_value(str(player.get("player_name", ""))) for player in core],
        "young_mlb_keeper_count": young_keeper_count,
        "outlook": outlook,
    }


def write_csv_report(teams: list[dict[str, object]]) -> None:
    fieldnames = [
        "team",
        "status",
        "player_name",
        "mlbam_id",
        "player_type",
        "eligible_positions",
        "mlb_team",
        "age",
        "roster_bucket",
        "injury_status",
        "dynasty_rank",
        "adp",
        "projection_value",
        "keeper_score",
    ]
    rows: list[dict[str, object]] = []
    for team in teams:
        for status, key in (("KEEPER", "keepers"), ("CUT", "cuts"), ("MINORS", "minors")):
            for player in team[key]:
                rows.append({"team": team["team"], "status": status, **player})
    with OUTPUT_CSV_PATH.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_summary(payload: dict[str, object]) -> None:
    lines = [
        "# 2026 Season And Offseason Summary",
        "",
        f"Final standings through {payload['season_end_date']}. The first-year player draft order is the reverse of these standings.",
        "",
        "## Final Standings",
        "",
        "| Rank | Team | Points | Rookie Draft Pick |",
        "| ---: | --- | ---: | ---: |",
    ]
    draft_pick_by_team = {row["team"]: row["pick"] for row in payload["rookie_draft_order"]}
    for standing in payload["final_standings"]:
        lines.append(
            f"| {standing['rank']} | {standing['name']} | {standing['total_points']} | "
            f"{draft_pick_by_team[standing['name']]} |"
        )

    lines.extend(["", "## Team Reviews", ""])
    for team in sorted(payload["teams"], key=lambda row: int(row["final_rank"])):
        strengths = ", ".join(f"{row['category']} ({row['points']:g})" for row in team["summary"]["strengths"])
        weaknesses = ", ".join(f"{row['category']} ({row['points']:g})" for row in team["summary"]["weaknesses"])
        cut_names = ", ".join(player["player_name"] for player in team["cuts"])
        lines.extend(
            [
                f"### {team['team']} - {team['summary']['performance']}",
                "",
                f"Finished {team['final_rank']} with {team['total_points']} roto points. Strengths: {strengths}. "
                f"Weaknesses: {weaknesses}.",
                "",
                team["summary"]["outlook"],
                "",
                f"Offseason declaration: 25 MLB keepers, {team['minor_keeper_count']} minor keepers. Cuts: {cut_names}.",
                "",
            ]
        )
    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    standings = sorted(results.get("standings", []), key=lambda row: int(row.get("rank", 999)))
    standings_by_team = {clean_value(str(row.get("name", ""))): row for row in standings}
    previous = json.loads(OUTPUT_JSON_PATH.read_text(encoding="utf-8")) if OUTPUT_JSON_PATH.exists() else {}
    previous_teams = {team["team"]: team for team in previous.get("teams", [])}

    board_rows = read_csv_rows(BOARD_PATH)
    board_index = board_index_rows(board_rows)
    settings = read_settings()
    teams: list[dict[str, object]] = []

    for roster_path in roster_order(ROSTERS_DIR, settings):
        team_name = team_name_from_path(roster_path)
        roster_rows = read_csv_rows(roster_path)
        fieldnames = list(roster_rows[0].keys()) if roster_rows else []
        joined_by_key = {
            canonical_roster_key(row, board_index): merge_roster_player(row, board_index)
            for row in roster_rows
        }
        minor_rows = [row for row in roster_rows if is_minor_roster_bucket(row)]
        mlb_rows = [row for row in roster_rows if not is_minor_roster_bucket(row)]
        if len(minor_rows) > MINOR_KEEPER_LIMIT:
            raise RuntimeError(f"{team_name} has {len(minor_rows)} minor leaguers; limit is {MINOR_KEEPER_LIMIT}")
        if len(mlb_rows) < MLB_KEEPER_LIMIT:
            previous_team = previous_teams.get(team_name, {})
            previous_keepers = previous_team.get("keepers", [])
            if len(previous_keepers) != MLB_KEEPER_LIMIT:
                raise RuntimeError(f"{team_name} has only {len(mlb_rows)} MLB-designated players")
            recovered_rows = [
                build_keeper_roster_row(keeper, board_index, team_name, fieldnames)
                for keeper in previous_keepers
            ]
            roster_rows = [*recovered_rows, *minor_rows]
            write_roster_csv(roster_path, fieldnames, roster_rows)
            mlb_rows = recovered_rows
            joined_by_key = {
                canonical_roster_key(row, board_index): merge_roster_player(row, board_index)
                for row in roster_rows
            }

        if len(mlb_rows) > MLB_KEEPER_LIMIT:
            keepers, cuts = select_keepers(
                [joined_by_key[canonical_roster_key(row, board_index)] for row in mlb_rows],
                team_name,
            )
            keeper_keys = {player_key(player) for player in keepers}
            retained_rows = [
                row
                for row in roster_rows
                if is_minor_roster_bucket(row) or canonical_roster_key(row, board_index) in keeper_keys
            ]
            write_roster_csv(roster_path, fieldnames, retained_rows)
        else:
            keepers = [joined_by_key[canonical_roster_key(row, board_index)] for row in mlb_rows]
            cuts = previous_teams.get(team_name, {}).get("cuts", [])

        standing = standings_by_team[team_name]
        keeper_summaries = [player_summary(player, team_name) for player in keepers]
        cut_summaries = [
            player if "keeper_score" in player else player_summary(player, team_name)
            for player in cuts
        ]
        minor_players = [joined_by_key[canonical_roster_key(row, board_index)] for row in minor_rows]
        minor_summaries = [player_summary(player, team_name) for player in minor_players]
        summary = build_team_outlook(standing, keepers, minor_players, team_name)
        teams.append(
            {
                "team": team_name,
                "final_rank": int(standing["rank"]),
                "total_points": float(standing["total_points"]),
                "mlb_keeper_count": len(keeper_summaries),
                "minor_keeper_count": len(minor_summaries),
                "open_minor_draft_slots": MINOR_KEEPER_LIMIT - len(minor_summaries),
                "keepers": keeper_summaries,
                "cuts": cut_summaries,
                "minors": minor_summaries,
                "summary": summary,
            }
        )

    rookie_draft_order = [
        {
            "pick": pick,
            "team": standing["name"],
            "final_rank": standing["rank"],
            "total_points": standing["total_points"],
        }
        for pick, standing in enumerate(reversed(standings), start=1)
    ]
    payload = {
        "season": 2026,
        "season_end_date": "2026-09-27",
        "generated_at": datetime.now(UTC).isoformat(),
        "rules": {
            "mlb_keeper_limit": MLB_KEEPER_LIMIT,
            "minor_keeper_limit": MINOR_KEEPER_LIMIT,
            "rookie_draft_order": "Reverse final standings",
        },
        "final_standings": standings,
        "rookie_draft_order": rookie_draft_order,
        "teams": sorted(teams, key=lambda row: int(row["final_rank"])),
    }
    write_json(OUTPUT_JSON_PATH, payload)
    write_csv_report(payload["teams"])
    write_summary(payload)

    print(f"Wrote offseason roster report to {OUTPUT_JSON_PATH}")
    print(f"Wrote offseason roster CSV to {OUTPUT_CSV_PATH}")
    print(f"Wrote season summary to {SUMMARY_PATH}")
    for team in payload["teams"]:
        print(
            f"{team['team']}: {team['mlb_keeper_count']} MLB keepers, "
            f"{team['minor_keeper_count']} minor keepers, {len(team['cuts'])} cuts"
        )


if __name__ == "__main__":
    main()