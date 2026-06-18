import { Link } from 'react-router-dom'
import { LogIn, ShieldCheck } from 'lucide-react'
import clsx from 'clsx'

export function AdminAccessButton({ admin, copy }) {
  const signedIn = Boolean(admin?.isAdmin)
  const label = admin?.checking
    ? copy.login.checking
    : signedIn
      ? admin.user?.email || copy.admin.unlocked
      : copy.admin.signIn

  return (
    <div className="admin-access topbar-control">
      <Link
        className={clsx('admin-access__button', signedIn && 'admin-access__button--active')}
        to="/login"
        aria-label={signedIn ? copy.login.accountLabel : copy.login.title}
      >
        {signedIn ? <ShieldCheck size={16} aria-hidden="true" /> : <LogIn size={16} aria-hidden="true" />}
        <span>{label}</span>
      </Link>
    </div>
  )
}
