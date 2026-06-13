import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { m, useReducedMotion } from 'motion/react'
import { ChevronDown, Pause, Play } from 'lucide-react'

// Cinematic landing hero: full-bleed Bodensee approach footage under a directional
// scrim + vignette, carrying the headline, description and primary actions. One
// coordinated entrance (Motion) staggers the copy in. The footage is muted/looping
// with a real pause control (WCAG 2.2.2); reduced-motion users get the static
// poster, no autoplay and no entrance animation.
const EASE = [0.22, 0.61, 0.36, 1]

export function ApproachHero({ copy }) {
  const reduceMotion = useReducedMotion()
  const videoRef = useRef(null)
  const [isPlaying, setIsPlaying] = useState(!reduceMotion)

  const toggleVideo = () => {
    const video = videoRef.current
    if (!video) return
    if (video.paused) {
      video.play().then(() => setIsPlaying(true)).catch(() => {})
    } else {
      video.pause()
      setIsPlaying(false)
    }
  }

  const copyContainer = {
    hidden: {},
    show: { transition: { staggerChildren: 0.1, delayChildren: 0.15 } },
  }
  const copyItem = {
    hidden: { opacity: 0, y: 18 },
    show: { opacity: 1, y: 0, transition: { duration: 0.6, ease: EASE } },
  }

  return (
    <section className="approach-hero">
      <div className="approach-hero__media" aria-hidden="true">
        <video
          ref={videoRef}
          className="approach-hero__video"
          src="/intro-hero.mp4"
          poster="/intro-hero-poster.jpg"
          muted
          loop
          playsInline
          autoPlay={!reduceMotion}
          preload="metadata"
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
        />
        <span className="approach-hero__scrim" />
        <span className="approach-hero__vignette" />
      </div>

      {/* Media control (WCAG 2.2.2) */}
      <button
        type="button"
        className="approach-hero__toggle"
        onClick={toggleVideo}
        aria-pressed={isPlaying}
        aria-label={isPlaying ? copy.intro.pauseMedia : copy.intro.playMedia}
      >
        {isPlaying ? <Pause size={15} aria-hidden="true" /> : <Play size={15} aria-hidden="true" />}
      </button>

      <m.div
        className="approach-hero__copy intro-copy"
        variants={copyContainer}
        initial={reduceMotion ? false : 'hidden'}
        animate="show"
      >
        <m.p className="eyebrow" variants={copyItem}>
          {copy.intro.eyebrow}
        </m.p>
        <m.h1 variants={copyItem}>{copy.intro.title}</m.h1>
        <m.p className="intro-description" variants={copyItem}>
          {copy.intro.description}
        </m.p>
        <m.div className="intro-actions" variants={copyItem}>
          <Link className="cta-button" to="/live-demo">
            {copy.intro.cta}
          </Link>
          <Link className="hero-secondary" to="/history">
            {copy.intro.secondaryCta}
          </Link>
        </m.div>
      </m.div>

      <a className="scroll-cue" href="#airport-context" aria-label={copy.intro.scroll}>
        <ChevronDown size={16} aria-hidden="true" />
        <small>{copy.intro.scroll}</small>
      </a>
    </section>
  )
}
