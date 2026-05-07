// Two informational surfaces driven by recent legislative activity:
//
//   - renderTicker: a horizontal scrolling marquee of the most recently
//     active bills in the current session. Uses ldoa (last date of action),
//     so it surfaces both new introductions and old bills that just got
//     voted on or signed.
//
//   - renderWhatsNew: a callout block reporting how many bills were added
//     to the dataset in the latest refresh. Uses first_seen, populated by
//     the scraper. Gracefully hides when the field isn't there yet (e.g.
//     before the first refresh after this feature ships).
//
// Neither reacts to the explore-section filter state — they describe the
// dataset itself, not the user's current view.

const TICKER_LIMIT = 20;

export function renderTicker(container, bills, meta) {
  if (!container) return;

  const currentSession = String(meta?.latest_session ?? "");
  const recent = bills
    .filter(b => b.session === currentSession && b.ldoa)
    .sort((a, b) => (a.ldoa < b.ldoa ? 1 : -1))
    .slice(0, TICKER_LIMIT);

  if (!recent.length) {
    container.hidden = true;
    return;
  }
  container.hidden = false;

  // The track is duplicated so a CSS translateX(-50%) loops seamlessly.
  // The duplicate is hidden from assistive tech to avoid double-reading.
  const items = recent.map(itemHtml).join('<span class="ticker-sep" aria-hidden="true">·</span>');
  container.innerHTML = `
    <span class="ticker-label" aria-hidden="true">Wire</span>
    <div class="ticker-viewport">
      <div class="ticker-track">
        <div class="ticker-row">${items}</div>
        <div class="ticker-row" aria-hidden="true">${items}</div>
      </div>
    </div>
  `;
}

function itemHtml(b) {
  const num = esc(b.full_number);
  const url = esc(b.url);
  const synopsis = truncate(b.synopsis || "", 110);
  return `<span class="ticker-item">
    <a class="ticker-bill" href="${url}" rel="external noopener">${num}</a>
    <span class="ticker-synopsis">${esc(synopsis)}</span>
  </span>`;
}

export function renderWhatsNew(container, bills, meta) {
  if (!container) return;

  // Hide entirely until the scraper has run at least once with this feature.
  // The field arrives in meta.json on the first weekly refresh after deploy.
  const added = meta?.added_this_refresh;
  if (added === undefined || added === null) {
    container.hidden = true;
    return;
  }
  container.hidden = false;

  const since = formatRefreshDate(meta?.previous_refresh_at);
  const sinceText = since ? ` since ${since}` : "";

  if (added === 0) {
    container.innerHTML = `
      <h3 class="whats-new-heading">What's new</h3>
      <p class="whats-new-empty">
        No new ceremonial bills${sinceText}. The legislature briefly rested.
      </p>
    `;
    return;
  }

  const today = (meta.updated_at || "").slice(0, 10);
  const newBills = bills
    .filter(b => b.first_seen === today)
    .sort((a, b) => (a.ldoa < b.ldoa ? 1 : -1));

  const list = newBills.map(b => `
    <li class="whats-new-item">
      <a class="whats-new-bill" href="${esc(b.url)}" rel="external noopener">${esc(b.full_number)}</a>
      <span class="whats-new-synopsis">${esc(b.synopsis || "")}</span>
    </li>
  `).join("");

  const noun = added === 1 ? "new ceremonial bill" : "new ceremonial bills";
  container.innerHTML = `
    <h3 class="whats-new-heading">What's new</h3>
    <p class="whats-new-lede">
      <strong>${added.toLocaleString()}</strong> ${noun}${sinceText}.
    </p>
    <ul class="whats-new-list">${list}</ul>
  `;
}

function formatRefreshDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, { month: "long", day: "numeric" });
  } catch {
    return "";
  }
}

function truncate(s, n) {
  if (!s || s.length <= n) return s;
  return s.slice(0, n - 1).trimEnd() + "…";
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
