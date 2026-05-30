import { LazyPlot } from './LazyPlot'
import { plotlyConfig } from '../../catalog/plotly'

export function PapiDecisionPlot({ evidence, activeIndex, selectedIndex, setHovered, plotTheme, states, copy }) {
  return (
    <LazyPlot
      className="plotly-chart"
      config={plotlyConfig}
      data={[
        {
          type: 'bar',
          orientation: 'h',
          x: evidence,
          y: states.map((state) => state.short),
          customdata: states.map((state) => [state.label, state.pattern]),
          marker: {
            // Navy for the active state, muted grey for the rest (Stage 4 —
            // recolor away from the per-state warm palette so the bars read as
            // a single decision chart, not a second lamp legend).
            color: states.map((_, index) =>
              index === activeIndex ? plotTheme.accent : plotTheme.track,
            ),
            line: {
              color: states.map((_, index) =>
                index === selectedIndex ? plotTheme.accent : 'rgba(0,0,0,0)',
              ),
              width: states.map((_, index) => (index === selectedIndex ? 3 : 0)),
            },
          },
          text: evidence.map((value) => `${value}%`),
          textposition: 'outside',
          hovertemplate:
            `<b>%{customdata[0]}</b><br>%{customdata[1]}<br>${copy.insights.evidence}: %{x}%<extra></extra>`,
        },
      ]}
      layout={{
        autosize: true,
        height: 400,
        margin: { l: 60, r: 40, t: 12, b: 40 },
        paper_bgcolor: plotTheme.paper,
        plot_bgcolor: plotTheme.plot,
        font: { color: plotTheme.text, family: 'Poppins, Segoe UI, sans-serif' },
        bargap: 0.34,
        xaxis: {
          range: [0, 100],
          ticksuffix: '%',
          gridcolor: plotTheme.grid,
          zeroline: false,
          fixedrange: true,
        },
        yaxis: {
          autorange: 'reversed',
          tickfont: { color: plotTheme.muted },
          fixedrange: true,
        },
        showlegend: false,
      }}
      onHover={(event) => setHovered(event.points[0].pointIndex)}
      onUnhover={() => setHovered(null)}
      useResizeHandler
    />
  )
}
