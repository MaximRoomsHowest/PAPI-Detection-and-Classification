import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { loadPlotlyBundle } from '../lib/plotlyBundle'

// Insights PDF export: captures every rendered Plotly chart under ``insightsRef``
// into a multi-page PDF. Fully self-contained — no dependency on the analysis /
// media state — so it lives in its own hook that the useAnalysis orchestrator and
// the InsightsPage both read through the Live-Demo context.
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
