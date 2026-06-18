import { statusCopy } from './statusCatalog'

export const plotlyConfig = {
  responsive: true,
  displaylogo: false,
  modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
}

// Shared chart height. The client asked for larger, more readable charts (~380px);
// every insights chart reads this so the sizing never drifts again (audit D1/D2).
export const CHART_HEIGHT = 380

// Single source of truth for lamp STATE colours: re-exported from the status catalog
// so red/white/transition can never drift between the cards, pills, and charts
// (audit C5). `warn` is chart chrome (the amber outline on a white-bound marker), not
// a state colour, so it stays local.
export const plotlyPalette = {
  white: statusCopy.white.color,
  red: statusCopy.red.color,
  transition: statusCopy.transition.color,
  // The two muted "no real detection" states, single-sourced from statusCopy so charts
  // can't drift from the cards: obscured = detector found nothing, unknown = occluded tone.
  obscured: statusCopy.obscured.color,
  unknown: statusCopy.occluded.color,
  warn: '#f0a22f',
}

// Lamp-IDENTITY palette (which physical lamp, 1..4) — deliberately distinct from the
// state colours above so a series colour is never read as a red/white/transition
// state. Okabe-Ito: colour-vision-deficiency-safe and theme-independent (audit B3).
export const LAMP_COLORS = ['#0072B2', '#E69F00', '#009E73', '#CC79A7']

// Neutral palette for arbitrary multi-series charts (e.g. one line per analysed
// flight/sequence). Kept SEPARATE from LAMP_COLORS so a sequence line is never the
// same colour as a "Light N" lamp identity in an adjacent card (readability audit).
export const SEQUENCE_COLORS = ['#5b6b7b', '#2f6fed', '#8a5cf6', '#0e8a6e', '#b8702f', '#9aa5b1']

// Shared layout/axis builders for the insights charts. Every chart repeated the same
// paper/plot/font wrapper and the same fixedrange + muted-tick axis defaults; these
// centralise that. They are behaviour-preserving: callers spread the result and add
// their chart-specific fields (height, margin, ranges, titles, ...) as overrides.
export const PLOT_FONT_FAMILY = '"Geist Variable", "Geist", Segoe UI, sans-serif'

// Axis ticks are almost always numbers (angles, frames, percentages), so they
// render in the cockpit mono to match every other value of record in the UI.
export const PLOT_MONO_FAMILY = '"Geist Mono Variable", "Geist Mono", ui-monospace, monospace'

export function basePlotLayout(plotTheme, overrides = {}) {
  return {
    autosize: true,
    paper_bgcolor: plotTheme.paper,
    plot_bgcolor: plotTheme.paper,
    font: { color: plotTheme.text, family: PLOT_FONT_FAMILY },
    ...overrides,
  }
}

// Axis fields shared by every chart axis (fixedrange + muted ticks). Pass axis-specific
// fields (gridcolor, title, range, dtick, ...) as overrides; note `gridcolor` is added
// only where it belongs, since several x-axes intentionally have no gridlines. A
// `tickfont` override fully replaces the default (e.g. to add a size).
export function baseAxisStyle(plotTheme, overrides = {}) {
  return {
    fixedrange: true,
    tickfont: { color: plotTheme.muted, family: PLOT_MONO_FAMILY },
    ...overrides,
  }
}

// The repeated muted 11px axis-title shape.
export function axisTitle(text, plotTheme) {
  return { text, font: { color: plotTheme.muted, size: 11 } }
}

// Readable integer-count axis ticks at ANY scale (audit B8): explicit 1-spacing for
// small ranges (so a 0..3 axis isn't 0,0,1,1 fractional dupes), and Plotly's nice
// integer-formatted auto-ticks for large ranges (so a 0..3000 axis isn't a wall of
// `dtick:1` labels). Spread onto a y-axis: `...integerTicks(maxCount)`.
export function integerTicks(maxValue) {
  const max = Number.isFinite(maxValue) ? maxValue : 0
  return max > 0 && max <= 10 ? { dtick: 1, tickformat: ',d' } : { tickformat: ',d' }
}

// The "white" lamp-state fill is near-white; on a near-white card it needs a visible
// outline (+ a faint cream fill) so "reached white" — the state the engineer checks —
// is never the least-visible mark on the chart (readability audit P0-B).
export const WHITE_FILL = '#eef2f8'
export const WHITE_OUTLINE = '#8a94a6'

// Direct value labels for low-cardinality bars: the PDF export is static (no hover), so
// a <=6-category bar must print its values or it exports as a label-less shape — data
// loss on the page's primary deliverable (readability audit). Spread onto a bar trace:
// `...barValueLabels(values)`.
export function barValueLabels(values, plotTheme) {
  return {
    text: values.map((value) => (Number.isFinite(value) ? String(value) : '')),
    textposition: 'outside',
    textfont: { color: plotTheme?.muted, size: 11 },
    cliponaxis: false,
  }
}
