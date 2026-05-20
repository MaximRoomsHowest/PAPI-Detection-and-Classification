import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, NavLink, Route, Routes } from 'react-router-dom'
import { motion } from 'framer-motion'
import createPlotlyComponentFactory from 'react-plotly.js/factory'
import Plotly from 'plotly.js/lib/core'
import bar from 'plotly.js/lib/bar'
import heatmap from 'plotly.js/lib/heatmap'
import {
  Activity,
  Cpu,
  Crosshair,
  Download,
  Gauge,
  Moon,
  Pause,
  Play,
  Radar,
  Sun,
  Upload,
  Video,
  Zap,
} from 'lucide-react'
import clsx from 'clsx'
import './App.css'

Plotly.register([bar, heatmap])

const createPlotlyComponent =
  createPlotlyComponentFactory.default ?? createPlotlyComponentFactory
const Plot = createPlotlyComponent(Plotly)

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
]

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
}

const plotlyConfig = {
  responsive: true,
  displaylogo: false,
  modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
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

const pipeline = [
  { label: 'Frame input', value: 'image, video, or stream', icon: Video },
  { label: 'PAPI detector', value: 'bounding box + confidence', icon: Crosshair },
  { label: 'Lamp classifier', value: 'white, red, transition', icon: Activity },
  { label: 'State aggregator', value: '5 glidepath states', icon: Gauge },
  { label: 'Edge runtime', value: 'low latency export target', icon: Cpu },
]

function App() {
  const [theme, setTheme] = useState('light')
  const [activeId, setActiveId] = useState('clean')
  const [isPlaying, setIsPlaying] = useState(true)
  const [media, setMedia] = useState(null)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const insightsRef = useRef(null)

  const activeScenario = useMemo(
    () => scenarios.find((scenario) => scenario.id === activeId) ?? scenarios[0],
    [activeId],
  )

  const activeState = useMemo(
    () => stateCatalog.find((state) => state.id === activeScenario.stateId),
    [activeScenario],
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
  }, [theme])

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
    const file = files?.[0]
    if (!file) {
      return
    }

    const url = URL.createObjectURL(file)
    setMedia((previous) => {
      if (previous?.url) {
        URL.revokeObjectURL(previous.url)
      }

      return {
        name: file.name,
        type: file.type.startsWith('video') ? 'video' : 'image',
        url,
      }
    })
    setIsPlaying(false)
  }

  function handleMediaChange(event) {
    handleMediaFiles(event.target.files)
  }

  async function handleDownloadCharts() {
    if (!insightsRef.current || isExporting) {
      return
    }

    setIsExporting(true)

    try {
      const { jsPDF } = await import('jspdf')
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

  function runMockInference() {
    setIsAnalyzing(true)
    setIsPlaying(false)
    window.setTimeout(() => {
      setActiveId('transition')
      setIsAnalyzing(false)
    }, 900)
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
            <small>AI detection prototype</small>
            <small className="brand-company">
              On your radar
              <span>Intersoft Electronics</span>
            </small>
          </span>
        </Link>

        <nav className="topnav" aria-label="Primary">
          <NavLink
            className={({ isActive }) => clsx('nav-link', isActive && 'active')}
            to="/"
            end
          >
            Introduction
          </NavLink>
          <NavLink
            className={({ isActive }) => clsx('nav-link', isActive && 'active')}
            to="/live-demo"
          >
            Live Demo
          </NavLink>
          <NavLink
            className={({ isActive }) => clsx('nav-link', isActive && 'active')}
            to="/insights"
          >
            Insights
          </NavLink>
        </nav>

        <button
          className="icon-button"
          type="button"
          onClick={() => setTheme((current) => (current === 'dark' ? 'light' : 'dark'))}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
        >
          {theme === 'dark' ? <Sun size={19} /> : <Moon size={19} />}
        </button>
      </header>

      <Routes>
        <Route path="/" element={<IntroductionPage activeScenario={activeScenario} />} />
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
              handleMediaFiles={handleMediaFiles}
              runMockInference={runMockInference}
              setActiveId={setActiveId}
              setIsPlaying={setIsPlaying}
              handleMediaChange={handleMediaChange}
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
            />
          }
        />
        <Route path="*" element={<IntroductionPage activeScenario={activeScenario} />} />
      </Routes>
    </main>
  )
}

function IntroductionPage({ activeScenario }) {
  const videoRef = useRef(null)

  const ensurePlayback = () => {
    const video = videoRef.current
    if (!video || !video.paused) {
      return
    }

    const playPromise = video.play()
    if (playPromise?.catch) {
      playPromise.catch(() => {})
    }
  }

  useEffect(() => {
    ensurePlayback()

    const handleVisibility = () => {
      if (!document.hidden) {
        ensurePlayback()
      }
    }

    document.addEventListener('visibilitychange', handleVisibility)
    return () => document.removeEventListener('visibilitychange', handleVisibility)
  }, [])

  return (
    <section className="intro-hero">
      <video
        ref={videoRef}
        className="intro-video"
        src="/Background-vid.mp4"
        autoPlay
        muted
        loop
        playsInline
        preload="auto"
        onLoadedData={ensurePlayback}
        onPause={ensurePlayback}
        onEnded={ensurePlayback}
        aria-hidden="true"
      />
      <div className="intro-hero-inner">
        <section className="intro-band">
          <div className="intro-copy">
            <p className="eyebrow">Intersoft Electronics Services BV</p>
            <h1>Real-time PAPI detection and glidepath classification.</h1>
            <p>
              A front-end prototype for testing model output, explaining lamp transitions,
              and presenting accuracy, speed, and robustness in one polished flow.
            </p>
            <div className="intro-actions">
              <Link className="cta-button" to="/live-demo">
                Try It Out
              </Link>
            </div>
          </div>

          <div className="hero-metrics" aria-label="Current run summary">
            <MetricTile icon={Gauge} label="Live FPS" value={activeScenario.metrics.fps} suffix="fps" />
            <MetricTile
              icon={Zap}
              label="Latency"
              value={activeScenario.metrics.latency}
              suffix="ms"
            />
            <MetricTile
              icon={Crosshair}
              label="Box confidence"
              value={activeScenario.metrics.boxConfidence}
              suffix="%"
            />
          </div>
        </section>

        <section className="workflow-strip" aria-label="Model workflow">
          {pipeline.map((step) => (
            <div className="workflow-step" key={step.label}>
              <step.icon size={18} />
              <span>{step.label}</span>
              <small>{step.value}</small>
            </div>
          ))}
        </section>

        <section className="airport-section">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Airport context</p>
              <h2>Bodensee-Airport Friedrichshafen runway snapshot.</h2>
            </div>
            <span className="source-note">Runway 06/24, asphalt, 2,356 m (7,729 ft)</span>
          </div>

          <div className="airport-grid">
            <div className="airport-card">
              <h3>Runway details</h3>
              <p>
                The project focuses on the single runway at Bodensee-Airport Friedrichshafen. The
                runway designation is 06/24 with an asphalt surface and a length of 2,356 meters
                (7,729 feet).
              </p>
              <div className="airport-meta">
                <div>
                  <span>Coordinates</span>
                  <strong>47.67139 N, 9.51139 E</strong>
                </div>
                <div>
                  <span>Elevation</span>
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
  handleMediaFiles,
  runMockInference,
  setActiveId,
  setIsPlaying,
  handleMediaChange,
}) {
  return (
    <section className="demo-section">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Live demo</p>
          <h2>Upload media, run a mocked inference, and inspect the detected PAPI unit.</h2>
        </div>
        <div className="demo-actions">
          <label className="upload-button">
            <Upload size={18} />
            <span>{media ? media.name : 'Upload media'}</span>
            <input accept="image/*,video/*" type="file" onChange={handleMediaChange} />
          </label>
          <button className="primary-button" type="button" onClick={runMockInference}>
            <Zap size={18} />
            {isAnalyzing ? 'Analyzing' : 'Run mock model'}
          </button>
        </div>
      </div>

      <div className="scenario-tabs" role="tablist" aria-label="Demo scenarios">
        {scenarios.map((scenario) => (
          <button
            className={clsx('scenario-tab', scenario.id === activeId && 'active')}
            key={scenario.id}
            type="button"
            onClick={() => {
              setActiveId(scenario.id)
              setIsPlaying(false)
            }}
          >
            <span>{scenario.label}</span>
            <small>{scenario.badge}</small>
          </button>
        ))}
        <button
          className="scenario-tab play-tab"
          type="button"
          onClick={() => setIsPlaying((current) => !current)}
          aria-label={isPlaying ? 'Pause scenario playback' : 'Play scenario loop'}
        >
          {isPlaying ? <Pause size={17} /> : <Play size={17} />}
          <span>{isPlaying ? 'Auto' : 'Paused'}</span>
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
              <LampCard key={lamp.id} lamp={lamp} />
            ))}
          </div>

          <div className="metric-grid">
            <InlineMetric label="Detection" value={activeScenario.metrics.boxConfidence} suffix="%" />
            <InlineMetric label="Global state" value={activeScenario.metrics.globalConfidence} suffix="%" />
            <InlineMetric label="Transitions" value={activeScenario.metrics.transitionRecall} suffix="%" />
            <InlineMetric label="Edge memory" value={activeScenario.metrics.edgeMemory} suffix="MB" />
          </div>
        </aside>
      </div>
    </section>
  )
}

function InsightsPage({ activeScenario, plotTheme, insightsRef, isExporting, onDownloadCharts }) {
  return (
    <section className="insights-section">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Insights</p>
          <h2>Accuracy, transitions, robustness, and speed without boring chart filler.</h2>
        </div>
        <div className="section-actions">
          <button
            className="secondary-button"
            type="button"
            onClick={onDownloadCharts}
            disabled={isExporting}
          >
            <Download size={18} />
            {isExporting ? 'Preparing PDF' : 'Download charts (PDF)'}
          </button>
          <span className="source-note">Inspired by visual forms from Data Viz Project</span>
        </div>
      </div>

      <div className="insight-grid" ref={insightsRef}>
        <GlobalStateDecoder scenario={activeScenario} plotTheme={plotTheme} />
        <TransitionRibbon activeScenario={activeScenario} plotTheme={plotTheme} />
      </div>
    </section>
  )
}

function MetricTile({ icon: Icon, label, value, suffix }) {
  return (
    <div className="metric-tile">
      <Icon size={18} />
      <span>{label}</span>
      <strong>
        {value}
        <small>{suffix}</small>
      </strong>
    </div>
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

function LampCard({ lamp }) {
  const status = statusCopy[lamp.status]

  return (
    <div className={clsx('lamp-card', `lamp-${status.tone}`)}>
      <div className="lamp-preview">
        <span />
        <strong>Lamp {lamp.id}</strong>
      </div>
      <div>
        <p>{status.label}</p>
        <small>{lamp.confidence}% confidence</small>
      </div>
      <div className="transition-meter" aria-label={`${lamp.transition}% transition score`}>
        <span style={{ width: `${lamp.transition}%` }} />
      </div>
    </div>
  )
}

function FrameStage({ scenario, media, analyzing, onFilesSelected }) {
  const [isDragActive, setIsDragActive] = useState(false)
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
        <span>{scenario.frame}</span>
        <span>{scenario.condition}</span>
      </div>

      <div
        className="video-surface"
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {media?.type === 'video' ? (
          <video src={media.url} autoPlay muted loop playsInline controls />
        ) : media?.type === 'image' ? (
          <img src={media.url} alt="Uploaded PAPI test frame" />
        ) : (
          <DropzonePlaceholder isDragActive={isDragActive} />
        )}

        {media && (
          <>
            <div className="scan-grid" />
            <div className="target-box" style={boxStyle}>
              <span className="box-label">PAPI {scenario.metrics.boxConfidence}%</span>
              <div className="lamp-overlay">
                {scenario.lamps.map((lamp) => (
                  <span
                    className={clsx('overlay-lamp', `overlay-${lamp.status}`)}
                    key={lamp.id}
                    title={`Lamp ${lamp.id}: ${statusCopy[lamp.status].label}`}
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
            <span>Mock inference running</span>
          </div>
        )}
      </div>
    </div>
  )
}

function DropzonePlaceholder({ isDragActive }) {
  return (
    <div className={clsx('dropzone-placeholder', isDragActive && 'active')}>
      <div className="dropzone-card">
        <Upload size={28} />
        <strong>Drag and drop an image or video</strong>
        <span>Or use the upload button above</span>
      </div>
    </div>
  )
}

function SyntheticRunway() {
  return (
    <div className="synthetic-runway" aria-label="Synthetic runway frame">
      <div className="sky-layer" />
      <div className="horizon-line" />
      <div className="runway">
        <span />
        <span />
        <span />
      </div>
      <div className="runway-markings">
        {Array.from({ length: 8 }).map((_, index) => (
          <span key={index} />
        ))}
      </div>
      <div className="approach-lights">
        {Array.from({ length: 18 }).map((_, index) => (
          <i key={index} />
        ))}
      </div>
      <div className="synthetic-papi">
        <span />
        <span />
        <span />
        <span />
      </div>
    </div>
  )
}

function GlobalStateDecoder({ scenario, plotTheme }) {
  const [hovered, setHovered] = useState(null)
  const activeIndex = stateCatalog.findIndex((state) => state.id === scenario.stateId)
  const selectedIndex = hovered ?? activeIndex
  const selectedState = stateCatalog[selectedIndex]
  const selectedPattern = stateLampPatterns[selectedState.id]
  const topEvidence = Math.max(...scenario.evidence)

  return (
    <article className="viz-card state-decoder-card">
      <div className="viz-heading">
        <Gauge size={18} />
        <div>
          <h3>PAPI state decoder</h3>
          <p>All five legal outputs, their lamp pattern, and model evidence.</p>
        </div>
      </div>

      <div className="decoder-layout">
        <div className="decoder-list" aria-label="PAPI state evidence list">
          {stateCatalog.map((state, index) => {
            const evidence = scenario.evidence[index]
            const pattern = stateLampPatterns[state.id]
            const isActive = index === activeIndex
            const isSelected = index === selectedIndex

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
            selectedIndex={selectedIndex}
            setHovered={setHovered}
          />
        </div>
      </div>

      <div className="decoder-readout" style={{ '--state-color': selectedState.color }}>
        <div>
          <span className="decoder-chip">
            {selectedIndex === activeIndex ? 'Active decision' : 'Compare state'}
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
          <span>Evidence</span>
          <strong>{scenario.evidence[selectedIndex]}%</strong>
          <small>
            {scenario.evidence[selectedIndex] === topEvidence
              ? 'Highest model score in this frame'
              : `${topEvidence - scenario.evidence[selectedIndex]} points below the selected result`}
          </small>
        </div>
      </div>
    </article>
  )
}

function PapiDecisionPlot({ evidence, activeIndex, selectedIndex, setHovered, plotTheme }) {
  return (
    <Plot
      className="plotly-chart"
      config={plotlyConfig}
      data={[
        {
          type: 'bar',
          orientation: 'h',
          x: evidence,
          y: stateCatalog.map((state) => state.short),
          customdata: stateCatalog.map((state) => [state.label, state.pattern]),
          marker: {
            color: stateCatalog.map((state, index) =>
              index === activeIndex ? state.color : 'rgba(145, 161, 154, 0.38)',
            ),
            line: {
              color: stateCatalog.map((state, index) =>
                index === selectedIndex ? state.color : 'rgba(0,0,0,0)',
              ),
              width: stateCatalog.map((_, index) => (index === selectedIndex ? 3 : 0)),
            },
          },
          text: evidence.map((value) => `${value}%`),
          textposition: 'outside',
          hovertemplate:
            '<b>%{customdata[0]}</b><br>%{customdata[1]}<br>Model evidence: %{x}%<extra></extra>',
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

function TransitionRibbon({ activeScenario, plotTheme }) {
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
      const status = statusCopy[frameStates[lampIndex]].label
      return `${lamp}<br>Frame ${218 + frameIndex}<br>Status: ${status}`
    }),
  )

  return (
    <article className="viz-card transition-card">
      <div className="viz-heading">
        <Activity size={18} />
        <div>
          <h3>Transition ribbon</h3>
          <p>Each cell is one lamp across consecutive frames.</p>
        </div>
      </div>

      <div className="plotly-panel">
        <Plot
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
        <span>Frame {218 + hovered}</span>
        <strong>
          {frame.filter((status) => status === 'transition').length > 0
            ? 'Transition detected'
            : activeScenario.summary}
        </strong>
      </div>
    </article>
  )
}

export default App
