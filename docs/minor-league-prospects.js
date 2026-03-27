const MLB_TEAMS = [
  { code: "ARI", name: "Arizona Diamondbacks" },
  { code: "ATL", name: "Atlanta Braves" },
  { code: "BAL", name: "Baltimore Orioles" },
  { code: "BOS", name: "Boston Red Sox" },
  { code: "CHC", name: "Chicago Cubs" },
  { code: "CWS", name: "Chicago White Sox" },
  { code: "CIN", name: "Cincinnati Reds" },
  { code: "CLE", name: "Cleveland Guardians" },
  { code: "COL", name: "Colorado Rockies" },
  { code: "DET", name: "Detroit Tigers" },
  { code: "HOU", name: "Houston Astros" },
  { code: "KC", name: "Kansas City Royals" },
  { code: "LAA", name: "Los Angeles Angels" },
  { code: "LAD", name: "Los Angeles Dodgers" },
  { code: "MIA", name: "Miami Marlins" },
  { code: "MIL", name: "Milwaukee Brewers" },
  { code: "MIN", name: "Minnesota Twins" },
  { code: "NYM", name: "New York Mets" },
  { code: "NYY", name: "New York Yankees" },
  { code: "ATH", name: "Athletics" },
  { code: "PHI", name: "Philadelphia Phillies" },
  { code: "PIT", name: "Pittsburgh Pirates" },
  { code: "SD", name: "San Diego Padres" },
  { code: "SEA", name: "Seattle Mariners" },
  { code: "SF", name: "San Francisco Giants" },
  { code: "STL", name: "St. Louis Cardinals" },
  { code: "TB", name: "Tampa Bay Rays" },
  { code: "TEX", name: "Texas Rangers" },
  { code: "TOR", name: "Toronto Blue Jays" },
  { code: "WSH", name: "Washington Nationals" },
];

const MLB_TEAM_ALIASES = {
  AZ: "ARI",
  OAK: "ATH",
};

async function loadLeagueData() {
  const response = await fetch("data/league-site-data.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Unable to load league site data.");
  }
  return response.json();
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

function normalizeMlbTeam(code) {
  const normalized = String(code || "").trim().toUpperCase();
  return MLB_TEAM_ALIASES[normalized] || normalized;
}

function isMinorLeaguer(player) {
  const rosterBucket = String(player.roster_bucket || "").trim().toUpperCase();
  if (rosterBucket) {
    return rosterBucket === "MINORS";
  }
  const level = String(player.current_level || "").trim().toUpperCase();
  return Boolean(level) && level !== "MLB";
}

function collectProspects(teams) {
  const prospects = new Map(MLB_TEAMS.map((team) => [team.code, []]));

  teams.forEach((fantasyTeam) => {
    const roster = Array.isArray(fantasyTeam.roster) ? fantasyTeam.roster : [];
    roster.filter(isMinorLeaguer).forEach((player) => {
      const mlbTeam = normalizeMlbTeam(player.mlb_team);
      if (!prospects.has(mlbTeam)) {
        return;
      }
      prospects.get(mlbTeam).push({
        playerName: player.player_name,
        positions: player.eligible_positions || "-",
        fantasyTeam: fantasyTeam.name,
        currentLevel: player.current_level || "Minors",
      });
    });
  });

  MLB_TEAMS.forEach((team) => {
    const sortedPlayers = prospects.get(team.code).sort((left, right) => {
      const nameCompare = left.playerName.localeCompare(right.playerName);
      if (nameCompare !== 0) {
        return nameCompare;
      }
      return left.fantasyTeam.localeCompare(right.fantasyTeam);
    });
    prospects.set(team.code, sortedPlayers);
  });

  return prospects;
}

function prospectItem(player) {
  return `
    <li class="usage-player">
      <div class="usage-player-row">
        <span class="usage-player-name">${player.playerName}</span>
        <span class="usage-position">${player.positions}</span>
      </div>
      <div class="small-note">${player.fantasyTeam} · ${player.currentLevel}</div>
    </li>
  `;
}

function prospectCard(team, players) {
  const playerList = players.length
    ? `<ul class="usage-list">${players.map(prospectItem).join("")}</ul>`
    : '<div class="empty-state">No drafted Boz Cup prospects are currently attached to this MLB affiliate.</div>';

  return `
    <article class="usage-card">
      <div class="usage-card-head">
        <h3>${team.name}</h3>
        <div class="usage-count">${players.length} prospects</div>
      </div>
      ${playerList}
    </article>
  `;
}

function render(data) {
  setText("page-title", "Minor League Prospects");

  const prospects = collectProspects(data.teams || []);
  const totalProspects = MLB_TEAMS.reduce((count, team) => count + (prospects.get(team.code) || []).length, 0);
  const summaryText = totalProspects
    ? `Current roster data includes ${totalProspects} player${totalProspects === 1 ? "" : "s"} on minor-league rosters. Each MLB affiliate card below reflects only minor-league roster slots.`
    : "No players are currently assigned to minor-league roster slots. Once the Boz Cup minor league draft is added to the roster files, this page will group those players under the correct MLB affiliate automatically.";

  setText("page-note", "Players are grouped by MLB affiliate and filtered strictly to minor-league roster slots.");
  setText("prospect-summary", summaryText);
  setHtml(
    "prospect-grid",
    MLB_TEAMS.map((team) => prospectCard(team, prospects.get(team.code) || [])).join(""),
  );
}

loadLeagueData().then(render).catch((error) => {
  document.body.innerHTML = `<main class="page-shell"><section class="panel"><h1>Minor League Prospects</h1><p>${error.message}</p></section></main>`;
});