import { useRef, useState } from 'react'
import { ShieldCheck, ShieldOff } from 'lucide-react'
import { useClickOutside } from '../hooks/useClickOutside'

// Topbar control that toggles "admin mode" (reveals the model-management surface)
// and optionally stores the API key sent on mutating requests. In an OPEN local
// deployment the key field can be left blank; in a GATED deployment the operator
// pastes the PAPI_API_KEY here so X-API-Key is attached to every call.
export function AdminUnlock({ admin, copy }) {
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState('')
  const ref = useRef(null)
  useClickOutside(ref, () => setOpen(false), open)

  const submit = (event) => {
    event.preventDefault()
    admin.unlock(value)
    setValue('')
    setOpen(false)
  }

  return (
    <div className="admin-switch topbar-control" ref={ref}>
      <button
        className="icon-button"
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={admin.isAdmin ? copy.admin.lockLabel : copy.admin.unlockLabel}
        title={admin.isAdmin ? copy.admin.unlocked : copy.admin.locked}
      >
        {admin.isAdmin ? <ShieldCheck size={17} /> : <ShieldOff size={17} />}
      </button>
      {open && (
        <div className="admin-menu" role="dialog" aria-label={copy.admin.title}>
          <p className="admin-menu__title">{copy.admin.title}</p>
          <p className="admin-menu__hint">{copy.admin.hint}</p>
          {admin.isAdmin ? (
            <button
              className="secondary-button"
              type="button"
              onClick={() => {
                admin.lock()
                setOpen(false)
              }}
            >
              {copy.admin.lock}
            </button>
          ) : (
            <form onSubmit={submit} className="admin-menu__form">
              <input
                type="password"
                className="admin-menu__input"
                placeholder={copy.admin.keyPlaceholder}
                value={value}
                onChange={(event) => setValue(event.target.value)}
                autoComplete="off"
              />
              <button className="cta-button" type="submit">
                {copy.admin.unlock}
              </button>
            </form>
          )}
        </div>
      )}
    </div>
  )
}
