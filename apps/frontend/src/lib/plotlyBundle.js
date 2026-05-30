// Plotly is lazy-loaded to keep the initial JS bundle small (saves ~700kB
// gzipped on first paint).
// Use `loadPlotlyBundle()` for direct API access (e.g. PDF export) and
// `<LazyPlot>` in JSX.
//
// Module-shape handling note (regression USERTEST-CRIT-2,
// papi-user-test-2026-05-28): plotly.js@3.x + Rolldown's CJS interop
// can produce module records where `bundle.default` is sometimes the
// real export, sometimes a re-wrapped { default: realExport } object.
// `unwrapDefault` peels at most two layers so it survives either shape,
// and `requireFunction` throws a clear diagnostic if the shape is so
// different that we'd otherwise get the cryptic
// "(e.default ?? e) is not a function" minified error.
//
// CRITICAL: `plotlyBundlePromise` is a module-level singleton shared by
// both <LazyPlot> and App's PDF export (handleDownloadCharts). It must
// live in exactly one module imported by both; never duplicate it.
let plotlyBundlePromise

export function unwrapDefault(mod) {
  if (mod == null) return mod
  if (typeof mod === 'function') return mod
  const first = mod.default !== undefined ? mod.default : mod
  if (first == null) return first
  if (typeof first === 'function') return first
  if (first.default !== undefined && typeof first.default === 'function') {
    return first.default
  }
  return first
}

export function requireFunction(value, label) {
  if (typeof value !== 'function') {
    const keys =
      value && typeof value === 'object'
        ? Object.keys(value).slice(0, 6).join(', ')
        : 'n/a'
    throw new TypeError(
      `Plotly bundle: ${label} did not expose a callable export. ` +
        `Got ${typeof value}; module keys: ${keys}. ` +
        `This usually means plotly.js or react-plotly.js were upgraded ` +
        `and the bundler's CJS interop produced an unexpected shape. ` +
        `Update src/App.jsx loadPlotlyBundle().`
    )
  }
  return value
}

export function loadPlotlyBundle() {
  if (!plotlyBundlePromise) {
    plotlyBundlePromise = Promise.all([
      import('react-plotly.js/factory'),
      import('plotly.js/lib/core'),
      import('plotly.js/lib/bar'),
      import('plotly.js/lib/heatmap'),
      import('plotly.js/lib/histogram'),
      import('plotly.js/lib/scatter'),
    ])
      .then(([factoryModule, plotlyModule, barModule, heatmapModule, histogramModule, scatterModule]) => {
        const factory = requireFunction(
          unwrapDefault(factoryModule),
          'react-plotly.js/factory',
        )
        const Plotly = unwrapDefault(plotlyModule)
        if (!Plotly || typeof Plotly.register !== 'function') {
          throw new TypeError(
            `Plotly bundle: plotly.js/lib/core did not expose register(). ` +
              `Got ${typeof Plotly}.`,
          )
        }
        const bar = unwrapDefault(barModule)
        const heatmap = unwrapDefault(heatmapModule)
        const histogram = unwrapDefault(histogramModule)
        const scatter = unwrapDefault(scatterModule)
        // scatter is needed explicitly for the angle-vs-state + transition
        // timeline charts; histogram for the confidence distribution. bar and
        // heatmap remain for the state-distribution and (legacy) ribbon.
        Plotly.register([bar, heatmap, histogram, scatter])
        const Plot = factory(Plotly)
        return { Plot, Plotly }
      })
      .catch((error) => {
        // Reset so the next call retries after a transient bundling failure.
        plotlyBundlePromise = undefined
        throw error
      })
  }
  return plotlyBundlePromise
}
