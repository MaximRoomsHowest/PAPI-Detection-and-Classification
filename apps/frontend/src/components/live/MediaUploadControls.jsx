import { FolderOpen, Upload } from 'lucide-react'
import { useLiveDemo } from '../../context/liveDemoContext'

// The image/video file picker + the folder picker (webkitdirectory) + the transition-method
// toggle. Lives in the section heading. Pulls the current media (for the filename label), the
// change handler, and the transition-method state from the Live-Demo context so the page shell
// doesn't thread them through.
export function MediaUploadControls({ copy }) {
  const { media, handleMediaChange, transitionMethod, setTransitionMethod } = useLiveDemo()

  const methods = [
    { id: 'tracking', label: copy.live.transitionMethodTracking, hint: copy.live.transitionMethodTrackingHint },
    { id: 'model', label: copy.live.transitionMethodModel, hint: copy.live.transitionMethodModelHint },
  ]

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
      <div className="transition-method" role="group" aria-label={copy.live.transitionMethod}>
        <span className="transition-method__label">{copy.live.transitionMethod}</span>
        <div className="transition-method__options">
          {methods.map((method) => (
            <button
              key={method.id}
              type="button"
              className={`transition-method__option${transitionMethod === method.id ? ' is-active' : ''}`}
              aria-pressed={transitionMethod === method.id}
              title={method.hint}
              onClick={() => setTransitionMethod(method.id)}
            >
              {method.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
