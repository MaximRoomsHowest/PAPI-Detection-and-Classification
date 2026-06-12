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
  // Until the registry has loaded (or after a failed load) there is no real entry to
  // show — render one NEUTRAL placeholder so the segmented control keeps its shape
  // without flashing a raw registry id as if it were a translated label (audit FE-15).
  const options = modelOptions.length
    ? modelOptions
    : [{ model_id: '', model_label: '…', available: true }]
  // One PERSISTENT status line for the loading/error text: a conditionally-mounted
  // live region is added to the DOM together with its content, so screen readers
  // never announce it. Empty once the options are ready.
  const statusText = modelOptionsError || (modelOptionsLoading ? copy.live.modelLoading : '')

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
      <div className="model-selector" role="group" aria-label={copy.live.inferenceModel}>
        <span className="model-selector__label">{copy.live.inferenceModel}</span>
        <div className="model-selector__options">
          {options.map((model) => {
            const unavailable = model.available === false
            // Block model switching mid-analysis: setSelectedModelId arms the auto-run, so a click
            // during an in-flight run queues a wasted re-run and flashes the stale-model result first (audit).
            // aria-disabled + an onClick guard instead of `disabled`: a disabled attribute would
            // drop keyboard focus to <body> mid-analysis and hide the disabled_reason from
            // screen readers; the title carries the reason as the accessible description (FE-8).
            const blocked = unavailable || isAnalyzing
            const reason = unavailable
              ? model.disabled_reason || copy.live.modelUnavailable
              : isAnalyzing
                ? copy.live.restartDisabledBusy
                : model.description || model.model_role || model.model_id
            return (
              <button
                key={model.model_id || 'placeholder'}
                type="button"
                className={`model-selector__option${selectedModelId === model.model_id ? ' is-active' : ''}`}
                aria-pressed={selectedModelId === model.model_id}
                aria-disabled={blocked || undefined}
                title={reason || undefined}
                onClick={() => {
                  if (!blocked) {
                    setSelectedModelId(model.model_id)
                  }
                }}
              >
                {model.model_label || model.model_id}
              </button>
            )
          })}
        </div>
        <small
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
