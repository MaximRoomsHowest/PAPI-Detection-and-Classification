import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

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

import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
