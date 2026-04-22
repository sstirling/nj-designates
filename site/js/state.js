// Centralized, URL-synced state for the app.
//
// Filter choices live in window.location.hash as a URL-querystring so every
// view is bookmarkable and shareable. That's non-negotiable for journalism —
// readers should be able to link to "Show me every state symbol since 2020"
// with a single URL.
//
// Subscribers are called on every state change. Small state surface means we
// don't need a framework or a diff algorithm.

export const DEFAULT_STATE = {
  category: "all",      // "all" | "state_symbol" | "holiday_observance" | "road_naming" | "place_naming"
  law: "all",           // "all" | "yes" | "no"
  sessions: [],         // [] means all; otherwise array of session strings ("2024", ...)
  search: "",
  sort: "session",      // column key
  sortDir: "desc",      // "asc" | "desc"
};

let currentState = { ...DEFAULT_STATE };
const subscribers = new Set();

function parseHash() {
  const hash = window.location.hash.replace(/^#/, "");
  if (!hash) return { ...DEFAULT_STATE };
  const params = new URLSearchParams(hash);
  const state = { ...DEFAULT_STATE };
  if (params.has("category")) state.category = params.get("category");
  if (params.has("law")) state.law = params.get("law");
  if (params.has("sessions")) {
    const raw = params.get("sessions").trim();
    state.sessions = raw ? raw.split(",").filter(Boolean) : [];
  }
  if (params.has("q")) state.search = params.get("q");
  if (params.has("sort")) state.sort = params.get("sort");
  if (params.has("dir")) state.sortDir = params.get("dir");
  return state;
}

function writeHash(state) {
  const params = new URLSearchParams();
  if (state.category !== DEFAULT_STATE.category) params.set("category", state.category);
  if (state.law !== DEFAULT_STATE.law) params.set("law", state.law);
  if (state.sessions.length) params.set("sessions", state.sessions.join(","));
  if (state.search) params.set("q", state.search);
  if (state.sort !== DEFAULT_STATE.sort) params.set("sort", state.sort);
  if (state.sortDir !== DEFAULT_STATE.sortDir) params.set("dir", state.sortDir);
  const next = params.toString();
  const target = next ? `#${next}` : " ";
  if (window.location.hash !== target) {
    history.replaceState(null, "", `${window.location.pathname}${window.location.search}${target}`);
  }
}

export function initState() {
  currentState = parseHash();
  window.addEventListener("hashchange", () => {
    currentState = parseHash();
    notify();
  });
  return currentState;
}

export function getState() {
  return currentState;
}

export function setState(patch) {
  currentState = { ...currentState, ...patch };
  writeHash(currentState);
  notify();
}

export function toggleSession(session) {
  const s = currentState.sessions.includes(session)
    ? currentState.sessions.filter(x => x !== session)
    : [...currentState.sessions, session];
  setState({ sessions: s });
}

export function subscribe(fn) {
  subscribers.add(fn);
  return () => subscribers.delete(fn);
}

function notify() {
  for (const fn of subscribers) fn(currentState);
}
