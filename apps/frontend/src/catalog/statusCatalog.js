export const statusCopy = {
  white: { label: 'White', tone: 'white', color: '#f8fbff' },
  red: { label: 'Red', tone: 'red', color: '#ff4545' },
  transition: { label: 'Transition', tone: 'transition', color: '#ffb11f' },
  // "obscured" = the detector found nothing at this lamp slot. Reuses the muted
  // "occluded" tone/styling but keeps its own label so charts + cards can name
  // non-detections distinctly (client ask: surface them, don't hide them).
  obscured: { label: 'Obscured', tone: 'occluded', color: '#7b8794' },
  occluded: { label: 'Occluded', tone: 'occluded', color: '#9aa5b1' },
}
