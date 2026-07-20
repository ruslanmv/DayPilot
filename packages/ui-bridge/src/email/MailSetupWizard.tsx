import React, { useMemo, useState } from 'react'

import {
  emailApi,
  mailErrorMessage,
  type MailboxProbeResult,
  type MailboxTestInput,
  type OnboardingProvider,
} from './emailClient'

/**
 * Shared mailbox setup wizard (Batch 3).
 *
 * Used identically from Email onboarding and Settings → Mail. Steps:
 *   Provider → Auth → Test → Permissions → Save.
 *
 * The wizard never fabricates a connection: it runs the backend's real,
 * non-destructive IMAP/SMTP probe, only offers to save after that probe
 * succeeds, and surfaces honest, specific errors. Credentials are posted to the
 * backend once (over the app proxy) and held server-side by reference — they are
 * never stored in the browser. OAuth is offered only when the deployment
 * actually supports it; otherwise the wizard is honest and falls back to an app
 * password over IMAP/SMTP.
 */

type Step = 'provider' | 'auth' | 'test' | 'permissions' | 'saved'

const KNOWN_HOSTS: Record<string, Partial<MailboxTestInput>> = {
  google: { imapHost: 'imap.gmail.com', imapPort: 993, imapSecurity: 'ssl', smtpHost: 'smtp.gmail.com', smtpPort: 587, smtpSecurity: 'starttls' },
  microsoft: { imapHost: 'outlook.office365.com', imapPort: 993, imapSecurity: 'ssl', smtpHost: 'smtp.office365.com', smtpPort: 587, smtpSecurity: 'starttls' },
}

const DEFAULT_PROVIDERS: OnboardingProvider[] = [
  { id: 'google', label: 'Gmail', auth: 'oauth' },
  { id: 'microsoft', label: 'Microsoft 365', auth: 'oauth' },
  { id: 'imap', label: 'Other email provider (IMAP/SMTP)', auth: 'password' },
]

export function MailSetupWizard({
  providers,
  onConnected,
  onCancel,
}: {
  providers?: OnboardingProvider[]
  onConnected: () => void
  onCancel?: () => void
}) {
  const list = providers && providers.length ? providers : DEFAULT_PROVIDERS
  const [step, setStep] = useState<Step>('provider')
  const [provider, setProvider] = useState<string>('imap')
  const [form, setForm] = useState<MailboxTestInput>({ provider: 'imap' })
  const [busy, setBusy] = useState(false)
  const [probe, setProbe] = useState<MailboxProbeResult | null>(null)
  const [oauthNote, setOauthNote] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const passwordLabel = useMemo(
    () => (provider === 'google' || provider === 'microsoft' ? 'App password' : 'Password'),
    [provider],
  )

  function chooseProvider(id: string) {
    const known = KNOWN_HOSTS[id] || {}
    setProvider(id)
    setForm({ provider: id === 'gmail' ? 'google' : id, ...known })
    setProbe(null)
    setError(null)
    if (id === 'google' || id === 'microsoft') {
      // Honest OAuth: only advertise it when the backend really supports it.
      setBusy(true)
      emailApi.oauthStart(id).then((r) => {
        setBusy(false)
        if (r.ok && r.data.available) { setStep('auth') }
        else { setOauthNote(r.ok ? r.data.message ?? null : null); setStep('auth') }
      })
    } else {
      setOauthNote(null)
      setStep('auth')
    }
  }

  function update(patch: Partial<MailboxTestInput>) {
    setForm((f) => ({ ...f, ...patch }))
  }

  async function runTest() {
    setBusy(true); setError(null)
    const r = await emailApi.test(form)
    setBusy(false)
    if (!r.ok) { setError('Could not reach DayPilot to run the test. Please try again.'); return }
    setProbe(r.data)
    setStep('test')
  }

  async function save() {
    setBusy(true); setError(null)
    const r = await emailApi.connect(form)
    setBusy(false)
    if (!r.ok) { setError('Could not reach DayPilot to save the connection.'); return }
    if (r.data.code === 'connected' || r.data.degraded) {
      setProbe(r.data)
      setStep('permissions')
    } else {
      setProbe(r.data)
      setStep('test')
      setError(mailErrorMessage(r.data.code))
    }
  }

  const canTest = Boolean((form.emailAddress || form.username) && form.password && form.imapHost)
  const testedOk = probe && (probe.code === 'connected' || probe.degraded)

  return (
    <div className="dp-mailwiz" role="dialog" aria-label="Connect your email">
      <div className="dp-mailwiz__head">
        <StepDots step={step} />
        {onCancel && <button type="button" className="dp-ghost-button dp-mailwiz__close" onClick={onCancel}>Close</button>}
      </div>

      {step === 'provider' && (
        <div className="dp-mailwiz__body">
          <h3 className="dp-mailwiz__title">Connect your email</h3>
          <p className="dp-mailwiz__sub">Read and draft replies from DayPilot. It never sends without your approval.</p>
          <div className="dp-mailwiz__providers">
            {list.map((p) => (
              <button key={p.id} type="button" className="dp-mailwiz__provider" onClick={() => chooseProvider(p.id)}>
                <span className="dp-mailwiz__provider-ic" aria-hidden="true">{p.id === 'microsoft' ? '◱' : p.id.includes('goog') || p.id === 'gmail' ? '✉' : '⚙'}</span>
                <span>{p.label}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {step === 'auth' && (
        <div className="dp-mailwiz__body">
          <h3 className="dp-mailwiz__title">Sign in to your mailbox</h3>
          {oauthNote && <p className="dp-mailwiz__note dp-mailwiz__note--warn">{oauthNote}</p>}
          {(provider === 'google' || provider === 'microsoft') && (
            <p className="dp-mailwiz__sub">
              Use an <strong>app password</strong> for {provider === 'google' ? 'Gmail' : 'Microsoft 365'} over IMAP/SMTP.
              Your normal account password won’t work when 2-step verification is on.
            </p>
          )}
          <div className="dp-mailwiz__grid">
            <Field label="Email address">
              <input className="dp-input" type="email" autoComplete="email" value={form.emailAddress ?? ''}
                onChange={(e) => update({ emailAddress: e.target.value, username: e.target.value })} placeholder="you@example.com" />
            </Field>
            <Field label="Display name (optional)">
              <input className="dp-input" value={form.displayName ?? ''} onChange={(e) => update({ displayName: e.target.value })} placeholder="Your name" />
            </Field>
            <Field label={passwordLabel}>
              <input className="dp-input" type="password" autoComplete="off" value={form.password ?? ''}
                onChange={(e) => update({ password: e.target.value })} placeholder="••••••••" />
            </Field>
          </div>

          {provider === 'imap' && (
            <details className="dp-mailwiz__adv" open>
              <summary>Server settings</summary>
              <div className="dp-mailwiz__grid">
                <Field label="IMAP host"><input className="dp-input" value={form.imapHost ?? ''} onChange={(e) => update({ imapHost: e.target.value })} placeholder="imap.example.com" /></Field>
                <Field label="IMAP port"><input className="dp-input" type="number" value={form.imapPort ?? 993} onChange={(e) => update({ imapPort: Number(e.target.value) })} /></Field>
                <Field label="IMAP security">
                  <select className="dp-input" value={form.imapSecurity ?? 'ssl'} onChange={(e) => update({ imapSecurity: e.target.value })}>
                    <option value="ssl">SSL/TLS</option><option value="starttls">STARTTLS</option>
                  </select>
                </Field>
                <Field label="SMTP host"><input className="dp-input" value={form.smtpHost ?? ''} onChange={(e) => update({ smtpHost: e.target.value })} placeholder="smtp.example.com" /></Field>
                <Field label="SMTP port"><input className="dp-input" type="number" value={form.smtpPort ?? 587} onChange={(e) => update({ smtpPort: Number(e.target.value) })} /></Field>
                <Field label="SMTP security">
                  <select className="dp-input" value={form.smtpSecurity ?? 'starttls'} onChange={(e) => update({ smtpSecurity: e.target.value })}>
                    <option value="starttls">STARTTLS</option><option value="ssl">SSL/TLS</option>
                  </select>
                </Field>
              </div>
            </details>
          )}

          {error && <p className="dp-mailwiz__note dp-mailwiz__note--err">{error}</p>}
          <div className="dp-mailwiz__actions">
            <button type="button" className="dp-ghost-button" onClick={() => setStep('provider')}>Back</button>
            <button type="button" className="dp-primary-button" disabled={!canTest || busy} onClick={runTest}>
              {busy ? 'Testing…' : 'Test connection'}
            </button>
          </div>
        </div>
      )}

      {step === 'test' && probe && (
        <div className="dp-mailwiz__body">
          <h3 className="dp-mailwiz__title">Connection test</h3>
          <ul className="dp-mailwiz__checks">
            <CheckRow label="Incoming mail (IMAP)" state={probe.checks?.imap} />
            <CheckRow label="Outgoing mail (SMTP)" state={probe.checks?.smtp} />
          </ul>
          <p className={'dp-mailwiz__note ' + (testedOk ? 'dp-mailwiz__note--ok' : 'dp-mailwiz__note--err')}>
            {mailErrorMessage(probe.code)}
            {probe.degraded && ' You can still connect for reading; sending will be unavailable until SMTP works.'}
          </p>
          {error && <p className="dp-mailwiz__note dp-mailwiz__note--err">{error}</p>}
          <div className="dp-mailwiz__actions">
            <button type="button" className="dp-ghost-button" onClick={() => setStep('auth')}>Edit settings</button>
            <button type="button" className="dp-primary-button" disabled={!testedOk || busy} onClick={save}>
              {busy ? 'Connecting…' : 'Connect'}
            </button>
          </div>
        </div>
      )}

      {step === 'permissions' && (
        <div className="dp-mailwiz__body">
          <h3 className="dp-mailwiz__title">What DayPilot can do</h3>
          <ul className="dp-mailwiz__perms">
            <li><span className="dp-mailwiz__perm-ic" aria-hidden="true">✓</span> Read your mail and draft replies</li>
            <li><span className="dp-mailwiz__perm-ic" aria-hidden="true">✓</span> Turn emails into tasks and plan around them</li>
            <li><span className="dp-mailwiz__perm-ic dp-mailwiz__perm-ic--gate" aria-hidden="true">!</span> Send only after you explicitly approve each message</li>
            <li><span className="dp-mailwiz__perm-ic dp-mailwiz__perm-ic--no" aria-hidden="true">×</span> Never deletes, and never sends on its own</li>
          </ul>
          <p className="dp-mailwiz__note">Your password is stored encrypted server-side and never shown in the app. You can disconnect anytime in Settings → Mail.</p>
          <div className="dp-mailwiz__actions">
            <button type="button" className="dp-primary-button" onClick={() => { setStep('saved'); onConnected() }}>Done</button>
          </div>
        </div>
      )}

      {step === 'saved' && (
        <div className="dp-mailwiz__body">
          <p className="dp-mailwiz__note dp-mailwiz__note--ok">Mailbox connected.</p>
        </div>
      )}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="dp-mailwiz__field">
      <span className="dp-mailwiz__field-label">{label}</span>
      {children}
    </label>
  )
}

function CheckRow({ label, state }: { label: string; state?: string }) {
  const ok = state === 'ok'
  const icon = state === undefined ? '·' : ok ? '✓' : '×'
  const cls = state === undefined ? '' : ok ? 'dp-mailwiz__check--ok' : 'dp-mailwiz__check--err'
  return (
    <li className={'dp-mailwiz__check ' + cls}>
      <span className="dp-mailwiz__check-ic" aria-hidden="true">{icon}</span>
      <span>{label}</span>
    </li>
  )
}

function StepDots({ step }: { step: Step }) {
  const order: Step[] = ['provider', 'auth', 'test', 'permissions']
  const idx = Math.min(order.indexOf(step === 'saved' ? 'permissions' : step), order.length - 1)
  return (
    <div className="dp-mailwiz__dots" aria-hidden="true">
      {order.map((_, i) => <span key={i} className={'dp-mailwiz__dot' + (i <= idx ? ' dp-mailwiz__dot--on' : '')} />)}
    </div>
  )
}
