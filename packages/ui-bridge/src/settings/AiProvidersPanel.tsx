import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  localErrorText,
  providersApi,
  type ProviderConnection,
  type ProviderKind,
  type ProviderStatus,
} from '../providersClient'
import { PROVIDER_ROUTES } from './settingsData'

/**
 * Settings → AI providers — fully backend-owned (Batch 2).
 *
 * Every value shown (connection state, account, models, active provider) comes
 * from `/v1/providers/status`; nothing is simulated in the browser and no key
 * or token is ever stored client-side. Local Ollabridge is *detected* (real
 * probe) rather than assumed connected; Ollabridge Cloud is authenticated
 * server-side. Identity is separate from provider activation.
 */
export function AiProvidersPanel() {
  const [status, setStatus] = useState<ProviderStatus | null>(null)
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading')
  const liveRef = useRef<HTMLDivElement>(null)

  const refresh = useCallback(() => {
    providersApi.status().then((r) => {
      if (r.ok) { setStatus(r.data); setLoadState('ready') } else setLoadState('error')
    })
  }, [])
  useEffect(() => { refresh() }, [refresh])

  const say = (m: string) => { if (liveRef.current) liveRef.current.textContent = m }
  const conn = (kind: ProviderKind) => status?.connections.find((c) => c.kind === kind)

  if (loadState === 'loading') {
    return <div className="dp-settings-list"><p className="dp-muted"><span className="dp-spinner" aria-hidden="true" /> Loading providers…</p></div>
  }
  if (loadState === 'error') {
    return <div className="dp-settings-list"><p className="dp-muted">Couldn’t load providers. <button className="dp-linkbtn" onClick={refresh}>Try again</button></p></div>
  }

  return (
    <div className="dp-settings-list dp-aip">
      <p className="dp-aip__lead">Choose where DayPilot runs its AI. Ollabridge runs locally by default; sign in to Ollabridge Cloud to reach your models from anywhere. Provider state is verified by the backend.</p>

      <CloudCard conn={conn('ollabridge_cloud')} onChanged={refresh} say={say} />
      <LocalCard conn={conn('local')} onChanged={refresh} say={say} />

      <p className="dp-muted"><button className="dp-linkbtn" type="button">Learn about privacy</button> · Only one provider is active at a time. Signing in never activates cloud inference on its own.</p>

      <p className="dp-muted">Routing policy per agent role (fallback in order):</p>
      {PROVIDER_ROUTES.map((r) => (
        <div key={r.role} className="dp-settings-row dp-settings-row--grid">
          <strong>{r.role}</strong>
          <span>{r.model}</span>
          <span className="dp-pill dp-pill--muted">{r.tier}</span>
          <span>{r.latencyMs}ms</span>
          <span className={'dp-tag dp-tag--' + r.status}>{r.status}</span>
          <span className="dp-provider-fallback">↳ {r.fallback.join(' · ') || 'none'}</span>
        </div>
      ))}

      <div className="dp-sr-live" role="status" aria-live="polite" ref={liveRef} />
    </div>
  )
}

// ---- cloud card -------------------------------------------------------------

function CloudCard({ conn, onChanged, say }: { conn?: ProviderConnection; onChanged: () => void; say: (m: string) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [confirm, setConfirm] = useState<null | 'use' | 'signout'>(null)

  const state = conn?.state ?? 'unconfigured'
  const connected = state === 'connected'
  const active = !!conn?.active && connected

  async function signIn(e: React.FormEvent) {
    e.preventDefault(); setError(''); setBusy(true)
    const res = await providersApi.cloudLogin(email, password)
    setBusy(false); setPassword('')
    if (res.ok && res.data.code === 'connected') { say('Ollabridge Cloud connected.'); onChanged() }
    else setError(cloudErrorText(res.ok ? res.data.code : res.error))
  }
  async function useCloud() { setConfirm(null); const r = await providersApi.setActive('ollabridge_cloud'); if (r.ok) { say('Ollabridge Cloud is now the active provider.'); onChanged() } }
  async function signOut() { setConfirm(null); await providersApi.cloudLogout(); say('Signed out of Ollabridge Cloud.'); onChanged() }

  return (
    <section className={'dp-provcard' + (active ? ' is-selected' : '')} aria-label="Ollabridge Cloud">
      <header className="dp-provcard__head">
        <span className="dp-provcard__icon" aria-hidden="true">☁</span>
        <div className="dp-provcard__titles">
          <strong>Ollabridge Cloud</strong>
          <span className="dp-provcard__privacy">Requests are sent securely to your Ollabridge Cloud workspace.</span>
        </div>
        <span className={'dp-provcard__status dp-provcard__status--' + (connected ? 'connected' : state === 'unauthorized' ? 'warn' : 'available')}>
          {active ? 'Connected · Active' : connected ? 'Connected' : state === 'expired' ? 'Reconnect required' : 'Not signed in'}
        </span>
      </header>

      {!connected && (
        <>
          <p className="dp-provcard__body">Access your approved AI models from any device through Ollabridge Cloud.</p>
          <form className="dp-provcard__form" onSubmit={signIn}>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Cloud account email" aria-label="Ollabridge Cloud email" autoComplete="username" />
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" aria-label="Ollabridge Cloud password" autoComplete="current-password" />
            <button className="dp-provcard__signin" type="submit" disabled={busy || !email || !password}>{busy ? 'Signing in…' : 'Sign in with email'}</button>
          </form>
          {error && <p className="dp-provcard__errbody" role="alert">{error}</p>}
          <p className="dp-provcard__hint">Sign-in happens on the DayPilot server; your password is never stored. API-key connection is available under Advanced setup. Google/SSO arrives when Ollabridge Cloud exposes a relying-party flow.</p>
        </>
      )}

      {connected && conn && (
        <div className="dp-provcard__account">
          <div className="dp-provcard__acctline"><strong>{conn.account?.displayName || conn.account?.email}</strong></div>
          {conn.account?.email && <div className="dp-provcard__acctmail">{conn.account.email}</div>}
          <div className="dp-provcard__acctmeta">{conn.modelsCount} approved models available{conn.defaultModel ? ` · default: ${conn.defaultModel}` : ''}</div>
          {!active
            ? <button className="dp-provcard__use" onClick={() => setConfirm('use')}>Use Ollabridge Cloud</button>
            : <p className="dp-provcard__acctmeta">Active provider.</p>}
          <div className="dp-provcard__acctactions">
            <button className="dp-linkbtn" type="button">Manage account</button>
            <button className="dp-linkbtn dp-linkbtn--danger" type="button" onClick={() => setConfirm('signout')}>Sign out</button>
          </div>
        </div>
      )}

      {confirm === 'use' && (
        <ConfirmDialog title="Use Ollabridge Cloud?" body="New AI requests will be processed through your Ollabridge Cloud account (new requests only)." confirmLabel="Switch provider" onCancel={() => setConfirm(null)} onConfirm={useCloud} />
      )}
      {confirm === 'signout' && (
        <ConfirmDialog title="Sign out of Ollabridge Cloud?" body="DayPilot removes the local authorization for this account. Your Ollabridge Cloud account is not deleted. If Cloud is active, Local Gateway becomes active." confirmLabel="Sign out" danger onCancel={() => setConfirm(null)} onConfirm={signOut} />
      )}
    </section>
  )
}

// ---- local card -------------------------------------------------------------

function LocalCard({ conn, onChanged, say }: { conn?: ProviderConnection; onChanged: () => void; say: (m: string) => void }) {
  const [advanced, setAdvanced] = useState(false)
  const [url, setUrl] = useState(conn?.baseUrl || 'http://localhost:11435/v1')
  const [apiKey, setApiKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  const state = conn?.state ?? 'unconfigured'
  const connected = state === 'connected'
  const active = !!conn?.active && connected

  async function detect() {
    setBusy(true); setMsg('Detecting…')
    const res = await providersApi.localDiscover()
    setBusy(false)
    if (res.ok && res.data.code === 'connected') { setMsg(''); say('Local Ollabridge detected.'); onChanged() }
    else setMsg(localErrorText(res.ok ? res.data.code : res.error))
  }
  async function connect() {
    setBusy(true); setMsg('Testing…')
    const res = await providersApi.localConnect(url, apiKey || undefined)
    setBusy(false)
    if (res.ok && res.data.code === 'connected') { setMsg('Connected.'); onChanged() }
    else setMsg(localErrorText(res.ok ? res.data.code : res.error))
  }
  async function useLocal() { const r = await providersApi.setActive('local'); if (r.ok) { say('Local Gateway is now the active provider.'); onChanged() } }

  return (
    <section className={'dp-provcard' + (active ? ' is-selected' : '')} aria-label="Local Gateway">
      <header className="dp-provcard__head">
        <span className="dp-provcard__icon" aria-hidden="true">💻</span>
        <div className="dp-provcard__titles">
          <strong>Local Gateway</strong>
          <span className="dp-provcard__privacy">Prompts and keys remain on this device.</span>
        </div>
        <span className={'dp-provcard__status dp-provcard__status--' + (connected ? 'connected' : 'available')}>
          {active ? 'Connected · Active' : connected ? 'Connected' : 'Not detected'}
        </span>
      </header>

      {connected ? (
        <>
          <p className="dp-provcard__body">Private, local model access with no cloud login. {conn?.modelsCount ?? 0} model(s) available{conn?.lastLatencyMs ? ` · ~${conn.lastLatencyMs}ms` : ''}.</p>
          {!active && <button className="dp-provcard__use" onClick={useLocal}>Use Local Gateway</button>}
        </>
      ) : (
        <>
          <p className="dp-provcard__body">Run Ollabridge on this machine: <code>pip install ollabridge</code> then <code>ollabridge start</code>.</p>
          <div className="dp-settings-actions">
            <button className="dp-ghost-button" type="button" onClick={detect} disabled={busy}>{busy ? 'Detecting…' : 'Detect again'}</button>
            <a className="dp-ghost-button" href="https://ollabridge.com" target="_blank" rel="noopener noreferrer">Install Ollabridge</a>
          </div>
        </>
      )}

      <button className="dp-linkbtn dp-provcard__adv" type="button" aria-expanded={advanced} onClick={() => setAdvanced((v) => !v)}>Advanced connection</button>
      {advanced && (
        <div className="dp-provcard__advbox">
          <label className="dp-settings-field"><span className="dp-settings-field__label">Endpoint</span></label>
          <input className="dp-provcard__input" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="http://localhost:11435/v1" aria-label="Local endpoint" />
          <input className="dp-provcard__input" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="API key (optional, from Ollabridge startup)" aria-label="Local API key" type="password" />
          <div className="dp-settings-actions">
            <button className="dp-ghost-button" type="button" onClick={connect} disabled={busy}>Test &amp; connect</button>
            <button className="dp-ghost-button" type="button" onClick={() => navigator.clipboard?.writeText(url).catch(() => undefined)}>Copy endpoint</button>
          </div>
          <p className="dp-provcard__hint">Only loopback/private addresses are accepted. Keys are stored server-side by reference and never shown here.</p>
        </div>
      )}
      {msg && <p className="dp-provcard__test">{msg}</p>}
    </section>
  )
}

function cloudErrorText(code: string): string {
  switch (code) {
    case 'unauthorized': return 'That email or password was rejected by Ollabridge Cloud.'
    case 'connection_refused': return 'Couldn’t reach Ollabridge Cloud.'
    case 'timeout': return 'Ollabridge Cloud didn’t respond in time.'
    case 'invalid_response': return 'Ollabridge Cloud returned an unexpected response.'
    default: return 'Sign-in failed. Please try again.'
  }
}

function ConfirmDialog({ title, body, confirmLabel, danger, onCancel, onConfirm }: {
  title: string; body: string; confirmLabel: string; danger?: boolean; onCancel: () => void; onConfirm: () => void
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onCancel() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onCancel])
  return (
    <div className="dp-confirm" role="dialog" aria-modal="true" aria-label={title}>
      <div className="dp-confirm__scrim" onClick={onCancel} aria-hidden="true" />
      <div className="dp-confirm__card">
        <h4 className="dp-confirm__title">{title}</h4>
        <p className="dp-confirm__body">{body}</p>
        <div className="dp-confirm__actions">
          <button className="dp-ghost-button" type="button" onClick={onCancel}>Cancel</button>
          <button className={'dp-provcard__use' + (danger ? ' dp-provcard__use--danger' : '')} type="button" onClick={onConfirm} autoFocus>{confirmLabel}</button>
        </div>
      </div>
    </div>
  )
}
