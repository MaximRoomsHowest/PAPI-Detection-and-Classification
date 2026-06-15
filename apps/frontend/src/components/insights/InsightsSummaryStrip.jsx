import clsx from 'clsx'
import {
  Radio,
  Clock,
  ArrowLeftRight,
  Spline,
  Film,
  Crosshair,
  Cpu,
  ShieldCheck,
  ShieldAlert,
} from 'lucide-react'
import { degrees } from '../../lib/format'

// At-a-glance session snapshot (the verdict layer). Rendered OUTSIDE the tabs so it
// shows on every section and isn't parked off-screen with an inactive force-mounted
// panel. Deliberately NO pass/fail verdict — that needs the commissioned set-angles
// (not on the frontend yet); the honest headline is "transitions on N/4 lamps,
// commissioned comparison pending".
//
// Layout has a clear hierarchy (the old flat tile-row gave every number equal weight):
//   • a hero stat — lamps crossed N/total with PAPI pips (the thing you scan first);
//   • a data-trust badge — can you believe the angles? (warn-coloured when not);
//   • an icon-led grid of supporting metrics;
//   • the verdict sentence.
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

  // Supporting metrics (the hero shows lamps-crossed, so it's not repeated here).
  const metrics = [
    sourceMeta?.label && { key: 'source', icon: Radio, label: copy.insights.summarySource, value: sourceMeta.label },
    sourceMeta?.timestamp && { key: 'captured', icon: Clock, label: copy.insights.summaryCaptured, value: sourceMeta.timestamp },
    Number.isFinite(transitionsCount) && { key: 'trans', icon: ArrowLeftRight, label: copy.insights.summaryTransitions, value: transitionsCount },
    { key: 'elev', icon: Spline, label: copy.insights.summaryElevation, value: elevationText },
    { key: 'frames', icon: Film, label: copy.insights.summaryFrames, value: Number.isFinite(frameCount) ? frameCount.toLocaleString() : frameCount },
    Number.isFinite(avgConfidence) && { key: 'conf', icon: Crosshair, label: copy.insights.summaryConfidence, value: avgConfidence, suffix: '%' },
    detectorLabel && { key: 'detector', icon: Cpu, label: copy.insights.summaryDetector, value: detectorLabel },
  ].filter(Boolean)

  const TrustIcon = trustWarn ? ShieldAlert : ShieldCheck

  return (
    <section className="session-snapshot" aria-label={copy.insights.summaryLabel}>
      <div className="session-snapshot__top">
        <div className="session-snapshot__hero">
          <span className="session-snapshot__eyebrow">{copy.insights.summaryEyebrow}</span>
          <div className="session-snapshot__crossed">
            <span className="session-snapshot__crossed-num tnum">{lampsCrossed}</span>
            <span className="session-snapshot__crossed-total tnum">/ {totalLamps}</span>
          </div>
          <span className="session-snapshot__crossed-label">{copy.insights.summaryLampsCrossed}</span>
          <span className="session-snapshot__pips" aria-hidden="true">
            {Array.from({ length: Math.max(totalLamps, 0) }, (_, i) => (
              <span key={i} className={clsx('snapshot-pip', i < lampsCrossed && 'is-on')} />
            ))}
          </span>
        </div>
        <span className={clsx('session-snapshot__trust', trustWarn && 'is-warn')}>
          <TrustIcon size={18} aria-hidden="true" />
          <span className="session-snapshot__trust-body">
            <span className="session-snapshot__trust-label">{copy.insights.summaryTrust}</span>
            <span className="session-snapshot__trust-value">{trustText}</span>
          </span>
        </span>
      </div>

      <div className="session-snapshot__grid">
        {metrics.map(({ key, icon: Icon, label, value, suffix }) => (
          <div className="snapshot-metric" key={key}>
            <span className="snapshot-metric__label">
              <Icon size={13} aria-hidden="true" />
              {label}
            </span>
            <strong className="snapshot-metric__value">
              {value}
              {suffix ? <small>{suffix}</small> : null}
            </strong>
          </div>
        ))}
      </div>

      <p className={clsx('session-snapshot__verdict', trustWarn && 'is-warn')}>{verdict}</p>
    </section>
  )
}
