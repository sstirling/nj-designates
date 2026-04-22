// The bill table — sortable columns, lazy for-loop rendering.
//
// 5k rows is fine for one-shot innerHTML rebuild; don't overthink it. If we
// ever cross ~20k rows we'll need virtualization.

import { getState, setState } from "./state.js";
import { CATEGORY_LABELS } from "./filters.js";
import { iconFor } from "./icons.js";

const STATUS_UNKNOWN = "Meaning not documented";

export function wireTable(table) {
  table.querySelectorAll("th[data-sort]").forEach(th => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      const state = getState();
      const nextDir = state.sort === key && state.sortDir === "desc" ? "asc" : "desc";
      setState({ sort: key, sortDir: nextDir });
    });
    th.tabIndex = 0;
    th.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        th.click();
      }
    });
  });
}

export function renderTable(tbody, bills) {
  if (!bills.length) {
    tbody.innerHTML = "";
    return;
  }
  const frag = document.createDocumentFragment();
  for (const b of bills) {
    const tr = document.createElement("tr");
    tr.innerHTML = rowHtml(b);
    frag.appendChild(tr);
  }
  tbody.replaceChildren(frag);
}

export function refreshSortHeaders(table) {
  const state = getState();
  table.querySelectorAll("th[data-sort]").forEach(th => {
    if (th.dataset.sort === state.sort) {
      th.setAttribute("aria-sort", state.sortDir === "asc" ? "ascending" : "descending");
    } else {
      th.removeAttribute("aria-sort");
    }
  });
}

function rowHtml(b) {
  const sponsors = (b.primary_sponsors || [])
    .map(s => s.bio_url
      ? `<a href="${esc(s.bio_url)}" rel="external noopener">${esc(s.name)}</a>`
      : esc(s.name))
    .join("; ") || "—";
  const statusLabel = b.status_label
    ? esc(b.status_label)
    : `<span class="status-unknown" title="${STATUS_UNKNOWN}">${esc(b.status_code || "—")}</span>`;
  const catLabel = CATEGORY_LABELS[b.primary_category] || b.primary_category;
  const catIcon = iconFor(b.primary_category);
  return `
    <td class="cell-bill"><a href="${esc(b.url)}" rel="external noopener">${esc(b.full_number)}</a></td>
    <td>${esc(b.session_label)}</td>
    <td class="cell-synopsis">${esc(b.synopsis)}</td>
    <td class="cell-category"><span class="cat-pill ${esc(b.primary_category)}">${catIcon}${esc(catLabel)}</span></td>
    <td>${statusLabel}</td>
    <td>${b.became_law ? '<span class="law-yes">Yes</span>' : '<span class="law-no">No</span>'}</td>
    <td class="cell-sponsors">${sponsors}</td>
  `;
}

export function sortBills(bills, state) {
  const { sort, sortDir } = state;
  const dir = sortDir === "asc" ? 1 : -1;
  const bySponsor = (b) => (b.primary_sponsors?.[0]?.name || "zz").toLowerCase();

  const getters = {
    full_number: (b) => ({ prefix: b.bill_type, num: Number(b.full_number.replace(/\D/g, "") || 0) }),
    session: (b) => Number(b.session),
    synopsis: (b) => (b.synopsis || "").toLowerCase(),
    primary_category: (b) => b.primary_category || "",
    status_label: (b) => (b.status_label || b.status_code || "").toLowerCase(),
    became_law: (b) => (b.became_law ? 1 : 0),
    sponsor: bySponsor,
  };
  const getter = getters[sort] || getters.session;

  return [...bills].sort((a, b) => {
    const av = getter(a);
    const bv = getter(b);
    // full_number gets special treatment so A10 sorts after A2 (numeric)
    if (sort === "full_number") {
      const byPrefix = av.prefix.localeCompare(bv.prefix);
      if (byPrefix) return byPrefix * dir;
      return (av.num - bv.num) * dir;
    }
    if (av < bv) return -1 * dir;
    if (av > bv) return 1 * dir;
    return 0;
  });
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
