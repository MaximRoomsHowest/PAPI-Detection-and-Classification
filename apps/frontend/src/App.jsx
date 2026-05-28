import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, NavLink, Route, Routes } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  Activity,
  ChevronLeft,
  ChevronRight,
  Download,
  FolderOpen,
  Gauge,
  Moon,
  Pause,
  Play,
  Radar,
  Sun,
  Upload,
  Zap,
} from 'lucide-react'
import clsx from 'clsx'
import './App.css'
import heroPosterUrl from './assets/hero.png'
import { analyzeFrame, analyzeFrames, analyzeMedia, fetchRunways, mediaUrl } from './lib/api'
import { extractFrameImages } from './lib/frameExtraction'

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
let plotlyBundlePromise

function unwrapDefault(mod) {
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

function requireFunction(value, label) {
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

function loadPlotlyBundle() {
  if (!plotlyBundlePromise) {
    plotlyBundlePromise = Promise.all([
      import('react-plotly.js/factory'),
      import('plotly.js/lib/core'),
      import('plotly.js/lib/bar'),
      import('plotly.js/lib/heatmap'),
    ])
      .then(([factoryModule, plotlyModule, barModule, heatmapModule]) => {
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
        Plotly.register([bar, heatmap])
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

const stateCatalog = [
  {
    id: 'far-high',
    label: 'Far too high',
    short: '4W',
    pattern: '4 white',
    description: 'Aircraft is well above glidepath',
    color: '#35d7b7',
  },
  {
    id: 'too-high',
    label: 'Too high',
    short: '3W 1R',
    pattern: '3 white + 1 red',
    description: 'Slightly above the ideal angle',
    color: '#6fc8ff',
  },
  {
    id: 'correct',
    label: 'Correct glidepath',
    short: '2W 2R',
    pattern: '2 white + 2 red',
    description: 'Stable 3 degree approach',
    color: '#a7e35c',
  },
  {
    id: 'too-low',
    label: 'Too low',
    short: '1W 3R',
    pattern: '1 white + 3 red',
    description: 'Below desired approach path',
    color: '#ffb657',
  },
  {
    id: 'far-low',
    label: 'Far too low',
    short: '4R',
    pattern: '4 red',
    description: 'Immediate correction needed',
    color: '#ff6b6b',
  },
  {
    id: 'unknown',
    label: 'Unknown',
    short: 'N/A',
    pattern: 'Incomplete detection',
    description: 'Not enough lamps detected for a reliable PAPI state',
    color: '#9aa5b1',
  },
]

const legalStateCatalog = stateCatalog.filter((state) => state.id !== 'unknown')

const statusCopy = {
  white: { label: 'White', tone: 'white', color: '#f8fbff' },
  red: { label: 'Red', tone: 'red', color: '#ff4545' },
  transition: { label: 'Transition', tone: 'transition', color: '#ffb11f' },
  occluded: { label: 'Occluded', tone: 'occluded', color: '#9aa5b1' },
}

const stateLampPatterns = {
  'far-high': ['white', 'white', 'white', 'white'],
  'too-high': ['white', 'white', 'white', 'red'],
  correct: ['white', 'white', 'red', 'red'],
  'too-low': ['white', 'red', 'red', 'red'],
  'far-low': ['red', 'red', 'red', 'red'],
  unknown: ['occluded', 'occluded', 'occluded', 'occluded'],
}

const backendStateId = {
  far_too_high: 'far-high',
  too_high: 'too-high',
  correct_glidepath: 'correct',
  too_low: 'too-low',
  far_too_low: 'far-low',
  unknown: 'unknown',
}

const defaultMetadata = {
  // Aligned with backend default (audit B-CRIT-2): papi_24's height is
  // confirmed (467.609 m WGS84); papi_06's installation height is still
  // open as of 26/05. Users can switch via the dropdown.
  runwayId: 'papi_24',
  droneId: '',
  droneLatitude: '',
  droneLongitude: '',
  droneAltitudeM: '',
}

const translations = {
  en: {
    brand: {
      subtitle: 'PAPI Detection v1.0',
      company: 'Intersoft Electronics',
    },
    nav: {
      introduction: 'Introduction',
      liveDemo: 'Live Demo',
      insights: 'Insights',
    },
    intro: {
      eyebrow: 'Intersoft Electronics Services BV',
      title: 'Real-time PAPI detection and glidepath classification.',
      description:
        'A front-end prototype for testing model output, explaining lamp transitions, and presenting accuracy, speed, and robustness in one polished flow.',
      cta: 'Try It Out',
      scroll: 'Airport details',
      airportEyebrow: 'Airport context',
      airportTitle: 'Bodensee-Airport Friedrichshafen runway snapshot.',
      runwayNote: 'Runway 06/24, asphalt, 2,356 m (7,729 ft)',
      runwayDetails: 'Runway details',
      runwayDescription:
        'The project focuses on the single runway at Bodensee-Airport Friedrichshafen. The runway designation is 06/24 with an asphalt surface and a length of 2,356 meters (7,729 feet).',
      coordinates: 'Coordinates',
      elevation: 'Elevation',
    },
    live: {
      eyebrow: 'Live demo',
      title: 'Upload media, run backend inference, and inspect the detected PAPI unit.',
      upload: 'Upload media',
      uploadFolder: 'Upload folder',
      analyzing: 'Analyzing',
      runModel: 'Run backend model',
      previousFrame: 'Previous frame',
      nextFrame: 'Next frame',
      runway: 'Runway',
      droneId: 'Drone ID',
      latitude: 'Latitude',
      longitude: 'Longitude',
      altitude: 'Altitude m',
      optional: 'optional',
      metadata: 'metadata',
      demoScenarios: 'Demo scenarios',
      pauseLoop: 'Pause scenario playback',
      playLoop: 'Play scenario loop',
      auto: 'Auto',
      paused: 'Paused',
      detection: 'Detection confidence',
      latency: 'Processing time',
      droneAngle: 'Drone elevation angle',
      angleUnavailable: 'Angle unavailable',
      missingMetadata: 'missing metadata',
      backendInference: 'Backend inference running',
      dropTitle: 'Drag and drop an image or video',
      dropText: 'Or use the upload button above',
    },
    insights: {
      eyebrow: 'Insights',
      title: 'Accuracy, transitions, robustness, and speed without boring chart filler.',
      preparing: 'Preparing PDF',
      download: 'Download charts (PDF)',
      source: 'Inspired by visual forms from Data Viz Project',
      decoderTitle: 'PAPI state decoder',
      decoderText: 'All five legal outputs, their lamp pattern, and model evidence.',
      activeDecision: 'Active decision',
      compareState: 'Compare state',
      evidence: 'Evidence',
      highestScore: 'Highest model score in this frame',
      pointsBelow: 'points below the selected result',
      transitionTitle: 'Transition ribbon',
      transitionText: 'Each cell is one lamp across consecutive frames.',
      transitionDetected: 'Transition detected',
      frame: 'Frame',
      status: 'Status',
    },
    states: {
      'far-high': ['Far too high', 'Aircraft is well above glidepath'],
      'too-high': ['Too high', 'Slightly above the ideal angle'],
      correct: ['Correct glidepath', 'Stable 3 degree approach'],
      'too-low': ['Too low', 'Below desired approach path'],
      'far-low': ['Far too low', 'Immediate correction needed'],
      unknown: ['Unknown', 'Not enough lamps detected for a reliable PAPI state'],
    },
    status: {
      white: 'White',
      red: 'Red',
      transition: 'Transition',
      occluded: 'Occluded',
    },
    scenarios: {
      clean: ['Clean example', 'baseline', '2 white + 2 red = correct glidepath', 'Clear evening, steady camera'],
      transition: ['Transition pause', 'yellow/orange', '2 white + 2 red = correct glidepath', 'Lamp 2 changing from white to red'],
      'hard-case': ['Hard case', 'weather + occlusion', '1 white + 3 red = too low', 'Rain, shallow angle, partial occlusion'],
      edge: ['Edge device', 'limited hardware', '4 red = far too low', 'Low light, compressed stream'],
      backend: ['Backend result', 'live'],
    },
  },
  nl: {
    brand: {
      subtitle: 'PAPI-detectie v1.0',
      company: 'Intersoft Electronics',
    },
    nav: {
      introduction: 'Introductie',
      liveDemo: 'Live demo',
      insights: 'Inzichten',
    },
    intro: {
      eyebrow: 'Intersoft Electronics Services BV',
      title: 'Realtime PAPI-detectie en glidepath-classificatie.',
      description:
        'Een frontendprototype om modeloutput te testen, lampovergangen uit te leggen en nauwkeurigheid, snelheid en robuustheid helder te presenteren.',
      cta: 'Probeer het',
      scroll: 'Luchthavendetails',
      airportEyebrow: 'Luchthavencontext',
      airportTitle: 'Overzicht van de baan van Bodensee-Airport Friedrichshafen.',
      runwayNote: 'Baan 06/24, asfalt, 2.356 m (7.729 ft)',
      runwayDetails: 'Baangegevens',
      runwayDescription:
        'Het project richt zich op de enige baan van Bodensee-Airport Friedrichshafen. De baanaanduiding is 06/24, met asfaltverharding en een lengte van 2.356 meter (7.729 feet).',
      coordinates: 'Coordinaten',
      elevation: 'Hoogte',
    },
    live: {
      eyebrow: 'Live demo',
      title: 'Upload media, voer backend-inferentie uit en bekijk de gedetecteerde PAPI-unit.',
      upload: 'Media uploaden',
      uploadFolder: 'Map uploaden',
      analyzing: 'Analyseren',
      runModel: 'Backendmodel starten',
      previousFrame: 'Vorig frame',
      nextFrame: 'Volgend frame',
      runway: 'Baan',
      droneId: 'Drone-ID',
      latitude: 'Breedtegraad',
      longitude: 'Lengtegraad',
      altitude: 'Hoogte m',
      optional: 'optioneel',
      metadata: 'metadata',
      demoScenarios: 'Demoscenario’s',
      pauseLoop: 'Scenariolus pauzeren',
      playLoop: 'Scenariolus afspelen',
      auto: 'Auto',
      paused: 'Gepauzeerd',
      detection: 'Detectievertrouwen',
      latency: 'Verwerkingstijd',
      droneAngle: 'Elevatiehoek drone',
      angleUnavailable: 'Hoek niet beschikbaar',
      missingMetadata: 'metadata ontbreekt',
      backendInference: 'Backend-inferentie actief',
      dropTitle: 'Sleep een afbeelding of video hierheen',
      dropText: 'Of gebruik de uploadknop hierboven',
    },
    insights: {
      eyebrow: 'Inzichten',
      title: 'Nauwkeurigheid, overgangen, robuustheid en snelheid in duidelijke grafieken.',
      preparing: 'PDF voorbereiden',
      download: 'Grafieken downloaden (PDF)',
      source: 'Geinspireerd door vormen van Data Viz Project',
      decoderTitle: 'PAPI-statusdecoder',
      decoderText: 'Alle vijf geldige outputs, hun lamppatroon en modelbewijs.',
      activeDecision: 'Actieve beslissing',
      compareState: 'Status vergelijken',
      evidence: 'Bewijs',
      highestScore: 'Hoogste modelscore in dit frame',
      pointsBelow: 'punten onder de geselecteerde uitkomst',
      transitionTitle: 'Overgangslint',
      transitionText: 'Elke cel is een lamp over opeenvolgende frames.',
      transitionDetected: 'Overgang gedetecteerd',
      frame: 'Frame',
      status: 'Status',
    },
    states: {
      'far-high': ['Veel te hoog', 'Het toestel zit ruim boven het glijpad'],
      'too-high': ['Te hoog', 'Iets boven de ideale hoek'],
      correct: ['Correct glijpad', 'Stabiele nadering van 3 graden'],
      'too-low': ['Te laag', 'Onder het gewenste naderingspad'],
      'far-low': ['Veel te laag', 'Directe correctie nodig'],
      unknown: ['Onbekend', 'Niet genoeg lampen gedetecteerd voor een betrouwbare PAPI-status'],
    },
    status: {
      white: 'Wit',
      red: 'Rood',
      transition: 'Overgang',
      occluded: 'Afgeschermd',
    },
    scenarios: {
      clean: ['Schoon voorbeeld', 'basis', '2 wit + 2 rood = correct glijpad', 'Heldere avond, stabiele camera'],
      transition: ['Overgangspauze', 'geel/oranje', '2 wit + 2 rood = correct glijpad', 'Lamp 2 verandert van wit naar rood'],
      'hard-case': ['Moeilijk geval', 'weer + afscherming', '1 wit + 3 rood = te laag', 'Regen, lage hoek, gedeeltelijke afscherming'],
      edge: ['Edge-apparaat', 'beperkte hardware', '4 rood = veel te laag', 'Weinig licht, gecomprimeerde stream'],
      backend: ['Backendresultaat', 'live'],
    },
  },
  fr: {
    brand: {
      subtitle: 'Détection PAPI v1.0',
      company: 'Intersoft Electronics',
    },
    nav: {
      introduction: 'Introduction',
      liveDemo: 'Demo live',
      insights: 'Analyses',
    },
    intro: {
      eyebrow: 'Intersoft Electronics Services BV',
      title: 'Detection PAPI en temps reel et classification du plan de descente.',
      description:
        'Un prototype frontend pour tester la sortie du modele, expliquer les transitions des lampes et presenter precision, vitesse et robustesse clairement.',
      cta: 'Essayer',
      scroll: 'Details aeroport',
      airportEyebrow: 'Contexte aeroport',
      airportTitle: 'Apercu de la piste de Bodensee-Airport Friedrichshafen.',
      runwayNote: 'Piste 06/24, asphalte, 2 356 m (7 729 ft)',
      runwayDetails: 'Details de piste',
      runwayDescription:
        'Le projet se concentre sur la piste unique de Bodensee-Airport Friedrichshafen. La designation est 06/24, avec une surface en asphalte et une longueur de 2 356 metres (7 729 feet).',
      coordinates: 'Coordonnees',
      elevation: 'Altitude',
    },
    live: {
      eyebrow: 'Demo live',
      title: 'Importez un media, lancez l’inference backend et inspectez l’unite PAPI detectee.',
      upload: 'Importer media',
      uploadFolder: 'Importer dossier',
      analyzing: 'Analyse',
      runModel: 'Lancer le modele backend',
      previousFrame: 'Frame precedent',
      nextFrame: 'Frame suivant',
      runway: 'Piste',
      droneId: 'ID drone',
      latitude: 'Latitude',
      longitude: 'Longitude',
      altitude: 'Altitude m',
      optional: 'optionnel',
      metadata: 'metadonnees',
      demoScenarios: 'Scenarios demo',
      pauseLoop: 'Mettre la boucle en pause',
      playLoop: 'Lancer la boucle',
      auto: 'Auto',
      paused: 'Pause',
      detection: 'Confiance de détection',
      latency: 'Temps de traitement',
      droneAngle: 'Angle d’elevation drone',
      angleUnavailable: 'Angle indisponible',
      missingMetadata: 'metadonnees manquantes',
      backendInference: 'Inference backend en cours',
      dropTitle: 'Glissez une image ou une video',
      dropText: 'Ou utilisez le bouton d’import ci-dessus',
    },
    insights: {
      eyebrow: 'Analyses',
      title: 'Precision, transitions, robustesse et vitesse dans des graphiques clairs.',
      preparing: 'Preparation du PDF',
      download: 'Telecharger les graphiques (PDF)',
      source: 'Inspire des formes du Data Viz Project',
      decoderTitle: 'Decodeur d’etat PAPI',
      decoderText: 'Les cinq sorties valides, leur schema de lampes et la preuve du modele.',
      activeDecision: 'Decision active',
      compareState: 'Comparer l’etat',
      evidence: 'Preuve',
      highestScore: 'Score modele le plus eleve dans ce frame',
      pointsBelow: 'points sous le resultat selectionne',
      transitionTitle: 'Ruban de transition',
      transitionText: 'Chaque cellule represente une lampe sur des frames consecutifs.',
      transitionDetected: 'Transition detectee',
      frame: 'Frame',
      status: 'Etat',
    },
    states: {
      'far-high': ['Beaucoup trop haut', 'L’appareil est largement au-dessus du plan'],
      'too-high': ['Trop haut', 'Legerement au-dessus de l’angle ideal'],
      correct: ['Plan correct', 'Approche stable a 3 degres'],
      'too-low': ['Trop bas', 'Sous le plan d’approche souhaite'],
      'far-low': ['Beaucoup trop bas', 'Correction immediate necessaire'],
      unknown: ['Inconnu', 'Pas assez de lampes detectees pour un etat PAPI fiable'],
    },
    status: {
      white: 'Blanc',
      red: 'Rouge',
      transition: 'Transition',
      occluded: 'Masque',
    },
    scenarios: {
      clean: ['Exemple clair', 'base', '2 blancs + 2 rouges = plan correct', 'Soiree claire, camera stable'],
      transition: ['Pause transition', 'jaune/orange', '2 blancs + 2 rouges = plan correct', 'La lampe 2 passe du blanc au rouge'],
      'hard-case': ['Cas difficile', 'meteo + masquage', '1 blanc + 3 rouges = trop bas', 'Pluie, angle bas, masquage partiel'],
      edge: ['Appareil edge', 'materiel limite', '4 rouges = beaucoup trop bas', 'Faible lumiere, flux compresse'],
      backend: ['Resultat backend', 'live'],
    },
  },
}

const plotlyConfig = {
  responsive: true,
  displaylogo: false,
  modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
}

function translateState(state, copy) {
  const translated = copy.states[state.id]
  if (!translated) {
    return state
  }
  return { ...state, label: translated[0], description: translated[1] }
}

function translateScenario(scenario, copy) {
  const translated = copy.scenarios[scenario.id]
  if (!translated) {
    return scenario
  }
  return {
    ...scenario,
    label: translated[0],
    badge: scenario.id === 'backend' && scenario.logId ? scenario.badge : translated[1],
    summary: translated[2] ?? scenario.summary,
    condition: translated[3] ?? scenario.condition,
    angle: scenario.angle === translations.en.live.angleUnavailable ? copy.live.angleUnavailable : scenario.angle,
    angleSummary:
      scenario.angleSummary && !scenario.angleSummary.available
        ? {
            ...scenario.angleSummary,
            source: copy.live.missingMetadata,
          }
        : scenario.angleSummary,
  }
}

const plotlyPalette = {
  white: '#f8fbff',
  red: '#ff4545',
  transition: '#ffb11f',
  warn: '#f0a22f',
}

const scenarios = [
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
      fps: 58,
      latency: 17.2,
      boxConfidence: 98.1,
      globalConfidence: 96.8,
      transitionRecall: 91.4,
      edgeMemory: 412,
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
      fps: 54,
      latency: 19.6,
      boxConfidence: 96.3,
      globalConfidence: 89.7,
      transitionRecall: 94.8,
      edgeMemory: 418,
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
      fps: 46,
      latency: 24.9,
      boxConfidence: 85.6,
      globalConfidence: 81.2,
      transitionRecall: 87.3,
      edgeMemory: 436,
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
      fps: 39,
      latency: 28.4,
      boxConfidence: 91.9,
      globalConfidence: 93.4,
      transitionRecall: 89.1,
      edgeMemory: 306,
    },
    evidence: [1, 2, 5, 15, 77],
    box: { left: 66, top: 50, width: 20, height: 11 },
    environmentClass: 'night',
  },
]

const transitionFrames = [
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

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

function percent(value) {
  return Math.round(clamp(Number(value) || 0, 0, 1) * 100)
}

function lampPattern(lamps) {
  const labels = lamps.map((lamp) => {
    if (lamp.state === 'white') {
      return 'white'
    }
    if (lamp.state === 'red') {
      return 'red'
    }
    if (lamp.state === 'transition') {
      return 'transition'
    }
    return 'unknown'
  })
  return labels.join(' + ')
}

function isVideoFile(file) {
  return file.type.startsWith('video') || /\.(avi|mov|mp4|mkv|webm)$/i.test(file.name)
}

function isImageFile(file) {
  return file.type.startsWith('image') || /\.(jpg|jpeg|png|bmp|webp)$/i.test(file.name)
}

function fileDisplayPath(file) {
  return file.webkitRelativePath || file.name
}

function boxFromLamps(lamps, frameWidth, frameHeight) {
  const boxes = lamps.map((lamp) => lamp.bbox).filter(Boolean)
  if (!boxes.length || !frameWidth || !frameHeight) {
    return { left: 58, top: 45, width: 28, height: 17 }
  }

  const x1 = Math.min(...boxes.map((box) => box.x1))
  const y1 = Math.min(...boxes.map((box) => box.y1))
  const x2 = Math.max(...boxes.map((box) => box.x2))
  const y2 = Math.max(...boxes.map((box) => box.y2))
  const padX = frameWidth * 0.015
  const padY = frameHeight * 0.025

  return {
    left: clamp(((x1 - padX) / frameWidth) * 100, 0, 100),
    top: clamp(((y1 - padY) / frameHeight) * 100, 0, 100),
    width: clamp(((x2 - x1 + padX * 2) / frameWidth) * 100, 4, 100),
    height: clamp(((y2 - y1 + padY * 2) / frameHeight) * 100, 4, 100),
  }
}

function evidenceForState(stateId, confidence) {
  const selectedIndex = Math.max(
    0,
    legalStateCatalog.findIndex((state) => state.id === stateId),
  )
  return legalStateCatalog.map((_, index) => {
    if (stateId === 'unknown') {
      return index === 2 ? 20 : 10
    }
    return index === selectedIndex ? percent(confidence) : Math.max(1, 18 - Math.abs(index - selectedIndex) * 5)
  })
}

function scenarioFromBackendResult(result, context) {
  const stateId = backendStateId[result.global_state] ?? 'unknown'
  const activeState = stateCatalog.find((state) => state.id === stateId) ?? stateCatalog[stateCatalog.length - 1]
  const lamps = result.lamps.map((lamp) => ({
    id: lamp.index,
    status: lamp.state === 'unknown' ? 'occluded' : lamp.state,
    confidence: percent(lamp.confidence),
    transition: lamp.state === 'transition' ? percent(lamp.confidence) : Math.max(3, 100 - percent(lamp.confidence)),
    bbox: lamp.bbox,
  }))
  const angle = result.angle?.angle_available
    ? `${result.angle.elevation_angle_deg.toFixed(3)} deg`
    : 'Angle unavailable'
  const angleSummary = result.angle?.angle_available
    ? {
        available: true,
        value: result.angle.elevation_angle_deg.toFixed(3),
        source: result.angle.angle_source ?? 'metadata',
        note: result.angle.angle_note,
      }
    : {
        available: false,
        value: 'N/A',
        source: 'missing metadata',
        note: result.angle?.angle_note ?? 'GPS/altitude metadata was not available.',
      }
  const latency = Math.max(0, Number(result.processing_ms) || 0)

  return {
    id: 'backend',
    label: 'Backend result',
    badge: result.log_id ? `log ${result.log_id.slice(0, 8)}` : 'live',
    stateId,
    summary: `${lampPattern(result.lamps)} = ${activeState.label.toLowerCase()}`,
    frame: context.totalFrames > 1 ? `${context.frameLabel} of ${context.totalFrames}` : context.frameLabel,
    condition: angle,
    lamps,
    metrics: {
      fps: latency ? Number((1000 / latency).toFixed(1)) : 0,
      latency,
      boxConfidence: percent(result.confidence),
      globalConfidence: percent(result.confidence),
      transitionRecall: result.angle?.angle_available ? 100 : 0,
      edgeMemory: result.frame_count ?? 1,
    },
    evidence: evidenceForState(stateId, result.confidence),
    box: boxFromLamps(result.lamps, result.frame_width, result.frame_height),
    environmentClass: 'clear',
    artifactUrl: mediaUrl(result.artifact_url),
    artifactType: result.media_type,
    logId: result.log_id,
    angle: result.angle,
    angleSummary,
  }
}

// localStorage keys for the small persistence surface. Centralising them
// here keeps writes/reads in sync and makes them easy to grep.
const STORAGE_KEYS = {
  theme: 'papi.theme',
  language: 'papi.language',
}

// Read a localStorage key and validate against an allowlist. Falls back to
// the provided default for any read error (Safari private mode, SSR, etc.).
function readStoredChoice(key, allowed, fallback) {
  if (typeof window === 'undefined') return fallback
  try {
    const value = window.localStorage.getItem(key)
    return value && allowed.includes(value) ? value : fallback
  } catch {
    return fallback
  }
}

// Initial theme: persisted value -> system preference -> light. Computed
// once via lazy initializer so the App doesn't re-read localStorage on
// every render.
function initialTheme() {
  const stored = readStoredChoice(STORAGE_KEYS.theme, ['light', 'dark'], null)
  if (stored) return stored
  if (typeof window === 'undefined') return 'light'
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light'
}

// Initial language: persisted -> navigator.language two-letter prefix
// (when in our supported set) -> 'en'.
function initialLanguage() {
  const stored = readStoredChoice(
    STORAGE_KEYS.language,
    ['en', 'nl', 'fr'],
    null,
  )
  if (stored) return stored
  if (typeof navigator === 'undefined') return 'en'
  const detected = (navigator.language || '').slice(0, 2).toLowerCase()
  return ['en', 'nl', 'fr'].includes(detected) ? detected : 'en'
}

function App() {
  const [theme, setTheme] = useState(initialTheme)
  const [activeId, setActiveId] = useState('clean')
  // Default OFF so a jury demo presenter controls the carousel manually
  // (audit F-MAJ-3 — auto-cycling every 5.2s was disorienting on stage).
  const [isPlaying, setIsPlaying] = useState(false)
  const [media, setMedia] = useState(null)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const [backendScenario, setBackendScenario] = useState(null)
  const [backendFrames, setBackendFrames] = useState([])
  const [backendFrameIndex, setBackendFrameIndex] = useState(0)
  const [runways, setRunways] = useState([])
  const [metadata, setMetadata] = useState(defaultMetadata)
  const [analysisError, setAnalysisError] = useState('')
  const [analysisProgress, setAnalysisProgress] = useState('')
  const [language, setLanguage] = useState(initialLanguage)
  const insightsRef = useRef(null)
  const copy = translations[language]

  const activeScenarioRaw = useMemo(
    () => {
      if (activeId === 'backend' && backendScenario) {
        return backendScenario
      }
      return scenarios.find((scenario) => scenario.id === activeId) ?? scenarios[0]
    },
    [activeId, backendScenario],
  )

  const activeScenario = useMemo(
    () => translateScenario(activeScenarioRaw, copy),
    [activeScenarioRaw, copy],
  )

  const activeState = useMemo(
    () =>
      translateState(
        stateCatalog.find((state) => state.id === activeScenario.stateId) ?? stateCatalog[stateCatalog.length - 1],
        copy,
      ),
    [activeScenario, copy],
  )

  const plotTheme = useMemo(
    () =>
      theme === 'dark'
        ? {
            paper: 'rgba(0,0,0,0)',
            plot: 'rgba(255,255,255,0.04)',
            text: '#dbe6f2',
            strong: '#ffffff',
            muted: '#9cb0c4',
            grid: 'rgba(219, 230, 242, 0.16)',
            border: 'rgba(219, 230, 242, 0.18)',
          }
        : {
            paper: 'rgba(0,0,0,0)',
            plot: 'rgba(25,42,61,0.035)',
            text: '#192a3d',
            strong: '#0c1d2d',
            muted: '#5a6b7d',
            grid: 'rgba(25, 42, 61, 0.16)',
            border: 'rgba(25, 42, 61, 0.18)',
          },
    [theme],
  )

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    // Persist so the choice survives a page reload (regression
    // FE-MOD-CRIT-3 / papi-user-test-2026-05-28). Wrapped in try/catch
    // because some browsers (Safari private mode) throw on setItem.
    try {
      window.localStorage.setItem(STORAGE_KEYS.theme, theme)
    } catch {
      /* localStorage not available — accept the loss for this session. */
    }
  }, [theme])

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEYS.language, language)
    } catch {
      /* see above */
    }
  }, [language])

  useEffect(() => {
    let ignore = false

    fetchRunways()
      .then((items) => {
        if (!ignore) {
          setRunways(items)
        }
      })
      .catch((error) => {
        if (!ignore) {
          setAnalysisError(error.message)
        }
      })

    return () => {
      ignore = true
    }
  }, [])

  useEffect(() => {
    if (!isPlaying) {
      return undefined
    }

    const interval = window.setInterval(() => {
      setActiveId((currentId) => {
        const index = scenarios.findIndex((scenario) => scenario.id === currentId)
        return scenarios[(index + 1) % scenarios.length].id
      })
    }, 5200)

    return () => window.clearInterval(interval)
  }, [isPlaying])

  useEffect(() => {
    return () => {
      if (media?.url) {
        URL.revokeObjectURL(media.url)
      }
    }
  }, [media?.url])

  function handleMediaFiles(files) {
    const selectedFiles = Array.from(files ?? [])
    if (!selectedFiles.length) {
      return
    }

    const imageFiles = selectedFiles
      .filter(isImageFile)
      .sort((first, second) => fileDisplayPath(first).localeCompare(fileDisplayPath(second), undefined, { numeric: true }))
    const isFolderBatch = imageFiles.length > 1
    const file = isFolderBatch ? imageFiles[0] : selectedFiles[0]

    // Client-side validation: the <input accept="..."> attribute is only a
    // picker hint, not a hard filter. A user can still pick "All files" and
    // upload anything. Without this guard we'd generate a blob URL for the
    // wrong content type, briefly render e.g. a text file as if it were an
    // image, and only fail once the backend returned 400 (regression
    // USERTEST-MAJ-1, papi-user-test-2026-05-28).
    if (!isFolderBatch && !isImageFile(file) && !isVideoFile(file)) {
      setAnalysisError(
        `Unsupported file: ${file.name}. Upload an image or video file.`,
      )
      return
    }

    const url = URL.createObjectURL(file)

    setMedia((previous) => {
      if (previous?.url) {
        URL.revokeObjectURL(previous.url)
      }

      return {
        file,
        files: isFolderBatch ? imageFiles : null,
        name: isFolderBatch
          ? `${fileDisplayPath(imageFiles[0]).split('/')[0]} (${imageFiles.length} images)`
          : file.name,
        type: isFolderBatch ? 'folder' : isVideoFile(file) ? 'video' : 'image',
        url,
        annotatedUrl: null,
      }
    })
    setIsPlaying(false)
    setBackendScenario(null)
    setBackendFrames([])
    setBackendFrameIndex(0)
    setAnalysisError('')
    setAnalysisProgress('')
  }

  function handleMediaChange(event) {
    handleMediaFiles(event.target.files)
    event.target.value = ''
  }

  function selectBackendFrame(index) {
    if (!backendFrames.length) {
      return
    }

    const nextIndex = Math.min(Math.max(index, 0), backendFrames.length - 1)
    setBackendFrameIndex(nextIndex)
    setBackendScenario(backendFrames[nextIndex])
    setActiveId('backend')
    setIsPlaying(false)
  }

  async function handleDownloadCharts() {
    if (!insightsRef.current || isExporting) {
      return
    }

    setIsExporting(true)

    try {
      const { jsPDF } = await import('jspdf')
      const { Plotly } = await loadPlotlyBundle()
      const chartNodes = Array.from(
        insightsRef.current.querySelectorAll('.js-plotly-plot'),
      )

      if (!chartNodes.length) {
        return
      }

      const images = []
      for (const node of chartNodes) {
        const rect = node.getBoundingClientRect()
        const width = Math.max(1, Math.round(rect.width))
        const height = Math.max(1, Math.round(rect.height))
        const dataUrl = await Plotly.toImage(node, {
          format: 'png',
          width,
          height,
          scale: 2,
        })
        images.push({
          dataUrl,
          width,
          height,
          orientation: width >= height ? 'landscape' : 'portrait',
        })
      }

      const [first, ...rest] = images
      const pdf = new jsPDF({
        orientation: first.orientation,
        unit: 'px',
        format: [first.width, first.height],
      })
      pdf.addImage(first.dataUrl, 'PNG', 0, 0, first.width, first.height)
      rest.forEach((image) => {
        pdf.addPage([image.width, image.height], image.orientation)
        pdf.addImage(image.dataUrl, 'PNG', 0, 0, image.width, image.height)
      })
      pdf.save('papi-vision-insights.pdf')
    } catch (error) {
      console.error('PDF export failed', error)
    } finally {
      setIsExporting(false)
    }
  }

  function handleMetadataChange(field, value) {
    setMetadata((current) => ({ ...current, [field]: value }))
  }

  async function runBackendInference() {
    if (!media?.file || isAnalyzing) {
      return
    }

    setIsAnalyzing(true)
    setIsPlaying(false)
    setAnalysisError('')

    try {
      let bestScenario = null
      let nextBackendFrames = []

      if (media.type === 'folder') {
        const folderImages = media.files ?? []
        if (!folderImages.length) {
          throw new Error('No images were found in the selected folder.')
        }

        setAnalysisProgress(`Uploading ${folderImages.length} folder images to backend analysis`)
        const batch = await analyzeFrames(folderImages, metadata)
        nextBackendFrames = batch.results.map((result, index) =>
          scenarioFromBackendResult(result, {
            frameLabel: `Frame ${index + 1}`,
            totalFrames: batch.results.length,
          }),
        )
        bestScenario = nextBackendFrames[0]
      } else if (media.type === 'video') {
        setAnalysisProgress('Uploading video to backend video analysis')
        const result = await analyzeMedia(media.file, metadata)
        bestScenario = scenarioFromBackendResult(result, {
          frameLabel: `${result.frame_count ?? 0} labeled frames`,
          totalFrames: 1,
        })
      } else {
        setAnalysisProgress('Extracting frames')
        const frames = await extractFrameImages(media.file)
        let bestScore = -1

        for (const [index, frame] of frames.entries()) {
          setAnalysisProgress(`Analyzing frame ${index + 1}/${frames.length}`)
          const result = await analyzeFrame(frame.file, metadata)
          const scenario = scenarioFromBackendResult(result, {
            frameLabel: frame.label,
            totalFrames: frames.length,
          })
          const score = result.global_state === 'unknown' ? result.confidence : result.confidence + 1
          if (score >= bestScore) {
            bestScore = score
            bestScenario = scenario
          }
        }
      }

      if (!bestScenario) {
        throw new Error('No media was analyzed.')
      }

      setBackendFrames(nextBackendFrames)
      setBackendFrameIndex(0)
      setBackendScenario(bestScenario)
      setActiveId('backend')
      setMedia((current) =>
        current
          ? {
              ...current,
              annotatedUrl: bestScenario.artifactUrl,
              annotatedType: bestScenario.artifactType,
            }
          : current,
      )
      setAnalysisProgress('Analysis complete')
    } catch (error) {
      setAnalysisError(error.message)
      setAnalysisProgress('')
    } finally {
      setIsAnalyzing(false)
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <Link className="brand" to="/" aria-label="PAPI Vision dashboard">
          <span className="brand-logo" aria-hidden="true">
            <img
              className="logo-light"
              src="/intersoft-electronics-logo.svg"
              alt=""
            />
            <img
              className="logo-dark"
              src="/intersoft-electronics-logo-white-inverse.svg"
              alt=""
            />
          </span>
          <span className="brand-text">
            <strong>PAPI Vision</strong>
            <small>{copy.brand.subtitle}</small>
            <small className="brand-company">{copy.brand.company}</small>
          </span>
        </Link>

        <nav className="topnav" aria-label="Primary">
          <NavLink
            className={({ isActive }) => clsx('nav-link', isActive && 'active')}
            to="/"
            end
          >
            {copy.nav.introduction}
          </NavLink>
          <NavLink
            className={({ isActive }) => clsx('nav-link', isActive && 'active')}
            to="/live-demo"
          >
            {copy.nav.liveDemo}
          </NavLink>
          <NavLink
            className={({ isActive }) => clsx('nav-link', isActive && 'active')}
            to="/insights"
          >
            {copy.nav.insights}
          </NavLink>
        </nav>

        <div className="topbar-actions">
          <div className="language-switch" aria-label="Language">
            {['en', 'nl', 'fr'].map((option) => (
              <button
                className={clsx(option === language && 'active')}
                key={option}
                type="button"
                onClick={() => setLanguage(option)}
                aria-pressed={option === language}
              >
                {option.toUpperCase()}
              </button>
            ))}
          </div>
          <button
            className="icon-button"
            type="button"
            onClick={() => setTheme((current) => (current === 'dark' ? 'light' : 'dark'))}
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          >
            {theme === 'dark' ? <Sun size={19} /> : <Moon size={19} />}
          </button>
        </div>
      </header>

      <Routes>
        <Route path="/" element={<IntroductionPage copy={copy} />} />
        <Route
          path="/live-demo"
          element={
            <LiveDemoPage
              activeId={activeId}
              activeScenario={activeScenario}
              activeState={activeState}
              isAnalyzing={isAnalyzing}
              isPlaying={isPlaying}
              media={media}
              backendScenario={backendScenario}
              backendFrames={backendFrames}
              backendFrameIndex={backendFrameIndex}
              runways={runways}
              metadata={metadata}
              analysisError={analysisError}
              analysisProgress={analysisProgress}
              handleMediaFiles={handleMediaFiles}
              runBackendInference={runBackendInference}
              setActiveId={setActiveId}
              setIsPlaying={setIsPlaying}
              selectBackendFrame={selectBackendFrame}
              handleMediaChange={handleMediaChange}
              handleMetadataChange={handleMetadataChange}
              copy={copy}
            />
          }
        />
        <Route
          path="/insights"
          element={
            <InsightsPage
              activeScenario={activeScenario}
              plotTheme={plotTheme}
              insightsRef={insightsRef}
              isExporting={isExporting}
              onDownloadCharts={handleDownloadCharts}
              copy={copy}
            />
          }
        />
        <Route path="*" element={<IntroductionPage copy={copy} />} />
      </Routes>
      {/* CookieConsent removed per audit F-MAJ-4 — non-functional gimmick that
          obscured live-demo content (SMOKE-MAJ-1) and read as AI-generated for a
          B2B aviation safety demo. */}
    </main>
  )
}

function IntroductionPage({ copy }) {
  return (
    <section className="intro-hero">
      {/*
        Hero background — static hero.png poster. The earlier
        <video src="/Background-vid.mp4"> + onError -> <img> fallback
        attempt was removed because the LFS-declared video file was
        never committed; the wasted 206 fetch + brief flash before the
        fallback rendered were demo-visible noise (audit F-CRIT-1 /
        papi-user-test-2026-05-28 finding 3). When (if) the video
        lands in /public, restore the <video> element with the same
        onError fallback pattern.
      */}
      <img
        className="intro-video"
        src={heroPosterUrl}
        alt=""
        aria-hidden="true"
      />
      <div className="intro-hero-inner">
        <section className="intro-band">
          <div className="intro-copy">
            <p className="eyebrow">{copy.intro.eyebrow}</p>
            <h1>{copy.intro.title}</h1>
            <p className="intro-description">
              {copy.intro.description}
            </p>
            <div className="intro-actions">
              <Link className="cta-button" to="/live-demo">
                {copy.intro.cta}
              </Link>
            </div>
            <a className="scroll-cue" href="#airport-context" aria-label="Scroll to airport details">
              <span />
              <small>{copy.intro.scroll}</small>
            </a>
          </div>
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
              <p>
                {copy.intro.runwayDescription}
              </p>
              <div className="airport-meta">
                <div>
                  <span>{copy.intro.coordinates}</span>
                  <strong>47.67139 N, 9.51139 E</strong>
                </div>
                <div>
                  <span>{copy.intro.elevation}</span>
                  <strong>414 m AMSL</strong>
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
              <span className="map-caption">47.67139 N, 9.51139 E</span>
            </div>
          </div>
        </section>
      </div>
    </section>
  )
}

function LiveDemoPage({
  activeId,
  activeScenario,
  activeState,
  isAnalyzing,
  isPlaying,
  media,
  backendScenario,
  backendFrames,
  backendFrameIndex,
  runways,
  metadata,
  analysisError,
  analysisProgress,
  handleMediaFiles,
  runBackendInference,
  setActiveId,
  setIsPlaying,
  selectBackendFrame,
  handleMediaChange,
  handleMetadataChange,
  copy,
}) {
  const scenarioTabs = (backendScenario ? [backendScenario, ...scenarios] : scenarios).map((scenario) =>
    translateScenario(scenario, copy),
  )

  return (
    <section className="demo-section">
      <div className="section-heading">
        <div>
          <p className="eyebrow">{copy.live.eyebrow}</p>
          <h2>{copy.live.title}</h2>
        </div>
        <div className="demo-actions">
          <label className="upload-button">
            <Upload size={18} />
            <span>{media ? media.name : copy.live.upload}</span>
            <input accept="image/*,video/*" type="file" onChange={handleMediaChange} />
          </label>
          <label className="upload-button folder-upload">
            <FolderOpen size={18} />
            <span>{copy.live.uploadFolder}</span>
            <input
              accept="image/*"
              type="file"
              multiple
              webkitdirectory="true"
              directory=""
              onChange={handleMediaChange}
            />
          </label>
          <button
            className="primary-button"
            type="button"
            onClick={runBackendInference}
            disabled={!media || isAnalyzing}
          >
            <Zap size={18} />
            {isAnalyzing ? copy.live.analyzing : copy.live.runModel}
          </button>
        </div>
      </div>

      <div className="metadata-panel">
        <label>
          <span>{copy.live.runway}</span>
          <select
            value={metadata.runwayId}
            onChange={(event) => handleMetadataChange('runwayId', event.target.value)}
          >
            {(runways.length ? runways : [{ id: 'papi_24', label: 'PAPI 24' }]).map((runway) => (
              <option key={runway.id} value={runway.id}>
                {runway.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>{copy.live.droneId}</span>
          <input
            value={metadata.droneId}
            onChange={(event) => handleMetadataChange('droneId', event.target.value)}
            placeholder={copy.live.optional}
          />
        </label>
        <label>
          <span>{copy.live.latitude}</span>
          <input
            inputMode="decimal"
            value={metadata.droneLatitude}
            onChange={(event) => handleMetadataChange('droneLatitude', event.target.value)}
            placeholder={copy.live.metadata}
          />
        </label>
        <label>
          <span>{copy.live.longitude}</span>
          <input
            inputMode="decimal"
            value={metadata.droneLongitude}
            onChange={(event) => handleMetadataChange('droneLongitude', event.target.value)}
            placeholder={copy.live.metadata}
          />
        </label>
        <label>
          <span>{copy.live.altitude}</span>
          <input
            inputMode="decimal"
            value={metadata.droneAltitudeM}
            onChange={(event) => handleMetadataChange('droneAltitudeM', event.target.value)}
            placeholder={copy.live.metadata}
          />
        </label>
      </div>

      {(analysisError || analysisProgress) && (
        <div className={clsx('analysis-status', analysisError && 'error')}>
          {analysisError || analysisProgress}
        </div>
      )}

      <div className="scenario-tabs" role="tablist" aria-label={copy.live.demoScenarios}>
        {scenarioTabs.map((scenario) => (
          <button
            className={clsx(
              'scenario-tab',
              scenario.id === activeId && 'active',
              scenario.id !== 'backend' && 'scenario-tab--preset',
            )}
            key={scenario.id}
            type="button"
            onClick={() => {
              setActiveId(scenario.id)
              setIsPlaying(false)
            }}
          >
            <span>{scenario.label}</span>
            <small>{scenario.badge}</small>
            {scenario.id !== 'backend' && (
              <span className="scenario-tab__preset-badge" aria-label="Demo preset">
                DEMO
              </span>
            )}
          </button>
        ))}
        <button
          className="scenario-tab play-tab"
          type="button"
          onClick={() => setIsPlaying((current) => !current)}
          aria-label={isPlaying ? copy.live.pauseLoop : copy.live.playLoop}
        >
          {isPlaying ? <Pause size={17} /> : <Play size={17} />}
          <span>{isPlaying ? copy.live.auto : copy.live.paused}</span>
        </button>
      </div>

      <div className="live-grid">
        <motion.div
          className="frame-tool"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45 }}
        >
          <FrameStage
            scenario={activeScenario}
            media={media}
            analyzing={isAnalyzing}
            onFilesSelected={handleMediaFiles}
            backendFrames={backendFrames}
            backendFrameIndex={backendFrameIndex}
            onBackendFrameChange={selectBackendFrame}
            copy={copy}
          />
        </motion.div>

        <aside className="analysis-panel">
          <div className="state-summary">
            <span className="status-dot" style={{ '--dot-color': activeState.color }} />
            <div>
              <p>{activeScenario.summary}</p>
              <h3>{activeState.label}</h3>
              <small>{activeState.description}</small>
            </div>
          </div>

          <div className="lamp-list">
            {activeScenario.lamps.map((lamp) => (
              <LampCard key={lamp.id} lamp={lamp} copy={copy} />
            ))}
          </div>

          {/*
            Real metrics only (audit F-CRIT-2). Detection confidence and
            processing time come from the live backend payload via
            scenarioFromBackendResult. For preset scenarios the same fields
            carry the hardcoded demo values; the "DEMO" watermark on the
            scenario tab makes the source clear.
          */}
          <div className="metric-grid metric-grid--compact">
            <InlineMetric
              label={copy.live.detection}
              value={activeScenario.metrics.boxConfidence}
              suffix="%"
            />
            <InlineMetric
              label={copy.live.latency}
              value={activeScenario.metrics.latency}
              suffix=" ms"
            />
          </div>

          {activeScenario.angleSummary && (
            <div className={clsx('angle-readout', !activeScenario.angleSummary.available && 'unavailable')}>
              <span>{copy.live.droneAngle}</span>
              <strong>
                {activeScenario.angleSummary.value}
                {activeScenario.angleSummary.available && <small>deg</small>}
              </strong>
              <p>{activeScenario.angleSummary.source}</p>
            </div>
          )}
        </aside>
      </div>
    </section>
  )
}

function InsightsPage({ activeScenario, plotTheme, insightsRef, isExporting, onDownloadCharts, copy }) {
  return (
    <section className="insights-section">
      <div className="section-heading">
        <div>
          <p className="eyebrow">{copy.insights.eyebrow}</p>
          <h2>{copy.insights.title}</h2>
        </div>
        <div className="section-actions">
          <button
            className="secondary-button"
            type="button"
            onClick={onDownloadCharts}
            disabled={isExporting}
          >
            <Download size={18} />
            {isExporting ? copy.insights.preparing : copy.insights.download}
          </button>
          <span className="source-note">{copy.insights.source}</span>
        </div>
      </div>

      <div className="insight-grid" ref={insightsRef}>
        <GlobalStateDecoder scenario={activeScenario} plotTheme={plotTheme} copy={copy} />
        <TransitionRibbon activeScenario={activeScenario} plotTheme={plotTheme} copy={copy} />
      </div>
    </section>
  )
}

function InlineMetric({ label, value, suffix }) {
  return (
    <div className="inline-metric">
      <span>{label}</span>
      <strong>
        {value}
        <small>{suffix}</small>
      </strong>
    </div>
  )
}

function LampCard({ lamp, copy }) {
  const status = statusCopy[lamp.status]
  const label = copy.status[lamp.status] ?? status.label

  return (
    <div className={clsx('lamp-card', `lamp-${status.tone}`)}>
      <div className="lamp-preview">
        <span />
        <strong>Lamp {lamp.id}</strong>
      </div>
      <div>
        <p>{label}</p>
        <small>{lamp.confidence}% confidence</small>
      </div>
      <div className="transition-meter" aria-label={`${lamp.transition}% transition score`}>
        <span style={{ width: `${lamp.transition}%` }} />
      </div>
    </div>
  )
}

function FrameStage({
  scenario,
  media,
  analyzing,
  onFilesSelected,
  backendFrames,
  backendFrameIndex,
  onBackendFrameChange,
  copy,
}) {
  const [isDragActive, setIsDragActive] = useState(false)
  const displayMedia = scenario.artifactUrl
    ? { type: scenario.artifactType ?? 'image', url: scenario.artifactUrl }
    : media?.annotatedUrl
      ? { type: media.annotatedType ?? 'image', url: media.annotatedUrl }
      : media
  const isAnnotatedExport = Boolean(scenario.artifactUrl || media?.annotatedUrl)
  const canNavigateFrames = backendFrames.length > 1
  const boxStyle = {
    left: `${scenario.box.left}%`,
    top: `${scenario.box.top}%`,
    width: `${scenario.box.width}%`,
    height: `${scenario.box.height}%`,
  }

  const handleDrop = (event) => {
    event.preventDefault()
    setIsDragActive(false)
    if (event.dataTransfer?.files?.length) {
      onFilesSelected?.(event.dataTransfer.files)
    }
  }

  const handleDragOver = (event) => {
    event.preventDefault()
    setIsDragActive(true)
  }

  const handleDragLeave = () => {
    setIsDragActive(false)
  }

  return (
    <div className={clsx('frame-stage', `frame-${scenario.environmentClass}`)}>
      <div className="frame-toolbar">
        <div className="frame-title">
          <span>{scenario.frame}</span>
          <span>{scenario.condition}</span>
        </div>
        {canNavigateFrames && (
          <div className="frame-nav-controls" aria-label="Backend frame navigation">
            <button
              type="button"
              onClick={() => onBackendFrameChange?.(backendFrameIndex - 1)}
              disabled={backendFrameIndex === 0}
              aria-label={copy.live.previousFrame}
            >
              <ChevronLeft size={16} />
            </button>
            <strong>
              {backendFrameIndex + 1}/{backendFrames.length}
            </strong>
            <button
              type="button"
              onClick={() => onBackendFrameChange?.(backendFrameIndex + 1)}
              disabled={backendFrameIndex === backendFrames.length - 1}
              aria-label={copy.live.nextFrame}
            >
              <ChevronRight size={16} />
            </button>
          </div>
        )}
      </div>

      <div
        className="video-surface"
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {displayMedia?.type === 'video' ? (
          <video src={displayMedia.url} autoPlay muted loop playsInline controls />
        ) : displayMedia?.type === 'image' ? (
          <img src={displayMedia.url} alt="Uploaded PAPI test frame" />
        ) : (
          <DropzonePlaceholder isDragActive={isDragActive} copy={copy} />
        )}

        {displayMedia && !isAnnotatedExport && (
          <>
            <div className="scan-grid" />
            <div className="target-box" style={boxStyle}>
              <span className="box-label">PAPI {scenario.metrics.boxConfidence}%</span>
              <div className="lamp-overlay">
                {scenario.lamps.map((lamp) => (
                  <span
                    className={clsx('overlay-lamp', `overlay-${lamp.status}`)}
                    key={lamp.id}
                    title={`Lamp ${lamp.id}: ${copy.status[lamp.status] ?? statusCopy[lamp.status].label}`}
                  />
                ))}
              </div>
            </div>
            {scenario.environmentClass === 'storm' && <div className="weather-layer" />}
          </>
        )}
        {analyzing && (
          <div className="analyzing-layer">
            <Radar size={34} />
            <span>{copy.live.backendInference}</span>
          </div>
        )}
      </div>
    </div>
  )
}

function DropzonePlaceholder({ isDragActive, copy }) {
  return (
    <div className={clsx('dropzone-placeholder', isDragActive && 'active')}>
      <div className="dropzone-card">
        <Upload size={28} />
        <strong>{copy.live.dropTitle}</strong>
        <span>{copy.live.dropText}</span>
      </div>
    </div>
  )
}

function GlobalStateDecoder({ scenario, plotTheme, copy }) {
  const [hovered, setHovered] = useState(null)
  const activeIndex = legalStateCatalog.findIndex((state) => state.id === scenario.stateId)
  const selectedIndex = hovered ?? activeIndex
  const readoutIndex = selectedIndex >= 0 ? selectedIndex : 2
  const translatedStates = legalStateCatalog.map((state) => translateState(state, copy))
  const selectedState = translatedStates[readoutIndex]
  const selectedPattern = stateLampPatterns[selectedState.id]
  const topEvidence = Math.max(...scenario.evidence)

  return (
    <article className="viz-card state-decoder-card">
      <div className="viz-heading">
        <Gauge size={18} />
        <div>
          <h3>{copy.insights.decoderTitle}</h3>
          <p>{copy.insights.decoderText}</p>
        </div>
      </div>

      <div className="decoder-layout">
        <div className="decoder-list" aria-label="PAPI state evidence list">
          {translatedStates.map((state, index) => {
            const evidence = scenario.evidence[index]
            const pattern = stateLampPatterns[state.id]
            const isActive = index === activeIndex
            const isSelected = index === readoutIndex

            return (
              <button
                className={clsx('decoder-row', isActive && 'active', isSelected && 'selected')}
                key={state.id}
                style={{ '--state-color': state.color, '--evidence': `${evidence}%` }}
                type="button"
                onMouseEnter={() => setHovered(index)}
                onMouseLeave={() => setHovered(null)}
                onFocus={() => setHovered(index)}
              >
                <span className="decoder-position">{index + 1}</span>
                <span className="decoder-label">
                  <strong>{state.label}</strong>
                  <small>{state.pattern}</small>
                </span>
                <span className="decoder-lamps" aria-hidden="true">
                  {pattern.map((status, lampIndex) => (
                    <i className={`decoder-lamp decoder-${status}`} key={`${state.id}-${lampIndex}`} />
                  ))}
                </span>
                <span className="decoder-evidence">
                  <span>
                    <i />
                  </span>
                  <strong>{evidence}%</strong>
                </span>
              </button>
            )
          })}
        </div>

        <div className="decoder-plot">
          <PapiDecisionPlot
            activeIndex={activeIndex}
            evidence={scenario.evidence}
            plotTheme={plotTheme}
            selectedIndex={readoutIndex}
            setHovered={setHovered}
            states={translatedStates}
            copy={copy}
          />
        </div>
      </div>

      <div className="decoder-readout" style={{ '--state-color': selectedState.color }}>
        <div>
          <span className="decoder-chip">
            {selectedIndex === activeIndex ? copy.insights.activeDecision : copy.insights.compareState}
          </span>
          <strong>{selectedState.label}</strong>
          <p>{selectedState.description}</p>
        </div>
        <div className="decoder-big-lamps" aria-label={`${selectedState.pattern} pattern`}>
          {selectedPattern.map((status, index) => (
            <span className={`decoder-${status}`} key={`${selectedState.id}-large-${index}`} />
          ))}
        </div>
        <div className="decoder-rule">
          <span>{copy.insights.evidence}</span>
          <strong>{scenario.evidence[readoutIndex]}%</strong>
          <small>
            {scenario.evidence[readoutIndex] === topEvidence
              ? copy.insights.highestScore
              : `${topEvidence - scenario.evidence[readoutIndex]} ${copy.insights.pointsBelow}`}
          </small>
        </div>
      </div>
    </article>
  )
}

function LazyPlot(props) {
  const [PlotComponent, setPlotComponent] = useState(null)
  const [loadError, setLoadError] = useState(null)

  useEffect(() => {
    let isMounted = true
    loadPlotlyBundle()
      .then(({ Plot }) => {
        if (isMounted) {
          setPlotComponent(() => Plot)
        }
      })
      .catch((error) => {
        // Surface the failure instead of swallowing it (audit SMOKE-CRIT-3).
        // A blank chart with no console error is undebuggable on stage.
        console.error('Failed to load Plotly bundle:', error)
        if (isMounted) {
          setLoadError(error)
        }
      })
    return () => {
      isMounted = false
    }
  }, [])

  if (loadError) {
    return (
      <div className="plot-loading plot-error" role="alert">
        <strong>Chart unavailable</strong>
        <small>{loadError.message || 'Plotly bundle failed to load.'}</small>
      </div>
    )
  }
  if (!PlotComponent) {
    return <div className="plot-loading" aria-hidden />
  }
  return <PlotComponent {...props} />
}

function PapiDecisionPlot({ evidence, activeIndex, selectedIndex, setHovered, plotTheme, states, copy }) {
  return (
    <LazyPlot
      className="plotly-chart"
      config={plotlyConfig}
      data={[
        {
          type: 'bar',
          orientation: 'h',
          x: evidence,
          y: states.map((state) => state.short),
          customdata: states.map((state) => [state.label, state.pattern]),
          marker: {
            color: states.map((state, index) =>
              index === activeIndex ? state.color : 'rgba(145, 161, 154, 0.38)',
            ),
            line: {
              color: states.map((state, index) =>
                index === selectedIndex ? state.color : 'rgba(0,0,0,0)',
              ),
              width: states.map((_, index) => (index === selectedIndex ? 3 : 0)),
            },
          },
          text: evidence.map((value) => `${value}%`),
          textposition: 'outside',
          hovertemplate:
            `<b>%{customdata[0]}</b><br>%{customdata[1]}<br>${copy.insights.evidence}: %{x}%<extra></extra>`,
        },
      ]}
      layout={{
        autosize: true,
        height: 250,
        margin: { l: 54, r: 34, t: 8, b: 34 },
        paper_bgcolor: plotTheme.paper,
        plot_bgcolor: plotTheme.plot,
        font: { color: plotTheme.text, family: 'Poppins, Segoe UI, sans-serif' },
        bargap: 0.34,
        xaxis: {
          range: [0, 100],
          ticksuffix: '%',
          gridcolor: plotTheme.grid,
          zeroline: false,
          fixedrange: true,
        },
        yaxis: {
          autorange: 'reversed',
          tickfont: { color: plotTheme.muted },
          fixedrange: true,
        },
        showlegend: false,
      }}
      onHover={(event) => setHovered(event.points[0].pointIndex)}
      onUnhover={() => setHovered(null)}
      useResizeHandler
    />
  )
}

function TransitionRibbon({ activeScenario, plotTheme, copy }) {
  const [hovered, setHovered] = useState(2)
  const frame = transitionFrames[hovered]
  const statusToValue = { white: 0, transition: 1, red: 2 }
  const lampLabels = ['Lamp 1', 'Lamp 2', 'Lamp 3', 'Lamp 4']
  const frameLabels = transitionFrames.map((_, index) => `F${218 + index}`)
  const z = lampLabels.map((_, lampIndex) =>
    transitionFrames.map((frameStates) => statusToValue[frameStates[lampIndex]]),
  )
  const hoverText = lampLabels.map((lamp, lampIndex) =>
    transitionFrames.map((frameStates, frameIndex) => {
      const status = copy.status[frameStates[lampIndex]] ?? statusCopy[frameStates[lampIndex]].label
      return `${lamp}<br>${copy.insights.frame} ${218 + frameIndex}<br>${copy.insights.status}: ${status}`
    }),
  )

  return (
    <article className="viz-card transition-card">
      <div className="viz-heading">
        <Activity size={18} />
        <div>
          <h3>{copy.insights.transitionTitle}</h3>
          <p>{copy.insights.transitionText}</p>
        </div>
      </div>

      <div className="plotly-panel">
        <LazyPlot
          className="plotly-chart"
          config={plotlyConfig}
          data={[
            {
              type: 'heatmap',
              x: frameLabels,
              y: lampLabels,
              z,
              text: hoverText,
              hovertemplate: '%{text}<extra></extra>',
              colorscale: [
                [0, plotlyPalette.white],
                [0.35, plotlyPalette.white],
                [0.5, plotlyPalette.transition],
                [0.68, plotlyPalette.transition],
                [0.84, plotlyPalette.red],
                [1, plotlyPalette.red],
              ],
              showscale: false,
              xgap: 6,
              ygap: 6,
            },
          ]}
          layout={{
            autosize: true,
            height: 206,
            margin: { l: 56, r: 14, t: 6, b: 38 },
            paper_bgcolor: plotTheme.paper,
            plot_bgcolor: plotTheme.paper,
            font: { color: plotTheme.text, family: 'Poppins, Segoe UI, sans-serif' },
            xaxis: { fixedrange: true, tickfont: { color: plotTheme.muted } },
            yaxis: {
              autorange: 'reversed',
              fixedrange: true,
              tickfont: { color: plotTheme.muted },
            },
            shapes: [
              {
                type: 'rect',
                xref: 'x',
                yref: 'paper',
                x0: frameLabels[hovered],
                x1: frameLabels[hovered],
                y0: 0,
                y1: 1,
                line: { color: plotlyPalette.warn, width: 3 },
              },
            ],
          }}
          onHover={(event) => {
            const nextIndex = frameLabels.indexOf(event.points[0].x)
            if (nextIndex >= 0) {
              setHovered(nextIndex)
            }
          }}
          useResizeHandler
        />
      </div>

      <div className="ribbon-readout">
        <span>
          {copy.insights.frame} {218 + hovered}
        </span>
        <strong>
          {frame.filter((status) => status === 'transition').length > 0
            ? copy.insights.transitionDetected
            : activeScenario.summary}
        </strong>
      </div>
    </article>
  )
}

export default App
