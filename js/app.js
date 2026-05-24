// Entry point. Loads data, wires controls, renders on every state change.

import { initState, getState, setState, subscribe, DEFAULT_STATE } from "./state.js";
import {
  applyFilters,
  renderCategoryChips,
  renderSessionChips,
  wireLawChips,
  refreshLawChips,
  wireSponsorActiveChips,
  refreshSponsorActiveChips,
} from "./filters.js";
import { wireTable, renderTable, sortBills, refreshSortHeaders } from "./table.js";
import { renderSessionChart } from "./charts.js";
import { aggregateSponsors, canonicalizeName, renderSponsors, wireSponsorToggle } from "./sponsors.js";
import { renderTicker, renderWhatsNew } from "./recent.js";
import { renderMovement } from "./movement.js";

const state = {
  bills: [],
  meta: null,
  sessionsInData: [],
  // Set of canonicalized names (see canonicalizeName in sponsors.js) for
  // legislators currently serving in the current biennial session. Populated
  // on boot from data/active_legislators.json. An empty Set is the failure
  // mode — the filter chip stays hidden and the leaderboard runs without
  // active badges if the roster file can't be loaded.
  activeCanon: new Set(),
  // Map of canonical_name → party code ("D", "R", "I"...) for currently
  // serving members. We only have party data for current-roster members, so
  // historical sponsors get no flag — which is the right editorial call
  // (we'd be guessing their party affiliation from the year).
  partyByCanon: new Map(),
  rosterMeta: null,
};

async function boot() {
  initState();

  // Load dataset and metadata in parallel. movement.json is optional — it
  // may not exist yet on the very first deploy of this feature — so we
  // fetch it separately and tolerate failure.
  let meta, bills, movement = null;
  try {
    [meta, bills] = await Promise.all([
      fetch("data/meta.json", { cache: "no-cache" }).then(r => r.json()),
      fetch("data/bills.json", { cache: "no-cache" }).then(r => r.json()),
    ]);
  } catch (e) {
    document.getElementById("main").innerHTML =
      '<p class="empty-state">Could not load the dataset. If you\'re running this locally, start a server with <code>python -m http.server -d site 8000</code> and try again.</p>';
    console.error(e);
    return;
  }
  state.meta = meta;
  state.bills = bills;
  state.sessionsInData = [...new Set(bills.map(b => b.session))];

  // Tolerated-failure load: if movement.json is missing or unparseable the
  // panel just stays hidden. Don't fail the page over an optional feed.
  try {
    movement = await fetch("data/movement.json", { cache: "no-cache" }).then(r => r.ok ? r.json() : null);
  } catch (e) {
    console.warn("Could not load data/movement.json; movement panel disabled.", e);
  }

  // Roster is non-essential — if it fails to load, the rest of the site still
  // works; the filter chip just stays hidden and badges don't render.
  try {
    const roster = await fetch("data/active_legislators.json", { cache: "no-cache" }).then(r => r.json());
    state.rosterMeta = { updated_at: roster.updated_at, current_session: roster.current_session };
    state.activeCanon = new Set((roster.legislators || []).map(l => l.canonical_name));
    state.partyByCanon = new Map(
      (roster.legislators || [])
        .filter(l => l.canonical_name && l.party)
        .map(l => [l.canonical_name, l.party])
    );
  } catch (e) {
    console.warn("Could not load data/active_legislators.json; active-legislator filter disabled.", e);
  }

  // Every number on the page is machine-generated from meta.json so copy
  // never drifts from the data.
  document.getElementById("meta-updated").textContent = formatDate(meta.updated_at);
  document.getElementById("lede-para").innerHTML = ledeCopy(meta);

  // Ticker + "what's new" callout describe the dataset, not the explore
  // view, so render once on boot rather than on every state change.
  renderTicker(document.getElementById("ticker"), state.bills, meta);
  renderWhatsNew(document.getElementById("whats-new"), state.bills, meta);
  renderMovement(document.getElementById("movement"), movement);

  // Wire static event handlers.
  wireTable(document.getElementById("bills-table"));
  wireLawChips(document.getElementById("filter-law"));
  wireSponsorActiveChips(document.getElementById("filter-active"));
  wireSponsorToggle(document.getElementById("sponsors-toggle"), () => render(getState()));

  // Hide the active-legislator filter group entirely if the roster didn't
  // load. Better to omit the control than to ship one that always returns
  // zero rows.
  const activeGroup = document.getElementById("filter-active-group");
  if (activeGroup) activeGroup.hidden = state.activeCanon.size === 0;

  document.getElementById("search").addEventListener("input", (e) => {
    setState({ search: e.target.value });
  });
  document.getElementById("search").value = getState().search;

  // Logo doubles as a home button: clears the search box and every filter
  // without a full page reload. The href="./" on the anchor is the no-JS
  // fallback and also handles cmd/ctrl/middle-click (open in new tab).
  document.querySelector(".masthead-home")?.addEventListener("click", (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    e.preventDefault();
    document.getElementById("search").value = "";
    setState({ ...DEFAULT_STATE });
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  // Initial paint + subscribe for state changes.
  subscribe(render);
  render(getState());
}

function render(st) {
  // Filter, sort, render.
  const filtered = applyFilters(state.bills, st, state.activeCanon);
  const sorted = sortBills(filtered, st);

  // Top-of-page counter: always reflects current filter set — that's the joke
  // the masthead runs with, so the absurdity scales with what you're looking at.
  const counter = document.getElementById("counter-number");
  const counterLabel = document.getElementById("counter-label");
  counter.textContent = filtered.length.toLocaleString();
  counterLabel.textContent = labelForCounter(st, filtered.length);

  const summary = document.getElementById("results-summary");
  const becameLaw = filtered.filter(b => b.became_law).length;
  summary.innerHTML = filtered.length
    ? `<strong>${filtered.length.toLocaleString()}</strong> bills match, <strong>${becameLaw}</strong> became law.`
    : "No bills match these filters.";

  // Sponsor leaderboard — respects filters so you can ask "who sponsors the
  // most state symbols" or "who has passed the most ceremonial bills this session".
  const sponsors = aggregateSponsors(filtered);
  renderSponsors(
    document.getElementById("sponsors-list"),
    document.getElementById("sponsors-toggle"),
    sponsors,
    {
      activeCanon: state.activeCanon,
      activeLabel: "Active",
      activeAriaLabel: state.rosterMeta
        ? `Currently serving in the ${state.rosterMeta.current_session}–${state.rosterMeta.current_session + 1} session`
        : "Currently serving",
      partyByCanon: state.partyByCanon,
    }
  );

  // Chips + table.
  const counts = countByCategory(state.bills, st);
  renderCategoryChips(document.getElementById("filter-categories"), counts);
  renderSessionChips(document.getElementById("filter-sessions"), state.sessionsInData);
  refreshLawChips(document.getElementById("filter-law"));
  refreshSponsorActiveChips(document.getElementById("filter-active"));

  const tbody = document.getElementById("bills-tbody");
  renderTable(tbody, sorted, { partyByCanon: state.partyByCanon });
  refreshSortHeaders(document.getElementById("bills-table"));

  const empty = document.getElementById("empty-state");
  empty.hidden = filtered.length > 0;

  // Chart: always renders against the full bills array. It's the 25-year
  // context view, not the exploration surface. (Filters drive table & sponsors.)
  renderSessionChart(document.getElementById("chart-by-session"), state.bills);
}

function countByCategory(bills, st) {
  // Counts respect every filter EXCEPT category, so each chip shows the
  // hypothetical count if you clicked it.
  const others = { ...st, category: "all" };
  const filtered = applyFilters(bills, others, state.activeCanon);
  return filtered.reduce((acc, b) => {
    acc[b.primary_category] = (acc[b.primary_category] || 0) + 1;
    return acc;
  }, {});
}

function labelForCounter(st, n) {
  const plural = n === 1 ? "ceremonial bill" : "ceremonial bills";
  const bits = [plural];
  if (st.category !== "all") {
    const catLabels = {
      state_symbol: "in state symbols",
      holiday_observance: "in holidays & observances",
      road_naming: "in road namings",
      place_naming: "in place namings",
    };
    bits.push(catLabels[st.category] || "");
  }
  if (st.law === "yes") bits.push("that became law");
  if (st.law === "no") bits.push("that did not pass");
  if (st.sessions.length === 1) bits.push(`in ${st.sessions[0]}–${Number(st.sessions[0]) + 1}`);
  if (st.sponsorActive === "yes") bits.push("from currently serving legislators");
  if (st.search) bits.push(`matching "${st.search}"`);
  return bits.filter(Boolean).join(" ");
}

function formatDate(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, { year: "numeric", month: "long", day: "numeric" });
  } catch {
    return iso;
  }
}

function ledeCopy(meta) {
  const total = meta.total_bills.toLocaleString();
  const laws = meta.total_became_law.toLocaleString();
  const first = meta.earliest_session;
  const last = meta.latest_session;

  // Single-session phase (Phase 1) reads differently from the eventual
  // multi-session backfill. Keep the voice consistent either way.
  const range = first === last
    ? `In the <strong>${first}–${first + 1}</strong> session, the New Jersey Legislature introduced`
    : `Since <strong>${first}</strong>, the New Jersey Legislature has introduced`;

  return `
    ${range} <strong>${total}</strong> ceremonial bills —
    designating state symbols, naming bridges and rest stops, or carving out a
    commemorative day or week. <strong>${laws}</strong> became law. The rest did not.
  `;
}

boot();
