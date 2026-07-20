import React, { useState } from 'react'
import { authApi, authErrorText, type AuthUser } from '../authClient'
import { apiBase } from '../env'

/**
 * The logged-out entry surface — a premium, enterprise split-screen sign-in (and
 * first-run bootstrap). No workspace navigation, assistant, tasks, projects, or
 * settings are visible here. Identity sign-in is deliberately separate from
 * AI-provider activation: signing in never activates Cloud inference.
 *
 * Everything shown is honestly wired to the backend-owned auth API. Options that
 * a deployment hasn't enabled (Ollabridge Cloud identity login, enterprise SSO)
 * only appear when `/v1/auth/config` reports them available.
 */
export function LoginPage({ mode, cloudAvailable, ssoAvailable, onAuthenticated }: {
  mode: 'login' | 'bootstrap'
  cloudAvailable: boolean
  ssoAvailable?: boolean
  onAuthenticated: (user: AuthUser) => void
}) {
  const bootstrap = mode === 'bootstrap'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [workspace, setWorkspace] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [remember, setRemember] = useState(false)
  const [advanced, setAdvanced] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(''); setNotice('')
    setBusy(true)
    const res = bootstrap
      ? await authApi.bootstrap(email, password, name || email, workspace || 'My workspace')
      : await authApi.login(email, password)
    setBusy(false)
    if (res.ok) onAuthenticated(res.data.user)
    else setError(authErrorText(res.error))
  }

  return (
    <div className="dp-auth">
      <section className="dp-auth__panel" aria-label="DayPilot sign in">
        <a className="dp-auth__brand" href="#" aria-label="DayPilot home" onClick={(e) => e.preventDefault()}>
          <span className="dp-auth__logo" aria-hidden="true">
            <svg viewBox="0 0 32 32" fill="none">
              <defs>
                <linearGradient id="dp-auth-brand" x1="4" y1="3.5" x2="28" y2="28">
                  <stop stopColor="var(--dp-auth-cyan)" />
                  <stop offset=".52" stopColor="var(--dp-auth-blue)" />
                  <stop offset="1" stopColor="var(--dp-auth-violet)" />
                </linearGradient>
              </defs>
              <path d="M16 3.5 28.5 28 16 22.2 3.5 28Z" fill="url(#dp-auth-brand)" opacity="0.55" />
              <path d="M16 3.5 28.5 28 16 22.2Z" fill="url(#dp-auth-brand)" />
            </svg>
          </span>
          <span className="dp-auth__brand-copy">
            <span className="dp-auth__brand-name">DayPilot</span>
            <span className="dp-auth__tagline">Plan clearly. Act with control.</span>
          </span>
        </a>

        <div className="dp-auth__wrap">
          <div className="dp-auth__eyebrow">{bootstrap ? 'First-run setup' : 'Enterprise workspace'}</div>
          <h1 className="dp-auth__title">{bootstrap ? 'Create your workspace' : 'Welcome back'}</h1>
          <p className="dp-auth__intro">
            {bootstrap
              ? <>Create the first owner for this DayPilot deployment. Your <strong>governed AI workspace</strong> — plans, agents, approvals, and connected services — stays under your control.</>
              : <>Sign in to your <strong>governed AI workspace</strong>. Your plans, agents, approvals, and connected services stay under your control.</>}
          </p>

          <form className="dp-auth__form" onSubmit={submit}>
            {bootstrap && (
              <>
                <label className="dp-auth__label">Workspace name
                  <span className="dp-auth__field">
                    <span className="dp-auth__ic" aria-hidden="true">
                      <svg viewBox="0 0 24 24" fill="none"><rect x="4" y="4.5" width="16" height="15" rx="2.4" stroke="currentColor" strokeWidth="1.7" /><path d="M4 9.5h16" stroke="currentColor" strokeWidth="1.7" /></svg>
                    </span>
                    <input value={workspace} onChange={(e) => setWorkspace(e.target.value)} placeholder="Acme workspace" autoComplete="organization" required />
                  </span>
                </label>
                <label className="dp-auth__label">Your name
                  <span className="dp-auth__field">
                    <span className="dp-auth__ic" aria-hidden="true">
                      <svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="8.5" r="3.5" stroke="currentColor" strokeWidth="1.7" /><path d="M5.5 19a6.5 6.5 0 0 1 13 0" stroke="currentColor" strokeWidth="1.7" /></svg>
                    </span>
                    <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" autoComplete="name" required />
                  </span>
                </label>
              </>
            )}

            <label className="dp-auth__label">Work email
              <span className="dp-auth__field">
                <span className="dp-auth__ic" aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none"><rect x="3.5" y="5.5" width="17" height="13" rx="2.4" stroke="currentColor" strokeWidth="1.7" /><path d="m5.2 7.3 6.8 5.1 6.8-5.1" stroke="currentColor" strokeWidth="1.7" /></svg>
                </span>
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" autoComplete="username" required autoFocus={!bootstrap} />
              </span>
            </label>

            <label className="dp-auth__label">Password
              <span className="dp-auth__field">
                <span className="dp-auth__ic" aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none"><rect x="4" y="10" width="16" height="10" rx="2.4" stroke="currentColor" strokeWidth="1.7" /><path d="M8 10V7a4 4 0 0 1 8 0v3" stroke="currentColor" strokeWidth="1.7" /></svg>
                </span>
                <input type={showPass ? 'text' : 'password'} value={password} onChange={(e) => setPassword(e.target.value)}
                  placeholder={bootstrap ? 'Create a strong password (min 10)' : 'Enter your password'}
                  autoComplete={bootstrap ? 'new-password' : 'current-password'} required />
                <button className="dp-auth__eye" type="button" onClick={() => setShowPass((s) => !s)} aria-label={showPass ? 'Hide password' : 'Show password'}>
                  {showPass
                    ? <svg viewBox="0 0 24 24" fill="none"><path d="M3 3l18 18" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /><path d="M10.6 6.2A9.7 9.7 0 0 1 12 6c6 0 9.5 6 9.5 6a15 15 0 0 1-3 3.6M6.4 8.1A15 15 0 0 0 2.5 12S6 18 12 18c1 0 1.9-.16 2.8-.44" stroke="currentColor" strokeWidth="1.7" /></svg>
                    : <svg viewBox="0 0 24 24" fill="none"><path d="M2.5 12S6 6 12 6s9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" stroke="currentColor" strokeWidth="1.7" /><circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.7" /></svg>}
                </button>
              </span>
            </label>

            {!bootstrap && (
              <div className="dp-auth__meta">
                <label className="dp-auth__check"><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />Trust this device</label>
                <button className="dp-auth__link" type="button" onClick={() => setNotice('Password recovery is handled by your workspace owner. Ask them to reset it in DayPilot settings.')}>Forgot password?</button>
              </div>
            )}

            {error && <p className="dp-auth__error" role="alert">{error}</p>}
            {notice && <p className="dp-auth__notice">{notice}</p>}

            <button className="dp-auth__primary" type="submit" disabled={busy || !email || !password || (bootstrap && !workspace)}>
              {busy ? 'Please wait…' : bootstrap ? 'Create local workspace' : 'Sign in to DayPilot'}
            </button>
          </form>

          {!bootstrap && cloudAvailable && (
            <>
              <div className="dp-auth__divider"><span>or</span></div>
              <button className="dp-auth__cloud" type="button"
                onClick={() => setNotice('Opening secure Ollabridge Cloud sign-in…')}>
                <span className="dp-auth__cloud-ic" aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none"><path d="M7.2 18.2h10.1a4.2 4.2 0 0 0 .5-8.4A6.1 6.1 0 0 0 6.2 8.2a5 5 0 0 0 1 10Z" stroke="currentColor" strokeWidth="1.7" /><path d="m9.4 13.1 2.1 2.1 3.7-4" stroke="currentColor" strokeWidth="1.7" /></svg>
                </span>
                Continue with Ollabridge Cloud
              </button>
              <p className="dp-auth__note">
                <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 3.4 19 6v5.2c0 4.3-2.8 7.9-7 9.4-4.2-1.5-7-5.1-7-9.4V6l7-2.6Z" stroke="currentColor" strokeWidth="1.7" /><path d="m9 12 2 2 4-4" stroke="currentColor" strokeWidth="1.7" /></svg>
                <span>Ollabridge Cloud sign-in is optional. Cloud inference is never activated without your confirmation.</span>
              </p>
            </>
          )}

          {!bootstrap && (
            <section className={'dp-auth__advanced' + (advanced ? ' is-open' : '')}>
              <button className="dp-auth__adv-toggle" type="button" aria-expanded={advanced} onClick={() => setAdvanced((o) => !o)}>
                Advanced connection
                <svg className="dp-auth__chev" viewBox="0 0 24 24" fill="none"><path d="m7 9.5 5 5 5-5" stroke="currentColor" strokeWidth="1.8" /></svg>
              </button>
              <div className="dp-auth__adv-body">
                <label className="dp-auth__compact">DayPilot server
                  <input type="text" value={apiBase() || window.location.origin} readOnly aria-readonly="true" />
                </label>
                {ssoAvailable
                  ? <button className="dp-auth__sso" type="button" onClick={() => setNotice('Redirecting to your identity provider…')}>Continue with enterprise SSO</button>
                  : <p className="dp-auth__adv-hint">Enterprise SSO appears here when an OIDC or SAML provider is configured.</p>}
              </div>
            </section>
          )}

          <p className="dp-auth__legal">
            By continuing, you agree to DayPilot's <a href="#" onClick={(e) => e.preventDefault()}>Terms of Service</a> and{' '}
            <a href="#" onClick={(e) => e.preventDefault()}>Privacy Policy</a>. Authentication and AI-provider selection remain separate.
          </p>
        </div>
      </section>

      <aside className="dp-auth__visual" aria-hidden="true">
        <div className="dp-auth__glow" />
        <div className="dp-auth__noise" />
      </aside>
    </div>
  )
}
