// Monochrome line-art SVG icons for each bill category. Inline strings so
// they inherit the current text color and scale cleanly without network
// requests. All icons are 24x24 with 1.75px stroke weight for consistency.
//
// Decorative by default (aria-hidden). Pass `label` to the builder when the
// icon stands alone without accompanying text.

const WRAP = (body) => `
  <svg viewBox="0 0 24 24" width="1em" height="1em" aria-hidden="true"
       fill="none" stroke="currentColor" stroke-width="1.75"
       stroke-linecap="round" stroke-linejoin="round">
    ${body}
  </svg>
`;

// Ribbon-wrapped five-point star — the "official seal" icon.
const STATE_SYMBOL = WRAP(`
  <path d="M12 3l2.3 4.7 5.2.7-3.8 3.7.9 5.2L12 14.9 7.4 17.3l.9-5.2-3.8-3.7 5.2-.7L12 3z"/>
  <path d="M7 19l1-2M17 19l-1-2" opacity="0.55"/>
`);

// Calendar page with a circled date.
const HOLIDAY = WRAP(`
  <rect x="3.5" y="5" width="17" height="15.5" rx="1.5"/>
  <path d="M3.5 9.5h17"/>
  <path d="M8 3v4M16 3v4"/>
  <circle cx="12" cy="15" r="2.5"/>
`);

// Highway shield — a US-style route marker.
const ROAD = WRAP(`
  <path d="M5.5 4h13l-0.4 10.5c-0.2 2.3-3 4.5-6.1 5.5
           c-3.1-1-5.9-3.2-6.1-5.5L5.5 4z"/>
  <path d="M8 10h8M8 13.5h8"/>
`);

// Classical civic building with a pediment and columns.
const PLACE = WRAP(`
  <path d="M3 20.5h18"/>
  <path d="M5 20.5V10M9 20.5V10M15 20.5V10M19 20.5V10"/>
  <path d="M3 10h18"/>
  <path d="M3 10l9-6 9 6"/>
  <path d="M11 4.5h2"/>
`);

// Simple dot for the "other" category — quieter than the categorized icons.
const OTHER = WRAP(`
  <circle cx="12" cy="12" r="3.5"/>
  <circle cx="12" cy="12" r="8.5" opacity="0.4"/>
`);

const ICONS = {
  state_symbol: STATE_SYMBOL,
  holiday_observance: HOLIDAY,
  road_naming: ROAD,
  place_naming: PLACE,
  other_ceremonial: OTHER,
};

export function iconFor(category) {
  return ICONS[category] || "";
}
