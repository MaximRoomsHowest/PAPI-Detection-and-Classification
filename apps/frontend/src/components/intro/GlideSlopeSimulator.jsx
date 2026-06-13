import { useEffect, useMemo, useRef, useState } from 'react'
import { Pause, Play } from 'lucide-react'
import { stateCatalog } from '../../catalog/stateCatalog'
import { translateState } from '../../i18n/translate'
import { PapiGlyph } from '../PapiGlyph'

// Interactive cross-section of a four-box PAPI approach. The lamp logic is the
// same count-based rule the backend applies (white lamps seen -> global
// state), so the hero literally demonstrates the product's own vocabulary.
//
// Nominal FAA four-box set angles for a 3° glide path, lowest first — which
// is also the leftmost lamp in the pilot's-view bar (a lamp turns white once
// the aircraft climbs above its set angle, so the low-angle lamps go white
// first and the on-path picture reads white-white-red-red).
const SET_ANGLES = [2.5, 2.8, 3.2, 3.5]
const MIN_ANGLE = 2.0
const MAX_ANGLE = 4.0
// Within this margin of a set angle the beam is mid-changeover: the lamp
// reads as a transition — the exact event the detector hunts for in video.
const TRANSITION_BAND = 0.05
// A real 2° spread is invisible in a side view; glide-slope diagrams
// conventionally exaggerate the vertical scale. Stated in the caption.
const VERTICAL_EXAGGERATION = 8
// One full down-and-up sweep takes this long when autoplay is on.
const SWEEP_DEG_PER_MS = ((MAX_ANGLE - MIN_ANGLE) * 2) / 18_000

const PREFERS_REDUCED_MOTION =
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

// SVG geometry (user units). The PAPI unit is the origin every ray fans out
// from; the aircraft rides a ray at the current approach angle.
const VIEW = { w: 880, h: 430 }
const ORIGIN = { x: 560, y: 358 }
const LEFT_EDGE = 40
const AIRCRAFT_DX = 430

function screenRadians(deg) {
  return (deg * VERTICAL_EXAGGERATION * Math.PI) / 180
}

// Y coordinate of the ray for `deg` at horizontal distance `dx` left of the unit.
function rayY(deg, dx) {
  return ORIGIN.y - Math.tan(screenRadians(deg)) * dx
}

function lampTone(angle, setAngle) {
  if (Math.abs(angle - setAngle) <= TRANSITION_BAND) return 'transition'
  return angle > setAngle ? 'white' : 'red'
}

const STATE_BY_WHITE_COUNT = ['far-low', 'too-low', 'correct', 'too-high', 'far-high']

export function GlideSlopeSimulator({ copy }) {
  const [angle, setAngle] = useState(3.0)
  const [sweeping, setSweeping] = useState(!PREFERS_REDUCED_MOTION)
  const sweepDirection = useRef(-1)
  const frameRef = useRef(null)
  const sim = copy.intro.sim

  // Autoplay sweep: a slow triangle wave driven by rAF. The slider always
  // wins — any manual input stops the sweep so the instrument never fights
  // the person holding it.
  useEffect(() => {
    if (!sweeping) return undefined
    let last = performance.now()
    const step = (now) => {
      const dt = now - last
      last = now
      setAngle((current) => {
        let next = current + sweepDirection.current * SWEEP_DEG_PER_MS * dt
        if (next <= MIN_ANGLE) {
          next = MIN_ANGLE
          sweepDirection.current = 1
        } else if (next >= MAX_ANGLE) {
          next = MAX_ANGLE
          sweepDirection.current = -1
        }
        return next
      })
      frameRef.current = requestAnimationFrame(step)
    }
    frameRef.current = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frameRef.current)
  }, [sweeping])

  const tones = SET_ANGLES.map((setAngle) => lampTone(angle, setAngle))
  const whiteCount = tones.filter((tone) => tone === 'white').length
  const verdictId = tones.includes('transition')
    ? 'transition'
    : STATE_BY_WHITE_COUNT[whiteCount]
  const verdict = translateState(
    stateCatalog.find((state) => state.id === verdictId),
    copy,
  )

  const angleText = useMemo(
    () =>
      new Intl.NumberFormat(copy.locale, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(angle),
    [angle, copy.locale],
  )

  const aircraftY = rayY(angle, AIRCRAFT_DX)
  const aircraftX = ORIGIN.x - AIRCRAFT_DX
  const zoneEdge = (deg) => rayY(deg, ORIGIN.x - LEFT_EDGE)

  return (
    <section className="glide-sim" aria-label={sim.title}>
      <header className="glide-sim__head">
        <div>
          <p className="glide-sim__eyebrow mono">{sim.eyebrow}</p>
          <h2>{sim.title}</h2>
        </div>
        <button
          type="button"
          className="glide-sim__sweep"
          onClick={() => setSweeping((current) => !current)}
          aria-pressed={sweeping}
        >
          {sweeping ? <Pause size={14} aria-hidden="true" /> : <Play size={14} aria-hidden="true" />}
          <span>{sweeping ? sim.sweepStop : sim.sweepStart}</span>
        </button>
      </header>

      <svg
        className="glide-sim__svg"
        viewBox={`0 0 ${VIEW.w} ${VIEW.h}`}
        role="img"
        aria-label={`${sim.title} — ${angleText}° — ${verdict.label}`}
      >
        {/* Optical sectors fanning out from the PAPI unit. The 2W2R corridor
            carries the accent tint: that band IS the product the lights sell. */}
        <polygon
          className="gs-zone gs-zone--red-deep"
          points={`${ORIGIN.x},${ORIGIN.y} ${LEFT_EDGE},${zoneEdge(2.5)} ${LEFT_EDGE},${ORIGIN.y}`}
        />
        <polygon
          className="gs-zone gs-zone--red"
          points={`${ORIGIN.x},${ORIGIN.y} ${LEFT_EDGE},${zoneEdge(2.8)} ${LEFT_EDGE},${zoneEdge(2.5)}`}
        />
        <polygon
          className="gs-zone gs-zone--corridor"
          points={`${ORIGIN.x},${ORIGIN.y} ${LEFT_EDGE},${zoneEdge(3.2)} ${LEFT_EDGE},${zoneEdge(2.8)}`}
        />
        <polygon
          className="gs-zone gs-zone--white"
          points={`${ORIGIN.x},${ORIGIN.y} ${LEFT_EDGE},${zoneEdge(3.5)} ${LEFT_EDGE},${zoneEdge(3.2)}`}
        />
        <polygon
          className="gs-zone gs-zone--white-deep"
          points={`${ORIGIN.x},${ORIGIN.y} ${LEFT_EDGE},18 ${LEFT_EDGE},${zoneEdge(3.5)}`}
        />

        {/* Set-angle rays + labels. */}
        {SET_ANGLES.map((setAngle) => (
          <g key={setAngle}>
            <line
              className="gs-ray"
              x1={ORIGIN.x}
              y1={ORIGIN.y}
              x2={LEFT_EDGE}
              y2={zoneEdge(setAngle)}
            />
            <text className="gs-ray-label" x={LEFT_EDGE + 4} y={zoneEdge(setAngle) - 5}>
              {setAngle.toFixed(1)}°
            </text>
          </g>
        ))}

        {/* Ground + runway + threshold marks. */}
        <line className="gs-ground" x1={16} y1={ORIGIN.y} x2={VIEW.w - 16} y2={ORIGIN.y} />
        <rect className="gs-runway" x={600} y={ORIGIN.y - 3} width={252} height={6} rx={1} />
        {[0, 1, 2, 3].map((i) => (
          <rect
            key={i}
            className="gs-threshold"
            x={606 + i * 7}
            y={ORIGIN.y - 1.5}
            width={3}
            height={3}
          />
        ))}

        {/* The PAPI unit itself, lamps live-coloured with the bar below. */}
        <rect className="gs-papi-box" x={547} y={ORIGIN.y - 13} width={26} height={9} rx={1.5} />
        {tones.map((tone, index) => (
          <circle
            key={index}
            className={`gs-papi-dot gs-papi-dot--${tone}`}
            cx={551.5 + index * 5.7}
            cy={ORIGIN.y - 8.5}
            r={1.9}
          />
        ))}

        {/* Aircraft: a tracked-target dart riding the current approach ray. */}
        <g transform={`translate(${aircraftX} ${aircraftY})`}>
          <path className="gs-aircraft" d="M16 0 L-12 -8 L-5 0 L-12 8 Z" />
          <text className="gs-angle-readout" x={-2} y={-16} textAnchor="middle">
            {angleText}°
          </text>
        </g>
      </svg>

      <div className="glide-sim__deck">
        <div className="glide-sim__pilot">
          <span className="glide-sim__pilot-label mono">{sim.pilotView}</span>
          <PapiGlyph size="lg" states={tones} label={`${sim.pilotView}: ${verdict.label}`} />
          <span className="glide-sim__short mono">{verdict.short}</span>
        </div>
        <div className="glide-sim__verdict" data-state={verdictId}>
          <strong>{verdict.label}</strong>
          <span>{verdict.description}</span>
        </div>
      </div>

      <div className="glide-sim__controls">
        <label className="glide-sim__slider">
          <span className="mono">{sim.angleLabel}</span>
          <input
            type="range"
            min={MIN_ANGLE}
            max={MAX_ANGLE}
            step={0.01}
            value={angle}
            aria-valuetext={`${angleText}°`}
            onChange={(event) => {
              setSweeping(false)
              setAngle(Number(event.target.value))
            }}
          />
          <output className="mono">{angleText}°</output>
        </label>
        <p className="glide-sim__note">{sim.scaleNote}</p>
      </div>
    </section>
  )
}
