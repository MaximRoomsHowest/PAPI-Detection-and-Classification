import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { LazyMotion, domAnimation } from 'motion/react'

// Self-hosted fonts (GDPR: Google Fonts CDN would transmit the visitor's IP
// to a third party without consent — audit F-MAJ-14; @fontsource inlines the
// WOFF2 files into our own bundle). Geist (Sans) is the UI face; Geist Mono
// carries every numeric readout (angles, confidences, timestamps) via
// var(--font-mono). Both are variable fonts — one file per family covers the
// whole 100–900 weight axis, so no per-weight imports are needed.
import '@fontsource-variable/geist'
import '@fontsource-variable/geist-mono'

import './index.css'
import App from './App.jsx'
import { ErrorBoundary } from './components/ErrorBoundary.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    {/* Top-level boundary so a render error shows a recover-by-reload fallback
        instead of a blank white screen. */}
    <ErrorBoundary>
      {/* react-router v7: relative-splat-path + startTransition are the DEFAULT now,
          so the v6 `future` opt-in flags are dropped (passing them warns in v7). */}
      <BrowserRouter>
        {/* LazyMotion + domAnimation loads only the DOM animation features (~15kB)
            instead of the full Motion bundle; `strict` enforces the lightweight
            `m` components so no component can pull in the heavy `motion.*` API. */}
        <LazyMotion features={domAnimation} strict>
          <App />
        </LazyMotion>
      </BrowserRouter>
    </ErrorBoundary>
  </StrictMode>,
)
