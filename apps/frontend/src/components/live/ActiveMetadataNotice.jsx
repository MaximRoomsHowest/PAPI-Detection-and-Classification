import { Info, X } from 'lucide-react'
import { useLiveDemo } from '../../context/liveDemoContext'

// Persistent notice that surfaces ACTIVE manual telemetry / a telemetry file whenever media
// is loaded — even after the angle came back available and the MetadataPrompt has hidden.
// Without it, telemetry the user supplied for an earlier upload silently overrides the next
// image's own GPS (backend priority: telemetry file > manual fields > embedded EXIF) with
// nothing on screen indicating it is still in effect (audit P1: hidden metadata can silently
// corrupt later angle scoring). Clearing it here removes both inputs in one action.
export function ActiveMetadataNotice({ copy }) {
  const { media, metadataFile, droneTelemetry, setMetadataFile, setDroneTelemetry } = useLiveDemo()

  const hasManualTelemetry = Boolean(
    droneTelemetry.latitude.trim() &&
      droneTelemetry.longitude.trim() &&
      droneTelemetry.altitudeM.trim(),
  )
  if (!media || (!metadataFile && !hasManualTelemetry)) {
    return null
  }

  const clearAll = () => {
    setMetadataFile(null)
    setDroneTelemetry({ latitude: '', longitude: '', altitudeM: '' })
  }

  return (
    <div className="active-metadata-notice" role="status">
      <Info size={15} aria-hidden="true" />
      <span className="active-metadata-notice__text">{copy.live.activeMetadataNotice}</span>
      {metadataFile && <span className="active-metadata-notice__file mono">{metadataFile.name}</span>}
      <button type="button" className="active-metadata-notice__clear" onClick={clearAll}>
        <X size={14} aria-hidden="true" />
        <span>{copy.live.activeMetadataClear}</span>
      </button>
    </div>
  )
}
