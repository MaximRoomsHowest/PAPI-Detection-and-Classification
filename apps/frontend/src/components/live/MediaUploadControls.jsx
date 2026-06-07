import { FolderOpen, Upload } from 'lucide-react'
import { useLiveDemo } from '../../context/liveDemoContext'

// The image/video file picker + the folder picker (webkitdirectory). Lives in the
// section heading. Pulls the current media (for the filename label) and the change
// handler from the Live-Demo context so the page shell doesn't thread them through.
export function MediaUploadControls({ copy }) {
  const { media, handleMediaChange } = useLiveDemo()

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
    </div>
  )
}
