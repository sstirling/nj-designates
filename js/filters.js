// Applies the current state to the bill dataset and renders the filter chips.

import { getState, setState, toggleSession } from "./state.js";
import { iconFor } from "./icons.js";

export const CATEGORY_LABELS = {
  all: "All",
  state_symbol: "State symbols",
  holiday_observance: "Holidays & observances",
  road_naming: "Road namings",
  place_naming: "Place namings",
  other_ceremonial: "Other",
};

export function applyFilters(bills, state) {
  const q = state.search.trim().toLowerCase();
  const activeSessions = new Set(state.sessions);

  return bills.filter(b => {
    if (state.category !== "all" && b.primary_category !== state.category) return false;
    if (state.law === "yes" && !b.became_law) return false;
    if (state.law === "no" && b.became_law) return false;
    if (activeSessions.size && !activeSessions.has(b.session)) return false;
    if (q) {
      const hay = [
        b.synopsis || "",
        b.full_number || "",
        (b.primary_sponsors || []).map(s => s.name).join(" "),
      ].join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

export function renderCategoryChips(container, counts) {
  const state = getState();
  const entries = [
    ["all", CATEGORY_LABELS.all],
    ["state_symbol", CATEGORY_LABELS.state_symbol],
    ["holiday_observance", CATEGORY_LABELS.holiday_observance],
    ["road_naming", CATEGORY_LABELS.road_naming],
    ["place_naming", CATEGORY_LABELS.place_naming],
  ];
  container.innerHTML = "";
  for (const [value, label] of entries) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `chip chip-category chip-category-${value}`;
    btn.dataset.filter = "category";
    btn.dataset.value = value;
    const n = value === "all"
      ? Object.values(counts).reduce((a, b) => a + b, 0)
      : (counts[value] || 0);
    const icon = value !== "all" ? iconFor(value) : "";
    btn.innerHTML = `${icon}<span>${label} (${n.toLocaleString()})</span>`;
    btn.setAttribute("aria-pressed", state.category === value ? "true" : "false");
    btn.addEventListener("click", () => setState({ category: value }));
    container.appendChild(btn);
  }
}

export function renderSessionChips(container, sessionsInData) {
  const state = getState();
  container.innerHTML = "";
  const sorted = [...sessionsInData].sort((a, b) => Number(b) - Number(a));
  for (const s of sorted) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip";
    btn.dataset.filter = "session";
    btn.dataset.value = s;
    btn.textContent = `${s}–${Number(s) + 1}`;
    const active = state.sessions.includes(s);
    btn.setAttribute("aria-pressed", active ? "true" : "false");
    btn.addEventListener("click", () => toggleSession(s));
    container.appendChild(btn);
  }
}

export function wireLawChips(container) {
  container.addEventListener("click", (e) => {
    const btn = e.target.closest("button.chip");
    if (!btn) return;
    setState({ law: btn.dataset.value });
  });
}

export function refreshLawChips(container) {
  const state = getState();
  container.querySelectorAll("button.chip").forEach(btn => {
    btn.setAttribute("aria-pressed", btn.dataset.value === state.law ? "true" : "false");
  });
}
