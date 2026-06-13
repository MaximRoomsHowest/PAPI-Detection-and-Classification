import { ArrowLeftRight, Crosshair, Film, Image as ImageIcon } from 'lucide-react'
import { ApproachHero } from '../components/intro/ApproachHero'
import { GlideSlopeSimulator } from '../components/intro/GlideSlopeSimulator'

// Landing page: a cinematic approach-footage hero with a live computer-vision
// HUD overlay (ApproachHero), the four-capability band, the interactive
// glide-slope explainer kept as its own section, and the real-airport context.
export function IntroductionPage({ copy }) {
  const capabilities = [
    { icon: ImageIcon, title: copy.intro.capImage, body: copy.intro.capImageBody },
    { icon: Film, title: copy.intro.capVideo, body: copy.intro.capVideoBody },
    { icon: Crosshair, title: copy.intro.capState, body: copy.intro.capStateBody },
    { icon: ArrowLeftRight, title: copy.intro.capTransition, body: copy.intro.capTransitionBody },
  ]

  return (
    <div className="intro-page">
      <ApproachHero copy={copy} />

      <section className="capability-section" aria-label={copy.intro.capabilitiesTitle}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">{copy.intro.capabilitiesEyebrow}</p>
            <h2>{copy.intro.capabilitiesTitle}</h2>
          </div>
        </div>
        <ul className="capability-band">
          {capabilities.map(({ icon: Icon, title, body }) => (
            <li key={title}>
              <Icon size={19} aria-hidden="true" />
              <h3>{title}</h3>
              <p>{body}</p>
            </li>
          ))}
        </ul>
      </section>

      {/* The interactive instrument that used to be the hero now lives as its own
          explainer section — it keeps the educational value without competing
          with the footage hero above. */}
      <section className="glide-explainer" aria-label={copy.intro.sim.title}>
        <GlideSlopeSimulator copy={copy} />
      </section>

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
                <strong className="mono">47.67139 N, 9.51139 E</strong>
              </div>
              <div>
                <span>{copy.intro.elevation}</span>
                <strong className="mono">414 m AMSL</strong>
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
            {/* The OSM embed needs scripts but nothing else — verified to render
                fully under an opaque-origin sandbox (no storage, no popups,
                no navigation, no access to this page). */}
            <iframe
              title="Bodensee-Airport Friedrichshafen map"
              loading="lazy"
              referrerPolicy="no-referrer-when-downgrade"
              sandbox="allow-scripts"
              src="https://www.openstreetmap.org/export/embed.html?bbox=9.4896%2C47.6572%2C9.5332%2C47.6856&layer=mapnik&marker=47.67139%2C9.51139"
            />
            <span className="map-caption mono">47.67139 N, 9.51139 E</span>
          </div>
        </div>
      </section>
    </div>
  )
}
