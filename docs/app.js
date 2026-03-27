async function loadLeagueData() {
  const response = await fetch("data/league-site-data.json", { cache: "no-store" });
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

function setSectionVisibility(id, isVisible) {
  const element = document.getElementById(id);
  const section = element ? element.closest(".roster-section") : null;
  if (section) {
    section.style.display = isVisible ? "block" : "none";
  }
}

function setHidden(id, isHidden) {
  const element = document.getElementById(id);
  if (element) {
    element.hidden = isHidden;
  }
}

function ordinal(place) {
  const remainder100 = place % 100;
  if (remainder100 >= 11 && remainder100 <= 13) {
    return `${place}th`;
  }
  const remainder10 = place % 10;
  if (remainder10 === 1) {
    return `${place}st`;
  }
  if (remainder10 === 2) {
    return `${place}nd`;
  }
  if (remainder10 === 3) {
    return `${place}rd`;
  }
  return `${place}th`;
}

function buildPlaceMap(standings, valueAccessor, higherIsBetter = true) {
  const sorted = [...standings].sort((left, right) => {
    const leftValue = valueAccessor(left);
    const rightValue = valueAccessor(right);
    if (leftValue === rightValue) {
      return left.name.localeCompare(right.name);
    }
    return higherIsBetter ? rightValue - leftValue : leftValue - rightValue;
  });

  const places = {};
  let currentPlace = 1;
  for (let index = 0; index < sorted.length; index += 1) {
    if (index > 0) {
      const currentValue = valueAccessor(sorted[index]);
      const previousValue = valueAccessor(sorted[index - 1]);
      if (currentValue !== previousValue) {
        currentPlace = index + 1;
      }
    }
    places[sorted[index].name] = currentPlace;
  }
  return places;
}

function formatStandingsValue(value, place, digits = 0) {
  return `${formatMaybe(value, digits)} (${ordinal(place)})`;
}

function formatRateNoLeadingZero(value, digits) {
  const formatted = formatMaybe(value, digits);
  if (formatted === "-" || formatted === "") {
    return formatted;
  }
  return formatted.replace(/^(-?)0\./, "$1.");
}

function formatStandingsRateValue(value, place, digits) {
  return `${formatRateNoLeadingZero(value, digits)} (${ordinal(place)})`;
}

function buildStandingsPlaces(standings) {
  return {
    total_points: buildPlaceMap(standings, (team) => Number(team.total_points || 0), true),
    runs: buildPlaceMap(standings, (team) => Number(team.season_totals?.runs || 0), true),
    home_runs: buildPlaceMap(standings, (team) => Number(team.season_totals?.home_runs || 0), true),
    rbi: buildPlaceMap(standings, (team) => Number(team.season_totals?.rbi || 0), true),
    stolen_bases: buildPlaceMap(standings, (team) => Number(team.season_totals?.stolen_bases || 0), true),
    obp: buildPlaceMap(standings, (team) => Number(team.season_totals?.obp || 0), true),
    wins: buildPlaceMap(standings, (team) => Number(team.season_totals?.wins || 0), true),
    strikeouts: buildPlaceMap(standings, (team) => Number(team.season_totals?.strikeouts || 0), true),
    saves: buildPlaceMap(standings, (team) => Number(team.season_totals?.saves || 0), true),
    era: buildPlaceMap(standings, (team) => Number(team.season_totals?.era || 0), false),
    whip: buildPlaceMap(standings, (team) => Number(team.season_totals?.whip || 0), false),
  };
}

function standingsRow(team, places) {
  const totals = team.season_totals || {};
  return `
    <tr>
      <td><span class="rank-pill">${team.rank}</span></td>
      <td>${team.name}</td>
      <td>${formatStandingsValue(team.total_points, places.total_points[team.name], 2)}</td>
      <td>${formatStandingsValue(totals.runs, places.runs[team.name])}</td>
      <td>${formatStandingsValue(totals.home_runs, places.home_runs[team.name])}</td>
      <td>${formatStandingsValue(totals.rbi, places.rbi[team.name])}</td>
      <td>${formatStandingsValue(totals.stolen_bases, places.stolen_bases[team.name])}</td>
      <td>${formatStandingsRateValue(totals.obp, places.obp[team.name], 3)}</td>
      <td>${formatStandingsValue(totals.wins, places.wins[team.name])}</td>
      <td>${formatStandingsValue(totals.strikeouts, places.strikeouts[team.name])}</td>
      <td>${formatStandingsValue(totals.saves, places.saves[team.name])}</td>
      <td>${formatStandingsValue(totals.era, places.era[team.name], 2)}</td>
      <td>${formatStandingsValue(totals.whip, places.whip[team.name], 2)}</td>
    </tr>
  `;
}

function leadersCard(label, items) {
  const list = items.length
    ? items
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
        .join("")
    : `
        <li class="leader-item">
          <div>
            <div>No qualifying totals yet</div>
            <div class="muted">This category will populate once an active lineup records a counted total.</div>
          </div>
          <div class="leader-value">0</div>
        </li>
      `;

  return `
    <article class="leader-card">
      <div class="leader-label">${label}</div>
      <ul class="leader-list">${list}</ul>
    </article>
  `;
}

function statusChip(player) {
  const injury = player.injury_status;
  return injury ? `<span class="status-chip">${injury}</span>` : '<span class="muted">Available</span>';
}

function hitterRow(player) {
  const ytd = player.ytd?.hitting || {};
  return `
    <tr>
      <td>${player.lineup_slot}</td>
      <td>${player.player_name}</td>
      <td>${player.mlb_team || "FA"}</td>
      <td>${player.eligible_positions}</td>
      <td>${player.age || "-"}</td>
      <td>${formatMaybe(ytd.games, 0)}</td>
      <td>${formatMaybe(ytd.runs, 0)}</td>
      <td>${formatMaybe(ytd.home_runs, 0)}</td>
      <td>${formatMaybe(ytd.rbi, 0)}</td>
      <td>${formatMaybe(ytd.stolen_bases, 0)}</td>
      <td>${formatRateNoLeadingZero(ytd.obp, 3)}</td>
      <td>${statusChip(player)}</td>
    </tr>
  `;
}

function pitcherRow(player) {
  const ytd = player.ytd?.pitching || {};
  return `
    <tr>
      <td>${player.lineup_slot}</td>
      <td>${player.player_name}</td>
      <td>${player.mlb_team || "FA"}</td>
      <td>${player.eligible_positions}</td>
      <td>${player.age || "-"}</td>
      <td>${formatMaybe(ytd.games, 0)}</td>
      <td>${formatMaybe(ytd.wins, 0)}</td>
      <td>${formatMaybe(ytd.strikeouts, 0)}</td>
      <td>${formatMaybe(ytd.saves, 0)}</td>
      <td>${ytd.innings_pitched || "0.0"}</td>
      <td>${formatMaybe(ytd.era, 2)}</td>
      <td>${formatMaybe(ytd.whip, 2)}</td>
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
      <td>${player.injury_status || "Available"}</td>
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
  setText("team-name-heading", `${team.name} Active Roster Snapshot`);
  setText("team-subheading", `Snapshot view shows only the current active lineup. Use the team page for reserves, minors, and contribution detail.`);

  setHtml("active-hitters-body", team.active_hitters.map(hitterRow).join(""));
  setHtml("active-pitchers-body", team.active_pitchers.map(pitcherRow).join(""));
  setHtml("bench-body", "");
  setSectionVisibility("bench-body", false);

  const totals = team.season_totals;
  setHtml("team-summary", [
    summaryCard("Current Roto", formatMaybe(team.standings.total_points, 2), `Hit ${formatMaybe(team.standings.hitting_points, 2)} · Pitch ${formatMaybe(team.standings.pitching_points, 2)}`),
    summaryCard("Hitting To Date", `${formatMaybe(totals.runs)} R / ${formatMaybe(totals.home_runs)} HR`, `${formatMaybe(totals.rbi)} RBI · ${formatMaybe(totals.stolen_bases)} SB · ${formatMaybe(totals.obp, 3)} OBP`),
    summaryCard("Pitching To Date", `${formatMaybe(totals.wins)} W / ${formatMaybe(totals.strikeouts)} K`, `${formatMaybe(totals.saves)} SV · ${formatMaybe(totals.era, 2)} ERA · ${formatMaybe(totals.whip, 2)} WHIP`),
  ].join(""));
}

function render(data) {
  setText("page-title", data.title);
  setText("page-note", data.standings_note);
  setText("stats-reflect-note", data.stats_reflect_note || "");
  setHidden("stats-reflect-note", !data.stats_reflect_note);

  const standingsPlaces = buildStandingsPlaces(data.standings);
  setHtml("standings-body", data.standings.map((team) => standingsRow(team, standingsPlaces)).join(""));

  setHtml("leaders-grid", [
    leadersCard("Home Runs", data.leaders.home_runs),
    leadersCard("Stolen Bases", data.leaders.stolen_bases),
    leadersCard("Strikeouts", data.leaders.strikeouts),
    leadersCard("Saves", data.leaders.saves),
  ].join(""));

  const teams = data.teams;
  const buttonContainer = document.getElementById("team-buttons");
  if (!buttonContainer) {
    return;
  }
  buttonContainer.innerHTML = teams
    .map(
      (team, index) =>
        `<button class="team-button${index === 0 ? " active" : ""}" data-team="${team.name}">${team.name}</button>`,
    )
    .join("");

  setHtml("team-page-links", teams
    .map(
      (team) =>
        `<a class="team-link" href="teams/${slugifyTeamName(team.name)}.html">${team.name} page</a>`,
    )
    .join(""));

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