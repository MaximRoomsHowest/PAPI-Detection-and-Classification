import { useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ArrowLeft, Cloud, Database, KeyRound, LockKeyhole, LogIn, Server, ShieldCheck, ShieldOff, UserRound } from 'lucide-react'
import { PapiGlyph } from '../components/PapiGlyph'

function providerName(admin, method, copy) {
  const provider = admin.isAdmin ? admin.user?.provider : method === 'api_key' ? 'api_key' : admin.authConfig.mode
  if (provider === 'supabase') return copy.admin.providerSupabase
  if (provider === 'local_supabase') return copy.admin.providerLocalSupabase
  if (provider === 'api_key') return copy.admin.providerApiKey
  if (provider === 'open') return copy.admin.providerOpen
  return copy.admin.providerLocal
}

function ProviderIcon({ admin, method }) {
  const provider = admin.isAdmin ? admin.user?.provider : method === 'api_key' ? 'api_key' : admin.authConfig.mode
  if (provider === 'supabase' || provider === 'local_supabase') return <Cloud size={16} aria-hidden="true" />
  if (provider === 'api_key') return <KeyRound size={16} aria-hidden="true" />
  if (provider === 'open') return <ShieldOff size={16} aria-hidden="true" />
  return <Server size={16} aria-hidden="true" />
}

function nextMethod({ current, passwordEnabled, apiKeyEnabled, openEnabled }) {
  if (current === 'password' && passwordEnabled) return current
  if (current === 'api_key' && apiKeyEnabled) return current
  if (current === 'open' && openEnabled) return current
  if (openEnabled) return 'open'
  if (passwordEnabled) return 'password'
  if (apiKeyEnabled) return 'api_key'
  return 'api_key'
}

export function LoginPage({ copy, admin }) {
  const location = useLocation()
  const navigate = useNavigate()
  const [requestedMethod, setRequestedMethod] = useState('password')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const passwordEnabled = Boolean(admin.authConfig.password_login_enabled)
  const openEnabled = admin.authConfig.mode === 'open'
  const apiKeyEnabled = Boolean(admin.authConfig.api_key_enabled) || (!passwordEnabled && !openEnabled)
  const method = nextMethod({ current: requestedMethod, passwordEnabled, apiKeyEnabled, openEnabled })
  const showMethodSwitch = passwordEnabled && apiKeyEnabled
  const destination = useMemo(() => {
    const from = location.state?.from?.pathname
    return from && from !== '/login' ? from : '/models'
  }, [location.state])

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      if (openEnabled && method === 'open') {
        admin.unlockOpen()
      } else if (method === 'password') {
        await admin.signIn({ email, password })
      } else {
        admin.unlockApiKey(apiKey.trim())
      }
      setPassword('')
      setApiKey('')
      navigate(destination, { replace: true })
    } catch (err) {
      setError(err?.message || copy.admin.loginError)
    } finally {
      setBusy(false)
    }
  }

  const statusLabel = admin.isAdmin ? copy.admin.unlocked : copy.admin.locked
  const providerLabel = providerName(admin, method, copy)

  return (
    <section className="login-page" aria-labelledby="login-title">
      <div className="login-page__frame">
        <aside className="login-brief">
          <Link className="login-back" to="/">
            <ArrowLeft size={15} aria-hidden="true" />
            <span>{copy.login.backHome}</span>
          </Link>
          <div className="login-brief__mark" aria-hidden="true">
            <PapiGlyph size="brand" />
          </div>
          <h1 id="login-title">{copy.login.title}</h1>
          <p>{copy.login.subtitle}</p>
          <dl className="login-status">
            <div>
              <dt>{copy.admin.provider}</dt>
              <dd>
                <ProviderIcon admin={admin} method={method} />
                <span>{providerLabel}</span>
              </dd>
            </div>
            <div>
              <dt>{copy.login.accessState}</dt>
              <dd>
                {admin.isAdmin ? <ShieldCheck size={16} aria-hidden="true" /> : <LockKeyhole size={16} aria-hidden="true" />}
                <span>{statusLabel}</span>
              </dd>
            </div>
          </dl>
        </aside>

        <div className="login-panel">
          {admin.checking ? (
            <div className="login-panel__loading" role="status">
              {copy.login.checking}
            </div>
          ) : admin.isAdmin ? (
            <div className="login-session">
              <div className="login-session__head">
                <span className="login-panel__icon" aria-hidden="true">
                  <ShieldCheck size={22} />
                </span>
                <div>
                  <h2>{copy.login.activeTitle}</h2>
                  <p>{copy.login.activeHint}</p>
                </div>
              </div>
              <dl className="login-session__meta">
                <div>
                  <dt>{copy.admin.operator}</dt>
                  <dd>
                    <UserRound size={15} aria-hidden="true" />
                    <span>{admin.user?.email || copy.admin.providerOpen}</span>
                  </dd>
                </div>
                <div>
                  <dt>{copy.admin.provider}</dt>
                  <dd>
                    <ProviderIcon admin={admin} method={method} />
                    <span>{providerLabel}</span>
                  </dd>
                </div>
              </dl>
              <div className="login-session__actions">
                <Link className="cta-button" to="/models">{copy.login.manageModels}</Link>
                <Link className="secondary-button" to="/datasets">{copy.login.manageDatasets}</Link>
                <button className="ghost-button ghost-button--danger" type="button" onClick={admin.lock}>
                  {copy.login.signOut}
                </button>
              </div>
            </div>
          ) : (
            <form className="login-form" onSubmit={submit}>
              <div className="login-form__head">
                <span className="login-panel__icon" aria-hidden="true">
                  {method === 'api_key' ? <KeyRound size={21} /> : method === 'open' ? <ShieldOff size={21} /> : <LogIn size={21} />}
                </span>
                <div>
                  <h2>{copy.admin.signIn}</h2>
                  <p>
                    {method === 'api_key'
                      ? copy.login.apiIntro
                      : method === 'open'
                        ? copy.admin.openLocalHint
                        : copy.login.passwordIntro}
                  </p>
                </div>
              </div>

              {showMethodSwitch && (
                <div className="login-methods" role="group" aria-label={copy.login.methodLabel}>
                  <button
                    type="button"
                    className={method === 'password' ? 'active' : ''}
                    onClick={() => setRequestedMethod('password')}
                  >
                    <Database size={15} aria-hidden="true" />
                    {copy.admin.usePassword}
                  </button>
                  <button
                    type="button"
                    className={method === 'api_key' ? 'active' : ''}
                    onClick={() => setRequestedMethod('api_key')}
                  >
                    <KeyRound size={15} aria-hidden="true" />
                    {copy.admin.useApiKey}
                  </button>
                </div>
              )}

              {method === 'password' && (
                <>
                  <label className="lc-field">
                    <span>{copy.admin.emailPlaceholder}</span>
                    <input
                      type="email"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      autoComplete="username"
                      required
                    />
                  </label>
                  <label className="lc-field">
                    <span>{copy.admin.passwordPlaceholder}</span>
                    <input
                      type="password"
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      autoComplete="current-password"
                      required
                    />
                  </label>
                </>
              )}

              {method === 'api_key' && (
                <label className="lc-field">
                  <span>{copy.admin.keyPlaceholder}</span>
                  <input
                    type="password"
                    value={apiKey}
                    onChange={(event) => setApiKey(event.target.value)}
                    autoComplete="off"
                    required
                  />
                </label>
              )}

              {error && <p className="login-form__error">{error}</p>}

              <button className="cta-button" type="submit" disabled={busy}>
                <LogIn size={16} aria-hidden="true" />
                {busy ? copy.admin.signingIn : openEnabled && method === 'open' ? copy.admin.openLocal : copy.admin.signIn}
              </button>
            </form>
          )}
        </div>
      </div>
    </section>
  )
}
