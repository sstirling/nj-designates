// Thin wrapper around Observable Plot, loaded from a CDN ESM.
//
// We load Plot lazily so the first render (table + filters) isn't blocked
// by the charting library. If the CDN fails, the table still works.

let _Plot = null;

async function getPlot() {
  if (_Plot) return _Plot;
  try {
    _Plot = await import("https://cdn.jsdelivr.net/npm/@observablehq/plot@0.6.17/+esm");
    return _Plot;
  } catch (e) {
    console.warn("Chart library failed to load; charts disabled.", e);
    return null;
  }
}

// Keep in sync with --cat-* CSS variables. ColorBrewer Set2, a softer,
// brighter palette than Dark2. Chart bars are decorative fills so the
// "text-contrast" constraint doesn't apply here.
const CAT_COLORS = {
  state_symbol:       "#66c2a5",
  holiday_observance: "#fc8d62",
  road_naming:        "#8da0cb",
  place_naming:       "#e78ac3",
  other_ceremonial:   "#b3b3b3",
};

const CAT_LABELS = {
  state_symbol: "State symbols",
  holiday_observance: "Holidays & observances",
  road_naming: "Road namings",
  place_naming: "Place namings",
  other_ceremonial: "Other",
};

export async function renderSessionChart(host, bills) {
  const Plot = await getPlot();
  if (!Plot) {
    host.innerHTML = '<p class="chart-dek">Chart unavailable — the filter and table above still work.</p>';
    return;
  }

  const data = bills.map(b => ({
    session: b.session_label,
    sessionSort: Number(b.session),
    category: b.primary_category,
    categoryLabel: CAT_LABELS[b.primary_category] || b.primary_category,
  }));

  const width = host.getBoundingClientRect().width || 800;

  const fig = Plot.plot({
    width,
    height: 320,
    marginLeft: 48,
    marginBottom: 48,
    style: {
      background: "transparent",
      fontFamily: "Inter, system-ui, sans-serif",
      fontSize: "12px",
    },
    x: {
      label: "Session",
      tickRotate: -30,
      domain: [...new Set(data.map(d => d.session))].sort((a, b) => Number(a.slice(0, 4)) - Number(b.slice(0, 4))),
    },
    y: { label: "Bills introduced", grid: true },
    color: {
      domain: Object.keys(CAT_COLORS),
      range: Object.values(CAT_COLORS),
      legend: true,
      tickFormat: d => CAT_LABELS[d] || d,
      label: "Category",
    },
    marks: [
      Plot.barY(data, Plot.groupX(
        { y: "count" },
        { x: "session", fill: "category", order: Object.keys(CAT_COLORS),
          tip: true, title: d => `${d.session}\n${CAT_LABELS[d.category]}` }
      )),
      Plot.ruleY([0]),
    ],
  });

  host.replaceChildren(fig);
}
