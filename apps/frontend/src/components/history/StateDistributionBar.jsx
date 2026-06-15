import { globalStateLabel } from '../../lib/stateLabels'

// A segmented bar showing how a set of analyses — or one video's frames — split
// across global states. Each segment grows in proportion to its count and is
// coloured by state (the .state-seg-* palette mirrors the .state-pill tints).
//
// Used in two places: the History header (overall by_global_state) and per video
// row in the table (per-frame state_counts), so a clip's state MIX reads visibly
// differently from a still image's single pill. The bar is role="img" with an
// aria-label summarising the split, and each segment carries the same text as a
// title — colour is never the only carrier of meaning.
export function StateDistributionBar({ counts, copy, className = '', compact = false }) {
  const entries = Object.entries(counts || {}).filter(
    ([, n]) => Number.isFinite(n) && n > 0,
  )
  const total = entries.reduce((sum, [, n]) => sum + n, 0)
  if (total === 0) {
    return null
  }
  // Largest share first: the dominant state leads and tiny slivers don't fragment
  // the start of the bar.
  entries.sort((a, b) => b[1] - a[1])
  const summary = entries
    .map(([state, n]) => `${globalStateLabel(state, copy)} ${Math.round((n / total) * 100)}%`)
    .join(' · ')
  return (
    <span
      className={`state-dist${compact ? ' state-dist--compact' : ''}${className ? ` ${className}` : ''}`}
      role="img"
      aria-label={summary}
      title={summary}
    >
      {entries.map(([state, n]) => (
        <span
          key={state}
          className={`state-dist__seg state-seg-${state}`}
          style={{ flexGrow: n }}
        />
      ))}
    </span>
  )
}
