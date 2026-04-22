// Entry point. Loads data, wires controls, renders on every state change.

import { initState, getState, setState, subscribe } from "./state.js";
import { applyFilters, renderCategoryChips, renderSessionChips, wireLawChips, refreshLawChips } from "./filters.js";
import { wireTable, renderTable, sortBills, refreshSortHeaders } from "./table.js";
import { renderSessionChart } from "./charts.js";

const state = {
  bills: [],
  meta: null,
  sessionsInData: [],
};

async function boot() {
  initState();

  // Load dataset and metadata in parallel.
  let meta, bills;
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

  // Wire masthead numbers from meta.json. Every number on the page is
  // machine-generated so copy never drifts from the data.
  document.getElementById("meta-updated").textContent = formatDate(meta.updated_at);
  document.getElementById("span-total").textContent = meta.total_bills.toLocaleString();
  document.getElementById("span-first-session").textContent =
    meta.earliest_session ? `${meta.earliest_session}` : "—";

  // Wire static event handlers.
  wireTable(document.getElementById("bills-table"));
  wireLawChips(document.getElementById("filter-law"));

  document.getElementById("search").addEventListener("input", (e) => {
    setState({ search: e.target.value });
  });
  document.getElementById("search").value = getState().search;

  // Initial paint + subscribe for state changes.
  subscribe(render);
  render(getState());
}

function render(st) {
  // Filter, sort, render.
  const filtered = applyFilters(state.bills, st);
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

  // Chips + table.
  const counts = countByCategory(state.bills, st);
  renderCategoryChips(document.getElementById("filter-categories"), counts);
  renderSessionChips(document.getElementById("filter-sessions"), state.sessionsInData);
  refreshLawChips(document.getElementById("filter-law"));

  const tbody = document.getElementById("bills-tbody");
  renderTable(tbody, sorted);
  refreshSortHeaders(document.getElementById("bills-table"));

  const empty = document.getElementById("empty-state");
  empty.hidden = filtered.length > 0;

  // Chart: always renders against the full bills array but could be narrowed
  // to the filter set — for now it's the 25-year context view.
  renderSessionChart(document.getElementById("chart-by-session"), state.bills);
}

function countByCategory(bills, st) {
  // Counts respect every filter EXCEPT category, so each chip shows the
  // hypothetical count if you clicked it.
  const others = { ...st, category: "all" };
  const filtered = applyFilters(bills, others);
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

boot();
