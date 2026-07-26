import React, { useEffect, useRef, useState } from 'react'

import {
  emailApi,
  mailRecovery,
  type MailboxConnection,
  type MailboxTestInput,
  type MailRecovery,
  type OnboardingProvider,
} from './emailClient'

/**
 * Premium email connection wizard.
 *
 * Reduces mailbox setup from a technical configuration process to a guided
 * sign-in: Choose account → Enter credentials → Connected. Server discovery,
 * protocol/port selection, connection testing, and saving all happen in one
 * backend action; ordinary users never see IMAP/SMTP, ports, or SSL/STARTTLS —
 * those live behind a collapsed "Advanced settings" recovery option.
 *
 * The backend stays the source of truth: it discovers settings, runs the same
 * non-destructive IMAP/SMTP probe, and only persists on success. Passwords are
 * posted once and cleared from React state immediately after the response.
 */

type MailSetupStep = 'choose-account' | 'credentials' | 'connecting' | 'connection-help' | 'connected'
type Mode = 'google' | 'microsoft' | 'generic'

export function MailSetupWizard({
  onConnected,
  onCancel,
  asModal = false,
}: {
  providers?: OnboardingProvider[]
  onConnected: () => void
  onCancel?: () => void
  asModal?: boolean
}) {
  const [step, setStep] = useState<MailSetupStep>('choose-account')
  const [mode, setMode] = useState<Mode>('generic')
  const [form, setForm] = useState<MailboxTestInput>({ provider: 'imap' })
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [appHelpOpen, setAppHelpOpen] = useState(false)
  const [appPasswordRecommended, setAppPasswordRecommended] = useState(false)
  const [busy, setBusy] = useState(false)
  const [oauthNote, setOauthNote] = useState<string | null>(null)
  const [recovery, setRecovery] = useState<MailRecovery | null>(null)
  const [degraded, setDegraded] = useState(false)
  const [connection, setConnection] = useState<MailboxConnection | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)

  // Move focus to the heading on each screen (screen-reader + keyboard clarity).
  useEffect(() => { headingRef.current?.focus() }, [step])

  const emailAddress = form.emailAddress ?? ''
  const update = (patch: Partial<MailboxTestInput>) => setForm((f) => ({ ...f, ...patch }))

  function goCredentials(next: Mode) {
    setMode(next)
    setRecovery(null)
    setDegraded(false)
    setForm((f) => ({ ...f, provider: next === 'generic' ? 'imap' : next }))
    setStep('credentials')
  }

  async function startOAuth(provider: 'google' | 'microsoft') {
    setBusy(true); setOauthNote(null)
    const r = await emailApi.oauthStart(provider)
    setBusy(false)
    if (r.ok && r.data.available && r.data.authorizationUrl) {
      window.location.assign(r.data.authorizationUrl)  // real authorization-code redirect
      return
    }
    // Not configured on this deployment — fall back to an app password, honestly.
    setOauthNote(r.ok ? r.data.message ?? null : 'Secure sign-in is temporarily unavailable.')
    goCredentials(provider)
  }

  async function onEmailBlur() {
    if (!emailAddress.includes('@')) return
    const r = await emailApi.discover(emailAddress)
    if (r.ok) {
      setAppPasswordRecommended(Boolean(r.data.appPasswordRecommended))
      if (r.data.settings) {
        update({
          imapHost: r.data.settings.imapHost, imapPort: r.data.settings.imapPort, imapSecurity: r.data.settings.imapSecurity,
          smtpHost: r.data.settings.smtpHost, smtpPort: r.data.settings.smtpPort, smtpSecurity: r.data.settings.smtpSecurity,
          username: form.username || emailAddress,
        })
      }
    }
  }

  async function connect() {
    setStep('connecting'); setRecovery(null); setBusy(true)
    const payload: MailboxTestInput = {
      provider: mode === 'generic' ? 'imap' : mode,
      emailAddress,
      username: form.username || emailAddress,
      password,
      ...(advancedOpen || mode === 'generic'
        ? { imapHost: form.imapHost, imapPort: form.imapPort, imapSecurity: form.imapSecurity, smtpHost: form.smtpHost, smtpPort: form.smtpPort, smtpSecurity: form.smtpSecurity }
        : {}),
    }
    const r = await emailApi.connect(payload)
    setPassword('')  // remove the secret from browser state as soon as possible
    setBusy(false)
    if (!r.ok) {
      setRecovery({ title: 'We couldn’t complete the connection', message: 'DayPilot couldn’t reach the server. Please try again.', primary: 'retry' })
      setStep('connection-help'); return
    }
    const d = r.data
    if (d.code === 'connected' && !d.degraded) {
      setConnection(d.connection ?? null); setDegraded(false); setStep('connected'); return
    }
    if (d.degraded) {
      setConnection(d.connection ?? null); setDegraded(true)
      setRecovery(mailRecovery(d.code, appPasswordRecommended)); setStep('connection-help'); return
    }
    setRecovery(mailRecovery(d.code, appPasswordRecommended)); setStep('connection-help')
  }

  function doRecovery(action: MailRecovery['primary']) {
    switch (action) {
      case 'app_password_help': setAppHelpOpen(true); setStep('credentials'); break
      case 'manual_settings':
      case 'advanced': setAdvancedOpen(true); setStep('credentials'); break
      case 'retry':
      default: setStep('credentials'); break
    }
  }

  const connectedEmail = connection?.emailAddress || emailAddress
  const canConnect = Boolean(emailAddress.includes('@') && password)

  const Wrapper: React.ElementType = 'div'
  const wrapperProps = asModal
    ? { role: 'dialog', 'aria-modal': true, 'aria-label': 'Connect your email' }
    : { 'aria-labelledby': 'mail-setup-title' }

  return (
    <Wrapper className="dp-mailwiz" {...wrapperProps}>
      {step !== 'choose-account' && step !== 'connected' && (
        <div className="dp-mailwiz__head">
          <button type="button" className="dp-ghost-button dp-mailwiz__back" onClick={() => setStep('choose-account')}>← Back</button>
          <span className="dp-mailwiz__stepno">Step 2 of 2 — Sign in</span>
        </div>
      )}

      {step === 'choose-account' && (
        <div className="dp-mailwiz__body">
          <h3 className="dp-mailwiz__title" id="mail-setup-title" tabIndex={-1} ref={headingRef}>Connect your email</h3>
          <p className="dp-mailwiz__sub">Bring your inbox into DayPilot to organize messages, prepare replies, and turn emails into tasks. Nothing is sent or deleted without your approval.</p>
          <div className="dp-mailwiz__accounts">
            <AccountRow icon={<GoogleMark />} title="Continue with Google" desc="Gmail and Google Workspace" busy={busy} onClick={() => startOAuth('google')} />
            <AccountRow icon={<MicrosoftMark />} title="Continue with Microsoft" desc="Outlook and Microsoft 365" busy={busy} onClick={() => startOAuth('microsoft')} />
            <AccountRow icon={<MailMark />} title="Connect another email account" desc="Use your email address and password or app password" busy={busy} onClick={() => goCredentials('generic')} />
          </div>
          <ul className="dp-mailwiz__trust">
            <li>✓ Creates drafts by default</li>
            <li>✓ Every send requires approval</li>
            <li>✓ Disconnect anytime</li>
          </ul>
          {onCancel && <button type="button" className="dp-mailwiz__notnow" onClick={onCancel}>Not now</button>}
        </div>
      )}

      {step === 'credentials' && (
        <div className="dp-mailwiz__body">
          <h3 className="dp-mailwiz__title" id="mail-setup-title" tabIndex={-1} ref={headingRef}>
            {mode === 'google' ? 'Sign in to Gmail' : mode === 'microsoft' ? 'Sign in to Microsoft 365' : 'Connect another email account'}
          </h3>
          <p className="dp-mailwiz__sub">Enter the sign-in details you use for email applications.</p>
          {oauthNote && <p className="dp-mailwiz__note dp-mailwiz__note--warn" role="status">{oauthNote}</p>}

          <Field label="Email address">
            <input className="dp-input" type="email" autoComplete="email" value={emailAddress}
              onChange={(e) => update({ emailAddress: e.target.value, username: e.target.value })}
              onBlur={onEmailBlur} placeholder="you@example.com" />
          </Field>

          <Field label="Password or app password" htmlFor="dp-mail-pw"
            error={recovery?.field === 'password' ? recovery.message : undefined}>
            <div className="dp-mailwiz__pwrow">
              <input id="dp-mail-pw" className="dp-input" type={showPassword ? 'text' : 'password'} autoComplete="current-password"
                aria-invalid={recovery?.field === 'password' || undefined}
                aria-describedby={recovery?.field === 'password' ? 'dp-mail-pw-err' : undefined}
                value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••••••" />
              <button type="button" className="dp-mailwiz__reveal" aria-pressed={showPassword} onClick={() => setShowPassword((v) => !v)}>
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </div>
          </Field>

          <p className="dp-mailwiz__hint">Some email services require a separate password for external email applications.</p>
          <button type="button" className="dp-linkbtn" onClick={() => setAppHelpOpen((v) => !v)} aria-expanded={appHelpOpen}>
            Where do I find an app password?
          </button>
          {appHelpOpen && <AppPasswordHelp emailAddress={emailAddress} />}

          <details className="dp-mailwiz__adv" open={advancedOpen} onToggle={(e) => setAdvancedOpen((e.target as HTMLDetailsElement).open)}>
            <summary>Advanced settings</summary>
            <p className="dp-mailwiz__hint">Change these only when your email service or administrator has provided them.</p>
            <div className="dp-mailwiz__grid">
              <Field label="Username"><input className="dp-input" value={form.username ?? emailAddress} onChange={(e) => update({ username: e.target.value })} placeholder="Defaults to your email address" /></Field>
              <Field label="IMAP host"><input className="dp-input" value={form.imapHost ?? ''} onChange={(e) => update({ imapHost: e.target.value })} placeholder="imap.example.com" /></Field>
              <Field label="IMAP security">
                <select className="dp-input" value={form.imapSecurity ?? 'ssl'}
                  onChange={(e) => update({ imapSecurity: e.target.value, imapPort: suggestedPort('imap', e.target.value) })}>
                  <option value="ssl">SSL/TLS</option><option value="starttls">STARTTLS</option>
                </select>
              </Field>
              <Field label="IMAP port"><input className="dp-input" type="number" value={form.imapPort ?? 993} onChange={(e) => update({ imapPort: Number(e.target.value) })} /></Field>
              <Field label="SMTP host"><input className="dp-input" value={form.smtpHost ?? ''} onChange={(e) => update({ smtpHost: e.target.value })} placeholder="smtp.example.com" /></Field>
              <Field label="SMTP security">
                <select className="dp-input" value={form.smtpSecurity ?? 'starttls'}
                  onChange={(e) => update({ smtpSecurity: e.target.value, smtpPort: suggestedPort('smtp', e.target.value) })}>
                  <option value="starttls">STARTTLS</option><option value="ssl">SSL/TLS</option>
                </select>
              </Field>
              <Field label="SMTP port"><input className="dp-input" type="number" value={form.smtpPort ?? 587} onChange={(e) => update({ smtpPort: Number(e.target.value) })} /></Field>
            </div>
          </details>

          <div className="dp-mailwiz__actions">
            <button type="button" className="dp-primary-button dp-mailwiz__connect" disabled={!canConnect || busy} onClick={connect}>Connect securely</button>
          </div>
        </div>
      )}

      {step === 'connecting' && (
        <div className="dp-mailwiz__body">
          <h3 className="dp-mailwiz__title" id="mail-setup-title" tabIndex={-1} ref={headingRef}>Connecting your email</h3>
          <p className="dp-mailwiz__sub">Please keep this window open.</p>
          <div className="dp-mailwiz__progress" role="status" aria-live="polite" aria-atomic="true">
            <span className="dp-spinner" aria-hidden="true" />
            <span>Finding secure settings, checking your sign-in, inbox, and outgoing mail…</span>
          </div>
        </div>
      )}

      {step === 'connection-help' && recovery && (
        <div className="dp-mailwiz__body">
          <h3 className="dp-mailwiz__title" id="mail-setup-title" tabIndex={-1} ref={headingRef}>{recovery.title}</h3>
          <p className="dp-mailwiz__note dp-mailwiz__note--err" id="dp-mail-pw-err" role="alert">{recovery.message}</p>
          {degraded ? (
            <div className="dp-mailwiz__actions">
              <button type="button" className="dp-primary-button" onClick={() => setStep('connected')}>Continue with inbox only</button>
              <button type="button" className="dp-ghost-button" onClick={() => doRecovery('advanced')}>Fix outgoing mail</button>
            </div>
          ) : (
            <div className="dp-mailwiz__actions">
              <button type="button" className="dp-primary-button" onClick={() => doRecovery(recovery.primary)}>
                {primaryLabel(recovery.primary)}
              </button>
              {recovery.secondary && (
                <button type="button" className="dp-ghost-button" onClick={() => doRecovery(recovery.secondary!)}>
                  {primaryLabel(recovery.secondary)}
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {step === 'connected' && (
        <div className="dp-mailwiz__body dp-mailwiz__success">
          <div className="dp-mailwiz__success-ic" aria-hidden="true">✓</div>
          <h3 className="dp-mailwiz__title" id="mail-setup-title" tabIndex={-1} ref={headingRef}>Your email is connected</h3>
          <p className="dp-mailwiz__addr">{connectedEmail}</p>
          <ul className="dp-mailwiz__perms">
            <li><span aria-hidden="true">✓</span> Read and organize your inbox</li>
            <li><span aria-hidden="true">✓</span> Prepare reply drafts</li>
            <li><span aria-hidden="true">✓</span> Turn messages into tasks</li>
            <li><span aria-hidden="true">✓</span> Send only after you approve the exact message</li>
          </ul>
          {degraded && <p className="dp-mailwiz__note dp-mailwiz__note--warn">Reading and drafts are available. Sending stays disabled until outgoing mail is fixed.</p>}
          <p className="dp-mailwiz__hint">DayPilot does not automatically send or delete email.</p>
          <div className="dp-mailwiz__actions">
            <button type="button" className="dp-primary-button" onClick={onConnected}>Open my inbox</button>
            <button type="button" className="dp-linkbtn" onClick={() => (onCancel ?? onConnected)()}>Manage connection</button>
          </div>
        </div>
      )}
    </Wrapper>
  )
}

function AccountRow({ icon, title, desc, busy, onClick }: { icon: React.ReactNode; title: string; desc: string; busy: boolean; onClick: () => void }) {
  return (
    <button type="button" className="dp-mailwiz__account" disabled={busy} onClick={onClick}>
      <span className="dp-mailwiz__account-ic" aria-hidden="true">{icon}</span>
      <span className="dp-mailwiz__account-main">
        <span className="dp-mailwiz__account-title">{title}</span>
        <span className="dp-mailwiz__account-desc">{desc}</span>
      </span>
      <span className="dp-mailwiz__chev" aria-hidden="true">›</span>
    </button>
  )
}

function AppPasswordHelp({ emailAddress }: { emailAddress: string }) {
  const domain = emailAddress.includes('@') ? emailAddress.split('@')[1].toLowerCase() : ''
  const securityUrl = domain.includes('gmail') || domain.includes('google') ? 'https://myaccount.google.com/apppasswords'
    : domain.includes('outlook') || domain.includes('hotmail') || domain.includes('live') || domain.includes('office365') ? 'https://account.microsoft.com/security'
    : domain.includes('icloud') || domain.includes('me.com') ? 'https://appleid.apple.com'
    : domain.includes('yahoo') ? 'https://login.yahoo.com/account/security'
    : ''
  return (
    <div className="dp-mailwiz__help">
      <strong>Create a password for email applications</strong>
      <p className="dp-mailwiz__hint">Some email services don’t allow external applications to use your normal account password.</p>
      <ol className="dp-mailwiz__helpsteps">
        <li>Open your email account’s security settings.</li>
        <li>Enable two-step verification if your service requires it.</li>
        <li>Find <em>App passwords</em> (or “passwords for email apps”).</li>
        <li>Create a new password and name it <strong>DayPilot</strong>.</li>
        <li>Copy it, return here, and paste it into the password field.</li>
      </ol>
      <p className="dp-mailwiz__hint">Use the generated password only for this connection. You can revoke it later from your account’s security settings.</p>
      {securityUrl && <a className="dp-ghost-button" href={securityUrl} target="_blank" rel="noopener noreferrer">Open my email security settings</a>}
    </div>
  )
}

function Field({ label, htmlFor, error, children }: { label: string; htmlFor?: string; error?: string; children: React.ReactNode }) {
  return (
    <label className="dp-mailwiz__field" htmlFor={htmlFor}>
      <span className="dp-mailwiz__field-label">{label}</span>
      {children}
      {error && <span className="dp-mailwiz__field-err" id={htmlFor ? `${htmlFor}-err` : undefined} role="alert">{error}</span>}
    </label>
  )
}

/** Suggest a port when the user changes the security mode (never silently
 *  overwrites a value the user typed — the caller only calls this on change). */
function suggestedPort(protocol: 'imap' | 'smtp', security: string): number {
  if (protocol === 'imap') return security === 'ssl' ? 993 : 143
  return security === 'ssl' ? 465 : 587
}

function primaryLabel(action: MailRecovery['primary']): string {
  switch (action) {
    case 'app_password_help': return 'How to create an app password'
    case 'manual_settings': return 'Enter settings manually'
    case 'advanced': return 'Review advanced settings'
    case 'retry':
    default: return 'Try again'
  }
}

// --- neutral, accessible provider marks (decorative; label carries meaning) ---
function GoogleMark() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" focusable="false">
      <path fill="#4285F4" d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.5a5.6 5.6 0 0 1-2.4 3.7v3h3.9c2.3-2.1 3.5-5.2 3.5-8.9z" />
      <path fill="#34A853" d="M12 24c3.2 0 6-1.1 8-2.9l-3.9-3c-1.1.7-2.5 1.2-4.1 1.2-3.1 0-5.8-2.1-6.7-5H1.3v3.1A12 12 0 0 0 12 24z" />
      <path fill="#FBBC05" d="M5.3 14.3a7.2 7.2 0 0 1 0-4.6V6.6H1.3a12 12 0 0 0 0 10.8l4-3.1z" />
      <path fill="#EA4335" d="M12 4.8c1.8 0 3.3.6 4.6 1.8l3.4-3.4A12 12 0 0 0 1.3 6.6l4 3.1C6.2 6.9 8.9 4.8 12 4.8z" />
    </svg>
  )
}
function MicrosoftMark() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" focusable="false">
      <path fill="#F25022" d="M1 1h10v10H1z" /><path fill="#7FBA00" d="M13 1h10v10H13z" />
      <path fill="#00A4EF" d="M1 13h10v10H1z" /><path fill="#FFB900" d="M13 13h10v10H13z" />
    </svg>
  )
}
function MailMark() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.7" focusable="false">
      <rect x="2.5" y="4.5" width="19" height="15" rx="2.5" /><path d="M3 6l9 6 9-6" />
    </svg>
  )
}
