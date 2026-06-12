import { Fragment, memo, useMemo } from 'react'
import { ArrowLeftRight, Check, Crosshair, TriangleAlert } from 'lucide-react'
import { LazyPlot } from './LazyPlot'
import { AngleEmptyState } from './AngleEmptyState'
import {
  axisTitle,
  basePlotLayout,
  baseAxisStyle,
  plotlyConfig,
  plotlyPalette,
  LAMP_COLORS,
  WHITE_FILL,
} from '../../catalog/plotly'
import {
  FAA_DEFAULT_SET_ANGLES_DEG,
  STATE_BAND_CODES,
  stateBandSeries,
  transitionAngleSummary,
} from '../../lib/insightsTransforms'
import { degrees } from '../../lib/format'

// Transition surfaces for video / folder-sequence analyses, in order of value:
// 1. Measured transition angle per light — THE commissioning number: where each
//    lamp actually crossed red<->white, with its blend zone, against the FAA
//    default set angles (labelled as defaults; commissioned values pending).
// 2. Lamp state bands — what every lamp showed at every frame (flicker reads as
//    thin stripes in the blend zone), with the raw flip markers on top.
// 3. The per-event table, grouped per light.
// Every value comes from the backend's transitions[] / angle_track[] — nothing
// is fabricated: a field a given method doesn't produce shows "—".
const LANE_COUNT = 4

const clampLamp = (lampIndex) => Math.min(Math.max(lampIndex, 1), LANE_COUNT)

// Which method(s) produced these events, for the provenance badge (audit C3).
function methodLabel(transitions, copy) {
  const methods = [...new Set(transitions.map((event) => event.method ?? 'tracking'))]
  if (methods.length !== 1) {
    return copy.insights.transitionMethodMixed
  }
  const label = methods[0] === 'model' ? copy.live.transitionMethodModel : copy.live.transitionMethodTracking
  return copy.live.transitionMethodUsed.replace('{method}', label)
}

function eventHover(event, copy) {
  const lampIndex = clampLamp(event.lamp_index)
  const fromLabel = copy.status?.[event.from_state] ?? event.from_state
  const toLabel = copy.status?.[event.to_state] ?? event.to_state
  const lines = [
    `${copy.live.light} ${lampIndex}`,
    `${copy.insights.thFrame} ${event.frame_index}`,
    `${fromLabel} → ${toLabel}`,
  ]
  if (Number.isFinite(event.elevation_angle_deg)) {
    lines.push(degrees(event.elevation_angle_deg))
  }
  if (Number.isFinite(event.duration_frames)) {
    lines.push(`${copy.insights.thDuration}: ${event.duration_frames}`)
  }
  return lines.join('<br>')
}

// One marker trace per direction, distinguished by marker SYMBOL (not colour alone),
// so direction survives greyscale / the static PDF export / colour-vision deficiency,
// and a real legend explains it (audit B4).
function directionTrace(events, { symbol, fill, outline, name }, copy) {
  return {
    type: 'scatter',
    mode: 'markers',
    name,
    x: events.map((event) => event.frame_index),
    y: events.map((event) => `${copy.live.light} ${clampLamp(event.lamp_index)}`),
    text: events.map((event) => eventHover(event, copy)),
    hovertemplate: '%{text}<extra></extra>',
    marker: { size: 11, symbol, color: fill, line: { color: outline, width: 1.6 } },
  }
}

// --- 1. Measured transition angle per light ----------------------------------

const TransitionAngleChart = memo(function TransitionAngleChart({ summary, plotTheme, copy }) {
  const measured = summary.filter((entry) => entry.settledAngle !== null || entry.bandMin !== null)

  const { data, layout } = useMemo(() => {
    const labels = measured.map((entry) => `${copy.live.light} ${entry.lampIndex}`)
    // Dot = the settled crossing (same value as the redness charts' dashed line).
    // A light with flips but no settled crossing gets an open marker on its band
    // midpoint so the evidence still shows without claiming a crossing.
    const xs = measured.map((entry) =>
      entry.settledAngle ?? (entry.bandMin + entry.bandMax) / 2,
    )
    const hover = measured.map((entry) => {
      const lines = [`${copy.live.light} ${entry.lampIndex}`]
      if (entry.settledAngle !== null) {
        lines.push(`${copy.insights.measuredAngleLabel}: ${degrees(entry.settledAngle)}`)
      }
      if (entry.bandMin !== null) {
        lines.push(`${copy.insights.blendZoneLabel}: ${degrees(entry.bandMin)} – ${degrees(entry.bandMax)}`)
      }
      lines.push(copy.insights.flipsLabel.replace('{n}', entry.flips))
      return lines.join('<br>')
    })

    const angles = [
      ...xs,
      ...measured.flatMap((entry) => (entry.bandMin !== null ? [entry.bandMin, entry.bandMax] : [])),
      ...FAA_DEFAULT_SET_ANGLES_DEG,
    ]
    const xMin = Math.min(...angles) - 0.2
    const xMax = Math.max(...angles) + 0.2

    return {
      data: [
        {
          type: 'scatter',
          mode: 'markers',
          x: xs,
          y: labels,
          text: hover,
          hovertemplate: '%{text}<extra></extra>',
          marker: {
            size: 13,
            symbol: measured.map((entry) => (entry.settledAngle !== null ? 'circle' : 'circle-open')),
            color: measured.map((entry) => LAMP_COLORS[(entry.lampIndex - 1) % LAMP_COLORS.length]),
            line: { color: plotTheme.paper, width: 1.5 },
          },
          // Whiskers span the blend zone: the lowest..highest angle at which the
          // tracker logged ANY flip for this light.
          error_x: {
            type: 'data',
            symmetric: false,
            array: measured.map((entry, i) => (entry.bandMax !== null ? entry.bandMax - xs[i] : 0)),
            arrayminus: measured.map((entry, i) => (entry.bandMin !== null ? xs[i] - entry.bandMin : 0)),
            color: plotTheme.muted,
            thickness: 1.4,
            width: 7,
          },
          showlegend: false,
        },
      ],
      layout: basePlotLayout(plotTheme, {
        height: 300,
        margin: { l: 78, r: 16, t: 26, b: 48 },
        xaxis: baseAxisStyle(plotTheme, {
          title: axisTitle(copy.insights.thAngle, plotTheme),
          range: [xMin, xMax],
          gridcolor: plotTheme.grid,
          zeroline: false,
        }),
        yaxis: baseAxisStyle(plotTheme, {
          categoryorder: 'array',
          categoryarray: [...labels].reverse(),
          gridcolor: plotTheme.grid,
        }),
        // FAA defaults as labelled reference lines — sorted values against sorted
        // measurements, never slot-by-slot (the image lamp order flips with the
        // approach direction and EDNY's commissioned values are unconfirmed).
        shapes: FAA_DEFAULT_SET_ANGLES_DEG.map((angle) => ({
          type: 'line',
          xref: 'x',
          yref: 'paper',
          x0: angle,
          x1: angle,
          y0: 0,
          y1: 1,
          line: { color: plotTheme.muted, width: 1, dash: 'dot' },
          opacity: 0.55,
        })),
        annotations: [
          {
            xref: 'x',
            yref: 'paper',
            x: FAA_DEFAULT_SET_ANGLES_DEG[FAA_DEFAULT_SET_ANGLES_DEG.length - 1],
            y: 1.04,
            text: copy.insights.faaReferenceLabel,
            showarrow: false,
            font: { color: plotTheme.muted, size: 11 },
            xanchor: 'right',
          },
        ],
      }),
    }
  }, [measured, plotTheme, copy])

  if (!measured.length) {
    return (
      <AngleEmptyState
        icon={<Crosshair size={26} aria-hidden="true" />}
        message={copy.insights.transitionNone}
      />
    )
  }

  return (
    <LazyPlot
      className="plotly-chart"
      config={plotlyConfig}
      data={data}
      copy={copy}
      ariaLabel={copy.insights.transitionAngleTitle}
      layout={layout}
      useResizeHandler
    />
  )
})

// --- 2. Lamp state bands -------------------------------------------------------

// Discrete colour per state code (insightsTransforms.STATE_BAND_CODES order).
const BAND_COLORS = [
  'rgba(127, 135, 148, 0.12)', // unknown: faint neutral — "not seen this frame"
  '#9aa5b1', // obscured
  plotlyPalette.red,
  plotlyPalette.transition,
  WHITE_FILL,
]

// Plotly discrete colorscale: code k owns the band [k/5, (k+1)/5) with
// zmin/zmax pinned to -0.5..4.5 so cell colours never interpolate.
const BAND_COLORSCALE = BAND_COLORS.flatMap((color, code) => [
  [code / BAND_COLORS.length, color],
  [(code + 1) / BAND_COLORS.length, color],
])

const StateBandsChart = memo(function StateBandsChart({ block, transitions, plotTheme, copy }) {
  const laneLabels = useMemo(
    () => Array.from({ length: LANE_COUNT }, (_, i) => `${copy.live.light} ${i + 1}`),
    [copy.live.light],
  )

  const data = useMemo(() => {
    // Heatmap rows must match the reversed category order (Light 1 on top).
    const reversedLabels = [...laneLabels].reverse()
    const reversedZ = [...block.z].reverse()
    const customdata = reversedZ.map((row) =>
      row.map((code, column) => {
        const stateKey = STATE_BAND_CODES[code]
        const stateLabel = copy.status?.[stateKey] ?? stateKey
        const angle = block.angles[column]
        return Number.isFinite(angle) ? `${stateLabel} · ${degrees(angle)}` : stateLabel
      }),
    )
    const bands = {
      type: 'heatmap',
      x: block.frames,
      y: reversedLabels,
      z: reversedZ,
      zmin: -0.5,
      zmax: BAND_COLORS.length - 0.5,
      colorscale: BAND_COLORSCALE,
      showscale: false,
      xgap: 0,
      ygap: 4,
      customdata,
      hovertemplate: `%{y}<br>${copy.insights.thFrame} %{x}<br>%{customdata}<extra></extra>`,
    }
    const toWhite = transitions.filter((event) => event.to_state === 'white')
    const toRed = transitions.filter((event) => event.to_state !== 'white')
    return [
      bands,
      directionTrace(
        toWhite,
        { symbol: 'triangle-up', fill: plotlyPalette.white, outline: plotlyPalette.red, name: copy.insights.dirToWhite },
        copy,
      ),
      directionTrace(
        toRed,
        { symbol: 'triangle-down', fill: plotlyPalette.red, outline: plotlyPalette.warn, name: copy.insights.dirToRed },
        copy,
      ),
    ]
  }, [block, transitions, laneLabels, copy])

  return (
    <>
      <LazyPlot
        className="plotly-chart"
        config={plotlyConfig}
        data={data}
        copy={copy}
        ariaLabel={copy.insights.stateBandsTitle}
        layout={basePlotLayout(plotTheme, {
          height: 320,
          margin: { l: 78, r: 16, t: 10, b: 56 },
          legend: { orientation: 'h', x: 0.5, y: -0.18, xanchor: 'center', font: { color: plotTheme.muted, size: 11 } },
          xaxis: baseAxisStyle(plotTheme, {
            title: axisTitle(copy.insights.thFrame, plotTheme),
            gridcolor: plotTheme.grid,
            zeroline: false,
          }),
          yaxis: baseAxisStyle(plotTheme, {
            categoryorder: 'array',
            categoryarray: [...laneLabels].reverse(),
          }),
          showlegend: true,
        })}
        useResizeHandler
      />
      {/* The heatmap has no Plotly legend — plain chips name the band colours. */}
      <div className="band-legend" aria-hidden="true">
        {STATE_BAND_CODES.map((stateKey, code) => (
          <span key={stateKey} className="band-legend__chip">
            <span className="band-legend__swatch" style={{ '--band-color': BAND_COLORS[code] }} />
            {copy.status?.[stateKey] ?? stateKey}
          </span>
        ))}
      </div>
    </>
  )
})

// --- 3. Per-event table ----------------------------------------------------------

function TransitionTable({ transitions, summary, copy }) {
  // Group per light; within a group read in frame order so a clean ascending
  // sweep reads top-to-bottom (audit P1-C).
  const groups = [1, 2, 3, 4]
    .map((lampIndex) => ({
      lampIndex,
      events: transitions
        .filter((event) => event.lamp_index === lampIndex)
        .sort((a, b) => a.frame_index - b.frame_index),
      summary: summary[lampIndex - 1],
    }))
    .filter((group) => group.events.length > 0)
  // The duration column only carries data for "model" events — for a
  // tracking-only session it was a full column of "—", so it is gated out.
  const hasModelEvents = transitions.some((event) => event.method === 'model')
  const columnCount = hasModelEvents ? 5 : 4

  return (
    <div className="transition-table-wrap">
      <table className="transition-table" aria-labelledby="transition-table-heading">
        <thead>
          <tr>
            <th className="num">{copy.insights.thAngle}</th>
            <th>{copy.insights.thDirection}</th>
            <th className="num">{copy.insights.thFrame}</th>
            {hasModelEvents && <th className="num">{copy.insights.thDuration}</th>}
            <th>{copy.insights.thStatus}</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => {
            const zone =
              group.summary.bandMin !== null
                ? `${degrees(group.summary.bandMin)} – ${degrees(group.summary.bandMax)}`
                : '—'
            return (
              <Fragment key={group.lampIndex}>
                <tr className="transition-group-row">
                  <th scope="rowgroup" colSpan={columnCount}>
                    {`${copy.live.light} ${group.lampIndex} · `}
                    {copy.insights.flipsSummary
                      .replace('{flips}', group.events.length)
                      .replace('{zone}', zone)}
                  </th>
                </tr>
                {group.events.map((event, index) => {
                  const isModel = event.method === 'model'
                  // On an ascending sweep red→white is the expected climb-through; a →red
                  // flip is a reversal worth flagging (audit P1-C).
                  const climbThrough = event.to_state === 'white'
                  const statusLabel = climbThrough ? copy.insights.statusClimb : copy.insights.statusReversal
                  return (
                    <tr key={`${group.lampIndex}-${event.frame_index}-${index}`}>
                      <td className="num mono tnum">{degrees(event.elevation_angle_deg)}</td>
                      <td className="direction-cell">
                        <span className={`state-pill is-${event.from_state}`}>
                          {copy.status?.[event.from_state] ?? event.from_state}
                        </span>
                        <span className="dir-arrow" aria-hidden="true">→</span>
                        {isModel && (
                          <>
                            <span className="state-pill is-transition">{copy.status?.transition ?? 'transition'}</span>
                            <span className="dir-arrow" aria-hidden="true">→</span>
                          </>
                        )}
                        <span className={`state-pill is-${event.to_state}`}>
                          {copy.status?.[event.to_state] ?? event.to_state}
                        </span>
                      </td>
                      <td className="num mono tnum">{event.frame_index}</td>
                      {hasModelEvents && (
                        <td className="num mono tnum">
                          {Number.isFinite(event.duration_frames) ? event.duration_frames : '—'}
                        </td>
                      )}
                      <td>
                        <span
                          className={`transition-status ${climbThrough ? 'is-ok' : 'is-warn'}`}
                          role="img"
                          aria-label={statusLabel}
                          title={statusLabel}
                        >
                          {climbThrough ? <Check size={15} aria-hidden="true" /> : <TriangleAlert size={15} aria-hidden="true" />}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </Fragment>
            )
          })}
        </tbody>
      </table>
      <p className="viz-footnote">{copy.insights.transitionTableFootnote}</p>
    </div>
  )
}

export function TransitionCharts({ backendResults, plotTheme, copy }) {
  const transitions = useMemo(() => {
    const all = []
    for (const result of backendResults ?? []) {
      for (const event of result?.transitions ?? []) {
        // Single source of truth for lamp identity: drop events outside 1..4 here so the
        // angle chart, state bands, and table all operate on the same validated set.
        if (Number.isInteger(event?.lamp_index) && event.lamp_index >= 1 && event.lamp_index <= LANE_COUNT) {
          all.push(event)
        }
      }
    }
    return all
  }, [backendResults])

  const summary = useMemo(() => transitionAngleSummary(backendResults ?? []), [backendResults])
  const bandBlocks = useMemo(() => stateBandSeries(backendResults ?? []), [backendResults])
  const provenance = useMemo(() => (transitions.length ? methodLabel(transitions, copy) : ''), [transitions, copy])

  if (!transitions.length && !bandBlocks.length) {
    return (
      <article className="viz-card">
        <div className="viz-heading">
          <Crosshair size={18} />
          <div>
            <h3>{copy.insights.transitionAngleTitle}</h3>
            <p>{copy.insights.transitionAngleText}</p>
          </div>
        </div>
        <AngleEmptyState
          icon={<ArrowLeftRight size={26} aria-hidden="true" />}
          message={copy.insights.transitionNone}
        />
      </article>
    )
  }

  return (
    <>
      <article className="viz-card span-all">
        <div className="viz-heading">
          <Crosshair size={18} />
          <div>
            <h3>{copy.insights.transitionAngleTitle}</h3>
            <p>{copy.insights.transitionAngleText}</p>
          </div>
          {provenance ? <span className="client-tag method-tag">{provenance}</span> : null}
        </div>
        <TransitionAngleChart summary={summary} plotTheme={plotTheme} copy={copy} />
      </article>

      {bandBlocks.map((block) => (
        <article className="viz-card span-all" key={block.label}>
          <div className="viz-heading">
            <ArrowLeftRight size={18} />
            <div>
              <h3>{copy.insights.stateBandsTitle}</h3>
              <p>
                {copy.insights.stateBandsText}
                {bandBlocks.length > 1 ? ` — ${block.label}` : ''}
              </p>
            </div>
          </div>
          <StateBandsChart block={block} transitions={transitions} plotTheme={plotTheme} copy={copy} />
        </article>
      ))}

      {transitions.length > 0 && (
        <article className="viz-card transition-table-card span-all">
          <div className="viz-heading">
            <ArrowLeftRight size={18} />
            <div>
              <h3 id="transition-table-heading">{copy.insights.transitionTableTitle}</h3>
              <p>{copy.insights.transitionTableText}</p>
            </div>
          </div>
          <TransitionTable transitions={transitions} summary={summary} copy={copy} />
        </article>
      )}
    </>
  )
}
