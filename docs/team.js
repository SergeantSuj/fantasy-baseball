async function loadLeagueData() {
  const response = await fetch("../data/league-site-data.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Unable to load league site data.");
  }
  return response.json();
}

function slugifyTeamName(name) {
  return String(name || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function formatMaybe(value, digits = 1) {
  if (value === "" || value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "number") {
    return value.toFixed(digits).replace(/\.0$/, "");
  }
  return String(value);
}

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) {
    element.textContent = value;
  }
}

function setHtml(id, value) {
  const element = document.getElementById(id);
  if (element) {
    element.innerHTML = value;
  }
}

function formatRateNoLeadingZero(value, digits) {
  const formatted = formatMaybe(value, digits);
  if (formatted === "-" || formatted === "") {
    return formatted;
  }
  return formatted.replace(/^(-?)0\./, "$1.");
}

function currentTeamSlug() {
  return document.body.dataset.team || "";
}

function minorLeaguePlayers(team) {
  return team.roster.filter((player) => {
    const level = String(player.current_level || "").toUpperCase();
    return level && level !== "MLB" && level !== "FA";
  });
}

function majorLeaguePlayers(team) {
  const minorKeys = new Set(minorLeaguePlayers(team).map((player) => player.player_name));
  return team.roster.filter((player) => !minorKeys.has(player.player_name));
}

function activePlayerKeySet(team) {
  return new Set(
    [...team.active_hitters, ...team.active_pitchers].map((player) => `${player.player_name}::${player.mlb_team || ""}`),
  );
}

function playerStatus(team, player) {
  const activeKeys = activePlayerKeySet(team);
  const playerKey = `${player.player_name}::${player.mlb_team || ""}`;
  if (activeKeys.has(playerKey)) {
    return "Active";
  }
  return "Reserve";
}

function navLinks(teams, activeTeamName) {
  return teams
    .map((team) => {
      const slug = slugifyTeamName(team.name);
      const activeClass = team.name === activeTeamName ? " active" : "";
      return `<a class="nav-link${activeClass}" href="${slug}.html">${team.name}</a>`;
    })
    .join("");
}

function summaryCard(label, value, sublabel) {
  return `
    <article class="summary-card">
      <div class="leader-label">${label}</div>
      <span class="summary-value">${value}</span>
      <div class="muted">${sublabel}</div>
    </article>
  `;
}

function rosterRow(team, player) {
  return `
    <tr>
      <td>${playerStatus(team, player)}</td>
      <td>
        <div class="player-name-cell">
          <span>${player.player_name}</span>
          <span class="small-note">${player.current_level || "MLB"}</span>
        </div>
      </td>
      <td>${player.mlb_team || "FA"}</td>
      <td>${player.eligible_positions || "-"}</td>
      <td>${player.age || "-"}</td>
      <td>${player.dynasty_rank || "-"}</td>
      <td>${player.adp || "-"}</td>
      <td>${player.injury_status || "Available"}</td>
    </tr>
  `;
}

function contributionHitterRow(player) {
  const contribution = player.season_contribution || {};
  return `
    <tr>
      <td>${player.player_name}</td>
      <td>${player.mlb_team || "FA"}</td>
      <td>${formatMaybe(contribution.weeks_active, 0)}</td>
      <td>${formatMaybe(contribution.runs, 0)}</td>
      <td>${formatMaybe(contribution.home_runs, 0)}</td>
      <td>${formatMaybe(contribution.rbi, 0)}</td>
      <td>${formatMaybe(contribution.stolen_bases, 0)}</td>
      <td>${formatRateNoLeadingZero(contribution.obp, 3)}</td>
      <td>${formatMaybe(contribution.hits, 0)}</td>
      <td>${formatMaybe(contribution.walks, 0)}</td>
      <td>${formatMaybe(contribution.hit_by_pitch, 0)}</td>
      <td>${formatMaybe(contribution.at_bats, 0)}</td>
      <td>${formatMaybe(contribution.sac_flies, 0)}</td>
    </tr>
  `;
}

function contributionPitcherRow(player) {
  const contribution = player.season_contribution || {};
  return `
    <tr>
      <td>${player.player_name}</td>
      <td>${player.mlb_team || "FA"}</td>
      <td>${formatMaybe(contribution.weeks_active, 0)}</td>
      <td>${formatMaybe(contribution.wins, 0)}</td>
      <td>${formatMaybe(contribution.strikeouts, 0)}</td>
      <td>${formatMaybe(contribution.saves, 0)}</td>
      <td>${formatMaybe(contribution.era, 2)}</td>
      <td>${formatMaybe(contribution.earned_runs, 0)}</td>
      <td>${contribution.innings_pitched || "0.0"}</td>
      <td>${formatMaybe(contribution.whip, 2)}</td>
      <td>${formatMaybe(contribution.hits_allowed, 0)}</td>
      <td>${formatMaybe(contribution.walks_allowed, 0)}</td>
    </tr>
  `;
}

function formulaCard(title, formula, details) {
  return `
    <article class="formula-card">
      <div class="leader-label">${title}</div>
      <p><code>${formula}</code></p>
      <p class="muted">${details}</p>
    </article>
  `;
}

function playerContributionGroups(team) {
  const majorLeaguers = majorLeaguePlayers(team);
  const hitters = majorLeaguers.filter((player) => {
    const contribution = player.season_contribution || {};
    const hasHittingContribution = [
      contribution.runs,
      contribution.home_runs,
      contribution.rbi,
      contribution.stolen_bases,
      contribution.at_bats,
      contribution.hits,
      contribution.walks,
      contribution.hit_by_pitch,
      contribution.sac_flies,
    ].some((value) => Number(value || 0) > 0);
    const positions = String(player.eligible_positions || "");
    const roleFallback = !positions.includes("SP") && !positions.includes("RP") && positions !== "P";
    return hasHittingContribution || roleFallback || String(player.player_type || "") === "two-way";
  });
  const pitchers = majorLeaguers.filter((player) => {
    const contribution = player.season_contribution || {};
    const hasPitchingContribution = [
      contribution.wins,
      contribution.strikeouts,
      contribution.saves,
      contribution.outs_pitched,
      contribution.earned_runs,
      contribution.hits_allowed,
      contribution.walks_allowed,
    ].some((value) => Number(value || 0) > 0);
    const positions = String(player.eligible_positions || "");
    const roleFallback = positions.includes("SP") || positions.includes("RP") || positions === "P" || positions.includes("/P");
    return hasPitchingContribution || roleFallback;
  });
  return { hitters, pitchers };
}

function renderTeamPage(data) {
  const slug = currentTeamSlug();
  const team = data.teams.find((item) => slugifyTeamName(item.name) === slug);
  if (!team) {
    throw new Error(`Unable to find team page data for ${slug}.`);
  }

  const teams = data.teams;
  const minors = minorLeaguePlayers(team);
  const mlbRoster = majorLeaguePlayers(team);
  const { hitters, pitchers } = playerContributionGroups(team);
  const totals = team.season_totals;

  document.title = `${team.name} Team Page`;
  setText("page-title", `${team.name} Team Page`);
  setText("page-note", data.standings_note);
  setHtml("team-nav", navLinks(teams, team.name));
  setHtml("team-summary", [
    summaryCard("Current Roto", formatMaybe(team.standings.total_points, 2), `Rank ${formatMaybe(team.standings.rank, 0)} · Hit ${formatMaybe(team.standings.hitting_points, 2)} · Pitch ${formatMaybe(team.standings.pitching_points, 2)}`),
    summaryCard("Hitting To Date", `${formatMaybe(totals.runs)} R / ${formatMaybe(totals.home_runs)} HR`, `${formatMaybe(totals.rbi)} RBI · ${formatMaybe(totals.stolen_bases)} SB · ${formatRateNoLeadingZero(totals.obp, 3)} OBP`),
    summaryCard("Pitching To Date", `${formatMaybe(totals.wins)} W / ${formatMaybe(totals.strikeouts)} K`, `${formatMaybe(totals.saves)} SV · ${formatMaybe(totals.era, 2)} ERA · ${formatMaybe(totals.whip, 2)} WHIP`),
  ].join(""));

  setHtml("formula-grid", [
    formulaCard("OBP", "(H + BB + HBP) / (AB + BB + HBP + SF)", "Track hits, walks, hit by pitch, at-bats, and sacrifice flies for every counted plate appearance."),
    formulaCard("ERA", "(ER * 9) / IP", "Track earned runs and innings pitched. The data model stores pitching outs so values like 6.2 innings remain 6 and 2/3 innings."),
    formulaCard("WHIP", "(H allowed + BB allowed) / IP", "Track hits allowed, walks allowed, and innings pitched for every counted outing."),
  ].join(""));

  setHtml("mlb-roster-body", mlbRoster.map((player) => rosterRow(team, player)).join(""));
  setHtml("minor-roster-content", minors.length
    ? `
        <div class="table-wrap">
          <table class="roster-table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Player</th>
                <th>MLB</th>
                <th>Pos</th>
                <th>Age</th>
                <th>Dyn</th>
                <th>ADP</th>
                <th>Status Note</th>
              </tr>
            </thead>
            <tbody>${minors.map((player) => rosterRow(team, player)).join("")}</tbody>
          </table>
        </div>
      `
    : `<div class="empty-state">No players are currently stored in minor-league roster slots for ${team.name}.</div>`);

  setHtml("hitter-contributions-body", hitters.map(contributionHitterRow).join(""));
  setHtml("pitcher-contributions-body", pitchers.map(contributionPitcherRow).join(""));
}

loadLeagueData()
  .then(renderTeamPage)
  .catch((error) => {
    document.body.innerHTML = `<main class="page-shell"><section class="panel"><h1>Team Page</h1><p>${error.message}</p></section></main>`;
  });