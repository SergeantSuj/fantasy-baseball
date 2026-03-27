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

const POSITION_ORDER = {
  SP: 0,
  RP: 1,
  C: 2,
  "1B": 3,
  "2B": 4,
  "3B": 5,
  SS: 6,
  OF: 7,
  DH: 8,
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

function isMajorLeaguer(player) {
  const rosterBucket = String(player.roster_bucket || "").trim().toUpperCase();
  if (rosterBucket) {
    return rosterBucket !== "MINORS";
  }
  const level = String(player.current_level || "").trim().toUpperCase();
  return !level || level === "MLB" || level === "FA";
}

function normalizePosition(position) {
  const normalized = String(position || "").trim().toUpperCase();
  if (["LF", "CF", "RF"].includes(normalized)) {
    return "OF";
  }
  if (normalized === "P") {
    return "RP";
  }
  return normalized;
}

function primaryPositionRank(positions) {
  const parts = String(positions || "")
    .split("/")
    .map((part) => normalizePosition(part))
    .filter(Boolean);

  let bestRank = Number.MAX_SAFE_INTEGER;
  for (const part of parts) {
    const rank = POSITION_ORDER[part];
    if (rank !== undefined && rank < bestRank) {
      bestRank = rank;
    }
  }

  return bestRank === Number.MAX_SAFE_INTEGER ? 999 : bestRank;
}

function collectUsage(teams) {
  const usage = new Map(MLB_TEAMS.map((team) => [team.code, []]));

  teams.forEach((fantasyTeam) => {
    const roster = Array.isArray(fantasyTeam.roster) ? fantasyTeam.roster : [];
    roster.filter(isMajorLeaguer).forEach((player) => {
      const mlbTeam = normalizeMlbTeam(player.mlb_team);
      if (!usage.has(mlbTeam)) {
        return;
      }
      usage.get(mlbTeam).push({
        playerName: player.player_name,
        positions: player.eligible_positions || "-",
        fantasyTeam: fantasyTeam.name,
        currentLevel: player.current_level || "MLB",
      });
    });
  });

  MLB_TEAMS.forEach((team) => {
    const seen = new Set();
    const deduped = usage
      .get(team.code)
      .filter((player) => {
        const key = `${player.playerName}|${player.fantasyTeam}`;
        if (seen.has(key)) {
          return false;
        }
        seen.add(key);
        return true;
      })
      .sort((left, right) => {
        const positionGap = primaryPositionRank(left.positions) - primaryPositionRank(right.positions);
        if (positionGap !== 0) {
          return positionGap;
        }
        const nameCompare = left.playerName.localeCompare(right.playerName);
        if (nameCompare !== 0) {
          return nameCompare;
        }
        return left.fantasyTeam.localeCompare(right.fantasyTeam);
      });
    usage.set(team.code, deduped);
  });

  return usage;
}

function usageItem(player) {
  const levelNote = player.currentLevel && player.currentLevel !== "MLB" ? ` · ${player.currentLevel}` : "";
  return `
    <li class="usage-player">
      <div class="usage-player-row">
        <span class="usage-player-name">${player.playerName}</span>
        <span class="usage-position">${player.positions}</span>
      </div>
      <div class="small-note">${player.fantasyTeam}${levelNote}</div>
    </li>
  `;
}

function usageCard(team, players) {
  const playerList = players.length
    ? `<ul class="usage-list">${players.map(usageItem).join("")}</ul>`
    : '<div class="empty-state">No Boz Cup players are currently rostered from this MLB team.</div>';

  return `
    <article class="usage-card">
      <div class="usage-card-head">
        <h3>${team.name}</h3>
        <div class="usage-count">${players.length} rostered</div>
      </div>
      ${playerList}
    </article>
  `;
}

function render(data) {
  setText("page-title", "MLB Team Usage");
  setText("page-note", "Every MLB team is listed with the Boz Cup players currently stored on major-league rosters from that club.");

  const usage = collectUsage(data.teams || []);
  setHtml(
    "usage-grid",
    MLB_TEAMS.map((team) => usageCard(team, usage.get(team.code) || [])).join(""),
  );
}

loadLeagueData().then(render).catch((error) => {
  document.body.innerHTML = `<main class="page-shell"><section class="panel"><h1>MLB Team Usage</h1><p>${error.message}</p></section></main>`;
});