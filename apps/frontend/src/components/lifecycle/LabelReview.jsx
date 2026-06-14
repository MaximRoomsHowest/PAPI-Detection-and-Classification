import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import { Trash2 } from 'lucide-react'
import { commitLabels, fetchAuthedImageUrl, fetchCandidates, revokeMediaUrl } from '../../lib/api'

// Per-class overlay colours (class 0=red, 1=white, 2=transition) — mirror the lamp
// palette so a reviewer reads the candidate boxes the same way as a live overlay.
const CLASS_COLORS = ['#d2393b', '#b3a576', '#c98414']

function boxColor(classId) {
  return CLASS_COLORS[classId] ?? '#0a6e89'
}

// One candidate image: the staged frame with the model's predicted boxes drawn as
// normalized-percentage overlays. The reviewer can reclassify or delete each box,
// or skip the whole image; positions are kept as-is (model-predicted).
function CandidateCard({ image, classNames, state, onChange, copy }) {
  const [src, setSrc] = useState(null)

  useEffect(() => {
    let active = true
    let url = null
    fetchAuthedImageUrl(image.image_url)
      .then((resolved) => {
        // Always store the URL so cleanup can revoke it; if the card already
        // unmounted while the fetch was in flight, revoke immediately (no leak).
        url = resolved
        if (active) setSrc(resolved)
        else revokeMediaUrl(resolved)
      })
      .catch(() => {})
    return () => {
      active = false
      revokeMediaUrl(url)
    }
  }, [image.image_url])

  const setBoxClass = (index, classId) => {
    const boxes = state.boxes.map((box, i) => (i === index ? { ...box, class_id: classId } : box))
    onChange({ ...state, boxes })
  }
  const removeBox = (index) => {
    onChange({ ...state, boxes: state.boxes.filter((_, i) => i !== index) })
  }

  return (
    <article className={`review-card${state.skip ? ' review-card--skip' : ''}`}>
      <div className="review-stage">
        {src ? (
          <img src={src} alt={image.image_id} className="review-img" />
        ) : (
          <div className="review-img review-img--placeholder" />
        )}
        {!state.skip &&
          state.boxes.map((box, index) => (
            <span
              key={index}
              className="review-box"
              style={{
                left: `${(box.x - box.w / 2) * 100}%`,
                top: `${(box.y - box.h / 2) * 100}%`,
                width: `${box.w * 100}%`,
                height: `${box.h * 100}%`,
                borderColor: boxColor(box.class_id),
              }}
            />
          ))}
      </div>
      <div className="review-controls">
        <p className="review-card__id mono">{image.image_id}</p>
        <label className="lc-check">
          <input
            type="checkbox"
            checked={state.skip}
            onChange={(event) => onChange({ ...state, skip: event.target.checked })}
          />
          {copy.datasets.review.skip}
        </label>
        {!state.skip && (
          <ul className="review-box-list">
            {state.boxes.length === 0 && <li className="lc-empty">{copy.datasets.review.noBoxes}</li>}
            {state.boxes.map((box, index) => (
              <li key={index} className="review-box-row">
                <span className="review-swatch" style={{ background: boxColor(box.class_id) }} aria-hidden="true" />
                <select
                  value={box.class_id}
                  onChange={(event) => setBoxClass(index, Number(event.target.value))}
                  aria-label={copy.datasets.review.classLabel}
                >
                  {Object.entries(classNames).map(([id, name]) => (
                    <option key={id} value={Number(id)}>{name}</option>
                  ))}
                </select>
                {box.conf != null && <span className="mono tnum review-conf">{box.conf.toFixed(2)}</span>}
                <button
                  className="icon-button"
                  type="button"
                  onClick={() => removeBox(index)}
                  aria-label={copy.datasets.review.deleteBox}
                >
                  <Trash2 size={14} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </article>
  )
}

export function LabelReview({ datasetId, classNames, copy, onCommitted }) {
  const [data, setData] = useState(null)
  const [editing, setEditing] = useState({})
  const [loading, setLoading] = useState(true)
  const [committing, setCommitting] = useState(false)
  // Guards against state updates / stray toasts if the modal is closed mid-commit.
  const mountedRef = useRef(true)
  useEffect(() => () => {
    mountedRef.current = false
  }, [])

  useEffect(() => {
    let active = true
    // Deferred to a microtask so the fetch kick-off is not a synchronous setState
    // in the effect body (react-hooks/set-state-in-effect) — same shape as useFetch.
    Promise.resolve()
      .then(() => fetchCandidates(datasetId))
      .then((payload) => {
        if (!active) return
        setData(payload)
        const initial = {}
        for (const image of payload.images || []) {
          initial[image.image_id] = { boxes: image.boxes.map((b) => ({ ...b })), skip: false }
        }
        setEditing(initial)
      })
      .catch((err) => {
        if (active) toast.error(err?.message)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [datasetId])

  const resolvedClassNames = useMemo(
    () => classNames || { 0: 'papi_light_red', 1: 'papi_light_white', 2: 'papi_light_transition' },
    [classNames],
  )

  const commit = async () => {
    const images = (data?.images || []).map((image) => {
      const state = editing[image.image_id] || { boxes: [], skip: false }
      return {
        image_id: image.image_id,
        skip: state.skip,
        boxes: state.skip ? [] : state.boxes.map(({ class_id, x, y, w, h }) => ({ class_id, x, y, w, h })),
      }
    })
    setCommitting(true)
    try {
      const result = await commitLabels(datasetId, images)
      if (!mountedRef.current) return
      toast.success(copy.datasets.review.committed.replace('{count}', String(result.n_committed)))
      onCommitted?.()
    } catch (err) {
      if (mountedRef.current) toast.error(err?.message)
    } finally {
      if (mountedRef.current) setCommitting(false)
    }
  }

  if (loading) {
    return <p className="lc-empty">{copy.datasets.review.loading}</p>
  }
  if (!data || (data.images || []).length === 0) {
    return <p className="lc-empty">{copy.datasets.review.empty}</p>
  }

  return (
    <div className="label-review">
      <p className="lc-page__subtitle">{copy.datasets.review.hint}</p>
      <div className="review-grid">
        {data.images.map((image) => (
          <CandidateCard
            key={image.image_id}
            image={image}
            classNames={resolvedClassNames}
            copy={copy}
            state={editing[image.image_id] || { boxes: [], skip: false }}
            onChange={(next) => setEditing((current) => ({ ...current, [image.image_id]: next }))}
          />
        ))}
      </div>
      <button className="cta-button" type="button" onClick={commit} disabled={committing}>
        {committing ? copy.datasets.review.committing : copy.datasets.review.commit}
      </button>
    </div>
  )
}
