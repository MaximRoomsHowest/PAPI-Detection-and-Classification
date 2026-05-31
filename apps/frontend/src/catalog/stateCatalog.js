export const stateCatalog = [
  {
    id: 'far-high',
    label: 'Far too high',
    short: '4W',
    pattern: '4 white',
    description: 'Aircraft is well above glidepath',
    color: '#35d7b7',
  },
  {
    id: 'too-high',
    label: 'Too high',
    short: '3W 1R',
    pattern: '3 white + 1 red',
    description: 'Slightly above the ideal angle',
    color: '#6fc8ff',
  },
  {
    id: 'correct',
    label: 'Correct glidepath',
    short: '2W 2R',
    pattern: '2 white + 2 red',
    description: 'Stable 3 degree approach',
    color: '#a7e35c',
  },
  {
    id: 'too-low',
    label: 'Too low',
    short: '1W 3R',
    pattern: '1 white + 3 red',
    description: 'Below desired approach path',
    color: '#ffb657',
  },
  {
    id: 'far-low',
    label: 'Far too low',
    short: '4R',
    pattern: '4 red',
    description: 'Immediate correction needed',
    color: '#ff6b6b',
  },
  {
    id: 'unknown',
    label: 'Unknown',
    short: 'N/A',
    pattern: 'Incomplete detection',
    description: 'Not enough lamps detected for a reliable PAPI state',
    color: '#9aa5b1',
  },
]

export const backendStateId = {
  far_too_high: 'far-high',
  too_high: 'too-high',
  correct_glidepath: 'correct',
  too_low: 'too-low',
  far_too_low: 'far-low',
  unknown: 'unknown',
}
