import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { loadPlotlyBundle } from '../lib/plotlyBundle'

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

function todayLabel() {
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date())
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

function addFooter(pdf, pageNo) {
  const { width, height } = pageSize(pdf)
  pdf.setDrawColor(...BORDER)
  pdf.line(PAGE_MARGIN, height - 14, width - PAGE_MARGIN, height - 14)
  pdf.setFont('helvetica', 'normal')
  pdf.setFontSize(8)
  setTextColor(pdf, MUTED)
  pdf.text('PAPI Vision student project - educational prototype, not certified for operational airport use.', PAGE_MARGIN, height - 7)
  pdf.text(String(pageNo), width - PAGE_MARGIN, height - 7, { align: 'right' })
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

  addFooter(pdf, 1)
}

function addOverviewPage(pdf, logoDataUrl, pageNo) {
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

  addFooter(pdf, pageNo)
}

function chartDescription(title, fallback) {
  const normalized = `${title} ${fallback ?? ''}`.toLowerCase()
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

function addChartPage(pdf, logoDataUrl, image, index, pageNo) {
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
  addFooter(pdf, pageNo)
}

// Insights PDF export: captures every rendered Plotly chart under ``insightsRef``
// into a branded report PDF with a cover, explanatory pages, and chart evidence.
// Fully self-contained — no dependency on the analysis / media state — so it lives
// in its own hook that the useAnalysis orchestrator and the InsightsPage both read
// through the Live-Demo context.
export function useChartExport(copy) {
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
      addOverviewPage(pdf, logoDataUrl, 2)
      images.forEach((image, index) => {
        addChartPage(pdf, logoDataUrl, image, index, index + 3)
      })
      pdf.save('papi-vision-insights-report.pdf')
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
