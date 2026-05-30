// Renders the "on the move" panel: ceremonial bills that advanced (committee,
// floor, governor, transfer, other) inside the recent date window written by
// scraper/movement.py. Hidden entirely when no events landed in the window.
//
// The panel is purely informational — it does not react to the explore-section
// filter state, since it describes what the legislature did that week.

// Bucket display labels and ordering. Governor actions first (most consequential),
// then floor, committee, transfer, anything else.
const BUCKETS = [
  { key: "governor",  label: "Governor's desk" },
  { key: "floor",     label: "Passed a chamber" },
  { key: "committee", label: "Reported from committee" },
  { key: "transfer",  label: "Sent to the other chamber" },
  { key: "other",     label: "Other movement" },
];

export function renderMovement(container, movement) {
  if (!container) return;

  const events = (movement && movement.events) || [];
  if (!events.length) {
    container.hidden = true;
    return;
  }
  container.hidden = false;

  const grouped = groupByBucket(events);
  const windowText = formatWindow(movement.window_start, movement.window_end);
  const noun = events.length === 1 ? "ceremonial bill or resolution" : "ceremonial bills and resolutions";

  const sections = BUCKETS
    .filter(b => grouped[b.key] && grouped[b.key].length)
    .map(b => renderSection(b, grouped[b.key]))
    .join("");

  container.innerHTML = `
    <h3 class="movement-heading">On the move</h3>
    <p class="movement-lede">
      <strong>${events.length}</strong> ${noun} ${windowText}.
    </p>
    ${sections}
  `;
}

function groupByBucket(events) {
  const out = {};
  for (const e of events) {
    (out[e.bucket] = out[e.bucket] || []).push(e);
  }
  return out;
}

function renderSection(bucket, events) {
  const items = events.map(e => `
    <li class="movement-item">
      <div class="movement-item-head">
        <a class="movement-bill" href="${esc(e.url)}" rel="external noopener">${esc(e.full_number)}</a>
        <span class="movement-date">${formatShortDate(e.action_date)}</span>
      </div>
      <p class="movement-action">${esc(e.action)}</p>
      <p class="movement-synopsis">${esc(e.synopsis || "")}</p>
    </li>
  `).join("");

  return `
    <section class="movement-bucket">
      <h4 class="movement-bucket-heading">${esc(bucket.label)} <span class="movement-bucket-count">(${events.length})</span></h4>
      <ul class="movement-list">${items}</ul>
    </section>
  `;
}

function formatWindow(start, end) {
  // "this week" reads better than spelling out the dates when the window is
  // the standard 7 days, but we always render the actual range so a reader
  // can verify when a missed cron makes the window stale.
  if (!start || !end) return "this week";
  const startD = parseISO(start);
  const endD = parseISO(end);
  if (!startD || !endD) return "this week";
  const fmt = { month: "short", day: "numeric" };
  return `between ${startD.toLocaleDateString(undefined, fmt)} and ${endD.toLocaleDateString(undefined, fmt)}`;
}

function formatShortDate(iso) {
  const d = parseISO(iso);
  if (!d) return "";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function parseISO(iso) {
  if (!iso) return null;
  // Construct as local-time midnight to avoid the UTC-vs-ET off-by-one that
  // makes "5/24" render as "May 23" in Eastern time zones.
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d);
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
