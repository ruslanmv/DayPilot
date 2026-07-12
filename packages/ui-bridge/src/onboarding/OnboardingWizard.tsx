import React, { useState } from 'react'
import { api } from '../apiClient'
import { OLLABRIDGE_PAIRING } from '../settings/settingsData'

const STORAGE_KEY = 'daypilot.onboarded'
const PROFILE_KEY = 'daypilot.profile'
const AI_READY_KEY = 'daypilot.ai_ready'

export type OnboardingProfile = {
  name: string
  email: string
  mailbox: string
  sourceKind: 'folder' | 'box'
  source: string
  aiProvider: 'local' | 'cloud'
  aiBaseUrl: string
  aiReady: boolean
}

const EMPTY: OnboardingProfile = {
  name: '', email: '', mailbox: '', sourceKind: 'folder', source: '',
  aiProvider: 'local', aiBaseUrl: OLLABRIDGE_PAIRING.modes[0].endpoint, aiReady: false,
}

function alreadyOnboarded(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true'
  } catch {
    return false
  }
}

export function hasOnboarded(): boolean {
  return alreadyOnboarded()
}

/** Whether an AI provider was verified during onboarding. AI features should
 *  present themselves as "ready" only when this is true; otherwise the app runs
 *  in a limited (no-AI) mode until a provider is connected in Settings. */
export function isAiReady(): boolean {
  try {
    return localStorage.getItem(AI_READY_KEY) === 'true'
  } catch {
    return false
  }
}

type TestState = 'idle' | 'testing' | 'ok' | 'fail'

/**
 * A minimalist first-run wizard, in the spirit of ChatGPT/Claude onboarding.
 * The first step is **AI provider setup** because DayPilot's value is its AI —
 * we never claim AI features are ready until a provider is connected. Ollabridge
 * runs locally by default (no cloud login); Ollabridge Cloud is optional. A
 * "Test connection" button verifies the provider against the gateway before the
 * user can mark AI as ready. The provider step can be deferred into a clearly
 * labelled limited mode, but not silently skipped. Everything else lives in
 * Settings. Renders nothing once completed.
 */
export function OnboardingWizard({ onFinish }: { onFinish?: (profile: OnboardingProfile | null) => void }) {
  const [open, setOpen] = useState(() => !alreadyOnboarded())
  const [step, setStep] = useState(0)
  const [p, setP] = useState<OnboardingProfile>(EMPTY)
  const [test, setTest] = useState<TestState>('idle')
  const [testMsg, setTestMsg] = useState('')

  if (!open) return null

  const steps = ['AI provider', 'You', 'Mailbox', 'Knowledge']
  const last = step === steps.length - 1

  function close(profile: OnboardingProfile | null) {
    try {
      localStorage.setItem(STORAGE_KEY, 'true')
      localStorage.setItem(AI_READY_KEY, profile?.aiReady ? 'true' : 'false')
      if (profile) localStorage.setItem(PROFILE_KEY, JSON.stringify({ ...profile, aiBaseUrl: profile.aiBaseUrl }))
    } catch {
      /* ignore storage failures */
    }
    setOpen(false)
    onFinish?.(profile)
  }

  const set = (patch: Partial<OnboardingProfile>) => setP((prev) => ({ ...prev, ...patch }))

  function pickMode(mode: 'local' | 'cloud') {
    const m = OLLABRIDGE_PAIRING.modes.find((x) => x.id === mode) ?? OLLABRIDGE_PAIRING.modes[0]
    set({ aiProvider: mode, aiBaseUrl: m.endpoint, aiReady: false })
    setTest('idle')
    setTestMsg('')
  }

  async function testConnection() {
    setTest('testing')
    setTestMsg('Contacting the AI provider…')
    const res = await api.get<{ status?: string; latencyMs?: number; models?: string[] }>('/v1/providers/health')
    if (res.ok && (res.data.status === 'healthy' || res.data.status === 'ok' || res.data.status === 'degraded')) {
      setTest('ok')
      setTestMsg(`Connected — provider ${res.data.status}${res.data.latencyMs ? ` (~${res.data.latencyMs}ms)` : ''}.`)
      set({ aiReady: true })
    } else {
      setTest('fail')
      setTestMsg(res.ok ? `Provider reachable but not ready (${res.data.status ?? 'unknown'}).` : `Couldn't reach the provider (${res.error}).`)
      set({ aiReady: false })
    }
  }

  return (
    <div className="dp-onb" role="dialog" aria-modal="true" aria-label="Set up DayPilot">
      <div className="dp-onb__card">
        <header className="dp-onb__head">
          <div className="dp-onb__brand">
            <svg className="dp-brand__mark" viewBox="0 0 32 32" fill="none" aria-hidden="true">
              <path d="M16 3.5 28.5 28 16 22.2 3.5 28Z" fill="currentColor" opacity="0.5" />
              <path d="M16 3.5 28.5 28 16 22.2Z" fill="currentColor" />
            </svg>
            <span className="dp-brand__word">DayPilot</span>
          </div>
          {step > 0 && <button className="dp-onb__skip" onClick={() => close(p)}>Skip for now</button>}
        </header>

        <div className="dp-onb__steps" aria-hidden="true">
          {steps.map((s, i) => (
            <span key={s} className={'dp-onb__dot' + (i === step ? ' is-active' : i < step ? ' is-done' : '')} />
          ))}
        </div>

        {step === 0 && (
          <div className="dp-onb__body">
            <h2 className="dp-onb__title">Connect your AI</h2>
            <p className="dp-onb__sub">DayPilot is powered by Ollabridge. It runs locally by default — no cloud login, and prompts, history, and keys never leave your device. Connect a provider before you rely on AI features.</p>
            <div className="dp-onb__seg">
              <button className={'dp-onb__segbtn' + (p.aiProvider === 'local' ? ' is-active' : '')} onClick={() => pickMode('local')}>💻 Ollabridge (local)</button>
              <button className={'dp-onb__segbtn' + (p.aiProvider === 'cloud' ? ' is-active' : '')} onClick={() => pickMode('cloud')}>☁ Ollabridge Cloud</button>
            </div>
            <label className="dp-onb__field">
              <span>Provider URL</span>
              <input value={p.aiBaseUrl} onChange={(e) => { set({ aiBaseUrl: e.target.value, aiReady: false }); setTest('idle') }} placeholder="http://localhost:11435/v1" />
            </label>
            {p.aiProvider === 'cloud' && (
              <p className="dp-onb__hint">Ollabridge Cloud is optional. Add your API key or device code in Settings → AI providers; the local gateway needs no login.</p>
            )}
            <div className="dp-onb__testrow">
              <button className="dp-onb__test" onClick={testConnection} disabled={test === 'testing'}>
                {test === 'testing' ? 'Testing…' : 'Test connection'}
              </button>
              {test !== 'idle' && (
                <span className={'dp-onb__teststatus dp-onb__teststatus--' + test} role="status">
                  {test === 'ok' ? '✓ ' : test === 'fail' ? '✕ ' : ''}{testMsg}
                </span>
              )}
            </div>
            {test !== 'ok' && (
              <p className="dp-onb__hint">Until a provider is verified, DayPilot runs in <strong>limited mode</strong> — planning and chat that need AI stay disabled.</p>
            )}
          </div>
        )}

        {step === 1 && (
          <div className="dp-onb__body">
            <h2 className="dp-onb__title">Welcome to DayPilot</h2>
            <p className="dp-onb__sub">Your local-first AI operator workspace. A couple of quick details and you're set.</p>
            <label className="dp-onb__field">
              <span>Your name</span>
              <input value={p.name} onChange={(e) => set({ name: e.target.value })} placeholder="Your name" autoFocus />
            </label>
            <label className="dp-onb__field">
              <span>Work email</span>
              <input type="email" value={p.email} onChange={(e) => set({ email: e.target.value, mailbox: prev(p.mailbox, e.target.value) })} placeholder="you@company.com" />
            </label>
          </div>
        )}

        {step === 2 && (
          <div className="dp-onb__body">
            <h2 className="dp-onb__title">Connect your mailbox</h2>
            <p className="dp-onb__sub">DayPilot drafts replies and spots schedule impact. It never sends without your approval.</p>
            <label className="dp-onb__field">
              <span>Mailbox address</span>
              <input type="email" value={p.mailbox} onChange={(e) => set({ mailbox: e.target.value })} placeholder="you@company.com" autoFocus />
            </label>
            <p className="dp-onb__hint">IMAP/SMTP, Gmail, or Microsoft 365. Server details go in Settings → Mail.</p>
          </div>
        )}

        {step === 3 && (
          <div className="dp-onb__body">
            <h2 className="dp-onb__title">Add a knowledge source</h2>
            <p className="dp-onb__sub">Point DayPilot at one place to read from so the AI can answer over your projects (RAG). Read + index only.</p>
            <div className="dp-onb__seg">
              <button className={'dp-onb__segbtn' + (p.sourceKind === 'folder' ? ' is-active' : '')} onClick={() => set({ sourceKind: 'folder' })}>📁 Local folder</button>
              <button className={'dp-onb__segbtn' + (p.sourceKind === 'box' ? ' is-active' : '')} onClick={() => set({ sourceKind: 'box' })}>▤ Box</button>
            </div>
            <label className="dp-onb__field">
              <span>{p.sourceKind === 'folder' ? 'Folder path' : 'Box folder'}</span>
              <input value={p.source} onChange={(e) => set({ source: e.target.value })} placeholder={p.sourceKind === 'folder' ? '/data/projects' : 'box://folder/…'} autoFocus />
            </label>
            <p className="dp-onb__hint">You can add more sources anytime in Settings → Knowledge sources.</p>
          </div>
        )}

        <footer className="dp-onb__foot">
          {step > 0 ? <button className="dp-onb__back" onClick={() => setStep(step - 1)}>Back</button> : <span />}
          {step === 0 ? (
            <div className="dp-onb__foot-actions">
              <button className="dp-onb__back" onClick={() => { set({ aiReady: false }); setStep(1) }}>Set up later (limited mode)</button>
              <button className="dp-onb__next" onClick={() => setStep(1)} disabled={!p.aiReady}>Continue</button>
            </div>
          ) : last ? (
            <button className="dp-onb__next" onClick={() => close(p)}>Finish setup</button>
          ) : (
            <button className="dp-onb__next" onClick={() => setStep(step + 1)}>Continue</button>
          )}
        </footer>
      </div>
    </div>
  )
}

function prev(current: string, fallback: string): string {
  return current || fallback
}
