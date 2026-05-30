import { useState } from 'react'
import { Gauge } from 'lucide-react'
import clsx from 'clsx'
import { PapiDecisionPlot } from './PapiDecisionPlot'
import { legalStateCatalog, stateLampPatterns } from '../../catalog/stateCatalog'
import { translateState } from '../../i18n/translate'

export function GlobalStateDecoder({ scenario, plotTheme, copy }) {
  const [hovered, setHovered] = useState(null)
  const activeIndex = legalStateCatalog.findIndex((state) => state.id === scenario.stateId)
  const selectedIndex = hovered ?? activeIndex
  const readoutIndex = selectedIndex >= 0 ? selectedIndex : 2
  const translatedStates = legalStateCatalog.map((state) => translateState(state, copy))
  const selectedState = translatedStates[readoutIndex]
  const selectedPattern = stateLampPatterns[selectedState.id]
  const topEvidence = Math.max(...scenario.evidence)
  // Evidence before a real backend run is approximated from a preset scenario;
  // tag it as demo data so a juror never mistakes the ladder for live model
  // output (audit F04 + no-fabrication). The 'backend' scenario carries the
  // real per-frame confidence distribution.
  const isDemoData = scenario.id !== 'backend'

  return (
    <article className="viz-card state-decoder-card">
      <div className="viz-heading">
        <Gauge size={18} />
        <div>
          <h3>{copy.insights.decoderTitle}</h3>
          <p>{copy.insights.decoderText}</p>
        </div>
        {isDemoData && <span className="demo-tag">{copy.insights.demoData}</span>}
      </div>

      <div className="decoder-layout">
        <div className="decoder-ladder" aria-label="PAPI state evidence ladder">
          <div className="decoder-ladder__axis" aria-hidden="true">
            <span className="cap top">{copy.insights.ladderAbove}</span>
            <span className="cap mid">{copy.insights.ladderNominal}</span>
            <span className="cap bot">{copy.insights.ladderBelow}</span>
          </div>
          <div className="decoder-ladder__rows">
            {translatedStates.map((state, index) => {
              const evidence = scenario.evidence[index]
              const pattern = stateLampPatterns[state.id]
              const isActive = index === activeIndex
              const isSelected = index === readoutIndex
              const band = copy.insights.angleBands?.[state.id] ?? state.pattern

              return (
                <button
                  className={clsx('decoder-rung', isActive && 'active', isSelected && 'selected')}
                  key={state.id}
                  style={{ '--evidence': `${evidence}%` }}
                  type="button"
                  onMouseEnter={() => setHovered(index)}
                  onMouseLeave={() => setHovered(null)}
                  onFocus={() => setHovered(index)}
                >
                  <span className="decoder-rung__lamps" aria-hidden="true">
                    {pattern.map((status, lampIndex) => (
                      <i
                        className={`decoder-lamp decoder-${status}`}
                        key={`${state.id}-${lampIndex}`}
                      />
                    ))}
                  </span>
                  <span className="decoder-rung__name">
                    <strong>{state.label}</strong>
                    <small className="mono">{band}</small>
                  </span>
                  <span className="decoder-rung__bar" aria-hidden="true">
                    <i />
                  </span>
                  <strong className="decoder-rung__pct mono tnum">{evidence}%</strong>
                </button>
              )
            })}
          </div>
        </div>

        <div className="decoder-plot">
          <PapiDecisionPlot
            activeIndex={activeIndex}
            evidence={scenario.evidence}
            plotTheme={plotTheme}
            selectedIndex={readoutIndex}
            setHovered={setHovered}
            states={translatedStates}
            copy={copy}
          />
        </div>
      </div>

      <div className="decoder-readout" style={{ '--state-color': selectedState.color }}>
        <div>
          <span className="decoder-chip">
            {selectedIndex === activeIndex ? copy.insights.activeDecision : copy.insights.compareState}
          </span>
          <strong>{selectedState.label}</strong>
          <p>{selectedState.description}</p>
        </div>
        <div className="decoder-big-lamps" aria-label={`${selectedState.pattern} pattern`}>
          {selectedPattern.map((status, index) => (
            <span className={`decoder-${status}`} key={`${selectedState.id}-large-${index}`} />
          ))}
        </div>
        <div className="decoder-rule">
          <span>{copy.insights.evidence}</span>
          <strong className="mono tnum">{scenario.evidence[readoutIndex]}%</strong>
          <small>
            {scenario.evidence[readoutIndex] === topEvidence
              ? copy.insights.highestScore
              : `${topEvidence - scenario.evidence[readoutIndex]} ${copy.insights.pointsBelow}`}
          </small>
        </div>
      </div>
      <p className="viz-footnote">{copy.insights.evidenceApprox}</p>
    </article>
  )
}
