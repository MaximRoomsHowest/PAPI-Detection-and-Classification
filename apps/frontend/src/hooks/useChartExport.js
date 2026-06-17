import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { loadPlotlyBundle } from '../lib/plotlyBundle'
import {
  FAA_DEFAULT_SET_ANGLES_DEG,
  stableTransitionEvents,
  summarizeSession,
  transitionAngleSummary,
} from '../lib/insightsTransforms'

const PAGE = {
  orientation: 'landscape',
  unit: 'mm',
  format: 'a4',
}
const PAGE_MARGIN = 16
const BRAND_BLUE = [0, 66, 110]
const TEXT = [22, 34, 48]
const MUTED = [92, 107, 125]
const BORDER = [218, 225, 232]

const TIMESTAMP_FORMAT = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
})

function todayLabel() {
  return TIMESTAMP_FORMAT.format(new Date())
}

function pageSize(pdf) {
  return {
    width: pdf.internal.pageSize.getWidth(),
    height: pdf.internal.pageSize.getHeight(),
  }
}

function setTextColor(pdf, color) {
  pdf.setTextColor(color[0], color[1], color[2])
}

function addWrappedText(pdf, text, x, y, maxWidth, lineHeight, options = {}) {
  const lines = pdf.splitTextToSize(text, maxWidth)
  pdf.text(lines, x, y, options)
  return y + lines.length * lineHeight
}

async function imageToDataUrl(path, maxWidthPx = 520) {
  try {
    const response = await fetch(path)
    if (!response.ok) return null
    const blob = await response.blob()
    const objectUrl = URL.createObjectURL(blob)
    try {
      const image = await new Promise((resolve, reject) => {
        const img = new Image()
        img.onload = () => resolve(img)
        img.onerror = reject
        img.src = objectUrl
      })
      // An SVG without intrinsic dimensions reports naturalWidth 0 in some
      // browsers — scaling by it would paint a 1px smear into the PDF header.
      // Fall back to the text branding instead.
      if (!image.naturalWidth || !image.naturalHeight) return null
      const scale = Math.min(1, maxWidthPx / image.naturalWidth)
      const canvas = document.createElement('canvas')
      canvas.width = Math.max(1, Math.round(image.naturalWidth * scale))
      canvas.height = Math.max(1, Math.round(image.naturalHeight * scale))
      const context = canvas.getContext('2d')
      if (!context) return null
      context.drawImage(image, 0, 0, canvas.width, canvas.height)
      return canvas.toDataURL('image/png')
    } finally {
      URL.revokeObjectURL(objectUrl)
    }
  } catch {
    return null
  }
}

function addReportHeader(pdf, logoDataUrl, sectionTitle) {
  const { width } = pageSize(pdf)
  if (logoDataUrl) {
    pdf.addImage(logoDataUrl, 'PNG', PAGE_MARGIN, 8, 42, 14)
  } else {
    setTextColor(pdf, BRAND_BLUE)
    pdf.setFont('helvetica', 'bold')
    pdf.setFontSize(11)
    pdf.text('INTERSOFT ELECTRONICS', PAGE_MARGIN, 16)
  }
  setTextColor(pdf, MUTED)
  pdf.setFont('helvetica', 'normal')
  pdf.setFontSize(9)
  pdf.text(sectionTitle, width - PAGE_MARGIN, 16, { align: 'right' })
  pdf.setDrawColor(...BORDER)
  pdf.line(PAGE_MARGIN, 25, width - PAGE_MARGIN, 25)
}

// All footers are stamped in ONE final pass so every page can carry a real
// "page X / Y" — the total is only known once the data tables (which paginate
// by content length) have been laid out.
function stampFooters(pdf) {
  const total = pdf.getNumberOfPages()
  for (let page = 1; page <= total; page += 1) {
    pdf.setPage(page)
    const { width, height } = pageSize(pdf)
    pdf.setDrawColor(...BORDER)
    pdf.line(PAGE_MARGIN, height - 14, width - PAGE_MARGIN, height - 14)
    pdf.setFont('helvetica', 'normal')
    pdf.setFontSize(8)
    setTextColor(pdf, MUTED)
    pdf.text('PAPI Vision - educational prototype, not certified for operational airport use.', PAGE_MARGIN, height - 7)
    pdf.text(`${page} / ${total}`, width - PAGE_MARGIN, height - 7, { align: 'right' })
  }
}

function addCoverPage(pdf, logoDataUrl) {
  const { width, height } = pageSize(pdf)
  pdf.setFillColor(247, 250, 252)
  pdf.rect(0, 0, width, height, 'F')
  pdf.setFillColor(...BRAND_BLUE)
  pdf.rect(0, 0, 9, height, 'F')

  if (logoDataUrl) {
    pdf.addImage(logoDataUrl, 'PNG', PAGE_MARGIN + 4, 18, 58, 19)
  }

  setTextColor(pdf, BRAND_BLUE)
  pdf.setFont('helvetica', 'bold')
  pdf.setFontSize(26)
  pdf.text('PAPI Vision Insights Report', PAGE_MARGIN + 4, 62)

  setTextColor(pdf, TEXT)
  pdf.setFontSize(14)
  pdf.text('Detection, lamp-state interpretation, and elevation-angle analysis', PAGE_MARGIN + 4, 74)

  setTextColor(pdf, MUTED)
  pdf.setFont('helvetica', 'normal')
  pdf.setFontSize(11)
  pdf.text(`Generated ${todayLabel()}`, PAGE_MARGIN + 4, 88)

  pdf.setFillColor(255, 255, 255)
  pdf.setDrawColor(...BORDER)
  pdf.roundedRect(PAGE_MARGIN + 4, 105, width - PAGE_MARGIN * 2 - 8, 47, 3, 3, 'FD')
  pdf.setFont('helvetica', 'bold')
  pdf.setFontSize(12)
  setTextColor(pdf, TEXT)
  pdf.text('Document purpose', PAGE_MARGIN + 12, 119)
  pdf.setFont('helvetica', 'normal')
  pdf.setFontSize(10)
  addWrappedText(
    pdf,
    'This report turns the live demo results into a readable handout: what was detected, how lamp colours relate to approach state, where transition evidence appears, and how model/session metrics should be interpreted.',
    PAGE_MARGIN + 12,
    130,
    width - PAGE_MARGIN * 2 - 24,
    5,
  )
}

function addOverviewPage(pdf, logoDataUrl) {
  pdf.addPage(PAGE.format, PAGE.orientation)
  addReportHeader(pdf, logoDataUrl, 'Report overview')
  const { width } = pageSize(pdf)
  let y = 42
  setTextColor(pdf, BRAND_BLUE)
  pdf.setFont('helvetica', 'bold')
  pdf.setFontSize(18)
  pdf.text('How to read this report', PAGE_MARGIN, y)

  const sections = [
    ['Lamp colour state', 'Each PAPI lamp is shown as red, white, transition, obscured, or inferred. Inferred lamps are calculated from the elevation angle when exactly one lamp is missing and the geometry is reliable.'],
    ['Elevation angle', 'Angle values come from drone telemetry or manual metadata and the selected runway geometry. They explain where the drone was relative to the PAPI installation.'],
    ['Transitions', 'Transition charts show red-to-white or white-to-red changes across video or frame sequences. These are useful for validating set-angle behaviour.'],
    ['Model and session metrics', 'Confidence and distribution charts summarise how strongly the model detected the lamps in the current session and across logged backend results.'],
  ]

  y += 18
  sections.forEach(([title, body]) => {
    pdf.setFont('helvetica', 'bold')
    pdf.setFontSize(11)
    setTextColor(pdf, TEXT)
    pdf.text(title, PAGE_MARGIN, y)
    pdf.setFont('helvetica', 'normal')
    pdf.setFontSize(9.5)
    setTextColor(pdf, MUTED)
    y = addWrappedText(pdf, body, PAGE_MARGIN, y + 6, width - PAGE_MARGIN * 2, 4.8)
    y += 7
  })
}

// --- Data pages (session summary + transition events) -------------------------

// English verdict labels for the report body (the UI localizes; the handout
// keeps one fixed wording — same decision as the rest of the report text).
const VERDICT_LABELS = {
  far_too_low: 'Far too low',
  too_low: 'Too low',
  correct_glidepath: 'Correct glidepath',
  too_high: 'Too high',
  far_too_high: 'Far too high',
  unknown: 'No verdict',
}

const FAA_NOTE =
  `FAA default set angles (${FAA_DEFAULT_SET_ANGLES_DEG.map((a) => `${a.toFixed(2)}°`).join(' / ')}) ` +
  'are shown for reference only — EDNY\'s commissioned per-lamp values are pending, so compare ' +
  'sorted values, never slot-by-slot.'

// Minimal paginating table: fixed column widths, header redrawn on every page
// break. Hand-rolled on purpose — no extra dependency for four columns.
function drawDataTable(pdf, logoDataUrl, sectionTitle, columns, rows, startY) {
  const { height } = pageSize(pdf)
  let y = startY

  const drawHead = () => {
    pdf.setFont('helvetica', 'bold')
    pdf.setFontSize(8.5)
    setTextColor(pdf, MUTED)
    let x = PAGE_MARGIN
    for (const column of columns) {
      pdf.text(column.label.toUpperCase(), column.align === 'right' ? x + column.width : x, y, column.align === 'right' ? { align: 'right' } : undefined)
      x += column.width + 4
    }
    y += 2.5
    pdf.setDrawColor(...BORDER)
    pdf.line(PAGE_MARGIN, y, x - 4, y)
    y += 5
  }

  drawHead()
  for (const row of rows) {
    if (y > height - 24) {
      pdf.addPage(PAGE.format, PAGE.orientation)
      addReportHeader(pdf, logoDataUrl, sectionTitle)
      y = 38
      drawHead()
    }
    pdf.setFont('helvetica', row.bold ? 'bold' : 'normal')
    pdf.setFontSize(9)
    setTextColor(pdf, row.bold ? TEXT : MUTED)
    let x = PAGE_MARGIN
    row.cells.forEach((cell, index) => {
      const column = columns[index]
      pdf.text(String(cell ?? '—'), column.align === 'right' ? x + column.width : x, y, column.align === 'right' ? { align: 'right' } : undefined)
      x += column.width + 4
    })
    y += 6
  }
  return y
}

function addSessionSummaryPage(pdf, logoDataUrl, session) {
  pdf.addPage(PAGE.format, PAGE.orientation)
  addReportHeader(pdf, logoDataUrl, 'Session summary')
  const { width } = pageSize(pdf)

  setTextColor(pdf, BRAND_BLUE)
  pdf.setFont('helvetica', 'bold')
  pdf.setFontSize(15)
  pdf.text('Session summary', PAGE_MARGIN, 39)

  // Left column: the session facts.
  const summary = session.summary
  const elevation =
    summary.elevationMin !== null
      ? `${summary.elevationMin.toFixed(2)}° – ${summary.elevationMax.toFixed(2)}°`
      : '—'
  const facts = [
    ['Source', session.sourceLabel ?? 'Live session'],
    ...(session.logId ? [['Log ID', session.logId]] : []),
    ...(session.createdAt ? [['Captured', session.createdAt]] : []),
    ['Runway', session.runwayLabel ?? summary.runwayId ?? '—'],
    ['Model', session.modelLabel ?? '—'],
    ['Transition method', session.transitionMethod ?? '—'],
    ['Analyses', String(summary.analysisCount)],
    ['Frames analysed', String(summary.frameCount)],
    ['Elevation sweep', elevation],
    ['Angle source', session.angleSourceLabel ?? summary.angleSource ?? '—'],
    ['Lights crossed red↔white', `${summary.lampsCrossed} / ${summary.totalLamps}`],
  ]
  let y = 50
  for (const [label, value] of facts) {
    pdf.setFont('helvetica', 'normal')
    pdf.setFontSize(9)
    setTextColor(pdf, MUTED)
    pdf.text(label, PAGE_MARGIN, y)
    pdf.setFont('helvetica', 'bold')
    pdf.setFontSize(10)
    setTextColor(pdf, TEXT)
    pdf.text(String(value), PAGE_MARGIN + 52, y)
    y += 7.4
  }

  // Right column: one line per analysed result (file — verdict, confidence).
  const rightX = width / 2 + 8
  pdf.setFont('helvetica', 'bold')
  pdf.setFontSize(10)
  setTextColor(pdf, TEXT)
  pdf.text('Analysed media', rightX, 50)
  let resultY = 58
  for (const result of session.results.slice(0, 10)) {
    const verdict = VERDICT_LABELS[result.global_state] ?? result.global_state ?? '—'
    const confidence = Number.isFinite(result.confidence) ? ` (${Math.round(result.confidence * 100)}%)` : ''
    pdf.setFont('helvetica', 'normal')
    pdf.setFontSize(9)
    setTextColor(pdf, MUTED)
    resultY = addWrappedText(
      pdf,
      `${result.original_filename ?? 'analysis'} — ${verdict}${confidence}`,
      rightX,
      resultY,
      width - rightX - PAGE_MARGIN,
      4.6,
    )
    resultY += 2.6
  }
  if (session.results.length > 10) {
    pdf.text(`… and ${session.results.length - 10} more`, rightX, resultY)
  }

  // The commissioning numbers: measured transition angle per light.
  let tableY = Math.max(y, resultY) + 8
  pdf.setFont('helvetica', 'bold')
  pdf.setFontSize(12)
  setTextColor(pdf, BRAND_BLUE)
  pdf.text('Measured transition angles', PAGE_MARGIN, tableY)
  tableY += 7
  const rows = session.angleSummary.map((entry) => ({
    cells: [
      `Light ${entry.lampIndex}`,
      entry.settledAngle !== null ? `${entry.settledAngle.toFixed(2)}°` : '—',
      entry.bandMin !== null ? `${entry.bandMin.toFixed(2)}° – ${entry.bandMax.toFixed(2)}°` : '—',
      String(entry.flips),
    ],
  }))
  const endY = drawDataTable(
    pdf,
    logoDataUrl,
    'Session summary',
    [
      { label: 'Light', width: 30 },
      { label: 'Measured crossing', width: 44, align: 'right' },
      { label: 'Blend zone', width: 56, align: 'right' },
      { label: 'Flips logged', width: 30, align: 'right' },
    ],
    rows,
    tableY,
  )
  pdf.setFont('helvetica', 'normal')
  pdf.setFontSize(8.5)
  setTextColor(pdf, MUTED)
  addWrappedText(pdf, FAA_NOTE, PAGE_MARGIN, endY + 3, width - PAGE_MARGIN * 2, 4.2)
}

function addTransitionEventsPages(pdf, logoDataUrl, transitions) {
  if (!transitions.length) {
    return
  }
  pdf.addPage(PAGE.format, PAGE.orientation)
  addReportHeader(pdf, logoDataUrl, 'Transition events')
  setTextColor(pdf, BRAND_BLUE)
  pdf.setFont('helvetica', 'bold')
  pdf.setFontSize(15)
  pdf.text('Transition events', PAGE_MARGIN, 39)
  setTextColor(pdf, MUTED)
  pdf.setFont('helvetica', 'normal')
  pdf.setFontSize(9)
  pdf.text('Every tracked red↔white switch, grouped per light in frame order.', PAGE_MARGIN, 46)

  const hasModelEvents = transitions.some((event) => event.method === 'model')
  const columns = [
    { label: 'Light', width: 24 },
    { label: 'Angle', width: 26, align: 'right' },
    { label: 'Direction', width: 50 },
    { label: 'Frame', width: 22, align: 'right' },
    ...(hasModelEvents ? [{ label: 'Duration (frames)', width: 36, align: 'right' }] : []),
    { label: 'Reading', width: 46 },
  ]
  const sorted = transitions.toSorted(
    (a, b) => a.lamp_index - b.lamp_index || a.frame_index - b.frame_index,
  )
  const rows = sorted.map((event) => ({
    cells: [
      `Light ${event.lamp_index}`,
      Number.isFinite(event.elevation_angle_deg) ? `${event.elevation_angle_deg.toFixed(2)}°` : '—',
      `${event.from_state} -> ${event.to_state}`,
      String(event.frame_index),
      ...(hasModelEvents
        ? [Number.isFinite(event.duration_frames) ? String(event.duration_frames) : '—']
        : []),
      event.to_state === 'white' ? 'climb-through' : 'reversal',
    ],
  }))
  drawDataTable(pdf, logoDataUrl, 'Transition events', columns, rows, 54)
}

function chartDescription(title, fallback) {
  const normalized = `${title} ${fallback ?? ''}`.toLowerCase()
  // Order matters: "measured transition angle" must not fall into the generic
  // 'transition' branch, nor "lamp state over the sweep" into the 'state' one.
  if (normalized.includes('measured')) {
    return 'The commissioning view: where each lamp actually crossed red-white (dot), its blend zone (whiskers), against the FAA default set angles (dotted reference lines; commissioned values pending).'
  }
  if (normalized.includes('band') || normalized.includes('sweep')) {
    return 'Each row is one lamp, coloured by its detected state on every analysed frame; flicker appears as thin stripes inside the blend zone. Triangles mark the logged flips.'
  }
  if (normalized.includes('redness')) {
    return 'Shows measured red-channel intensity against real elevation angle for each lamp. A strong drop usually indicates the lamp changing from red to white.'
  }
  if (normalized.includes('elevation')) {
    return 'Shows the drone viewing angle over processed frames, which helps validate whether the sequence follows the expected approach geometry.'
  }
  if (normalized.includes('transition')) {
    return 'Summarises red-white lamp changes and their timing/angle evidence across the analysed media.'
  }
  if (normalized.includes('state')) {
    return 'Summarises how often each lamp was classified as red, white, transition, obscured, or inferred in this session.'
  }
  if (normalized.includes('confidence')) {
    return 'Shows model confidence so low-confidence or difficult frames are visible in the exported report.'
  }
  if (normalized.includes('model')) {
    return 'Provides aggregate model and dataset context for the detector used by the live analysis.'
  }
  return 'Chart exported from the PAPI Vision Insights page with the active session context.'
}

function chartTitleFor(node, index) {
  const container = node.closest('.angle-chart, .insight-card, article, section') ?? node.parentElement
  const heading = container?.querySelector('h3, h4')
  return heading?.textContent?.trim() || `Insight chart ${index + 1}`
}

function addChartPage(pdf, logoDataUrl, image, index) {
  pdf.addPage(PAGE.format, PAGE.orientation)
  addReportHeader(pdf, logoDataUrl, 'Insights evidence')
  const { width, height } = pageSize(pdf)
  const title = image.title
  const description = chartDescription(title, image.description)

  setTextColor(pdf, BRAND_BLUE)
  pdf.setFont('helvetica', 'bold')
  pdf.setFontSize(15)
  pdf.text(`${index + 1}. ${title}`, PAGE_MARGIN, 39)

  setTextColor(pdf, MUTED)
  pdf.setFont('helvetica', 'normal')
  pdf.setFontSize(9)
  const textBottom = addWrappedText(pdf, description, PAGE_MARGIN, 48, width - PAGE_MARGIN * 2, 4.5)

  const chartTop = Math.max(62, textBottom + 5)
  const chartWidth = width - PAGE_MARGIN * 2
  const chartHeight = height - chartTop - 22
  const scale = Math.min(chartWidth / image.width, chartHeight / image.height)
  const renderedWidth = image.width * scale
  const renderedHeight = image.height * scale
  const x = PAGE_MARGIN + (chartWidth - renderedWidth) / 2

  pdf.setDrawColor(...BORDER)
  pdf.roundedRect(PAGE_MARGIN, chartTop - 2, chartWidth, chartHeight + 4, 2, 2)
  pdf.addImage(image.dataUrl, 'PNG', x, chartTop, renderedWidth, renderedHeight)
}

// Insights PDF export: a branded report with a cover, a how-to-read page, the
// SESSION DATA pages (session summary + measured transition angles + the full
// transition-events table), and one evidence page per rendered chart.
//
// ``sessionRef`` is an optional ref the orchestrator (useAnalysis) keeps
// pointed at { results, runways, selectedRunwayId } — read once at export time
// so the hook stays decoupled from analysis re-renders. Without it the report
// degrades to the chart-pages-only form.
//
// The report BODY is intentionally English-only: it is a client-facing handout
// (Intersoft Electronics) with a fixed reference wording, unlike the UI which
// follows the active locale. Only the toasts/errors around the export localize.
export function useChartExport(copy, sessionRef) {
  const [isExporting, setIsExporting] = useState(false)
  const [exportError, setExportError] = useState('')
  const insightsRef = useRef(null)

  // Drop any stale PDF-export banner when the locale switches so it never
  // lingers in the previous language (was App's onSelectLanguage job before the
  // provider owned this state). Guarded set-state during render (the React
  // "storing information from previous renders" pattern) instead of an effect,
  // so the stale message never paints.
  const [prevCopy, setPrevCopy] = useState(copy)
  if (prevCopy !== copy) {
    setPrevCopy(copy)
    if (exportError) setExportError('')
  }

  async function handleDownloadCharts() {
    if (!insightsRef.current || isExporting) {
      return
    }

    setIsExporting(true)
    setExportError('')

    try {
      const { jsPDF } = await import('jspdf')
      const { Plotly } = await loadPlotlyBundle()
      const chartNodes = Array.from(
        insightsRef.current.querySelectorAll('.js-plotly-plot'),
      )

      if (!chartNodes.length) {
        // No rendered charts to capture — tell the user instead of silently
        // doing nothing (audit F06/F07).
        setExportError(copy.insights.downloadUnavailable)
        return
      }

      const images = []
      for (const [index, node] of chartNodes.entries()) {
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
          title: chartTitleFor(node, index),
          description: node.closest('section, article, .insight-card')?.querySelector('p')?.textContent?.trim(),
          orientation: width >= height ? 'landscape' : 'portrait',
        })
      }

      const pdf = new jsPDF({
        orientation: PAGE.orientation,
        unit: PAGE.unit,
        format: PAGE.format,
      })
      const logoDataUrl = await imageToDataUrl('/intersoft-electronics-logo.svg')
      addCoverPage(pdf, logoDataUrl)
      addOverviewPage(pdf, logoDataUrl)

      // Session data pages — the numbers, not just chart screenshots. Read once
      // at export time; every value is a real backend field or a transform of it.
      const session = sessionRef?.current
      if (session?.results?.length) {
        const { results, runways = [], selectedRunwayId } = session
        const first = results[0]
        const runwayId = first?.runway_id ?? selectedRunwayId
        const transitions = stableTransitionEvents(results)
        addSessionSummaryPage(pdf, logoDataUrl, {
          results,
          summary: summarizeSession(results),
          angleSummary: transitionAngleSummary(results),
          sourceLabel: session.sourceLabel,
          logId: session.logId,
          createdAt: session.createdAt,
          runwayLabel: runways.find((runway) => runway.id === runwayId)?.label ?? runwayId,
          modelLabel: first?.model_label ?? first?.model_id ?? null,
          transitionMethod: first?.transition_method ?? null,
          angleSourceLabel: first?.angle?.angle_source ?? null,
        })
        addTransitionEventsPages(
          pdf,
          logoDataUrl,
          transitions.filter(
            (event) => Number.isInteger(event?.lamp_index) && event.lamp_index >= 1 && event.lamp_index <= 4,
          ),
        )
      }

      images.forEach((image, index) => {
        addChartPage(pdf, logoDataUrl, image, index)
      })
      stampFooters(pdf)
      pdf.save(`papi-vision-insights-report-${new Date().toISOString().slice(0, 10)}.pdf`)
      toast.success(copy.insights.downloadReady)
    } catch (error) {
      console.error('PDF export failed', error)
      setExportError(copy.insights.downloadFailed)
      toast.error(copy.insights.downloadFailed)
    } finally {
      setIsExporting(false)
    }
  }

  return { insightsRef, isExporting, exportError, setExportError, handleDownloadCharts }
}
