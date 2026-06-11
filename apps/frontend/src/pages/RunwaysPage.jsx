import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import clsx from 'clsx'
import { Check, ChevronRight, MapPin, Trash2 } from 'lucide-react'
import { useLiveDemo } from '../context/liveDemoContext'
import { localizedErrorMessage } from '../lib/errorMessages'

// EDNY 24 surveyed coordinates, offered as a one-click starting template so a
// demo user can register a valid (non-degenerate) runway quickly and then tweak.
const TEMPLATE_LIGHTS = [
  { point: 1, latitude: '47.673521', longitude: '9.518154' },
  { point: 2, latitude: '47.673450', longitude: '9.518214' },
  { point: 3, latitude: '47.673380', longitude: '9.518274' },
  { point: 4, latitude: '47.673309', longitude: '9.518333' },
]
const DEFAULT_ALTITUDE = '461.37'

const emptyLamp = (point) => ({ point, latitude: '', longitude: '', altitude_m: DEFAULT_ALTITUDE })
const emptyForm = () => ({
  label: '',
  airport: '',
  designation: '',
  lights: [1, 2, 3, 4].map(emptyLamp),
})

// Accept a dot or comma decimal separator (a de/nl/fr user may type "47,67").
const toNumber = (value) => Number(String(value).trim().replace(',', '.'))
const inRange = (value, min, max) => {
  // An EMPTY field must fail validation: Number('') is 0, which sits inside
  // every coordinate range — a half-filled form would otherwise create a lamp
  // at (0, 0), distinct enough to pass the backend's 4-distinct-positions
  // check and silently corrupt the runway geometry (audit 2026-06-11).
  if (!String(value).trim()) return false
  const n = toNumber(value)
  return Number.isFinite(n) && n >= min && n <= max
}

const papiNumberFromText = (value) => {
  const match = String(value ?? '')
    .trim()
    .match(/^papi[\s_-]*0*(\d+)$/i)
  return match ? Number(match[1]) : null
}

const nextAvailablePapiLabel = (runways) => {
  const used = new Set()
  runways.forEach((runway) => {
    const labelNumber = papiNumberFromText(runway.label)
    const idNumber = papiNumberFromText(runway.id)
    if (Number.isInteger(labelNumber) && labelNumber > 0) used.add(labelNumber)
    if (Number.isInteger(idNumber) && idNumber > 0) used.add(idNumber)
  })

  let candidate = 1
  while (used.has(candidate)) candidate += 1
  return `PAPI ${candidate}`
}

export function RunwaysPage({ copy }) {
  const {
    runways,
    runwayLoading,
    runwayError,
    selectedRunwayId,
    selectedRunway,
    setSelectedRunwayId,
    addRunway,
    removeRunway,
    refetchRunways,
  } = useLiveDemo()
  const t = copy.runways

  const [form, setForm] = useState(emptyForm)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [openRunwayId, setOpenRunwayId] = useState(selectedRunwayId)
  const openRunway = useMemo(
    () =>
      runways.find((runway) => runway.id === openRunwayId) ??
      selectedRunway ??
      runways[0] ??
      null,
    [openRunwayId, runways, selectedRunway],
  )
  const runwayStatusMessage = runwayError
    ? t.loadError.replace('{message}', localizedErrorMessage(runwayError, copy))
    : runways.length > 0
      ? t.refreshing
      : t.loading

  const setField = (key, value) => setForm((current) => ({ ...current, [key]: value }))
  const setLamp = (index, key, value) =>
    setForm((current) => ({
      ...current,
      lights: current.lights.map((lamp, i) => (i === index ? { ...lamp, [key]: value } : lamp)),
    }))

  const fillTemplate = () =>
    setForm((current) => ({
      ...current,
      lights: TEMPLATE_LIGHTS.map((lamp) => ({ ...lamp, altitude_m: DEFAULT_ALTITUDE })),
    }))

  const validate = () => {
    return form.lights.every(
      (lamp) =>
        inRange(lamp.latitude, -90, 90) &&
        inRange(lamp.longitude, -180, 180) &&
        inRange(lamp.altitude_m, -500, 15000),
    )
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')
    if (!validate()) {
      setError(t.invalidHint)
      return
    }
    const resolvedLabel = form.label.trim() || nextAvailablePapiLabel(runways)
    const payload = {
      label: resolvedLabel,
      airport: form.airport.trim() || undefined,
      designation: form.designation.trim() || undefined,
      lights: form.lights.map((lamp) => ({
        point: lamp.point,
        latitude: toNumber(lamp.latitude),
        longitude: toNumber(lamp.longitude),
        altitude_m: toNumber(lamp.altitude_m),
      })),
    }
    setSubmitting(true)
    try {
      const created = await addRunway(payload)
      setOpenRunwayId(created.id)
      toast.success(t.added.replace('{label}', created.label))
      setForm(emptyForm())
    } catch (caught) {
      const message = localizedErrorMessage(caught, copy) || t.errorGeneric
      setError(message)
      toast.error(message)
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (runway) => {
    const label = runway.label ?? runway.id
    if (!window.confirm(t.deleteConfirm.replace('{label}', label))) {
      return
    }

    try {
      await removeRunway(runway.id)
      toast.success(t.deleted.replace('{label}', label))
    } catch (caught) {
      toast.error(localizedErrorMessage(caught, copy) || t.errorGeneric)
    }
  }

  return (
    <section className="runways-section">
      <div className="section-heading">
        <div>
          <p className="eyebrow">{t.eyebrow}</p>
          <h2>{t.title}</h2>
        </div>
        <span className="source-note">
          {t.activeNote.replace('{id}', selectedRunway?.label ?? selectedRunwayId)}
        </span>
      </div>

      <p className="runways-intro">{t.intro}</p>

      {(runwayLoading || runwayError) && (
        <div
          className={clsx('runway-status', runwayError && 'error')}
          role={runwayError ? 'alert' : 'status'}
          aria-live={runwayError ? 'assertive' : 'polite'}
        >
          <span>{runwayStatusMessage}</span>
          {runwayError ? (
            <button type="button" className="ghost-button" onClick={refetchRunways}>
              {t.retry}
            </button>
          ) : null}
        </div>
      )}

      <div className="runways-layout">
        {/* Add-runway form: the four lamp coordinates are required because the
            backend's elevation-angle solver scores against per-lamp geometry. */}
        <form className="runway-form" onSubmit={handleSubmit} aria-labelledby="runway-form-heading">
          <h3 id="runway-form-heading">{t.addTitle}</h3>
          <p className="runway-form__intro">{t.addIntro}</p>

          <div className="runway-form__row">
            <label>
              <span>{t.fieldLabel}</span>
              <input
                type="text"
                value={form.label}
                onChange={(event) => setField('label', event.target.value)}
                placeholder={t.fieldLabelPlaceholder}
                maxLength={120}
              />
            </label>
            <p className="runway-form__hint">{t.autoLabelHint}</p>
          </div>
          <div className="runway-form__row runway-form__row--split">
            <label>
              <span>{t.fieldAirport}</span>
              <input
                type="text"
                value={form.airport}
                onChange={(event) => setField('airport', event.target.value)}
                placeholder="EDNY"
                maxLength={120}
              />
            </label>
            <label>
              <span>{t.fieldDesignation}</span>
              <input
                type="text"
                value={form.designation}
                onChange={(event) => setField('designation', event.target.value)}
                placeholder="24"
                maxLength={40}
              />
            </label>
          </div>

          <fieldset className="runway-lamps-fieldset">
            <legend>
              <span className="runway-lamps-legend__inner">
                <span>{t.lampsLegend}</span>
                <button type="button" className="runway-template-button" onClick={fillTemplate}>
                  {t.useTemplate}
                </button>
              </span>
            </legend>
            <div className="runway-lamp-grid runway-lamp-grid--head" aria-hidden="true">
              <span />
              <span>{t.latitude}</span>
              <span>{t.longitude}</span>
              <span>{t.altitude}</span>
            </div>
            {form.lights.map((lamp, index) => (
              <div className="runway-lamp-grid" key={lamp.point}>
                <span className="runway-lamp-no mono">
                  {t.lamp} {lamp.point}
                </span>
                <input
                  type="text"
                  inputMode="decimal"
                  className="mono"
                  value={lamp.latitude}
                  onChange={(event) => setLamp(index, 'latitude', event.target.value)}
                  placeholder={TEMPLATE_LIGHTS[index].latitude}
                  aria-label={`${t.lamp} ${lamp.point} ${t.latitude}`}
                />
                <input
                  type="text"
                  inputMode="decimal"
                  className="mono"
                  value={lamp.longitude}
                  onChange={(event) => setLamp(index, 'longitude', event.target.value)}
                  placeholder={TEMPLATE_LIGHTS[index].longitude}
                  aria-label={`${t.lamp} ${lamp.point} ${t.longitude}`}
                />
                <input
                  type="text"
                  inputMode="decimal"
                  className="mono"
                  value={lamp.altitude_m}
                  onChange={(event) => setLamp(index, 'altitude_m', event.target.value)}
                  placeholder={DEFAULT_ALTITUDE}
                  aria-label={`${t.lamp} ${lamp.point} ${t.altitude}`}
                />
              </div>
            ))}
          </fieldset>

          {error && (
            <p className="runway-form__error" role="alert">
              {error}
            </p>
          )}

          <button className="primary-button" type="submit" disabled={submitting}>
            <MapPin size={18} />
            {submitting ? t.adding : t.addButton}
          </button>
        </form>

        {/* Configured runways: compact selector + one expanded details panel.
            This scales better once the airport list grows beyond a handful of PAPI units. */}
        <div className="runway-browser" aria-label={t.listTitle}>
          <div className="runway-list">
            <h3 className="runway-list__title">{t.listTitle}</h3>
            {runways.length === 0 && (
              <p className="runway-list__empty">{runwayLoading ? t.loading : t.listEmpty}</p>
            )}
            <div className="runway-list__items">
              {runways.map((runway) => {
                const isActive = runway.id === selectedRunwayId
                const isOpen = runway.id === openRunway?.id
                const isCustom = runway.source === 'custom'
                return (
                  <button
                    type="button"
                    key={runway.id}
                    className={clsx('runway-list-item', isOpen && 'open', isActive && 'active')}
                    onClick={() => setOpenRunwayId(runway.id)}
                    aria-expanded={isOpen}
                  >
                    <span className="runway-list-item__main">
                      <strong>{runway.label}</strong>
                      <span>
                        {[runway.airport, runway.designation && `${t.fieldDesignation} ${runway.designation}`]
                          .filter(Boolean)
                          .join(' · ') || runway.id}
                      </span>
                    </span>
                    <span className="runway-list-item__status">
                      {isActive && <Check size={14} aria-label={t.activeBadge} />}
                      <span className={clsx('runway-badge', isCustom ? 'is-custom' : 'is-builtin')}>
                        {isCustom ? t.custom : t.builtin}
                      </span>
                      <ChevronRight size={16} aria-hidden="true" />
                    </span>
                  </button>
                )
              })}
            </div>
          </div>

          {openRunway && (
            <article className={clsx('runway-card', openRunway.id === selectedRunwayId && 'active')}>
              <div className="runway-card__header">
                <div>
                  <span className="runway-card__kicker">{t.detailsTitle}</span>
                  <strong>{openRunway.label}</strong>
                  <span className="runway-card__id mono">{openRunway.id}</span>
                </div>
                <span
                  className={clsx(
                    'runway-badge',
                    openRunway.source === 'custom' ? 'is-custom' : 'is-builtin',
                  )}
                >
                  {openRunway.source === 'custom' ? t.custom : t.builtin}
                </span>
              </div>

              {(openRunway.airport || openRunway.designation) && (
                <p className="runway-card__meta">
                  {[openRunway.airport, openRunway.designation && `${t.fieldDesignation} ${openRunway.designation}`]
                    .filter(Boolean)
                    .join(' · ')}
                </p>
              )}

              <ul className="runway-card__lamps">
                {openRunway.lights.map((light) => (
                  <li key={light.point}>
                    <span className="runway-lamp-no mono">{light.point}</span>
                    <span className="mono tnum">
                      {light.latitude.toFixed(5)}, {light.longitude.toFixed(5)}
                    </span>
                    <span className="mono tnum runway-card__alt">{light.altitude_m} m</span>
                  </li>
                ))}
              </ul>

              <div className="runway-card__actions">
                {openRunway.id === selectedRunwayId ? (
                  <span className="runway-active-tag">
                    <Check size={15} aria-hidden="true" /> {t.activeBadge}
                  </span>
                ) : (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => setSelectedRunwayId(openRunway.id)}
                  >
                    {t.useButton}
                  </button>
                )}
                {openRunway.source === 'custom' && (
                  <button
                    type="button"
                    className="ghost-button runway-delete"
                    onClick={() => handleDelete(openRunway)}
                    aria-label={`${t.deleteButton} ${openRunway.label}`}
                  >
                    <Trash2 size={15} aria-hidden="true" />
                    {t.deleteButton}
                  </button>
                )}
              </div>
            </article>
          )}
        </div>
      </div>
    </section>
  )
}
