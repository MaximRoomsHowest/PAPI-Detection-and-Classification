import { describe, it, expect } from 'vitest'

import { axisTitle, basePlotLayout, baseAxisStyle, PLOT_FONT_FAMILY, PLOT_MONO_FAMILY } from './plotly'

// A representative plotTheme (the real one is computed from CSS vars at runtime).
const plotTheme = {
  paper: '#0b0f17',
  text: '#e8eef7',
  muted: '#8a97a8',
  grid: '#1d2733',
  accent: '#3b82f6',
}

describe('basePlotLayout', () => {
  it('supplies the shared paper/plot/font wrapper and merges overrides', () => {
    expect(basePlotLayout(plotTheme, { height: 320, showlegend: false })).toEqual({
      autosize: true,
      paper_bgcolor: '#0b0f17',
      plot_bgcolor: '#0b0f17',
      font: { color: '#e8eef7', family: PLOT_FONT_FAMILY },
      height: 320,
      showlegend: false,
    })
  })

  it('lets overrides win over the defaults', () => {
    expect(basePlotLayout(plotTheme, { autosize: false }).autosize).toBe(false)
  })
})

describe('baseAxisStyle', () => {
  it('defaults to fixedrange + muted mono ticks only', () => {
    expect(baseAxisStyle(plotTheme)).toEqual({
      fixedrange: true,
      tickfont: { color: '#8a97a8', family: PLOT_MONO_FAMILY },
    })
  })

  it('does NOT inject gridcolor unless asked (gridline-less x-axes stay clean)', () => {
    expect(baseAxisStyle(plotTheme)).not.toHaveProperty('gridcolor')
    expect(baseAxisStyle(plotTheme, { gridcolor: plotTheme.grid }).gridcolor).toBe('#1d2733')
  })

  it('a tickfont override fully replaces the default (e.g. to add a size)', () => {
    expect(
      baseAxisStyle(plotTheme, { tickangle: -25, tickfont: { color: plotTheme.muted, size: 11 } }),
    ).toEqual({
      fixedrange: true,
      tickangle: -25,
      tickfont: { color: '#8a97a8', size: 11 },
    })
  })
})

describe('axisTitle', () => {
  it('builds the muted 11px axis-title shape', () => {
    expect(axisTitle('Frame', plotTheme)).toEqual({
      text: 'Frame',
      font: { color: '#8a97a8', size: 11 },
    })
  })
})
