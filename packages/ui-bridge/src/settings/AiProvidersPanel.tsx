import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { apiBase } from '../env'
import {
  CLOUD_WEB_LOGIN_URL,
  CLOUD_WEB_REGISTER_URL,
  PROVIDERS_CHANGED_EVENT,
  cloudErrorText,
  cloudKeyErrorText,
  gatewayDashboardUrl,
  gatewayRoot,
  humanizeRole,
  localErrorText,
  providerLoadError,
  providersApi,
  type GatewayInfo,
  type ProviderConnection,
  type ProviderKind,
  type ProviderStatus,
  type RoutePolicy,
} from '../providersClient'
import { PROVIDER_ROUTES } from './settingsData'

/**
 * Settings → AI providers — fully backend-owned (Batch 2, v2 surface).
 *
 * Every value shown (connection state, account, models, active provider) comes
 * from `/v1/providers/status`; nothing is simulated in the browser and no key
 * or token is ever kept client-side. Local Ollabridge is *detected* (real
 * probe) rather than assumed connected; Ollabridge Cloud is authenticated
 * server-side with an account sign-in or a dashboard API key. Identity is
 * separate from provider activation.
 *
 * The panel never dead-ends on a failed status read: `make run` brings the web
 * server up a few seconds before the API gateway finishes importing, so the
 * first call routinely fails for reasons that fix themselves. It retries with
 * back-off, names the actual cause while it does, and re-syncs on focus.
 */

/** Back-off for the status load. The first retries are silent; after that the
 *  cause is shown while retrying continues, then a slow steady poll. */
const RETRY_DELAYS_MS = [800, 1500, 3000, 5000, 8000]
const QUIET_ATTEMPTS = 2
const SLOW_RETRY_MS = 10_000

type LoadState =
  | { kind: 'loading'; attempt: number }
  | { kind: 'error'; error: string; status?: number; attempt: number }
  | { kind: 'ready' }

function useProviderStatus() {
  const [status, setStatus] = useState<ProviderStatus | null>(null)
  const [load, setLoad] = useState<LoadState>({ kind: 'loading', attempt: 0 })
  const timer = useRef<number | null>(null)
  const alive = useRef(true)

  const clearTimer = useCallback(() => {
    if (timer.current !== null) { window.clearTimeout(timer.current); timer.current = null }
  }, [])

  const attempt = useCallback(async (n: number) => {
    const r = await providersApi.status()
    if (!alive.current) return
    if (r.ok) { setStatus(r.data); setLoad({ kind: 'ready' }); return }
    const next = n + 1
    const delay = next <= RETRY_DELAYS_MS.length ? RETRY_DELAYS_MS[next - 1] : SLOW_RETRY_MS
    setLoad(next <= QUIET_ATTEMPTS
      ? { kind: 'loading', attempt: next }
      : { kind: 'error', error: r.error, status: r.status, attempt: next })
    clearTimer()
    timer.current = window.setTimeout(() => { void attempt(next) }, delay)
  }, [clearTimer])

  /** Full reload on the fast schedule (mount, "Try again"). */
  const refresh = useCallback(() => {
    clearTimer()
    setLoad({ kind: 'loading', attempt: 0 })
    void attempt(0)
  }, [attempt, clearTimer])

  /** Quiet re-sync that keeps the current view (focus, provider change events,
   *  after a mutation). Also the way an error state heals itself. */
  const resync = useCallback(() => {
    providersApi.status().then((r) => {
      if (alive.current && r.ok) { setStatus(r.data); setLoad({ kind: 'ready' }); clearTimer() }
    })
  }, [clearTimer])

  useEffect(() => {
    alive.current = true
    refresh()
    const onChange = () => resync()
    const onVisible = () => { if (document.visibilityState === 'visible') resync() }
    window.addEventListener(PROVIDERS_CHANGED_EVENT, onChange)
    window.addEventListener('focus', onChange)
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      alive.current = false
      clearTimer()
      window.removeEventListener(PROVIDERS_CHANGED_EVENT, onChange)
      window.removeEventListener('focus', onChange)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [refresh, resync, clearTimer])

  return { status, load, refresh, resync }
}

export function AiProvidersPanel() {
  const { status, load, refresh, resync } = useProviderStatus()
  const liveRef = useRef<HTMLDivElement>(null)
  const say = useCallback((m: string) => { if (liveRef.current) liveRef.current.textContent = m }, [])
  const conn = (kind: ProviderKind) => status?.connections.find((c) => c.kind === kind)

  if (!status) {
    if (load.kind === 'error') {
      return <LoadError error={load.error} status={load.status} attempt={load.attempt} onRetry={refresh} />
    }
    const connecting = load.kind === 'loading' && load.attempt > 0
    return (
      <div className="dp-settings-list dp-aip">
        <p className="dp-muted dp-aip__loading">
          <span className="dp-spinner" aria-hidden="true" /> {connecting ? 'Connecting to the DayPilot API…' : 'Loading providers…'}
        </p>
      </div>
    )
  }

  return (
    <div className="dp-settings-list dp-aip">
      <p className="dp-aip__lead">Choose where DayPilot runs its AI. Ollabridge on this machine is the private default; sign in to Ollabridge Cloud to reach your approved models from anywhere. Every state shown here is verified by the DayPilot server.</p>

      <ActiveSummary status={status} />

      <LocalCard conn={conn('local')} onChanged={resync} say={say} />
      <CloudCard
        conn={conn('ollabridge_cloud')}
        loginUrl={status.cloudLoginUrl || CLOUD_WEB_LOGIN_URL}
        registerUrl={status.cloudRegisterUrl || CLOUD_WEB_REGISTER_URL}
        onChanged={resync}
        say={say}
      />

      <p className="dp-muted dp-aip__note">Only one provider is active at a time, and only new requests follow a switch. Signing in never activates cloud inference on its own.</p>

      <RoutingPolicy />

      <div className="dp-sr-live" role="status" aria-live="polite" ref={liveRef} />
    </div>
  )
}

// ---- load error ---------------------------------------------------------------

function LoadError({ error, status, attempt, onRetry }: { error: string; status?: number; attempt: number; onRetry: () => void }) {
  const why = providerLoadError(error, status)
  return (
    <div className="dp-settings-list dp-aip">
      <section className="dp-aip__loaderr" role="alert">
        <h5 className="dp-aip__loaderr-title">Couldn’t load providers</h5>
        <p className="dp-aip__loaderr-reason"><strong>{why.title}.</strong> {why.detail}</p>
        {why.hint && <p className="dp-aip__loaderr-hint">{why.hint}</p>}
        <div className="dp-aip__loaderr-actions">
          <button className="dp-ghost-button" type="button" onClick={onRetry}>Try again</button>
          <span className="dp-aip__retrying"><span className="dp-spinner" aria-hidden="true" /> Retrying automatically…</span>
        </div>
        <details className="dp-aip__loaderr-details">
          <summary>Details</summary>
          <code>{status ? `HTTP ${status} · ` : ''}{error || 'no response'} · {attempt} attempt{attempt === 1 ? '' : 's'} · API base {apiBase()}</code>
        </details>
      </section>
      <p className="dp-muted">Provider state lives on the DayPilot server, so nothing here can change until the API is reachable. Ollabridge itself may be running fine.</p>
    </div>
  )
}

// ---- summary strip -----------------------------------------------------------

function providerName(kind: ProviderKind): string {
  return kind === 'local' ? 'Local Gateway' : 'Ollabridge Cloud'
}

function ActiveSummary({ status }: { status: ProviderStatus }) {
  const active = status.connections.find((c) => c.active && c.state === 'connected')
  if (!active) {
    const idle = status.connections.find((c) => c.state === 'connected')
    return (
      <div className="dp-aip__summary dp-aip__summary--none" role="status">
        <span className="dp-aip__summary-dot" aria-hidden="true" />
        <div>
          <strong>No active provider.</strong>{' '}
          <span>
            {idle
              ? `${providerName(idle.kind)} is connected but not active — choose “Use ${providerName(idle.kind)}” below.`
              : 'Connect Local Gateway or sign in to Ollabridge Cloud — until then the assistant runs in limited mode.'}
          </span>
        </div>
      </div>
    )
  }
  const n = active.modelsCount
  return (
    <div className="dp-aip__summary" role="status">
      <span className="dp-aip__summary-dot is-on" aria-hidden="true" />
      <div>
        <strong>{providerName(active.kind)} is active.</strong>{' '}
        <span>
          {active.defaultModel ? <>Default model <code>{active.defaultModel}</code></> : 'No default model chosen'}
          {' · '}{n} model{n === 1 ? '' : 's'}{' · '}<code>{gatewayRoot(active.baseUrl)}</code>
        </span>
      </div>
    </div>
  )
}

// ---- shared bits ----------------------------------------------------------------

type Tone = 'connected' | 'warn' | 'offline' | 'available' | 'testing'

function localLabel(conn?: ProviderConnection): { text: string; tone: Tone } {
  const s = conn?.state ?? 'unconfigured'
  if (s === 'connected') return { text: conn?.active ? 'Connected · Active' : 'Connected', tone: 'connected' }
  if (s === 'degraded') return { text: 'Reachable · no models', tone: 'warn' }
  if (s === 'unauthorized') return { text: conn?.lastErrorCode === 'unauthorized' ? 'Key rejected' : 'Key required', tone: 'warn' }
  if (s === 'offline') return { text: 'Offline', tone: 'offline' }
  if (s === 'testing') return { text: 'Checking…', tone: 'testing' }
  return { text: 'Not detected', tone: 'available' }
}

function cloudLabel(conn?: ProviderConnection): { text: string; tone: Tone } {
  const s = conn?.state ?? 'unconfigured'
  if (s === 'connected') return { text: conn?.active ? 'Connected · Active' : 'Connected', tone: 'connected' }
  if (s === 'expired') return { text: 'Reconnect required', tone: 'warn' }
  if (s === 'unauthorized') return { text: 'Sign-in failed', tone: 'warn' }
  if (s === 'offline') return { text: 'Unreachable', tone: 'offline' }
  if (s === 'testing') return { text: 'Signing in…', tone: 'testing' }
  return { text: 'Not signed in', tone: 'available' }
}

type Msg = { text: string; tone: 'info' | 'ok' | 'err' }

function ModelPicker({ label, models, value, busy, onChange, emptyHint }: {
  label: string; models: string[]; value: string | null; busy: boolean; onChange: (m: string) => void; emptyHint: string
}) {
  const id = useId()
  const options = useMemo(() => (value && !models.includes(value) ? [value, ...models] : models), [models, value])
  if (!options.length) return <p className="dp-provcard__hint">{emptyHint}</p>
  return (
    <div className="dp-provcard__modelrow">
      <label htmlFor={id}>{label}</label>
      <select id={id} className="dp-provcard__select" value={value ?? ''} disabled={busy} onChange={(e) => onChange(e.target.value)}>
        {!value && <option value="" disabled>Choose a model…</option>}
        {options.map((m) => <option key={m} value={m}>{m}</option>)}
      </select>
    </div>
  )
}

// ---- local card -------------------------------------------------------------

function LocalCard({ conn, onChanged, say }: { conn?: ProviderConnection; onChanged: () => void; say: (m: string) => void }) {
  const state = conn?.state ?? 'unconfigured'
  const connected = state === 'connected'
  const needsKey = state === 'unauthorized'
  const reachable = connected || state === 'degraded' || needsKey
  const active = !!conn?.active && connected

  const [advanced, setAdvanced] = useState(needsKey)
  const [url, setUrl] = useState(conn?.baseUrl || 'http://localhost:11435/v1')
  const [apiKey, setApiKey] = useState('')
  const [busy, setBusy] = useState<'idle' | 'detect' | 'connect' | 'recheck' | 'model'>('idle')
  const [msg, setMsg] = useState<Msg | null>(null)
  const [models, setModels] = useState<string[]>([])
  const [gateway, setGateway] = useState<GatewayInfo | null>(null)
  const keyRef = useRef<HTMLInputElement>(null)

  useEffect(() => { if (conn?.baseUrl) setUrl(conn.baseUrl) }, [conn?.baseUrl])
  // A key-gated gateway opens the key field by itself — that is the one thing to do.
  useEffect(() => { if (needsKey) { setAdvanced(true); keyRef.current?.focus() } }, [needsKey])

  // The gateway's live model list (+ public health facts) whenever it is reachable.
  useEffect(() => {
    if (!reachable || needsKey) { setModels([]); setGateway(null); return }
    let cancelled = false
    providersApi.localModels().then((r) => {
      if (cancelled || !r.ok) return
      setModels(r.data.models)
      setGateway(r.data.gateway)
    })
    return () => { cancelled = true }
  }, [reachable, needsKey, conn?.lastTestedAt, conn?.baseUrl, conn?.modelsCount])

  const label = localLabel(conn)
  const root = gatewayRoot(conn?.baseUrl || url)
  const lastError = conn?.lastErrorCode && !connected ? localErrorText(conn.lastErrorCode) : ''

  async function detect() {
    setBusy('detect'); setMsg({ text: 'Looking for Ollabridge on this machine…', tone: 'info' })
    const res = await providersApi.localDiscover()
    setBusy('idle')
    if (res.ok && res.data.code === 'connected') { setMsg(null); say('Local Ollabridge detected.') }
    else setMsg({ text: localErrorText(res.ok ? res.data.code : res.error), tone: 'err' })
    onChanged()
  }
  async function connect() {
    setBusy('connect'); setMsg({ text: 'Testing the connection…', tone: 'info' })
    const res = await providersApi.localConnect(url.trim(), apiKey.trim() || undefined)
    setBusy('idle')
    if (res.ok && res.data.code === 'connected') { setApiKey(''); setMsg({ text: 'Connected.', tone: 'ok' }); say('Local Gateway connected.') }
    else setMsg({ text: localErrorText(res.ok ? res.data.code : res.error), tone: 'err' })
    onChanged()
  }
  async function recheck() {
    setBusy('recheck'); setMsg(null)
    const res = await providersApi.localTest(conn?.baseUrl || url.trim())
    setBusy('idle')
    if (res.ok && res.data.code === 'connected') {
      const c = res.data.connection
      setMsg({ text: `Healthy · ${c.modelsCount} model${c.modelsCount === 1 ? '' : 's'}${c.lastLatencyMs ? ` · ~${c.lastLatencyMs} ms` : ''}.`, tone: 'ok' })
    } else setMsg({ text: localErrorText(res.ok ? res.data.code : res.error), tone: 'err' })
    onChanged()
  }
  async function useLocal() {
    const r = await providersApi.setActive('local')
    if (r.ok) { say('Local Gateway is now the active provider.'); onChanged() }
    else setMsg({ text: 'Couldn’t activate Local Gateway — connect it first.', tone: 'err' })
  }
  async function chooseModel(m: string) {
    setBusy('model')
    const r = await providersApi.setDefaultModel('local', m)
    setBusy('idle')
    if (r.ok) { say(`Default model set to ${m}.`); onChanged() }
  }
  function copyEndpoint() {
    navigator.clipboard?.writeText(url).then(() => setMsg({ text: 'Endpoint copied.', tone: 'ok' })).catch(() => undefined)
  }

  const dashboard = (
    <a className="dp-ghost-button" href={gatewayDashboardUrl(conn?.baseUrl || url)} target="_blank" rel="noopener noreferrer">Open OllaBridge dashboard</a>
  )

  return (
    <section className={'dp-provcard' + (active ? ' is-selected' : '')} aria-label="Local Gateway">
      <header className="dp-provcard__head">
        <span className="dp-provcard__icon" aria-hidden="true">💻</span>
        <div className="dp-provcard__titles">
          <strong>Local Gateway</strong>
          <span className="dp-provcard__privacy">Ollabridge on this machine · prompts and keys never leave the device.</span>
        </div>
        <span className={'dp-provcard__status dp-provcard__status--' + label.tone}>{label.text}</span>
      </header>

      {connected && conn && (
        <>
          <dl className="dp-provcard__facts">
            <dt>Endpoint</dt><dd><code>{root}</code></dd>
            <dt>Models</dt><dd>{conn.modelsCount} available{conn.lastLatencyMs ? ` · ~${conn.lastLatencyMs} ms` : ''}</dd>
            {gateway && (
              <>
                <dt>Gateway</dt>
                <dd>{[gateway.mode, gateway.authMode ? `auth ${gateway.authMode}` : null, gateway.defaultModel ? `gateway default ${gateway.defaultModel}` : null].filter(Boolean).join(' · ')}</dd>
              </>
            )}
            <dt>Credential</dt><dd>{conn.authMethod === 'api_key' ? 'API key stored on the DayPilot server' : 'None needed (local-trust)'}</dd>
          </dl>
          <ModelPicker label="Default model for DayPilot" models={models} value={conn.defaultModel} busy={busy === 'model'} onChange={chooseModel} emptyHint="Model list unavailable right now — re-check the connection." />
          <div className="dp-provcard__actions">
            {!active
              ? <button className="dp-provcard__use" type="button" onClick={useLocal}>Use Local Gateway</button>
              : <span className="dp-provcard__activemark">✓ Active provider</span>}
            <button className="dp-ghost-button" type="button" onClick={recheck} disabled={busy !== 'idle'}>{busy === 'recheck' ? 'Checking…' : 'Re-check'}</button>
            {dashboard}
          </div>
        </>
      )}

      {state === 'degraded' && (
        <>
          <p className="dp-provcard__body">Ollabridge answers at <code>{root}</code> but lists no models yet. Add or enable a model in the OllaBridge dashboard (or <code>ollama pull</code> one), then re-check.</p>
          <div className="dp-provcard__actions">
            <button className="dp-ghost-button" type="button" onClick={recheck} disabled={busy !== 'idle'}>{busy === 'recheck' ? 'Checking…' : 'Re-check'}</button>
            {dashboard}
          </div>
        </>
      )}

      {needsKey && (
        <p className="dp-provcard__body">
          Ollabridge is running at <code>{root}</code>, but its model list is protected.{' '}
          {conn?.lastErrorCode === 'unauthorized'
            ? 'The key DayPilot has was rejected — paste the current one below.'
            : 'Paste the sk-ollabridge-… key printed when the gateway started.'}
        </p>
      )}

      {!reachable && (
        <>
          <p className="dp-provcard__body">Run Ollabridge on this machine: <code>pip install ollabridge</code> then <code>ollabridge start</code>. DayPilot looks at <code>{root}</code>, the WSL/Docker host, and nearby ports.</p>
          {lastError && <p className="dp-provcard__hint">Last check: {lastError}</p>}
          <div className="dp-settings-actions">
            <button className="dp-ghost-button" type="button" onClick={detect} disabled={busy !== 'idle'}>{busy === 'detect' ? 'Detecting…' : 'Detect again'}</button>
            <a className="dp-ghost-button" href="https://ollabridge.com" target="_blank" rel="noopener noreferrer">Install Ollabridge</a>
          </div>
        </>
      )}

      <button className="dp-linkbtn dp-provcard__adv" type="button" aria-expanded={advanced} onClick={() => setAdvanced((v) => !v)}>
        {advanced ? 'Hide advanced connection' : 'Advanced connection'}
      </button>
      {advanced && (
        <div className="dp-provcard__advbox">
          <label className="dp-provcard__label" htmlFor="dp-local-endpoint">Endpoint</label>
          <input id="dp-local-endpoint" className="dp-provcard__input" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="http://localhost:11435/v1" autoComplete="off" />
          <label className="dp-provcard__label" htmlFor="dp-local-key">API key {needsKey ? '(required by this gateway)' : '(optional)'}</label>
          <input id="dp-local-key" ref={keyRef} className="dp-provcard__input" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="sk-ollabridge-… from the gateway startup banner" autoComplete="off" />
          <div className="dp-settings-actions">
            <button className="dp-ghost-button" type="button" onClick={connect} disabled={busy !== 'idle' || !url.trim()}>{busy === 'connect' ? 'Testing…' : 'Test & connect'}</button>
            <button className="dp-ghost-button" type="button" onClick={copyEndpoint}>Copy endpoint</button>
          </div>
          <p className="dp-provcard__hint">Loopback and private addresses only; the WSL2 / Docker host and nearby ports are tried automatically. Keys are stored on the server by reference and never shown again.</p>
        </div>
      )}
      {msg && <p className={'dp-provcard__test dp-provcard__test--' + msg.tone} role={msg.tone === 'err' ? 'alert' : undefined}>{msg.text}</p>}
    </section>
  )
}

// ---- cloud card -------------------------------------------------------------

function CloudCard({ conn, loginUrl, registerUrl, onChanged, say }: {
  conn?: ProviderConnection; loginUrl: string; registerUrl: string; onChanged: () => void; say: (m: string) => void
}) {
  const [method, setMethod] = useState<'email' | 'key'>('email')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [confirm, setConfirm] = useState<null | 'use' | 'signout'>(null)
  const [models, setModels] = useState<string[]>([])
  const [modelBusy, setModelBusy] = useState(false)

  const state = conn?.state ?? 'unconfigured'
  const connected = state === 'connected'
  const active = !!conn?.active && connected
  const label = cloudLabel(conn)

  useEffect(() => {
    if (!connected) { setModels([]); return }
    let cancelled = false
    providersApi.cloudModels().then((r) => { if (!cancelled && r.ok) setModels(r.data.models) })
    return () => { cancelled = true }
  }, [connected, conn?.lastTestedAt, conn?.modelsCount])

  async function signIn(e: React.FormEvent) {
    e.preventDefault(); setError(''); setBusy(true)
    const res = await providersApi.cloudLogin(email.trim(), password)
    setBusy(false); setPassword('')
    if (res.ok && res.data.code === 'connected') { say('Ollabridge Cloud connected.'); onChanged() }
    else { setError(cloudErrorText(res.ok ? res.data.code : res.error)); onChanged() }
  }
  async function connectKey(e: React.FormEvent) {
    e.preventDefault(); setError(''); setBusy(true)
    const res = await providersApi.cloudConnectKey(apiKey.trim())
    setBusy(false); setApiKey('')
    if (res.ok && res.data.code === 'connected') { say('Ollabridge Cloud connected with an API key.'); onChanged() }
    else { setError(cloudKeyErrorText(res.ok ? res.data.code : res.error)); onChanged() }
  }
  async function useCloud() {
    setConfirm(null)
    const r = await providersApi.setActive('ollabridge_cloud')
    if (r.ok) { say('Ollabridge Cloud is now the active provider.'); onChanged() }
  }
  async function signOut() {
    setConfirm(null)
    await providersApi.cloudLogout()
    say('Signed out of Ollabridge Cloud.')
    onChanged()
  }
  async function chooseModel(m: string) {
    setModelBusy(true)
    const r = await providersApi.setDefaultModel('ollabridge_cloud', m)
    setModelBusy(false)
    if (r.ok) { say(`Default cloud model set to ${m}.`); onChanged() }
  }

  const accountName = conn?.account?.displayName || conn?.account?.email || 'Ollabridge Cloud'
  const viaKey = conn?.authMethod === 'api_key'

  return (
    <section className={'dp-provcard' + (active ? ' is-selected' : '')} aria-label="Ollabridge Cloud">
      <header className="dp-provcard__head">
        <span className="dp-provcard__icon" aria-hidden="true">☁</span>
        <div className="dp-provcard__titles">
          <strong>Ollabridge Cloud</strong>
          <span className="dp-provcard__privacy">Requests go securely to your Ollabridge Cloud workspace.</span>
        </div>
        <span className={'dp-provcard__status dp-provcard__status--' + label.tone}>{label.text}</span>
      </header>

      {!connected && (
        <>
          <p className="dp-provcard__body">Reach your approved models from any device. Sign in with your Cloud account, or paste an API key from the Cloud dashboard — either way the credential is exchanged and kept on the DayPilot server, never in this browser.</p>
          <div className="dp-provcard__seg" role="tablist" aria-label="Cloud sign-in method">
            <button type="button" role="tab" aria-selected={method === 'email'} className={method === 'email' ? 'is-on' : ''} onClick={() => { setMethod('email'); setError('') }}>Sign in with email</button>
            <button type="button" role="tab" aria-selected={method === 'key'} className={method === 'key' ? 'is-on' : ''} onClick={() => { setMethod('key'); setError('') }}>Use an API key</button>
          </div>

          {method === 'email' ? (
            <form className="dp-provcard__form" onSubmit={signIn}>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Cloud account email" aria-label="Ollabridge Cloud email" autoComplete="username" />
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" aria-label="Ollabridge Cloud password" autoComplete="current-password" />
              <button className="dp-provcard__signin" type="submit" disabled={busy || !email.trim() || !password}>{busy ? 'Signing in…' : 'Sign in'}</button>
            </form>
          ) : (
            <form className="dp-provcard__form" onSubmit={connectKey}>
              <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="ob_live_… or ob_test_…" aria-label="Ollabridge Cloud API key" autoComplete="off" />
              <button className="dp-provcard__signin" type="submit" disabled={busy || !apiKey.trim()}>{busy ? 'Connecting…' : 'Connect with API key'}</button>
              <p className="dp-provcard__hint">Create a key in your Ollabridge Cloud dashboard. DayPilot checks it against your model list and stores it by reference.</p>
            </form>
          )}
          {error && <p className="dp-provcard__errbody" role="alert">{error}</p>}

          <div className="dp-provcard__weblogin">
            <a className="dp-ghost-button" href={loginUrl} target="_blank" rel="noopener noreferrer">Log in on the web (Google / SSO)</a>
            <a className="dp-linkbtn" href={registerUrl} target="_blank" rel="noopener noreferrer">Create an account</a>
          </div>
          <p className="dp-provcard__hint">Prefer Google, single sign-on, or a password reset? Open the Ollabridge Cloud login page, then come back and sign in here — or create an API key there and paste it under “Use an API key”.</p>
        </>
      )}

      {connected && conn && (
        <div className="dp-provcard__account">
          <div className="dp-provcard__acctline"><strong>{accountName}</strong></div>
          {conn.account?.email && <div className="dp-provcard__acctmail">{conn.account.email}</div>}
          <div className="dp-provcard__acctmeta">
            {conn.modelsCount} approved model{conn.modelsCount === 1 ? '' : 's'} · connected with {viaKey ? 'an API key' : 'your account'} · <code>{gatewayRoot(conn.baseUrl)}</code>
          </div>
          <ModelPicker label="Default cloud model" models={models} value={conn.defaultModel} busy={modelBusy} onChange={chooseModel} emptyHint="No approved models are listed for this account yet." />
          <div className="dp-provcard__actions">
            {!active
              ? <button className="dp-provcard__use" type="button" onClick={() => setConfirm('use')}>Use Ollabridge Cloud</button>
              : <span className="dp-provcard__activemark">✓ Active provider</span>}
          </div>
          <div className="dp-provcard__acctactions">
            <a className="dp-linkbtn" href={loginUrl} target="_blank" rel="noopener noreferrer">Manage account</a>
            <button className="dp-linkbtn dp-linkbtn--danger" type="button" onClick={() => setConfirm('signout')}>Sign out</button>
          </div>
        </div>
      )}

      {confirm === 'use' && (
        <ConfirmDialog title="Use Ollabridge Cloud?" body="New AI requests will be processed through your Ollabridge Cloud account (new requests only)." confirmLabel="Switch provider" onCancel={() => setConfirm(null)} onConfirm={useCloud} />
      )}
      {confirm === 'signout' && (
        <ConfirmDialog title="Sign out of Ollabridge Cloud?" body="DayPilot removes the stored authorization for this account. Your Ollabridge Cloud account is not deleted. If Cloud is active, Local Gateway becomes active." confirmLabel="Sign out" danger onCancel={() => setConfirm(null)} onConfirm={signOut} />
      )}
    </section>
  )
}

// ---- routing policy ---------------------------------------------------------

function RoutingPolicy() {
  const [routes, setRoutes] = useState<RoutePolicy[] | null>(null)
  const [live, setLive] = useState(false)

  useEffect(() => {
    let cancelled = false
    providersApi.routes().then((r) => {
      if (cancelled) return
      if (r.ok && r.data.routes?.length) { setRoutes(r.data.routes); setLive(true) }
      else setRoutes(PROVIDER_ROUTES)
    })
    return () => { cancelled = true }
  }, [])

  if (!routes) return null
  return (
    <section className="dp-aip__routes" aria-label="Routing policy">
      <h5 className="dp-aip__routes-title">Routing policy per agent role</h5>
      <p className="dp-muted">Preferred model, privacy tier and latency budget for each role, with fallbacks in order. The active provider executes every request{live ? '' : ' (showing built-in defaults — the live policy could not be loaded)'}.</p>
      <div className="dp-aip__routes-head" aria-hidden="true"><span>Role</span><span>Model</span><span>Tier</span><span>Budget</span><span>Fallback</span></div>
      {routes.map((r) => (
        <div key={r.role} className="dp-aip__route">
          <strong>{humanizeRole(r.role)}</strong>
          <code>{r.model}</code>
          <span className={'dp-pill dp-pill--tier-' + r.tier}>{r.tier}</span>
          <span>≤ {r.latencyBudgetMs} ms</span>
          <span className="dp-provider-fallback">{r.fallback.length ? r.fallback.join(' · ') : 'none'}</span>
        </div>
      ))}
    </section>
  )
}

// ---- confirm dialog ---------------------------------------------------------

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
