import clsx from 'clsx'

// The four-box PAPI unit as a compact glyph — the product's recurring mark.
// Renders one square per lamp, coloured by state through the same --lamp-*
// tokens the cards use, so the mark can also encode REAL per-lamp results
// (History rows, verdict strips) rather than being decoration.
//
// `states` is an array of up to four catalog tones ('red' | 'white' |
// 'transition' | 'occluded' | 'obscured' | 'unknown'); missing entries render
// as empty housings. The default is the on-glidepath signature (2 red + 2
// white) used for the brand mark.
const DEFAULT_STATES = ['red', 'red', 'white', 'white']

export function PapiGlyph({ states = DEFAULT_STATES, size = 'md', label, className }) {
  const cells = Array.from({ length: 4 }, (_, index) => {
    const tone = states[index]
    return tone === 'obscured' ? 'occluded' : tone ?? 'unknown'
  })

  return (
    <span
      className={clsx('papi-glyph', `papi-glyph--${size}`, className)}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {cells.map((tone, index) => (
        <span key={index} className={`papi-glyph__cell papi-glyph__cell--${tone}`} />
      ))}
    </span>
  )
}
