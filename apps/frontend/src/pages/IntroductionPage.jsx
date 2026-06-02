import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Pause, Play } from 'lucide-react'

// Respect the OS "reduce motion" setting: don't auto-play the looping hero video
// for users who asked for less motion (WCAG 2.3.3). Computed once at module load;
// this is a client-only SPA so window is always present.
const PREFERS_REDUCED_MOTION =
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

export function IntroductionPage({ copy }) {
  const videoRef = useRef(null)
  const [isPlaying, setIsPlaying] = useState(!PREFERS_REDUCED_MOTION)

  // Pause/play control satisfies WCAG 2.2.2 for the auto-playing looping video.
  const toggleHeroVideo = () => {
    const video = videoRef.current
    if (!video) return
    if (video.paused) {
      video.play().then(() => setIsPlaying(true)).catch(() => {})
    } else {
      video.pause()
      setIsPlaying(false)
    }
  }

  return (
    <section className="intro-hero">
      <div className="intro-hero-inner">
        <section className="intro-band">
          {/* Bodensee approach footage as a faint hero wash (compressed 720p loop).
              Muted + looping; the toggle is a pause control and reduced-motion users
              get the poster instead of autoplay. Absolutely positioned, so the
              single-column copy layout sits cleanly on top of it. */}
          <div className="intro-band__bg" aria-hidden="true">
            <video
              ref={videoRef}
              className="intro-band__video"
              src="/intro-hero.mp4"
              poster="/intro-hero-poster.jpg"
              muted
              loop
              playsInline
              autoPlay={!PREFERS_REDUCED_MOTION}
              preload="metadata"
            />
            <span className="intro-band__scrim" />
          </div>
          <button
            type="button"
            className="intro-band__toggle"
            onClick={toggleHeroVideo}
            aria-label={isPlaying ? copy.intro.pauseMedia : copy.intro.playMedia}
          >
            {isPlaying ? <Pause size={15} aria-hidden="true" /> : <Play size={15} aria-hidden="true" />}
          </button>
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
