/**
 * Tests for the file-kind predicates used to route uploads (image vs. video)
 * and to derive a display path for folder uploads.
 *
 * Behaviour pinned against the real implementation:
 *   - Both predicates check `file.type.startsWith(...)` FIRST, then fall back
 *     to a filename-extension regex. So a blank MIME type still classifies by
 *     extension, and a `type` of e.g. 'image/png' classifies even for a name
 *     with no recognised extension.
 *   - The extension regexes are case-insensitive and anchored to the end.
 *   - `fileDisplayPath` prefers `webkitRelativePath` (set by folder uploads)
 *     and falls back to `name`.
 *
 * `File` exists in jsdom; we set `type` via the constructor and
 * `webkitRelativePath` via defineProperty (jsdom doesn't accept it in the
 * constructor), mirroring how the browser populates it on folder uploads.
 */

import { describe, it, expect } from 'vitest'

import { isImageFile, isVideoFile, fileDisplayPath } from './fileType.js'

/** Build a File-like object with a controllable name + MIME type. */
function makeFile(name, type = '') {
  return new File(['x'], name, { type })
}

describe('isVideoFile', () => {
  it('matches by MIME type prefix regardless of extension', () => {
    expect(isVideoFile(makeFile('clip', 'video/mp4'))).toBe(true)
    expect(isVideoFile(makeFile('weird.dat', 'video/webm'))).toBe(true)
  })

  it('matches known video extensions case-insensitively when type is blank', () => {
    expect(isVideoFile(makeFile('a.mp4'))).toBe(true)
    expect(isVideoFile(makeFile('a.MOV'))).toBe(true)
    expect(isVideoFile(makeFile('a.AvI'))).toBe(true)
    expect(isVideoFile(makeFile('a.mkv'))).toBe(true)
    expect(isVideoFile(makeFile('a.webm'))).toBe(true)
  })

  it('rejects images and unknown extensions when type is blank', () => {
    expect(isVideoFile(makeFile('a.jpg'))).toBe(false)
    expect(isVideoFile(makeFile('a.txt'))).toBe(false)
    expect(isVideoFile(makeFile('noextension'))).toBe(false)
  })

  it('only matches the extension at the end of the name', () => {
    // ".mp4" appears mid-name but the real extension is .txt
    expect(isVideoFile(makeFile('a.mp4.txt'))).toBe(false)
    expect(isVideoFile(makeFile('mp4'))).toBe(false)
  })
})

describe('isImageFile', () => {
  it('matches by MIME type prefix regardless of extension', () => {
    expect(isImageFile(makeFile('photo', 'image/png'))).toBe(true)
    expect(isImageFile(makeFile('weird.dat', 'image/jpeg'))).toBe(true)
  })

  it('matches known image extensions case-insensitively when type is blank', () => {
    expect(isImageFile(makeFile('a.jpg'))).toBe(true)
    expect(isImageFile(makeFile('a.JPEG'))).toBe(true)
    expect(isImageFile(makeFile('a.png'))).toBe(true)
    expect(isImageFile(makeFile('a.bmp'))).toBe(true)
    expect(isImageFile(makeFile('a.webp'))).toBe(true)
  })

  it('rejects videos and unknown extensions when type is blank', () => {
    expect(isImageFile(makeFile('a.mp4'))).toBe(false)
    expect(isImageFile(makeFile('a.gif'))).toBe(false) // gif is intentionally not in the set
    expect(isImageFile(makeFile('noextension'))).toBe(false)
  })
})

describe('isImageFile / isVideoFile are mutually exclusive for typical inputs', () => {
  it('a jpg is an image and not a video', () => {
    const f = makeFile('a.jpg', 'image/jpeg')
    expect(isImageFile(f)).toBe(true)
    expect(isVideoFile(f)).toBe(false)
  })

  it('an mp4 is a video and not an image', () => {
    const f = makeFile('a.mp4', 'video/mp4')
    expect(isVideoFile(f)).toBe(true)
    expect(isImageFile(f)).toBe(false)
  })
})

describe('fileDisplayPath', () => {
  it('returns the bare name when no webkitRelativePath is set', () => {
    expect(fileDisplayPath(makeFile('frame.jpg'))).toBe('frame.jpg')
  })

  it('prefers webkitRelativePath when the browser populated it (folder upload)', () => {
    const f = makeFile('a.jpg')
    Object.defineProperty(f, 'webkitRelativePath', { value: 'flight1/sub/a.jpg' })
    expect(fileDisplayPath(f)).toBe('flight1/sub/a.jpg')
  })

  it('falls back to name when webkitRelativePath is an empty string', () => {
    // The browser sets '' for non-folder picks; '' is falsy so we fall back.
    const f = makeFile('a.jpg')
    Object.defineProperty(f, 'webkitRelativePath', { value: '' })
    expect(fileDisplayPath(f)).toBe('a.jpg')
  })
})
