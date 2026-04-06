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

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

let allTransactions = [];
let activeTeamFilter = null;

function renderTable() {
  const tbody = document.getElementById("transaction-body");
  const table = document.getElementById("transaction-table");
  const empty = document.getElementById("transaction-empty");

  const filtered = activeTeamFilter
    ? allTransactions.filter((t) => t.team === activeTeamFilter)
    : allTransactions;

  if (filtered.length === 0) {
    table.hidden = true;
    empty.hidden = false;
    empty.textContent = activeTeamFilter
      ? `No transactions for ${activeTeamFilter}.`
      : "No transactions recorded yet.";
    return;
  }

  table.hidden = false;
  empty.hidden = true;

  const typeClass = {
    "FA Acquisition": "type-add",
    "FA Add (IL Replacement)": "type-add",
    "Drop": "type-drop",
    "IL Move": "type-il",
    "Status Update": "type-status",
  };

  tbody.innerHTML = filtered
    .map(
      (t) => `
    <tr>
      <td>${escapeHtml(t.week)}</td>
      <td>${escapeHtml(t.date)}</td>
      <td>${escapeHtml(t.team)}</td>
      <td><span class="tx-type ${typeClass[t.type] || ""}">${escapeHtml(t.type)}</span></td>
      <td>${escapeHtml(t.player_name)}</td>
      <td>${escapeHtml(t.detail)}</td>
      <td>${escapeHtml(t.related_player)}</td>
    </tr>`,
    )
    .join("");
}

function buildTeamFilter(teams) {
  const container = document.getElementById("team-filter");

  const allBtn = document.createElement("button");
  allBtn.className = "team-button active";
  allBtn.textContent = "All Teams";
  allBtn.addEventListener("click", () => {
    activeTeamFilter = null;
    setActiveButton(container, allBtn);
    renderTable();
  });
  container.appendChild(allBtn);

  teams.forEach((name) => {
    const btn = document.createElement("button");
    btn.className = "team-button";
    btn.textContent = name;
    btn.addEventListener("click", () => {
      activeTeamFilter = name;
      setActiveButton(container, btn);
      renderTable();
    });
    container.appendChild(btn);
  });
}

function setActiveButton(container, active) {
  container.querySelectorAll(".team-button").forEach((b) => b.classList.remove("active"));
  active.classList.add("active");
}

async function init() {
  try {
    const data = await loadLeagueData();
    allTransactions = Array.isArray(data.transactions) ? data.transactions : [];

    // Sort: most recent week first, then by type
    allTransactions.sort((a, b) => {
      if (a.week !== b.week) return b.week.localeCompare(a.week);
      if (a.team !== b.team) return a.team.localeCompare(b.team);
      return a.type.localeCompare(b.type);
    });

    // Build team list from standings order if available, else from transactions
    const teamNames = data.standings
      ? data.standings.map((s) => s.name)
      : [...new Set(allTransactions.map((t) => t.team))].sort();

    buildTeamFilter(teamNames);
    renderTable();
  } catch (err) {
    setText("page-note", "Error loading transaction data.");
    console.error(err);
  }
}

init();
