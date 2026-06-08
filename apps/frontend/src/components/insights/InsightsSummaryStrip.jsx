import { degrees } from '../../lib/format'
import { InlineMetric } from '../InlineMetric'

// At-a-glance header strip (the verdict layer). Rendered OUTSIDE the tabs so it shows on
// both tabs and isn't parked off-screen with an inactive force-mounted panel. It states
// what the session found and whether to trust it — deliberately NO pass/fail verdict,
// which needs the commissioned set-angles (not on the frontend yet); the honest headline
// is "transitions on N/4 lamps, commissioned comparison pending".
export function InsightsSummaryStrip({ summary, copy }) {
  if (!summary || summary.analysisCount === 0) {
    return null
  }
  const {
    lampsCrossed,
    totalLamps,
    elevationMin,
    elevationMax,
    frameCount,
    hasAngles,
    anglePlausible,
    angleSource,
    maxUncertaintyDeg,
  } = summary
  const elevationText = hasAngles ? `${degrees(elevationMin)}–${degrees(elevationMax)}` : '—'
  const trustWarn = hasAngles && !anglePlausible
  const trustText = !hasAngles
    ? copy.insights.trustNoAngle
    : !anglePlausible
      ? copy.insights.trustImplausible
      : [
          angleSource ? angleSource.toUpperCase() : null,
          Number.isFinite(maxUncertaintyDeg) ? `±${maxUncertaintyDeg.toFixed(2)}°` : null,
        ]
          .filter(Boolean)
          .join(' · ') || copy.insights.trustOk
  const verdict = copy.insights.summaryVerdict
    .replace('{n}', String(lampsCrossed))
    .replace('{total}', String(totalLamps))
  return (
    <div className="insights-summary" role="group" aria-label={copy.insights.summaryLabel}>
      <div className="insights-summary__tiles">
        <InlineMetric label={copy.insights.summaryLampsCrossed} value={`${lampsCrossed} / ${totalLamps}`} />
        <InlineMetric label={copy.insights.summaryElevation} value={elevationText} />
        <InlineMetric label={copy.insights.summaryFrames} value={frameCount} />
        <InlineMetric label={copy.insights.summaryTrust} value={trustText} />
      </div>
      <p className={`insights-summary__verdict${trustWarn ? ' is-warn' : ''}`}>{verdict}</p>
    </div>
  )
}
