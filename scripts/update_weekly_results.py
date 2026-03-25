from __future__ import annotations

import argparse
import csv
import json
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = WORKSPACE_ROOT / "data"
RESULTS_PATH = DATA_DIR / "season-results-2026.json"
CONTRIBUTIONS_PATH = DATA_DIR / "player-contributions-2026.csv"
SETTINGS_PATH = DATA_DIR / "startup-draft-settings-2026.json"
LINEUP_DIR = DATA_DIR / "weekly-lineups"
STATS_DIR = DATA_DIR / "weekly-stats"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0 Safari/537.36"

ACTIVE_HITTER_SLOTS = {"C", "1B", "2B", "3B", "SS", "CI", "MI", "OF", "UTIL"}
CATEGORY_LABELS = {
    "runs": "R",
    "home_runs": "HR",
    "rbi": "RBI",
    "stolen_bases": "SB",
    "obp": "OBP",
    "wins": "W",
    "strikeouts": "K",
    "saves": "SV",
    "era": "ERA",
    "whip": "WHIP",
}


def clean_value(value: str | None) -> str:
    return (value or "").strip()


def normalize_name(name: str) -> str:
    return " ".join(clean_value(name).lower().replace(".", " ").replace("-", " ").split())


def parse_float(value: str | None) -> float:
    text = clean_value(value)
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_int(value: str | None) -> int:
    number = parse_float(value)
    return int(number) if number else 0


def parse_innings_to_outs(value: str | None) -> int:
    text = clean_value(value)
    if not text:
        return 0
    if "." not in text:
        return parse_int(text) * 3
    whole, fraction = text.split(".", 1)
    outs = parse_int(whole) * 3
    if fraction == "1":
        return outs + 1
    if fraction == "2":
        return outs + 2
    if fraction in {"", "0"}:
        return outs
    return int(round(parse_float(text) * 3))


def outs_to_display_innings(outs: int) -> str:
    whole = outs // 3
    remainder = outs % 3
    return f"{whole}.{remainder}"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_settings() -> dict:
    return read_json(SETTINGS_PATH)


def workspace_relative_path(path: Path) -> str:
    resolved = path if path.is_absolute() else (WORKSPACE_ROOT / path)
    return str(resolved.relative_to(WORKSPACE_ROOT)).replace("\\", "/")


def team_order() -> list[str]:
    settings = read_settings()
    configured_order = settings.get("draft_order") or []
    if configured_order:
        return [clean_value(item) for item in configured_order]
    roster_paths = sorted((WORKSPACE_ROOT / "manager-rosters").glob("*-roster.csv"))
    return [clean_value(path.stem.replace("-roster", "").replace("-", " ")).title() for path in roster_paths]


def player_key(row: dict[str, object] | dict[str, str]) -> str:
    mlbam_id = clean_value(str(row.get("mlbam_id", "")))
    return mlbam_id or normalize_name(str(row.get("player_name", "")))


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def by_date_range_url(group: str, start_date: str, end_date: str, season: int) -> str:
    query = urllib.parse.urlencode(
        {
            "stats": "byDateRange",
            "group": group,
            "season": season,
            "startDate": start_date,
            "endDate": end_date,
            "playerPool": "ALL",
            "limit": 20000,
        }
    )
    return f"https://statsapi.mlb.com/api/v1/stats?{query}"


def stat_text(stat: dict, field: str) -> str:
    value = stat.get(field, "")
    return "" if value is None else str(value)


def build_stat_map(group: str, start_date: str, end_date: str, season: int) -> dict[str, dict]:
    payload = fetch_json(by_date_range_url(group, start_date, end_date, season))
    splits = payload.get("stats", [{}])[0].get("splits", [])
    return {str(split.get("player", {}).get("id", "")): split for split in splits if split.get("player", {}).get("id")}


def fetch_and_write_weekly_stats(path: Path, start_date: str, end_date: str, season: int) -> list[dict[str, str]]:
    hitting_map = build_stat_map("hitting", start_date, end_date, season)
    pitching_map = build_stat_map("pitching", start_date, end_date, season)
    all_keys = sorted(set(hitting_map) | set(pitching_map))

    rows: list[dict[str, str]] = []
    for mlbam_id in all_keys:
        hitting_row = hitting_map.get(mlbam_id, {})
        pitching_row = pitching_map.get(mlbam_id, {})
        hitting_stat = hitting_row.get("stat", {})
        pitching_stat = pitching_row.get("stat", {})
        player_name = clean_value(hitting_row.get("player", {}).get("fullName")) or clean_value(pitching_row.get("player", {}).get("fullName"))
        actual_team = clean_value(hitting_row.get("team", {}).get("abbreviation")) or clean_value(pitching_row.get("team", {}).get("abbreviation"))
        rows.append(
            {
                "mlbam_id": mlbam_id,
                "player_name": player_name,
                "team": actual_team,
                "weekly_pa": stat_text(hitting_stat, "plateAppearances"),
                "weekly_ab": stat_text(hitting_stat, "atBats"),
                "weekly_r": stat_text(hitting_stat, "runs"),
                "weekly_hr": stat_text(hitting_stat, "homeRuns"),
                "weekly_rbi": stat_text(hitting_stat, "rbi"),
                "weekly_sb": stat_text(hitting_stat, "stolenBases"),
                "weekly_h": stat_text(hitting_stat, "hits"),
                "weekly_bb": stat_text(hitting_stat, "baseOnBalls"),
                "weekly_hbp": stat_text(hitting_stat, "hitByPitch"),
                "weekly_sf": stat_text(hitting_stat, "sacFlies"),
                "weekly_obp": stat_text(hitting_stat, "obp"),
                "weekly_ip": stat_text(pitching_stat, "inningsPitched"),
                "weekly_w": stat_text(pitching_stat, "wins"),
                "weekly_sv": stat_text(pitching_stat, "saves"),
                "weekly_k": stat_text(pitching_stat, "strikeOuts"),
                "weekly_er": stat_text(pitching_stat, "earnedRuns"),
                "weekly_pitch_h": stat_text(pitching_stat, "hits"),
                "weekly_pitch_bb": stat_text(pitching_stat, "baseOnBalls"),
                "weekly_era": stat_text(pitching_stat, "era"),
                "weekly_whip": stat_text(pitching_stat, "whip"),
            }
        )

    write_csv(
        path,
        [
            "mlbam_id",
            "player_name",
            "team",
            "weekly_pa",
            "weekly_ab",
            "weekly_r",
            "weekly_hr",
            "weekly_rbi",
            "weekly_sb",
            "weekly_h",
            "weekly_bb",
            "weekly_hbp",
            "weekly_sf",
            "weekly_obp",
            "weekly_ip",
            "weekly_w",
            "weekly_sv",
            "weekly_k",
            "weekly_er",
            "weekly_pitch_h",
            "weekly_pitch_bb",
            "weekly_era",
            "weekly_whip",
        ],
        rows,
    )
    return rows


def zero_team_components() -> dict[str, int | float]:
    return {
        "runs": 0,
        "home_runs": 0,
        "rbi": 0,
        "stolen_bases": 0,
        "at_bats": 0,
        "hits": 0,
        "walks": 0,
        "hit_by_pitch": 0,
        "sac_flies": 0,
        "wins": 0,
        "strikeouts": 0,
        "saves": 0,
        "outs_pitched": 0,
        "earned_runs": 0,
        "hits_allowed": 0,
        "walks_allowed": 0,
    }


def merge_components(target: dict[str, int | float], source: dict[str, int | float]) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0) + value


def derive_display_totals(components: dict[str, int | float]) -> dict[str, int | float]:
    denominator = components["at_bats"] + components["walks"] + components["hit_by_pitch"] + components["sac_flies"]
    innings = components["outs_pitched"] / 3 if components["outs_pitched"] else 0.0
    obp = ((components["hits"] + components["walks"] + components["hit_by_pitch"]) / denominator) if denominator else 0.0
    era = ((components["earned_runs"] * 9.0) / innings) if innings else 0.0
    whip = ((components["hits_allowed"] + components["walks_allowed"]) / innings) if innings else 0.0
    return {
        "runs": int(components["runs"]),
        "home_runs": int(components["home_runs"]),
        "rbi": int(components["rbi"]),
        "stolen_bases": int(components["stolen_bases"]),
        "obp": round(obp, 3),
        "wins": int(components["wins"]),
        "strikeouts": int(components["strikeouts"]),
        "saves": int(components["saves"]),
        "era": round(era, 2),
        "whip": round(whip, 2),
    }


def build_stats_index(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for row in rows:
        key = player_key(row)
        if key:
            index[key] = row
    return index


def validate_active_lineups(rows: list[dict[str, str]]) -> None:
    counts_by_team: dict[str, dict[str, int]] = {}
    for row in rows:
        if clean_value(row.get("lineup_status")).upper() != "ACTIVE":
            continue
        team = clean_value(row.get("team"))
        lineup_slot = clean_value(row.get("lineup_slot"))
        counts = counts_by_team.setdefault(team, {"hitters": 0, "pitchers": 0})
        if lineup_slot.startswith("P"):
            counts["pitchers"] += 1
        else:
            counts["hitters"] += 1

    problems = []
    for team in team_order():
        counts = counts_by_team.get(team, {"hitters": 0, "pitchers": 0})
        if counts["hitters"] != 13 or counts["pitchers"] != 9:
            problems.append(f"{team}: expected 13 active hitters and 9 active pitchers, found {counts['hitters']} hitters and {counts['pitchers']} pitchers")
    if problems:
        raise ValueError("Invalid lineup snapshot.\n" + "\n".join(problems))


def build_week_result(
    week: str,
    season: int,
    start_date: str,
    end_date: str,
    lineup_path: Path,
    stats_path: Path,
    lineup_rows: list[dict[str, str]],
    stat_rows: list[dict[str, str]],
) -> dict[str, object]:
    stats_index = build_stats_index(stat_rows)
    teams: list[dict[str, object]] = []

    for team_name in team_order():
        active_rows = [
            row
            for row in lineup_rows
            if clean_value(row.get("team")) == team_name and clean_value(row.get("lineup_status")).upper() == "ACTIVE"
        ]
        team_components = zero_team_components()
        player_rows: list[dict[str, object]] = []

        for lineup_row in active_rows:
            stat_row = stats_index.get(player_key(lineup_row), {})
            outs_pitched = parse_innings_to_outs(stat_row.get("weekly_ip"))
            components = {
                "runs": parse_int(stat_row.get("weekly_r")),
                "home_runs": parse_int(stat_row.get("weekly_hr")),
                "rbi": parse_int(stat_row.get("weekly_rbi")),
                "stolen_bases": parse_int(stat_row.get("weekly_sb")),
                "at_bats": parse_int(stat_row.get("weekly_ab")),
                "hits": parse_int(stat_row.get("weekly_h")),
                "walks": parse_int(stat_row.get("weekly_bb")),
                "hit_by_pitch": parse_int(stat_row.get("weekly_hbp")),
                "sac_flies": parse_int(stat_row.get("weekly_sf")),
                "wins": parse_int(stat_row.get("weekly_w")),
                "strikeouts": parse_int(stat_row.get("weekly_k")),
                "saves": parse_int(stat_row.get("weekly_sv")),
                "outs_pitched": outs_pitched,
                "earned_runs": parse_int(stat_row.get("weekly_er")),
                "hits_allowed": parse_int(stat_row.get("weekly_pitch_h")),
                "walks_allowed": parse_int(stat_row.get("weekly_pitch_bb")),
            }
            merge_components(team_components, components)
            player_totals = derive_display_totals(components)
            player_rows.append(
                {
                    "week": week,
                    "team": team_name,
                    "lineup_slot": clean_value(lineup_row.get("lineup_slot")),
                    "mlbam_id": clean_value(lineup_row.get("mlbam_id")),
                    "player_name": clean_value(lineup_row.get("player_name")),
                    "player_type": clean_value(lineup_row.get("player_type")),
                    "mlb_team": clean_value(stat_row.get("team")) or clean_value(lineup_row.get("mlb_team")),
                    "weeks_active": 1,
                    "runs": int(components["runs"]),
                    "home_runs": int(components["home_runs"]),
                    "rbi": int(components["rbi"]),
                    "stolen_bases": int(components["stolen_bases"]),
                    "at_bats": int(components["at_bats"]),
                    "hits": int(components["hits"]),
                    "walks": int(components["walks"]),
                    "hit_by_pitch": int(components["hit_by_pitch"]),
                    "sac_flies": int(components["sac_flies"]),
                    "obp": player_totals["obp"],
                    "wins": int(components["wins"]),
                    "strikeouts": int(components["strikeouts"]),
                    "saves": int(components["saves"]),
                    "innings_pitched": outs_to_display_innings(outs_pitched),
                    "outs_pitched": outs_pitched,
                    "earned_runs": int(components["earned_runs"]),
                    "hits_allowed": int(components["hits_allowed"]),
                    "walks_allowed": int(components["walks_allowed"]),
                    "era": player_totals["era"],
                    "whip": player_totals["whip"],
                }
            )

        teams.append(
            {
                "name": team_name,
                "components": team_components,
                "season_totals": derive_display_totals(team_components),
                "player_contributions": player_rows,
            }
        )

    return {
        "week": week,
        "season": season,
        "start_date": start_date,
        "end_date": end_date,
        "lineup_snapshot_path": workspace_relative_path(lineup_path),
        "weekly_stats_path": workspace_relative_path(stats_path),
        "imported_at": datetime.now(UTC).isoformat(),
        "teams": teams,
    }


def roto_points(values: list[tuple[str, float]], higher_is_better: bool) -> dict[str, float]:
    sorted_values = sorted(values, key=lambda item: item[1], reverse=higher_is_better)
    team_count = len(sorted_values)
    points: dict[str, float] = {}
    index = 0
    while index < team_count:
        next_index = index + 1
        while next_index < team_count and abs(sorted_values[next_index][1] - sorted_values[index][1]) < 1e-9:
            next_index += 1
        slot_points = [team_count - position for position in range(index, next_index)]
        average_points = sum(slot_points) / len(slot_points)
        for team_name, _ in sorted_values[index:next_index]:
            points[team_name] = round(average_points, 2)
        index = next_index
    return points


def aggregate_season(weeks: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, list[dict[str, object]]]]:
    team_payloads: dict[str, dict[str, object]] = {
        team_name: {"name": team_name, "components": zero_team_components(), "player_contributions": {}}
        for team_name in team_order()
    }

    for week in weeks:
        for week_team in week.get("teams", []):
            team_name = clean_value(week_team.get("name"))
            if team_name not in team_payloads:
                continue
            team_entry = team_payloads[team_name]
            merge_components(team_entry["components"], dict(week_team.get("components", {})))
            player_map: dict[str, dict[str, object]] = team_entry["player_contributions"]
            for contribution in week_team.get("player_contributions", []):
                contribution_key = player_key(contribution)
                if contribution_key not in player_map:
                    player_map[contribution_key] = {
                        "mlbam_id": clean_value(contribution.get("mlbam_id")),
                        "player_name": clean_value(contribution.get("player_name")),
                        "player_type": clean_value(contribution.get("player_type")),
                        "mlb_team": clean_value(contribution.get("mlb_team")),
                        "weeks_active": 0,
                        **zero_team_components(),
                    }
                player_entry = player_map[contribution_key]
                player_entry["weeks_active"] += parse_int(str(contribution.get("weeks_active", 1)))
                merge_components(
                    player_entry,
                    {
                        "runs": parse_int(str(contribution.get("runs", 0))),
                        "home_runs": parse_int(str(contribution.get("home_runs", 0))),
                        "rbi": parse_int(str(contribution.get("rbi", 0))),
                        "stolen_bases": parse_int(str(contribution.get("stolen_bases", 0))),
                        "at_bats": parse_int(str(contribution.get("at_bats", 0))),
                        "hits": parse_int(str(contribution.get("hits", 0))),
                        "walks": parse_int(str(contribution.get("walks", 0))),
                        "hit_by_pitch": parse_int(str(contribution.get("hit_by_pitch", 0))),
                        "sac_flies": parse_int(str(contribution.get("sac_flies", 0))),
                        "wins": parse_int(str(contribution.get("wins", 0))),
                        "strikeouts": parse_int(str(contribution.get("strikeouts", 0))),
                        "saves": parse_int(str(contribution.get("saves", 0))),
                        "outs_pitched": parse_int(str(contribution.get("outs_pitched", 0))),
                        "earned_runs": parse_int(str(contribution.get("earned_runs", 0))),
                        "hits_allowed": parse_int(str(contribution.get("hits_allowed", 0))),
                        "walks_allowed": parse_int(str(contribution.get("walks_allowed", 0))),
                    },
                )

    team_rows: list[dict[str, object]] = []
    standings_input: list[tuple[str, dict[str, int | float], dict[str, int | float]]] = []
    for team_name in team_order():
        team_entry = team_payloads[team_name]
        season_totals = derive_display_totals(team_entry["components"])
        player_rows = []
        for contribution in sorted(team_entry["player_contributions"].values(), key=lambda item: (-int(item["weeks_active"]), item["player_name"])):
            display = derive_display_totals(contribution)
            player_rows.append(
                {
                    "mlbam_id": contribution["mlbam_id"],
                    "player_name": contribution["player_name"],
                    "player_type": contribution["player_type"],
                    "mlb_team": contribution["mlb_team"],
                    "weeks_active": int(contribution["weeks_active"]),
                    "runs": int(contribution["runs"]),
                    "home_runs": int(contribution["home_runs"]),
                    "rbi": int(contribution["rbi"]),
                    "stolen_bases": int(contribution["stolen_bases"]),
                    "at_bats": int(contribution["at_bats"]),
                    "hits": int(contribution["hits"]),
                    "walks": int(contribution["walks"]),
                    "hit_by_pitch": int(contribution["hit_by_pitch"]),
                    "sac_flies": int(contribution["sac_flies"]),
                    "obp": display["obp"],
                    "wins": int(contribution["wins"]),
                    "strikeouts": int(contribution["strikeouts"]),
                    "saves": int(contribution["saves"]),
                    "innings_pitched": outs_to_display_innings(int(contribution["outs_pitched"])),
                    "outs_pitched": int(contribution["outs_pitched"]),
                    "earned_runs": int(contribution["earned_runs"]),
                    "hits_allowed": int(contribution["hits_allowed"]),
                    "walks_allowed": int(contribution["walks_allowed"]),
                    "era": display["era"],
                    "whip": display["whip"],
                }
            )
        team_rows.append(
            {
                "name": team_name,
                "season_totals": season_totals,
                "components": team_entry["components"],
                "player_contributions": player_rows,
            }
        )
        standings_input.append((team_name, team_entry["components"], season_totals))

    category_points: dict[str, dict[str, float]] = {team_name: {} for team_name in team_order()}
    categories = [
        ("runs", True),
        ("home_runs", True),
        ("rbi", True),
        ("stolen_bases", True),
        ("obp", True),
        ("wins", True),
        ("strikeouts", True),
        ("saves", True),
        ("era", False),
        ("whip", False),
    ]
    for category_key, higher_is_better in categories:
        values = [(team_name, float(season_totals[category_key])) for team_name, _, season_totals in standings_input]
        points = roto_points(values, higher_is_better)
        for team_name, point_total in points.items():
            category_points[team_name][category_key] = point_total

    standings: list[dict[str, object]] = []
    max_category_points = len(team_order())
    for team_name, _, season_totals in standings_input:
        team_category_points = category_points[team_name]
        hitting_points = round(sum(team_category_points[key] for key in ["runs", "home_runs", "rbi", "stolen_bases", "obp"]), 2)
        pitching_points = round(sum(team_category_points[key] for key in ["wins", "strikeouts", "saves", "era", "whip"]), 2)
        total_points = round(hitting_points + pitching_points, 2)
        category_wins = sum(1 for value in team_category_points.values() if abs(value - max_category_points) < 1e-9)
        standings.append(
            {
                "name": team_name,
                "rank": 0,
                "total_points": total_points,
                "hitting_points": hitting_points,
                "pitching_points": pitching_points,
                "category_points": team_category_points,
                "season_totals": season_totals,
                "category_wins": category_wins,
            }
        )

    standings.sort(key=lambda item: (-float(item["total_points"]), -int(item["category_wins"]), -float(item["hitting_points"]), -float(item["pitching_points"]), str(item["name"])))
    for index, row in enumerate(standings, start=1):
        row["rank"] = index
        row.pop("category_wins", None)

    leaders = {
        "home_runs": [],
        "stolen_bases": [],
        "strikeouts": [],
        "saves": [],
    }
    leaderboard_specs = {
        "home_runs": "home_runs",
        "stolen_bases": "stolen_bases",
        "strikeouts": "strikeouts",
        "saves": "saves",
    }
    for label, field in leaderboard_specs.items():
        leader_rows = []
        for team in team_rows:
            for contribution in team["player_contributions"]:
                leader_rows.append(
                    {
                        "team": team["name"],
                        "player_name": contribution["player_name"],
                        "mlb_team": contribution["mlb_team"],
                        "value": contribution[field],
                    }
                )
        leaders[label] = [row for row in sorted(leader_rows, key=lambda item: (-int(item["value"]), item["player_name"])) if int(row["value"]) > 0][:5]

    return team_rows, standings, leaders


def write_contribution_csv(path: Path, teams: list[dict[str, object]]) -> None:
    rows: list[dict[str, object]] = []
    for team in teams:
        for contribution in team.get("player_contributions", []):
            rows.append(
                {
                    "team": team["name"],
                    **contribution,
                }
            )
    write_csv(
        path,
        [
            "team",
            "mlbam_id",
            "player_name",
            "player_type",
            "mlb_team",
            "weeks_active",
            "runs",
            "home_runs",
            "rbi",
            "stolen_bases",
            "at_bats",
            "hits",
            "walks",
            "hit_by_pitch",
            "sac_flies",
            "obp",
            "wins",
            "strikeouts",
            "saves",
            "innings_pitched",
            "outs_pitched",
            "earned_runs",
            "hits_allowed",
            "walks_allowed",
            "era",
            "whip",
        ],
        rows,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import prior-week stats, apply only active-lineup contributions, and update standings.")
    parser.add_argument("--week", required=True, help="Week key such as 2026-week-01")
    parser.add_argument("--start-date", required=True, help="Scoring-week start date in YYYY-MM-DD format")
    parser.add_argument("--end-date", required=True, help="Scoring-week end date in YYYY-MM-DD format")
    parser.add_argument("--season", type=int, default=2026, help="MLB season year to query")
    parser.add_argument("--lineup-path", help="Optional lineup snapshot CSV path")
    parser.add_argument("--stats-path", help="Optional weekly stats CSV path")
    parser.add_argument("--skip-fetch", action="store_true", help="Use an existing stats CSV instead of fetching MLB Stats API data")
    parser.add_argument("--replace-week", action="store_true", help="Replace an already-processed week in season-results-2026.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    lineup_path = Path(args.lineup_path) if args.lineup_path else LINEUP_DIR / f"{args.week}.csv"
    stats_path = Path(args.stats_path) if args.stats_path else STATS_DIR / f"{args.week}.csv"

    lineup_rows = read_csv_rows(lineup_path)
    if not lineup_rows:
        raise FileNotFoundError(f"Lineup snapshot not found or empty: {lineup_path}")
    validate_active_lineups(lineup_rows)

    if args.skip_fetch:
        stat_rows = read_csv_rows(stats_path)
        if not stat_rows:
            raise FileNotFoundError(f"Weekly stats CSV not found or empty: {stats_path}")
    else:
        stat_rows = fetch_and_write_weekly_stats(stats_path, args.start_date, args.end_date, args.season)

    week_result = build_week_result(args.week, args.season, args.start_date, args.end_date, lineup_path, stats_path, lineup_rows, stat_rows)
    existing = read_json(RESULTS_PATH) or {"season": args.season, "weeks": []}
    existing_weeks = [week for week in existing.get("weeks", []) if clean_value(week.get("week")) != args.week]
    if len(existing_weeks) != len(existing.get("weeks", [])) and not args.replace_week:
        raise ValueError(f"Week {args.week} already exists in {RESULTS_PATH}. Rerun with --replace-week to overwrite it.")
    existing_weeks.append(week_result)
    existing_weeks.sort(key=lambda item: (clean_value(item.get("start_date")), clean_value(item.get("week"))))

    teams, standings, leaders = aggregate_season(existing_weeks)
    standings_note = f"Standings updated through {existing_weeks[-1]['end_date']} using weekly active-lineup results only."
    payload = {
        "season": args.season,
        "generated_from": "draft-board-input-2026.csv, manager-rosters/*.csv, weekly lineup snapshots, and weekly MLB Stats API date-range imports",
        "standings_note": standings_note,
        "last_updated": datetime.now(UTC).isoformat(),
        "weeks": existing_weeks,
        "teams": teams,
        "standings": standings,
        "leaders": leaders,
    }
    write_json(RESULTS_PATH, payload)
    write_contribution_csv(CONTRIBUTIONS_PATH, teams)

    print(f"Wrote season results to {RESULTS_PATH}")
    print(f"Wrote player contribution totals to {CONTRIBUTIONS_PATH}")
    print(f"Processed {args.week} for {args.start_date} through {args.end_date}")


if __name__ == "__main__":
    main()