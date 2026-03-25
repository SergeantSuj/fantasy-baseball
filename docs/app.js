async function loadLeagueData() {
  const response = await fetch("data/league-site-data.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Unable to load league site data.");
  }
  return response.json();
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

function standingsRow(team) {
  const categories = team.category_points;
  return `
    <tr>
      <td><span class="rank-pill">${team.rank}</span></td>
      <td>${team.name}</td>
      <td>${formatMaybe(team.total_points, 2)}</td>
      <td>${formatMaybe(team.hitting_points, 2)}</td>
      <td>${formatMaybe(team.pitching_points, 2)}</td>
      <td>${formatMaybe(categories.runs, 2)}</td>
      <td>${formatMaybe(categories.home_runs, 2)}</td>
      <td>${formatMaybe(categories.rbi, 2)}</td>
      <td>${formatMaybe(categories.stolen_bases, 2)}</td>
      <td>${formatMaybe(categories.obp, 2)}</td>
      <td>${formatMaybe(categories.wins, 2)}</td>
      <td>${formatMaybe(categories.strikeouts, 2)}</td>
      <td>${formatMaybe(categories.saves, 2)}</td>
      <td>${formatMaybe(categories.era, 2)}</td>
      <td>${formatMaybe(categories.whip, 2)}</td>
    </tr>
  `;
}

function leadersCard(label, items) {
  const list = items
    .map(
      (item) => `
        <li class="leader-item">
          <div>
            <div>${item.player_name}</div>
            <div class="muted">${item.team} · ${item.mlb_team || "FA"}</div>
          </div>
          <div class="leader-value">${item.value}</div>
        </li>
      `,
    )
    .join("");

  return `
    <article class="leader-card">
      <div class="leader-label">${label}</div>
      <ul class="leader-list">${list}</ul>
    </article>
  `;
}

function statusChip(player) {
  const injury = player.injury_status;
  const transaction = player.transaction_status;
  const text = injury || transaction;
  return text ? `<span class="status-chip">${text}</span>` : '<span class="muted">Ready</span>';
}

function hitterRow(player) {
  return `
    <tr>
      <td>${player.lineup_slot}</td>
      <td>${player.player_name}</td>
      <td>${player.mlb_team || "FA"}</td>
      <td>${player.eligible_positions}</td>
      <td>${player.age || "-"}</td>
      <td>${player.dynasty_rank || "-"}</td>
      <td>${player.adp || "-"}</td>
      <td>${formatMaybe(player.projection.runs)}</td>
      <td>${formatMaybe(player.projection.home_runs)}</td>
      <td>${formatMaybe(player.projection.rbi)}</td>
      <td>${formatMaybe(player.projection.stolen_bases)}</td>
      <td>${formatMaybe(player.projection.obp, 3)}</td>
      <td>${statusChip(player)}</td>
    </tr>
  `;
}

function pitcherRow(player) {
  return `
    <tr>
      <td>${player.lineup_slot}</td>
      <td>${player.player_name}</td>
      <td>${player.mlb_team || "FA"}</td>
      <td>${player.eligible_positions}</td>
      <td>${player.age || "-"}</td>
      <td>${player.dynasty_rank || "-"}</td>
      <td>${player.adp || "-"}</td>
      <td>${formatMaybe(player.projection.wins)}</td>
      <td>${formatMaybe(player.projection.strikeouts)}</td>
      <td>${formatMaybe(player.projection.saves)}</td>
      <td>${formatMaybe(player.projection.innings_pitched)}</td>
      <td>${formatMaybe(player.projection.era, 2)}</td>
      <td>${formatMaybe(player.projection.whip, 2)}</td>
      <td>${statusChip(player)}</td>
    </tr>
  `;
}

function benchRow(player) {
  const actuals = player.actual_2025;
  const actualLine = [
    actuals.home_runs ? `HR ${actuals.home_runs}` : "",
    actuals.stolen_bases ? `SB ${actuals.stolen_bases}` : "",
    actuals.strikeouts ? `K ${actuals.strikeouts}` : "",
    actuals.saves ? `SV ${actuals.saves}` : "",
    actuals.obp ? `OBP ${actuals.obp}` : "",
    actuals.era ? `ERA ${actuals.era}` : "",
  ]
    .filter(Boolean)
    .join(" · ");

  return `
    <tr>
      <td>${player.player_name}</td>
      <td>${player.mlb_team || "FA"}</td>
      <td>${player.eligible_positions}</td>
      <td>${player.current_level || "MLB"}</td>
      <td>${player.dynasty_rank || "-"}</td>
      <td>${player.adp || "-"}</td>
      <td>${actualLine || "-"}</td>
      <td>${player.injury_status || player.transaction_status || "-"}</td>
    </tr>
  `;
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

function renderTeam(team) {
  document.getElementById("team-name-heading").textContent = `${team.name} Roster`;
  document.getElementById("team-subheading").textContent = `Projected rank ${team.standings.rank} with ${formatMaybe(team.standings.total_points, 2)} roto points.`;

  document.getElementById("active-hitters-body").innerHTML = team.active_hitters.map(hitterRow).join("");
  document.getElementById("active-pitchers-body").innerHTML = team.active_pitchers.map(pitcherRow).join("");
  document.getElementById("bench-body").innerHTML = team.bench.map(benchRow).join("");

  const totals = team.projected_totals;
  document.getElementById("team-summary").innerHTML = [
    summaryCard("Projected Roto", formatMaybe(team.standings.total_points, 2), `Hit ${formatMaybe(team.standings.hitting_points, 2)} · Pitch ${formatMaybe(team.standings.pitching_points, 2)}`),
    summaryCard("Hitting Line", `${formatMaybe(totals.runs)} R / ${formatMaybe(totals.home_runs)} HR`, `${formatMaybe(totals.rbi)} RBI · ${formatMaybe(totals.stolen_bases)} SB · ${formatMaybe(totals.obp, 3)} OBP`),
    summaryCard("Pitching Line", `${formatMaybe(totals.wins)} W / ${formatMaybe(totals.strikeouts)} K`, `${formatMaybe(totals.saves)} SV · ${formatMaybe(totals.era, 2)} ERA · ${formatMaybe(totals.whip, 2)} WHIP`),
  ].join("");
}

function render(data) {
  document.getElementById("page-title").textContent = data.title;
  document.getElementById("page-note").textContent = data.standings_note;
  document.getElementById("generated-from").textContent = data.generated_from;

  document.getElementById("standings-body").innerHTML = data.standings.map(standingsRow).join("");

  document.getElementById("leaders-grid").innerHTML = [
    leadersCard("Home Runs", data.leaders.home_runs),
    leadersCard("Stolen Bases", data.leaders.stolen_bases),
    leadersCard("Strikeouts", data.leaders.strikeouts),
    leadersCard("Saves", data.leaders.saves),
  ].join("");

  const teams = data.teams;
  const buttonContainer = document.getElementById("team-buttons");
  buttonContainer.innerHTML = teams
    .map(
      (team, index) =>
        `<button class="team-button${index === 0 ? " active" : ""}" data-team="${team.name}">${team.name}</button>`,
    )
    .join("");

  renderTeam(teams[0]);

  buttonContainer.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-team]");
    if (!button) {
      return;
    }
    const team = teams.find((item) => item.name === button.dataset.team);
    if (!team) {
      return;
    }
    buttonContainer.querySelectorAll(".team-button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    renderTeam(team);
  });
}

loadLeagueData().then(render).catch((error) => {
  document.body.innerHTML = `<main class="page-shell"><section class="panel"><h1>League Hub</h1><p>${error.message}</p></section></main>`;
});