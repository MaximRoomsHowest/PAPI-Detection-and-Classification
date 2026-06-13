import { degrees } from '../../lib/format'
import { InlineMetric } from '../InlineMetric'

// At-a-glance overview strip (the verdict layer + key session metrics). Rendered
// OUTSIDE the tabs so it shows on every section and isn't parked off-screen with an
// inactive force-mounted panel. It states what the session found and whether to trust
// it — deliberately NO pass/fail verdict, which needs the commissioned set-angles (not
// on the frontend yet); the honest headline is "transitions on N/4 lamps, commissioned
// comparison pending". Extra roll-ups (transitions, detection confidence, detector) are
// computed by the page from the real session results and passed in.
export function InsightsSummaryStrip({ summary, sourceMeta, extra = {}, copy }) {
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
  const { transitionsCount, avgConfidence, detectorLabel } = extra
  const elevationText = hasAngles ? `${degrees(elevationMin)}–${degrees(elevationMax)}` : '—'
  const trustWarn = hasAngles && !anglePlausible
  const trustText = !hasAngles
    ? copy.insights.trustNoAngle
    : !anglePlausible
      ? copy.insights.trustImplausible
      : [
          // Localise the backend angle_source enum (telemetry_file -> "from telemetry file")
          // instead of shouting the raw snake-case value (audit REFACTOR-2).
          angleSource ? (copy.live.angleSource?.[angleSource] ?? angleSource) : null,
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
        {sourceMeta?.label ? <InlineMetric label={copy.insights.summarySource} value={sourceMeta.label} /> : null}
        {sourceMeta?.timestamp ? <InlineMetric label={copy.insights.summaryCaptured} value={sourceMeta.timestamp} /> : null}
        <InlineMetric label={copy.insights.summaryLampsCrossed} value={`${lampsCrossed} / ${totalLamps}`} />
        {Number.isFinite(transitionsCount) ? (
          <InlineMetric label={copy.insights.summaryTransitions} value={transitionsCount} />
        ) : null}
        <InlineMetric label={copy.insights.summaryElevation} value={elevationText} />
        <InlineMetric label={copy.insights.summaryFrames} value={frameCount} />
        {Number.isFinite(avgConfidence) ? (
          <InlineMetric label={copy.insights.summaryConfidence} value={avgConfidence} suffix="%" />
        ) : null}
        <InlineMetric label={copy.insights.summaryTrust} value={trustText} />
        {detectorLabel ? <InlineMetric label={copy.insights.summaryDetector} value={detectorLabel} /> : null}
      </div>
      <p className={`insights-summary__verdict${trustWarn ? ' is-warn' : ''}`}>{verdict}</p>
    </div>
  )
}
