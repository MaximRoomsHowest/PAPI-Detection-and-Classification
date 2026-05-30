// Neutral placeholder the Live Demo shows before a real backend result exists.
// Once the synthetic preset overlay is gone, FrameStage only needs these few
// fields — it renders the dropzone / uploaded media, never fabricated boxes.
export const IDLE_SCENARIO = {
  frame: '',
  condition: '',
  environmentClass: 'clear',
  artifactUrl: null,
  artifactType: null,
}

export const scenarios = [
  {
    id: 'clean',
    label: 'Clean example',
    badge: 'baseline',
    stateId: 'correct',
    summary: '2 white + 2 red = correct glidepath',
    frame: 'Frame 0142',
    condition: 'Clear evening, steady camera',
    lamps: [
      { id: 1, status: 'white', confidence: 98, transition: 3 },
      { id: 2, status: 'white', confidence: 97, transition: 5 },
      { id: 3, status: 'red', confidence: 96, transition: 4 },
      { id: 4, status: 'red', confidence: 95, transition: 6 },
    ],
    metrics: {
      latency: 17.2,
      boxConfidence: 98.1,
    },
    evidence: [5, 8, 84, 2, 1],
    box: { left: 64, top: 47, width: 21, height: 12 },
    environmentClass: 'clear',
  },
  {
    id: 'transition',
    label: 'Transition pause',
    badge: 'yellow/orange',
    stateId: 'correct',
    summary: '2 white + 2 red = correct glidepath',
    frame: 'Frame 0218',
    condition: 'Lamp 2 changing from white to red',
    lamps: [
      { id: 1, status: 'white', confidence: 96, transition: 4 },
      { id: 2, status: 'transition', confidence: 88, transition: 83 },
      { id: 3, status: 'red', confidence: 95, transition: 7 },
      { id: 4, status: 'red', confidence: 94, transition: 8 },
    ],
    metrics: {
      latency: 19.6,
      boxConfidence: 96.3,
    },
    evidence: [3, 13, 72, 10, 2],
    box: { left: 62, top: 46, width: 24, height: 13 },
    environmentClass: 'clear',
  },
  {
    id: 'hard-case',
    label: 'Hard case',
    badge: 'weather + occlusion',
    stateId: 'too-low',
    summary: '1 white + 3 red = too low',
    frame: 'Frame 0359',
    condition: 'Rain, shallow angle, partial occlusion',
    lamps: [
      { id: 1, status: 'white', confidence: 82, transition: 12 },
      { id: 2, status: 'red', confidence: 79, transition: 9 },
      { id: 3, status: 'red', confidence: 74, transition: 18 },
      { id: 4, status: 'occluded', confidence: 67, transition: 16 },
    ],
    metrics: {
      latency: 24.9,
      boxConfidence: 85.6,
    },
    evidence: [2, 7, 14, 64, 13],
    box: { left: 58, top: 45, width: 28, height: 17 },
    environmentClass: 'storm',
  },
  {
    id: 'edge',
    label: 'Edge device',
    badge: 'limited hardware',
    stateId: 'far-low',
    summary: '4 red = far too low',
    frame: 'Frame 0441',
    condition: 'Low light, compressed stream',
    lamps: [
      { id: 1, status: 'red', confidence: 91, transition: 5 },
      { id: 2, status: 'red', confidence: 90, transition: 6 },
      { id: 3, status: 'red', confidence: 89, transition: 6 },
      { id: 4, status: 'red', confidence: 88, transition: 8 },
    ],
    metrics: {
      latency: 28.4,
      boxConfidence: 91.9,
    },
    evidence: [1, 2, 5, 15, 77],
    box: { left: 66, top: 50, width: 20, height: 11 },
    environmentClass: 'night',
  },
]

export const transitionFrames = [
  ['white', 'white', 'red', 'red'],
  ['white', 'white', 'red', 'red'],
  ['white', 'transition', 'red', 'red'],
  ['white', 'transition', 'red', 'red'],
  ['white', 'red', 'red', 'red'],
  ['white', 'red', 'red', 'red'],
  ['white', 'red', 'transition', 'red'],
  ['white', 'red', 'red', 'red'],
  ['red', 'red', 'red', 'red'],
]
