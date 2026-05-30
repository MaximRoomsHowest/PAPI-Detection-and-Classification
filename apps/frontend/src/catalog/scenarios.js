// Neutral placeholder the Live Demo shows before a real backend result exists.
// FrameStage only needs these few fields — it renders the dropzone / uploaded
// media, never fabricated boxes.
export const IDLE_SCENARIO = {
  frame: '',
  condition: '',
  environmentClass: 'clear',
  artifactUrl: null,
  artifactType: null,
}

// Minimal fallback scenarios that keep `activeScenario`/`activeState` valid
// before any backend run. Their content is never rendered (the Live Demo shows
// the empty state until a real result arrives, and Insights is driven entirely
// by real backend results), so they carry no synthetic evidence, boxes, or
// transition matrices — those fed the removed fabricated charts.
export const scenarios = [
  {
    id: 'clean',
    label: 'Clean example',
    badge: 'baseline',
    stateId: 'correct',
    summary: '2 white + 2 red = correct glidepath',
    frame: '',
    condition: '',
    lamps: [],
    metrics: { latency: 0, boxConfidence: 0 },
    environmentClass: 'clear',
  },
]
