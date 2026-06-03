import { describe, expect, it } from 'vitest'
import {
  FOLDER_MODE_ANGLE_SWEEP,
  FOLDER_MODE_SEQUENCE,
  metadataFileForAnalysis,
  shouldAnalyzeFolderAsSequence,
  shouldKeepFrameScenarios,
} from './analysisMode.js'

describe('analysis mode helpers', () => {
  it('routes only folder sequence mode through the tracked sequence endpoint', () => {
    expect(shouldAnalyzeFolderAsSequence('folder', FOLDER_MODE_SEQUENCE)).toBe(true)
    expect(shouldAnalyzeFolderAsSequence('folder', FOLDER_MODE_ANGLE_SWEEP)).toBe(false)
    expect(shouldAnalyzeFolderAsSequence('video', FOLDER_MODE_SEQUENCE)).toBe(false)
  })

  it('keeps per-frame scenarios for images and angle-sweep folders only', () => {
    expect(shouldKeepFrameScenarios('image', FOLDER_MODE_ANGLE_SWEEP)).toBe(true)
    expect(shouldKeepFrameScenarios('folder', FOLDER_MODE_ANGLE_SWEEP)).toBe(true)
    expect(shouldKeepFrameScenarios('folder', FOLDER_MODE_SEQUENCE)).toBe(false)
    expect(shouldKeepFrameScenarios('video', FOLDER_MODE_ANGLE_SWEEP)).toBe(false)
  })

  it('does not apply one telemetry file to an angle-sweep folder', () => {
    const telemetryFile = new File(['lat,lon,alt'], 'track.csv', { type: 'text/csv' })

    expect(metadataFileForAnalysis('folder', FOLDER_MODE_ANGLE_SWEEP, telemetryFile)).toBeNull()
    expect(metadataFileForAnalysis('folder', FOLDER_MODE_SEQUENCE, telemetryFile)).toBe(telemetryFile)
    expect(metadataFileForAnalysis('video', FOLDER_MODE_ANGLE_SWEEP, telemetryFile)).toBe(telemetryFile)
  })
})
