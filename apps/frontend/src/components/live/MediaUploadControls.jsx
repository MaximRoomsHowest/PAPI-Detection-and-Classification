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
  const options = modelOptions.length
    ? modelOptions
    : [{ model_id: selectedModelId, model_label: selectedModelId, available: true }]

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
          directory=""
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
            const reason = unavailable
              ? model.disabled_reason || copy.live.modelUnavailable
              : isAnalyzing
                ? copy.live.restartDisabledBusy
                : model.description || model.model_role || model.model_id
            return (
              <button
                key={model.model_id}
                type="button"
                className={`model-selector__option${selectedModelId === model.model_id ? ' is-active' : ''}`}
                aria-pressed={selectedModelId === model.model_id}
                disabled={unavailable || isAnalyzing}
                title={reason}
                onClick={() => setSelectedModelId(model.model_id)}
              >
                {model.model_label || model.model_id}
              </button>
            )
          })}
        </div>
        {modelOptionsLoading && <small>{copy.live.modelLoading}</small>}
        {modelOptionsError && (
          <small className="model-selector__error" role="status" aria-live="polite">
            {modelOptionsError}
          </small>
        )}
      </div>
    </div>
  )
}
