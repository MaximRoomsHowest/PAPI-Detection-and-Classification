import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { LazyMotion, domAnimation } from 'motion/react'

// Self-hosted Poppins — replaces the Google Fonts @import that was in
// index.css. GDPR concern for the German client: loading fonts from
// Google's CDN transmits the visitor's IP to a third party without
// consent (audit F-MAJ-14). These imports inline the WOFF2 files into
// Vite's bundle output so the browser fetches them from our own origin.
import '@fontsource/poppins/300.css'
import '@fontsource/poppins/400.css'
import '@fontsource/poppins/500.css'
import '@fontsource/poppins/600.css'
import '@fontsource/poppins/700.css'

// Self-hosted JetBrains Mono for numerals / labels (the .mono / .tnum utility
// classes via var(--font-mono)). Same GDPR rationale as Poppins above — these
// imports inline the WOFF2 files into our own bundle, no Google Fonts CDN.
import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/500.css'
import '@fontsource/jetbrains-mono/600.css'
import '@fontsource/jetbrains-mono/700.css'

import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      {/* LazyMotion + domAnimation loads only the DOM animation features (~15kB)
          instead of the full Motion bundle; `strict` enforces the lightweight
          `m` components so no component can pull in the heavy `motion.*` API. */}
      <LazyMotion features={domAnimation} strict>
        <App />
      </LazyMotion>
    </BrowserRouter>
  </StrictMode>,
)
