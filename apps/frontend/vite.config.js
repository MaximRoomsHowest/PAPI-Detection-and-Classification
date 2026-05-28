import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  define: {
    // Plotly references the bare identifier `global`. Vite (esbuild) does not
    // polyfill that in browser builds, so we shim it to globalThis. Without
    // this, `cartesian-*.js` throws ReferenceError at first render.
    global: 'globalThis',
  },
  build: {
    // Raise the warning threshold slightly so the legitimate Plotly chunk
    // doesn't spam every CI run, but keep it tight enough that runaway
    // bundles still surface.
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        // Named vendor chunks — audit F-MAJ-11. Browsers cache them
        // independently, so app-code changes do not bust the Plotly
        // cache (which alone weighs ~270 kB gzipped). Order matters:
        // most-specific matches must come BEFORE the catch-all vendor
        // chunk, otherwise everything would land there.
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('plotly.js') || id.includes('react-plotly.js')) return 'plotly'
          if (id.includes('jspdf') || id.includes('html2canvas')) return 'pdf-export'
          if (id.includes('react-router')) return 'router'
          if (id.includes('framer-motion')) return 'motion'
          if (id.includes('lucide-react')) return 'icons'
          return 'vendor'
        },
      },
    },
  },
})
