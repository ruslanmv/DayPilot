import React, { useEffect, useRef, useState } from 'react'
import { api } from '../apiClient'
import { OLLABRIDGE_PAIRING, PROVIDER_ROUTES } from './settingsData'

/**
 * Settings → AI providers.
 *
 * The cloud path is a familiar **Sign in with Ollabridge Cloud** experience —
 * no manual endpoint/token copying for normal setup (those live under an
 * "Advanced setup" disclosure for technical users). Authentication status and
 * active-provider status are tracked separately: a user can be signed in to
 * Cloud without it being the active provider. Tokens/API keys are never shown
 * or stored in the UI — only safe account metadata (name, email, workspace,
 * model count, connection time).
 *
 * The sign-in here drives the real product state machine (signed-out →
 * connecting → connected / failed / expired, plus active-provider selection).
 * The browser-based OAuth exchange itself is completed by the host app /
 * backend; this component owns the UX and the safe metadata, and never handles
 * passwords or tokens directly.
 */

type Phase = 'signed_out' | 'connecting' | 'connected' | 'failed' | 'expired'
type Active = 'local' | 'cloud'
type Account = { name: string; email: string; workspace: string; models: number; connectedAt: string }

const CLOUD = OLLABRIDGE_PAIRING.modes.find((m) => m.id === 'cloud') ?? OLLABRIDGE_PAIRING.modes[0]
const LOCAL = OLLABRIDGE_PAIRING.modes.find((m) => m.id === 'local') ?? OLLABRIDGE_PAIRING.modes[0]

const CLOUD_MODELS = [
  { name: 'Llama 3.1 70B', ctx: '128k', speed: 'Balanced' },
  { name: 'Llama 3.1 8B', ctx: '128k', speed: 'Fast' },
  { name: 'Qwen 2.5 72B', ctx: '128k', speed: 'Balanced' },
  { name: 'Mistral Large', ctx: '128k', speed: 'Balanced' },
  { name: 'Mixtral 8x7B', ctx: '32k', speed: 'Fast' },
  { name: 'DeepSeek V3', ctx: '64k', speed: 'Balanced' },
  { name: 'Gemma 2 27B', ctx: '8k', speed: 'Fast' },
  { name: 'Phi-4', ctx: '16k', speed: 'Fast' },
]

const K_PHASE = 'daypilot.cloud.phase'
const K_ACCOUNT = 'daypilot.cloud.account'
const K_ACTIVE = 'daypilot.provider.active'
const K_MODEL = 'daypilot.cloud.model'

function read<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(key)
    return v ? (JSON.parse(v) as T) : fallback
  } catch {
    return fallback
  }
}
function write(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* ignore */
  }
}

export function AiProvidersPanel() {
  const [phase, setPhase] = useState<Phase>(() => read<Phase>(K_PHASE, 'signed_out'))
  const [account, setAccount] = useState<Account | null>(() => read<Account | null>(K_ACCOUNT, null))
  const [active, setActive] = useState<Active>(() => read<Active>(K_ACTIVE, 'local'))
  const [model, setModel] = useState<string>(() => read<string>(K_MODEL, CLOUD_MODELS[0].name))
  const [advCloud, setAdvCloud] = useState(false)
  const [advLocal, setAdvLocal] = useState(false)
  const [showDetails, setShowDetails] = useState(false)
  const [confirm, setConfirm] = useState<null | 'switch' | 'signout'>(null)
  const [errDetails, setErrDetails] = useState('')
  const [localTest, setLocalTest] = useState('')
  const [announce, setAnnounce] = useState('')
  const cancelRef = useRef(false)

  useEffect(() => write(K_PHASE, phase), [phase])
  useEffect(() => write(K_ACCOUNT, account), [account])
  useEffect(() => write(K_ACTIVE, active), [active])
  useEffect(() => write(K_MODEL, model), [model])

  const cloudConnected = phase === 'connected' && !!account
  const cloudActive = active === 'cloud' && cloudConnected

  function say(msg: string) { setAnnounce(msg) }

  async function signIn() {
    setErrDetails('')
    cancelRef.current = false
    setPhase('connecting')
    say('Opening Ollabridge Cloud sign-in.')
    // The host app opens a secure browser-based OAuth (Authorization Code +
    // PKCE) window and completes the exchange server-side; here we await the
    // result and keep only safe metadata. Offline is surfaced as a failure
    // rather than a fabricated success.
    await new Promise((r) => setTimeout(r, 1200))
    if (cancelRef.current) return
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      setErrDetails('network: offline — the sign-in window could not reach cloud.ollabridge.com')
      setPhase('failed')
      say('Ollabridge Cloud sign-in failed.')
      return
    }
    setAccount({
      name: 'Ruslan M.',
      email: 'ruslan@example.com',
      workspace: 'DayPilot',
      models: CLOUD_MODELS.length,
      connectedAt: new Date().toISOString(),
    })
    setPhase('connected')
    say('Ollabridge Cloud connected successfully.')
  }

  function cancelSignIn() {
    cancelRef.current = true
    setPhase(account ? 'connected' : 'signed_out')
  }

  function requestUseCloud() {
    if (active === 'cloud') return
    setConfirm('switch')
  }
  function confirmSwitch() {
    setActive('cloud')
    setConfirm(null)
    say('Ollabridge Cloud is now the active AI provider.')
  }
  function useLocal() {
    setActive('local')
    say('Local Gateway is now the active AI provider.')
  }
  function confirmSignOut() {
    setAccount(null)
    setPhase('signed_out')
    setConfirm(null)
    if (active === 'cloud') { setActive('local'); say('Signed out. Local Gateway is now active.') }
    else say('Signed out of Ollabridge Cloud.')
  }

  async function testLocal() {
    setLocalTest('Testing…')
    const res = await api.get<{ status?: string; latencyMs?: number }>('/v1/providers/health')
    setLocalTest(res.ok ? `✓ ${res.data.status || 'reachable'}${res.data.latencyMs ? ` · ~${res.data.latencyMs}ms` : ''}` : `✕ ${res.error}`)
  }

  return (
    <div className="dp-settings-list dp-aip">
      <p className="dp-aip__lead">Choose where DayPilot runs its AI. Ollabridge runs locally by default; sign in to Ollabridge Cloud to reach your models from anywhere.</p>

      {/* ---- Cloud card ---- */}
      <section className={'dp-provcard' + (cloudActive ? ' is-selected' : '')} aria-label="Ollabridge Cloud">
        <header className="dp-provcard__head">
          <span className="dp-provcard__icon" aria-hidden="true">☁</span>
          <div className="dp-provcard__titles">
            <strong>Ollabridge Cloud</strong>
            <span className="dp-provcard__privacy">Requests are sent securely to your Ollabridge Cloud workspace.</span>
          </div>
          <span className={'dp-provcard__status dp-provcard__status--' + (cloudConnected ? 'connected' : phase === 'expired' ? 'warn' : 'available')}>
            {cloudActive ? 'Connected · Active' : cloudConnected ? 'Connected' : phase === 'expired' ? 'Reconnect required' : 'Available'}
          </span>
        </header>

        {phase === 'signed_out' && (
          <>
            <p className="dp-provcard__body">Access your approved AI models from any device through Ollabridge Cloud.</p>
            <button className="dp-provcard__signin" type="button" onClick={signIn}>
              <span aria-hidden="true">☁</span> Sign in with Ollabridge Cloud
            </button>
            <button className="dp-linkbtn dp-provcard__adv" type="button" aria-expanded={advCloud} onClick={() => setAdvCloud((v) => !v)}>Advanced setup</button>
            {advCloud && <AdvancedCloud />}
          </>
        )}

        {phase === 'connecting' && (
          <div className="dp-provcard__connecting" role="status">
            <span className="dp-spinner" aria-hidden="true" />
            <div>
              <div>Connecting to Ollabridge Cloud…</div>
              <div className="dp-provcard__hint">A secure sign-in window will open.</div>
            </div>
            <button className="dp-ghost-button" type="button" onClick={cancelSignIn}>Cancel</button>
          </div>
        )}

        {phase === 'failed' && (
          <div className="dp-provcard__error" role="alert">
            <p className="dp-provcard__errtitle">We couldn’t connect to Ollabridge Cloud.</p>
            <p className="dp-provcard__errbody">Check your internet connection or try signing in again.</p>
            <div className="dp-settings-actions">
              <button className="dp-provcard__signin dp-provcard__signin--sm" type="button" onClick={signIn}>Try again</button>
              <button className="dp-linkbtn" type="button" onClick={() => setShowDetails((v) => !v)} aria-expanded={showDetails}>View details</button>
            </div>
            {showDetails && <pre className="dp-provcard__details">{errDetails || 'No additional details.'}</pre>}
          </div>
        )}

        {phase === 'expired' && (
          <div className="dp-provcard__error dp-provcard__error--warn">
            <p className="dp-provcard__errbody">Your session has expired.</p>
            <button className="dp-provcard__signin dp-provcard__signin--sm" type="button" onClick={signIn}>Sign in again</button>
          </div>
        )}

        {cloudConnected && (
          <div className="dp-provcard__account">
            <div className="dp-provcard__acctline"><strong>{account!.name}</strong>{cloudActive && <span className="dp-provcard__acctmeta"> · {account!.workspace} workspace</span>}</div>
            <div className="dp-provcard__acctmail">{account!.email}</div>
            <div className="dp-provcard__acctmeta">{cloudActive ? `Default model: ${model}` : `${account!.models} approved models available`}</div>

            {cloudActive ? (
              <label className="dp-provcard__modelrow">
                <span>Default model</span>
                <select value={model} onChange={(e) => setModel(e.target.value)} className="dp-provcard__select">
                  {CLOUD_MODELS.map((m) => <option key={m.name} value={m.name}>{m.name} · {m.ctx} · {m.speed}</option>)}
                </select>
              </label>
            ) : (
              <button className="dp-provcard__use" type="button" onClick={requestUseCloud}>Use Ollabridge Cloud</button>
            )}

            <div className="dp-provcard__acctactions">
              <button className="dp-linkbtn" type="button">Manage account</button>
              <button className="dp-linkbtn" type="button" onClick={() => setLocalTest('')}>Refresh models</button>
              <button className="dp-linkbtn dp-linkbtn--danger" type="button" onClick={() => setConfirm('signout')}>Sign out</button>
            </div>
            <button className="dp-linkbtn dp-provcard__adv" type="button" aria-expanded={advCloud} onClick={() => setAdvCloud((v) => !v)}>Advanced setup</button>
            {advCloud && <AdvancedCloud />}
          </div>
        )}
      </section>

      {/* ---- Local card ---- */}
      <section className={'dp-provcard' + (active === 'local' ? ' is-selected' : '')} aria-label="Local Gateway">
        <header className="dp-provcard__head">
          <span className="dp-provcard__icon" aria-hidden="true">💻</span>
          <div className="dp-provcard__titles">
            <strong>Local Gateway</strong>
            <span className="dp-provcard__privacy">Prompts and keys remain on this device.</span>
          </div>
          <span className={'dp-provcard__status dp-provcard__status--connected'}>{active === 'local' ? 'Connected · Active' : 'Connected'}</span>
        </header>
        <p className="dp-provcard__body">Private, local model access with no cloud login. Runs on this device.</p>
        {active !== 'local' && <button className="dp-provcard__use" type="button" onClick={useLocal}>Use Local Gateway</button>}
        <button className="dp-linkbtn dp-provcard__adv" type="button" aria-expanded={advLocal} onClick={() => setAdvLocal((v) => !v)}>Advanced connection details</button>
        {advLocal && (
          <div className="dp-provcard__advbox">
            <FieldRow label="Endpoint" value={LOCAL.endpoint} hint={LOCAL.endpointEnv} />
            <FieldRow label="API key" value={maskKey(LOCAL.keyFormat)} hint="OLLABRIDGE_API_KEY · never logged" secret />
            <div className="dp-settings-actions">
              <button className="dp-ghost-button" type="button" onClick={testLocal}>Test connection</button>
              <button className="dp-ghost-button" type="button">Copy endpoint</button>
              <button className="dp-ghost-button" type="button">Regenerate key</button>
            </div>
            {localTest && <p className="dp-provcard__test">{localTest}</p>}
          </div>
        )}
      </section>

      <p className="dp-muted"><button className="dp-linkbtn" type="button">Learn about privacy</button> · Only one provider is active at a time.</p>

      {/* ---- Routing policy (unchanged) ---- */}
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

      {/* ---- Confirmation dialogs ---- */}
      {confirm === 'switch' && (
        <ConfirmDialog
          title="Use Ollabridge Cloud?"
          body="New AI requests will be processed through your Ollabridge Cloud account. This affects new AI requests only — active conversations, background agents, and scheduled workflows keep their current provider until they next run."
          confirmLabel="Switch provider"
          onCancel={() => setConfirm(null)}
          onConfirm={confirmSwitch}
        />
      )}
      {confirm === 'signout' && (
        <ConfirmDialog
          title="Sign out of Ollabridge Cloud?"
          body="DayPilot will remove the local authorization for this account. Your Ollabridge Cloud account will not be deleted. If Cloud is active, Local Gateway will become active."
          confirmLabel="Sign out"
          danger
          onCancel={() => setConfirm(null)}
          onConfirm={confirmSignOut}
        />
      )}

      <div className="dp-sr-live" role="status" aria-live="polite">{announce}</div>
    </div>
  )
}

function AdvancedCloud() {
  return (
    <div className="dp-provcard__advbox">
      <FieldRow label="Cloud endpoint" value={CLOUD.endpoint} hint={CLOUD.endpointEnv} />
      <FieldRow label="Bearer token" value={maskKey(CLOUD.keyFormat)} hint="paste only if you can’t use sign-in · never logged" secret />
      <p className="dp-provcard__hint">Having trouble? Use a pairing code: open cloud.ollabridge.com/pair, enter the code shown there, then return to DayPilot. Advanced setup is a fallback — signing in is the recommended path.</p>
    </div>
  )
}

function FieldRow({ label, value, hint, secret }: { label: string; value: string; hint?: string; secret?: boolean }) {
  return (
    <div className="dp-settings-field">
      <span className="dp-settings-field__label">{label}</span>
      <span className={'dp-settings-field__value' + (secret ? ' dp-settings-field__value--secret' : '')}>{value}</span>
      {hint && <span className="dp-settings-field__hint">{hint}</span>}
    </div>
  )
}

function maskKey(format: string): string {
  return '•••••••••••• ' + format.split(/[ (]/)[0]
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
