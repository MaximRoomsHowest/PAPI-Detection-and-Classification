import { Link } from 'react-router-dom'

/*
  Hero glidepath cross-section — inline SVG over a faint blueprint-grid
  panel (Stage 3). Replaces the former hero.png photo wash. Side view of
  the approach geometry: the vertical scale is exaggerated x5 so the 3.0deg
  slope reads as a meaningful angle — this is labelled honestly as a
  non-linear angular projection. No gradients/filters; primitives only;
  stroke = currentColor = var(--accent). All numerals JetBrains Mono.

  Real fixed aerodrome facts only (EDNY, RWY 24, 3.0deg nominal). The
  drone glyph rides the on-path ray with a dashed altitude drop-line; no
  fabricated AGL/airframe/timestamp numbers are drawn.
*/
function GlidepathDiagram({ copy }) {
  const W = 720
  const H = 540
  const lampX = 96
  const groundY = 470
  const lampY = groundY - 8

  // Vertical exaggeration so 3deg looks like a meaningful slope.
  const VY = 5.0
  const maxR = 600

  const d = copy.intro.diagram
  const zones = [
    { label: '4W', from: 3.5, to: 5.0, fill: 'none', meaning: d.zones.farHigh, on: false },
    { label: '3W1R', from: 3.2, to: 3.5, fill: 'none', meaning: d.zones.high, on: false },
    {
      label: '2W2R',
      from: 2.8,
      to: 3.2,
      fill: 'color-mix(in oklab, var(--accent) 12%, transparent)',
      meaning: d.zones.onPath,
      on: true,
    },
    { label: '1W3R', from: 2.5, to: 2.8, fill: 'none', meaning: d.zones.low, on: false },
    { label: '4R', from: 0.3, to: 2.5, fill: 'none', meaning: d.zones.farLow, on: false },
  ]

  // Project a polar (angle, radius) onto the diagram with vertical exaggeration.
  const proj = (degAngle, r) => {
    const a = (degAngle * Math.PI) / 180
    return [lampX + r * Math.cos(a), lampY - r * Math.sin(a) * VY]
  }

  const wedge = (fromDeg, toDeg) => {
    const [fx, fy] = proj(fromDeg, maxR)
    const [tx, ty] = proj(toDeg, maxR)
    return `${lampX},${lampY} ${fx},${fy} ${tx},${ty}`
  }

  const onPath = zones.find((z) => z.on)
  const droneAng = (onPath.from + onPath.to) / 2
  const [droneX, droneY] = proj(droneAng, 470)
  const [refX, refY] = proj(3.0, 600)
  const slots = [86, 150, 220, 298, 380] // legend y-positions, far-high .. far-low

  return (
    <svg
      className="intro-diagram__svg"
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label={`${copy.intro.airportTitle} ${d.nominal}`}
    >
      <defs>
        <pattern
          id="intro-hatch"
          patternUnits="userSpaceOnUse"
          width="6"
          height="6"
          patternTransform="rotate(45)"
        >
          <line x1="0" y1="0" x2="0" y2="6" stroke="var(--border-strong)" strokeWidth="0.8" />
        </pattern>
      </defs>

      {/* Glidepath wedges — only the on-path 2W2R wedge is faintly filled */}
      {zones.map((z) => (
        <polygon key={z.label} points={wedge(z.from, z.to)} fill={z.fill} />
      ))}

      {/* Boundary rays between zones */}
      {[2.5, 2.8, 3.2, 3.5].map((a) => {
        const [x, y] = proj(a, maxR)
        return (
          <line
            key={a}
            x1={lampX}
            y1={lampY}
            x2={x}
            y2={y}
            stroke="var(--border-strong)"
            strokeWidth="1"
            strokeDasharray="2 4"
          />
        )
      })}

      {/* Heavier dashed 3.0deg nominal reference line */}
      <line
        x1={lampX}
        y1={lampY}
        x2={refX}
        y2={refY}
        stroke="var(--accent)"
        strokeWidth="1.6"
        strokeDasharray="7 4"
        opacity="0.9"
      />
      {(() => {
        const [lx, ly] = proj(3.0, 348)
        return (
          <text
            x={lx}
            y={ly - 8}
            textAnchor="middle"
            fontFamily="var(--font-mono)"
            fontSize="11"
            fill="var(--accent)"
            fontWeight="700"
            letterSpacing="2"
          >
            {d.nominal}
          </text>
        )
      })()}

      {/* Ground line + hatched threshold */}
      <line x1="20" y1={groundY} x2={W - 20} y2={groundY} stroke="var(--border-strong)" strokeWidth="1" />
      <rect x="20" y={groundY} width={W - 40} height="10" fill="url(#intro-hatch)" />

      <text
        x="40"
        y={groundY + 26}
        fontFamily="var(--font-mono)"
        fontSize="10"
        letterSpacing="2"
        fill="var(--text-muted)"
        fontWeight="600"
      >
        {d.runway}
      </text>
      <text
        x={W - 40}
        y={groundY + 26}
        fontFamily="var(--font-mono)"
        fontSize="10"
        letterSpacing="2"
        fill="var(--text-muted)"
        fontWeight="600"
        textAnchor="end"
      >
        {d.approach} &#8594;
      </text>

      {/* Distance ticks (mono numerals) */}
      {[210, 330, 450, 570].map((x, i) => (
        <g key={x}>
          <line x1={x} y1={groundY} x2={x} y2={groundY + 5} stroke="var(--border-strong)" />
          <text
            x={x}
            y={groundY + 26}
            fontFamily="var(--font-mono)"
            fontSize="9"
            textAnchor="middle"
            fill="var(--faint)"
            letterSpacing="1"
          >
            {(i + 1) * 250}m
          </text>
        </g>
      ))}

      {/* Vertical angle ticks at the lamp */}
      {[1, 2, 3].map((deg) => {
        const [, y500] = proj(deg, 500)
        return (
          <g key={deg}>
            <line x1="20" y1={y500} x2="36" y2={y500} stroke="var(--border)" strokeWidth="1" />
            <text
              x="20"
              y={y500 - 4}
              fontFamily="var(--font-mono)"
              fontSize="8.5"
              fill="var(--faint)"
              letterSpacing="1"
            >
              {deg}.0&#176;
            </text>
          </g>
        )
      })}

      {/* Four PAPI lamp circles at the origin — two warm white, two red */}
      <g transform={`translate(${lampX - 30}, ${lampY - 2})`}>
        {[0, 1, 2, 3].map((i) => {
          const isWhite = i < 2
          return (
            <circle
              key={i}
              cx={i * 13}
              cy="0"
              r="5.5"
              fill={isWhite ? 'var(--lamp-white)' : 'var(--lamp-red)'}
              stroke={isWhite ? 'var(--lamp-white-border)' : 'var(--lamp-red-border)'}
              strokeWidth="1"
            />
          )
        })}
        <text
          x="20"
          y="-14"
          fontFamily="var(--font-mono)"
          fontSize="10"
          textAnchor="middle"
          letterSpacing="1.5"
          fill="var(--accent)"
          fontWeight="700"
        >
          {d.lamps}
        </text>
      </g>

      {/* Angle annotation arc near the lamp */}
      <path
        d={`M ${lampX + 80} ${lampY} A 80 ${80 * VY * 0.18} 0 0 0 ${proj(3.0, 80)[0]} ${proj(3.0, 80)[1]}`}
        fill="none"
        stroke="var(--accent)"
        strokeWidth="0.9"
        opacity="0.55"
      />
      <text
        x={lampX + 92}
        y={lampY - 22}
        fontFamily="var(--font-mono)"
        fontSize="10"
        fill="var(--accent)"
        fontWeight="600"
        letterSpacing="1"
      >
        &#945;
      </text>

      {/* Right-edge zone legend with thin leader lines */}
      {zones.map((z, i) => {
        const a = (z.from + z.to) / 2
        const [wx, wy] = proj(a, 540)
        const ly = slots[i]
        const colX = W - 24
        return (
          <g key={z.label}>
            <line
              x1={wx}
              y1={wy}
              x2={colX - 8}
              y2={ly + 4}
              stroke={z.on ? 'var(--accent)' : 'var(--border-strong)'}
              strokeWidth={z.on ? 1 : 0.7}
              opacity="0.6"
            />
            <circle cx={wx} cy={wy} r={z.on ? 2.2 : 1.6} fill={z.on ? 'var(--accent)' : 'var(--text-muted)'} />
            <text
              x={colX}
              y={ly}
              textAnchor="end"
              fontFamily="var(--font-mono)"
              fontSize="11"
              fill={z.on ? 'var(--accent)' : 'var(--text-muted)'}
              fontWeight={z.on ? 700 : 600}
              letterSpacing="1.6"
            >
              {z.label}
            </text>
            <text
              x={colX}
              y={ly + 13}
              textAnchor="end"
              fontFamily="var(--font-mono)"
              fontSize="9"
              fill={z.on ? 'var(--accent)' : 'var(--faint)'}
              letterSpacing="0.6"
            >
              {z.meaning}
            </text>
          </g>
        )
      })}

      {/* Drone on the on-path ray, with a dashed altitude drop-line */}
      <g transform={`translate(${droneX}, ${droneY})`}>
        <line x1="-16" y1="0" x2="16" y2="0" stroke="var(--accent)" strokeWidth="1.6" />
        <circle cx="-16" cy="0" r="4.5" fill="var(--surface)" stroke="var(--accent)" strokeWidth="1.6" />
        <circle cx="16" cy="0" r="4.5" fill="var(--surface)" stroke="var(--accent)" strokeWidth="1.6" />
        <rect x="-5" y="-3.5" width="10" height="7" fill="var(--accent)" />
        <line
          x1="0"
          y1="7"
          x2="0"
          y2={groundY - droneY - 1}
          stroke="var(--accent)"
          strokeWidth="0.7"
          strokeDasharray="2 4"
          opacity="0.55"
        />
        <text
          x="28"
          y="4"
          fontFamily="var(--font-mono)"
          fontSize="10"
          fill="var(--accent)"
          fontWeight="700"
          letterSpacing="1.2"
        >
          {d.drone}
        </text>
      </g>
    </svg>
  )
}

export function IntroductionPage({ copy }) {
  return (
    <section className="intro-hero">
      <div className="intro-hero-inner">
        <section className="intro-band">
          <div className="intro-copy">
            <p className="eyebrow">{copy.intro.eyebrow}</p>
            <h1>{copy.intro.title}</h1>
            <p className="intro-description">{copy.intro.description}</p>
            <div className="intro-actions">
              <Link className="cta-button" to="/live-demo">
                {copy.intro.cta}
              </Link>
            </div>
          </div>

          {/*
            Glidepath cross-section, drawn inline over a faint blueprint
            panel. The mono caption states the x5 vertical exaggeration so
            the exaggerated slope is read honestly (design deliverable #1:
            "aviation / glidepath / runway approach" within 5 seconds).
          */}
          <figure className="intro-diagram">
            <div className="intro-diagram__panel">
              <GlidepathDiagram copy={copy} />
            </div>
            <figcaption className="intro-diagram__caption mono">
              <span>{copy.intro.diagram.caption}</span>
              <span>{copy.intro.diagram.captionScale}</span>
            </figcaption>
          </figure>
        </section>

        <a className="scroll-cue" href="#airport-context" aria-label={copy.intro.scroll}>
          <span />
          <small>{copy.intro.scroll}</small>
        </a>

        <section className="airport-section" id="airport-context">
          <div className="section-heading">
            <div>
              <p className="eyebrow">{copy.intro.airportEyebrow}</p>
              <h2>{copy.intro.airportTitle}</h2>
            </div>
            <span className="source-note">{copy.intro.runwayNote}</span>
          </div>

          <div className="airport-grid">
            <div className="airport-card">
              <h3>{copy.intro.runwayDetails}</h3>
              <p>{copy.intro.runwayDescription}</p>
              <div className="airport-meta">
                <div>
                  <span>{copy.intro.coordinates}</span>
                  <strong className="tnum">47.67139 N, 9.51139 E</strong>
                </div>
                <div>
                  <span>{copy.intro.elevation}</span>
                  <strong className="tnum">414 m AMSL</strong>
                </div>
              </div>
              <a
                className="text-link"
                href="https://www.bodensee-airport.eu/en/"
                target="_blank"
                rel="noreferrer"
              >
                Bodensee-Airport Friedrichshafen
              </a>
            </div>

            <div className="airport-map">
              <iframe
                title="Bodensee-Airport Friedrichshafen map"
                loading="lazy"
                referrerPolicy="no-referrer-when-downgrade"
                src="https://www.openstreetmap.org/export/embed.html?bbox=9.4896%2C47.6572%2C9.5332%2C47.6856&layer=mapnik&marker=47.67139%2C9.51139"
              />
              <span className="map-caption tnum">47.67139 N, 9.51139 E</span>
            </div>
          </div>
        </section>
      </div>
    </section>
  )
}
