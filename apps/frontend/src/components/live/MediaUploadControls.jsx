import { FolderOpen, Upload } from 'lucide-react'
import { useLiveDemo } from '../../context/liveDemoContext'

// The image/video file picker + the folder picker (webkitdirectory) + the inference-model
// selector. Lives in the section heading and reads the Live-Demo context directly.
export function MediaUploadControls({ copy }) {
  const {
    media,
    handleMediaChange,
    selectedModelId,
    setSelectedModelId,
    modelOptions,
    modelOptionsLoading,
    modelOptionsError,
    isAnalyzing,
  } = useLiveDemo()
  // One PERSISTENT status line for the loading/error text: a conditionally-mounted
  // live region is added to the DOM together with its content, so screen readers
  // never announce it. Empty once the options are ready.
  const statusText = modelOptionsError || (modelOptionsLoading ? copy.live.modelLoading : '')
  // Group the registry into Detectors (2-class) and the Transition (3-class) model so the
  // dropdown stays scannable as the registry grows. Registry order is preserved within each
  // group; an entry with no role is treated as a detector.
  const modelGroups = [
    {
      id: 'detector',
      label: copy.live.modelGroupDetectors,
      items: modelOptions.filter((model) => model.model_role !== 'transition'),
    },
    {
      id: 'transition',
      label: copy.live.modelGroupTransition,
      items: modelOptions.filter((model) => model.model_role === 'transition'),
    },
  ].filter((group) => group.items.length > 0)
  // Whether the controlled value maps to a real option. Until the registry loads (or if the
  // current selection went unavailable and reset to ""), a disabled "…" placeholder keeps the
  // controlled <select> valid without flashing a raw registry id as a label (audit FE-15).
  const currentModelId = selectedModelId ?? ''
  const hasModelMatch = modelOptions.some((model) => model.model_id === currentModelId)

  return (
    <div className="demo-actions">
      <label className="upload-button">
        <Upload size={18} />
        <span>{media ? media.name : copy.live.upload}</span>
        <input
          id="papi-media-file"
          name="file"
          accept="image/*,video/*"
          type="file"
          aria-label={copy.live.upload}
          onChange={handleMediaChange}
        />
      </label>
      <label className="upload-button folder-upload">
        <FolderOpen size={18} />
        <span>{copy.live.uploadFolder}</span>
        <input
          id="papi-media-folder"
          name="files"
          accept="image/*"
          type="file"
          multiple
          webkitdirectory="true"
          onChange={handleMediaChange}
        />
      </label>
      <div className="model-selector">
        <span className="model-selector__label" id="model-selector-label">
          {copy.live.inferenceModel}
        </span>
        <select
          className="model-selector__select"
          aria-labelledby="model-selector-label"
          aria-describedby={statusText ? 'model-selector-status' : undefined}
          // No real entries yet (registry loading or failed) → nothing to choose.
          disabled={modelOptions.length === 0}
          // Keep the control ENABLED during analysis so keyboard focus survives, but ignore the
          // change: switching mid-run arms a wasted auto-run and flashes a stale result first. The
          // controlled value snaps the selection back; the title carries the busy reason (FE-8).
          title={isAnalyzing ? copy.live.restartDisabledBusy : copy.live.inferenceModel}
          value={currentModelId}
          onChange={(event) => {
            if (!isAnalyzing) {
              setSelectedModelId(event.target.value)
            }
          }}
        >
          {!hasModelMatch && (
            <option value={currentModelId} disabled>
              …
            </option>
          )}
          {modelGroups.map((group) => (
            <optgroup key={group.id} label={group.label}>
              {group.items.map((model) => {
                // Unavailable registry entries render as disabled <option>s: native, unselectable,
                // and the disabled reason rides along in the visible label so it stays reachable.
                const unavailable = model.available === false
                const label = model.model_label || model.model_id
                return (
                  <option key={model.model_id} value={model.model_id} disabled={unavailable}>
                    {unavailable
                      ? `${label} — ${model.disabled_reason || copy.live.modelUnavailable}`
                      : label}
                  </option>
                )
              })}
            </optgroup>
          ))}
        </select>
        <small
          id="model-selector-status"
          className={modelOptionsError ? 'model-selector__error' : undefined}
          role="status"
          aria-live="polite"
        >
          {statusText}
        </small>
      </div>
    </div>
  )
}
