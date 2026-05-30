export function isVideoFile(file) {
  return file.type.startsWith('video') || /\.(avi|mov|mp4|mkv|webm)$/i.test(file.name)
}

export function isImageFile(file) {
  return file.type.startsWith('image') || /\.(jpg|jpeg|png|bmp|webp)$/i.test(file.name)
}

export function fileDisplayPath(file) {
  return file.webkitRelativePath || file.name
}
