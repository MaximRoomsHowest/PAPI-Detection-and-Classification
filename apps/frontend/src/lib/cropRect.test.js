import { describe, expect, it } from 'vitest'
import { computeCropRect } from './cropRect'

const lamp = (id, x1, y1, x2, y2, extra = {}) => ({
  id,
  status: 'white',
  confidence: 90,
  bbox: { x1, y1, x2, y2 },
  ...extra,
})

describe('computeCropRect', () => {
  it('returns null without image dimensions', () => {
    expect(computeCropRect([lamp(1, 10, 10, 20, 20)], 0, 0)).toBeNull()
    expect(computeCropRect([lamp(1, 10, 10, 20, 20)], 100, undefined)).toBeNull()
  })

  it('returns null when no lamp has a usable bbox', () => {
    expect(computeCropRect([], 1000, 800)).toBeNull()
    expect(
      computeCropRect([{ id: 1, status: 'white', bbox: null }], 1000, 800),
    ).toBeNull()
  })

  it('frames a single box with padding and clamps to the image', () => {
    // Box near the top-left corner; padding should clamp at 0.
    const rect = computeCropRect([lamp(1, 5, 5, 25, 25)], 1000, 800)
    expect(rect).not.toBeNull()
    expect(rect.x).toBe(0) // 5 - max(24, 20*0.35=7) = 5-24 < 0 -> clamped
    expect(rect.y).toBe(0)
    expect(rect.width).toBeGreaterThan(20)
    expect(rect.boxes).toHaveLength(1)
    // The box origin is offset by the crop origin.
    expect(rect.boxes[0].x).toBe(5)
    expect(rect.boxes[0].width).toBe(20)
  })

  it('unions four lamps into one crop and keeps relative box coords', () => {
    const rect = computeCropRect(
      [
        lamp(1, 400, 300, 440, 340, { status: 'white' }),
        lamp(2, 460, 302, 500, 342, { status: 'white' }),
        lamp(3, 520, 304, 560, 344, { status: 'red' }),
        lamp(4, 580, 306, 620, 346, { status: 'red' }),
      ],
      1920,
      1080,
    )
    expect(rect).not.toBeNull()
    // Union x spans 400..620 (width 220); padX = 220*0.35 = 77.
    expect(rect.x).toBe(400 - 77)
    expect(rect.width).toBe(220 + 77 * 2)
    // Light 4's box stays inside the crop and to the right of light 1's.
    const light1 = rect.boxes.find((box) => box.id === 1)
    const light4 = rect.boxes.find((box) => box.id === 4)
    expect(light4.x).toBeGreaterThan(light1.x)
    expect(light1.x).toBe(400 - (400 - 77))
  })

  it('ignores lamps without a bbox but keeps the rest', () => {
    const rect = computeCropRect(
      [lamp(1, 100, 100, 140, 140), { id: 2, status: 'red', bbox: null }],
      800,
      600,
    )
    expect(rect.boxes).toHaveLength(1)
    expect(rect.boxes[0].id).toBe(1)
  })
})
