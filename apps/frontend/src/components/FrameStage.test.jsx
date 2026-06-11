import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { translations } from '../i18n/translations.js'
import { FrameStage } from './FrameStage.jsx'

const copy = translations.en

const baseScenario = {
  environmentClass: 'clean',
  frame: 'Frame 1',
  condition: 'Clear evening',
  artifactUrl: null,
  artifactType: 'image',
}

function makeProps(overrides = {}) {
  return {
    scenario: baseScenario,
    media: null,
    analyzing: false,
    onFilesSelected: vi.fn(),
    backendFrames: [],
    backendFrameIndex: 0,
    onBackendFrameChange: vi.fn(),
    folderVideo: null,
    canTransformFolderToVideo: false,
    transformingFolderVideo: false,
    onTransformFolderToVideo: vi.fn(),
    onRestart: vi.fn(),
    canRestart: false,
    restarting: false,
    artifactWarning: false,
    copy,
    ...overrides,
  }
}

const mountedRoots = []

function render(element) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  act(() => {
    root.render(element)
  })
  mountedRoots.push(root)
  return { container, root }
}

function click(button) {
  act(() => {
    button.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })
}

function findButton(container, label) {
  return (
    container.querySelector(`button[aria-label="${label}"]`) ??
    [...container.querySelectorAll('button')].find((button) => button.textContent.trim() === label)
  )
}

afterEach(() => {
  mountedRoots.splice(0).forEach((root) => {
    act(() => {
      root.unmount()
    })
  })
  document.body.replaceChildren()
  vi.clearAllMocks()
})

describe('FrameStage', () => {
  it('offers the annotated/original toggle only when both sources exist, and switches the source', () => {
    const both = makeProps({
      scenario: { ...baseScenario, artifactUrl: 'blob:annotated' },
      media: { type: 'image', url: 'blob:original' },
    })
    const { container, root } = render(<FrameStage {...both} />)

    const toggle = container.querySelector(`[role="group"][aria-label="${copy.live.viewToggle}"]`)
    expect(toggle).not.toBeNull()
    // Annotated export is the default view.
    expect(container.querySelector('.video-surface img').getAttribute('src')).toBe('blob:annotated')

    click(findButton(toggle, copy.live.viewOriginal))
    expect(container.querySelector('.video-surface img').getAttribute('src')).toBe('blob:original')

    // No original upload -> no toggle at all.
    act(() => {
      root.render(<FrameStage {...makeProps({ scenario: { ...baseScenario, artifactUrl: 'blob:annotated' } })} />)
    })
    expect(container.querySelector(`[role="group"][aria-label="${copy.live.viewToggle}"]`)).toBeNull()
  })

  it('resets zoom when the displayed media changes', () => {
    const props = makeProps({ media: { type: 'image', url: 'blob:one' } })
    const { container, root } = render(<FrameStage {...props} />)

    const zoomButton = findButton(container, copy.live.zoomIn)
    click(zoomButton)
    expect(findButton(container, copy.live.zoomOut).getAttribute('aria-pressed')).toBe('true')

    act(() => {
      root.render(<FrameStage {...makeProps({ media: { type: 'image', url: 'blob:two' } })} />)
    })
    expect(findButton(container, copy.live.zoomIn).getAttribute('aria-pressed')).toBe('false')
  })

  it('resets the view to annotated on a new analysis but not on a plain re-render', () => {
    const both = makeProps({
      scenario: { ...baseScenario, artifactUrl: 'blob:annotated' },
      media: { type: 'image', url: 'blob:original' },
    })
    const { container, root } = render(<FrameStage {...both} />)

    const toggle = container.querySelector(`[role="group"][aria-label="${copy.live.viewToggle}"]`)
    click(findButton(toggle, copy.live.viewOriginal))
    expect(findButton(toggle, copy.live.viewOriginal).getAttribute('aria-pressed')).toBe('true')

    // Re-render with the SAME media -> the user's choice sticks.
    act(() => {
      root.render(<FrameStage {...both} />)
    })
    expect(findButton(toggle, copy.live.viewOriginal).getAttribute('aria-pressed')).toBe('true')

    // A new upload (media.url changes) -> back to the annotated default.
    act(() => {
      root.render(
        <FrameStage
          {...makeProps({
            scenario: { ...baseScenario, artifactUrl: 'blob:annotated2' },
            media: { type: 'image', url: 'blob:original2' },
          })}
        />,
      )
    })
    const freshToggle = container.querySelector(`[role="group"][aria-label="${copy.live.viewToggle}"]`)
    expect(findButton(freshToggle, copy.live.viewAnnotated).getAttribute('aria-pressed')).toBe('true')
  })

  it('labels the folder-video button as a toggle that can exit the preview', () => {
    const props = makeProps({
      canTransformFolderToVideo: true,
      media: { type: 'folder', url: null },
    })
    const { container, root } = render(<FrameStage {...props} />)

    const button = container.querySelector('.frame-transform-button')
    expect(button.textContent).toContain(copy.live.transformFolderVideo)
    expect(button.getAttribute('aria-pressed')).toBe('false')

    act(() => {
      root.render(
        <FrameStage
          {...makeProps({
            canTransformFolderToVideo: true,
            media: { type: 'folder', url: null },
            folderVideo: { type: 'video', url: 'blob:folder-video' },
          })}
        />,
      )
    })
    expect(button.textContent).toContain(copy.live.folderVideoExit)
    expect(button.getAttribute('aria-pressed')).toBe('true')
  })

  it('forwards dropped files to onFilesSelected', () => {
    const onFilesSelected = vi.fn()
    const { container } = render(<FrameStage {...makeProps({ onFilesSelected })} />)

    const surface = container.querySelector('.video-surface')
    const files = [new File(['x'], 'approach.png', { type: 'image/png' })]
    const dropEvent = new Event('drop', { bubbles: true, cancelable: true })
    Object.defineProperty(dropEvent, 'dataTransfer', { value: { files } })
    act(() => {
      surface.dispatchEvent(dropEvent)
    })

    expect(onFilesSelected).toHaveBeenCalledWith(files)
  })
})
