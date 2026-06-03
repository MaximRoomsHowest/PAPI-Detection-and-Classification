export const FOLDER_MODE_ANGLE_SWEEP = 'angle-sweep'
export const FOLDER_MODE_SEQUENCE = 'sequence'

export function shouldAnalyzeFolderAsSequence(mediaType, folderMode) {
  return mediaType === 'folder' && folderMode === FOLDER_MODE_SEQUENCE
}

export function shouldKeepFrameScenarios(mediaType, folderMode) {
  return mediaType !== 'video' && !shouldAnalyzeFolderAsSequence(mediaType, folderMode)
}

export function metadataFileForAnalysis(mediaType, folderMode, metadataFile) {
  return mediaType === 'folder' && folderMode === FOLDER_MODE_ANGLE_SWEEP ? null : metadataFile
}
