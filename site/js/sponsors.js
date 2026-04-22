// Sponsor leaderboard — aggregates primary sponsors across the filtered set.
//
// A single bill can have multiple primary sponsors; each gets +1. Co-sponsors
// are ignored here on purpose — journalistically, "prime sponsor" is who owns
// the bill. Ties break alphabetically so the order is deterministic.
//
// The section supports a "show more" toggle. Default shows top 10; full list
// can be expanded. Count includes bills that became law as a separate figure
// so readers can see who's merely proposing vs. who's actually delivering.

const INITIAL_VISIBLE = 10;

export function aggregateSponsors(bills) {
  const byKey = new Map();
  for (const bill of bills) {
    for (const s of bill.primary_sponsors || []) {
      const name = (s.name || "").trim();
      if (!name) continue;
      const entry = byKey.get(name) || { name, count: 0, laws: 0, bio_url: s.bio_url || null };
      entry.count += 1;
      if (bill.became_law) entry.laws += 1;
      // If any occurrence of this sponsor has a bio_url, keep it.
      if (!entry.bio_url && s.bio_url) entry.bio_url = s.bio_url;
      byKey.set(name, entry);
    }
  }
  return [...byKey.values()].sort((a, b) => {
    if (b.count !== a.count) return b.count - a.count;
    return a.name.localeCompare(b.name);
  });
}

export function renderSponsors(listEl, toggleEl, sponsors) {
  const top = sponsors.slice(0, INITIAL_VISIBLE);
  const expanded = toggleEl.dataset.expanded === "true";
  const visible = expanded ? sponsors : top;

  if (!visible.length) {
    listEl.innerHTML = '<li class="empty-state">No sponsors in the current filter.</li>';
    toggleEl.hidden = true;
    return;
  }

  const maxCount = visible[0].count || 1;
  listEl.innerHTML = visible.map(s => {
    const pct = Math.round((s.count / maxCount) * 100);
    const suffix = s.count === 1 ? "bill" : "bills";
    const lawNote = s.laws > 0
      ? `<small>${s.laws} became law</small>`
      : `<small>none became law</small>`;
    const nameHtml = s.bio_url
      ? `<a href="${esc(s.bio_url)}" rel="external noopener">${esc(s.name)}</a>`
      : esc(s.name);
    return `
      <li class="sponsor-row">
        <span class="sponsor-name">
          <strong>${nameHtml}</strong>
          ${lawNote}
          <span class="sponsor-bar" aria-hidden="true">
            <span class="sponsor-bar-fill" style="width: ${pct}%"></span>
          </span>
        </span>
        <span class="sponsor-count">${s.count.toLocaleString()}<span class="suffix">${suffix}</span></span>
      </li>
    `;
  }).join("");

  if (sponsors.length > INITIAL_VISIBLE) {
    toggleEl.hidden = false;
    toggleEl.textContent = expanded
      ? `Show top ${INITIAL_VISIBLE}`
      : `Show all ${sponsors.length.toLocaleString()} sponsors`;
  } else {
    toggleEl.hidden = true;
  }
}

export function wireSponsorToggle(toggleEl, onToggle) {
  toggleEl.addEventListener("click", () => {
    toggleEl.dataset.expanded = toggleEl.dataset.expanded === "true" ? "false" : "true";
    onToggle();
  });
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
