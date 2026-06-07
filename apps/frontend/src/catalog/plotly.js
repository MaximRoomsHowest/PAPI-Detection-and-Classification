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
  warn: '#f0a22f',
}

// Lamp-IDENTITY palette (which physical lamp, 1..4) — deliberately distinct from the
// state colours above so a series colour is never read as a red/white/transition
// state. Okabe-Ito: colour-vision-deficiency-safe and theme-independent (audit B3).
export const LAMP_COLORS = ['#0072B2', '#E69F00', '#009E73', '#CC79A7']

// Shared layout/axis builders for the insights charts. Every chart repeated the same
// paper/plot/font wrapper and the same fixedrange + muted-tick axis defaults; these
// centralise that. They are behaviour-preserving: callers spread the result and add
// their chart-specific fields (height, margin, ranges, titles, ...) as overrides.
export const PLOT_FONT_FAMILY = 'Poppins, Segoe UI, sans-serif'

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
    tickfont: { color: plotTheme.muted },
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
