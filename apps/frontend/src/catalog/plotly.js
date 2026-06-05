export const plotlyConfig = {
  responsive: true,
  displaylogo: false,
  modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
}

export const plotlyPalette = {
  white: '#f8fbff',
  red: '#ff4545',
  transition: '#ffb11f',
  warn: '#f0a22f',
}

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
