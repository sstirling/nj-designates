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

// Mirrors scraper/fetch_roster.py::canonicalize_name. Strips honorifics
// (Jr./Sr./II/III/IV/M.D./Ph.D./Esq./Dr.), drops periods, collapses commas
// and whitespace, lowercases. We need it here because the roster's Full_Name
// and the bill-sponsor endpoint's Full_Name disagree on where to put the
// suffix — roster says "Amato Jr., Carmen F." while bills say
// "Amato, Carmen F., Jr." — and the canonical form ("amato,carmen f")
// collapses that gap.
//
// Bare "V" is deliberately omitted from the alternation. Middle initials like
// "John V. Smith" are common; a 5th-generation suffix is not. Including "V"
// would silently strip every "V." middle initial and create false matches.
//
// IMPORTANT: if this regex changes, update the Python counterpart in lockstep
// or the active-legislator filter will silently miss matches.
const _HONORIFIC = /(?<!\w)(?:Jr|Sr|II|III|IV|M\.?\s*D|Ph\.?\s*D|Esq|Dr)\.?(?!\w)/gi;

export function canonicalizeName(name) {
  let n = (name || "").replace(_HONORIFIC, "");
  n = n.replace(/\./g, "");
  n = n.replace(/\s+/g, " ");
  n = n.replace(/\s*,\s*/g, ",");
  n = n.replace(/,+/g, ",");
  return n.replace(/^[\s,]+|[\s,]+$/g, "").toLowerCase();
}

const PARTY_LABEL = { D: "Democrat", R: "Republican", I: "Independent" };

// Small inline pill for the legislator's party affiliation. Renders only when
// the name resolves to a currently-seated legislator — historical sponsors
// who are no longer in the roster get no flag (we don't have party data for
// them). Returns "" when nothing to render so callers can concatenate freely.
export function partyFlagHtml(name, partyByCanon) {
  if (!partyByCanon || !partyByCanon.size) return "";
  const code = partyByCanon.get(canonicalizeName(name));
  if (!code) return "";
  const cls = /^[A-Z]$/.test(code) ? code : "X";  // guard against unexpected values
  const label = PARTY_LABEL[code] || code;
  return `<span class="party-flag party-flag--${cls}" title="${label}" aria-label="${label}">${escForAttr(code)}</span>`;
}

function escForAttr(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

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

export function renderSponsors(listEl, toggleEl, sponsors, opts = {}) {
  const {
    activeCanon = null,
    activeLabel = "Active",
    activeAriaLabel = "Currently serving",
    partyByCanon = null,
  } = opts;
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
    const isActive = activeCanon && activeCanon.has(canonicalizeName(s.name));
    const activeBadge = isActive
      ? `<span class="sponsor-active-badge" title="${esc(activeAriaLabel)}" aria-label="${esc(activeAriaLabel)}">${esc(activeLabel)}</span>`
      : "";
    const partyFlag = partyFlagHtml(s.name, partyByCanon);
    const nameHtml = s.bio_url
      ? `<a href="${esc(s.bio_url)}" rel="external noopener">${esc(s.name)}</a>`
      : esc(s.name);
    return `
      <li class="sponsor-row${isActive ? " sponsor-row--active" : ""}">
        <span class="sponsor-name">
          <span class="sponsor-name-line">
            <strong>${nameHtml}</strong>${partyFlag}${activeBadge}
          </span>
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
