import React, { useEffect, useState } from 'react'
import { OLLABRIDGE_PAIRING } from '../settings/settingsData'
import { providersApi, localErrorText } from '../providersClient'
import {
  completeSetup,
  dismissSetup,
  isAiReady,
  isSetupComplete,
  readSetup,
  onSetupReset,
  patchSetup,
} from './setupState'

const PROFILE_KEY = 'daypilot.profile'

export type OnboardingProfile = {
  name: string
  email: string
  mailbox: string
  sourceKind: 'folder' | 'box'
  source: string
  aiProvider: 'local' | 'cloud'
  aiBaseUrl: string
  aiApiKey: string
  cloudEmail: string
  cloudPassword: string
  aiReady: boolean
}

const EMPTY: OnboardingProfile = {
  name: '', email: '', mailbox: '', sourceKind: 'folder', source: '',
  aiProvider: 'local', aiBaseUrl: OLLABRIDGE_PAIRING.modes[0].endpoint, aiApiKey: '',
  cloudEmail: '', cloudPassword: '', aiReady: false,
}

/** Back-compat: setup completion is now an explicit state (see setupState). */
export function hasOnboarded(): boolean {
  return isSetupComplete()
}
export { isAiReady }

type TestState = 'idle' | 'testing' | 'ok' | 'fail'

/**
 * A minimalist first-run wizard, in the spirit of ChatGPT/Claude onboarding.
 * The first step is **AI provider setup** because DayPilot's value is its AI —
 * we never claim AI features are ready until a provider is really connected via
 * the backend (`/v1/providers/local/connect` or `/cloud/login`), not a generic
 * health probe. Local Ollabridge needs no login; Ollabridge Cloud takes an
 * email + password. The provider step can be deferred into a clearly labelled
 * limited mode, but skipping never marks setup complete — only the final
 * "Enter DayPilot" does. Renders nothing once setup is completed.
 */
export function OnboardingWizard({ onFinish }: { onFinish?: (profile: OnboardingProfile | null) => void }) {
  // Auto-open only for a fresh, never-dismissed setup. After "Skip for now",
  // the wizard must not re-block every launch — the Home "Finish setting up
  // DayPilot" banner (and Settings → Restart setup) are the resume paths.
  const [open, setOpen] = useState(() => {
    const s = readSetup()
    return s.status !== 'completed' && !s.dismissedAt
  })
  const [step, setStep] = useState(0)
  const [p, setP] = useState<OnboardingProfile>(EMPTY)
  const [test, setTest] = useState<TestState>('idle')
  const [testMsg, setTestMsg] = useState('')

  // Reopen when setup is reset from Settings → Profile & workspace.
  useEffect(() => onSetupReset(() => { setStep(0); setP(EMPTY); setTest('idle'); setTestMsg(''); setOpen(true) }), [])

  if (!open) return null

  const steps = ['AI provider', 'You', 'Mailbox', 'Knowledge']
  const last = step === steps.length - 1

  function persistProfile(profile: OnboardingProfile) {
    try {
      localStorage.setItem(PROFILE_KEY, JSON.stringify({
        name: profile.name, email: profile.email, mailbox: profile.mailbox,
        sourceKind: profile.sourceKind, source: profile.source,
        aiProvider: profile.aiProvider, aiBaseUrl: profile.aiBaseUrl,
      }))
    } catch { /* ignore */ }
  }

  /** "Skip for now" — records in-progress + dismissed, never completed. */
  function skip() {
    dismissSetup({ provider: p.aiReady })
    persistProfile(p)
    setOpen(false)
    onFinish?.(p)
  }

  /** The final, explicit finish — the only action that completes setup. */
  function finish() {
    completeSetup(
      { provider: p.aiReady, profile: Boolean(p.name || p.email), mailbox: Boolean(p.mailbox), knowledge: Boolean(p.source) },
      p.aiReady,
    )
    persistProfile(p)
    setOpen(false)
    onFinish?.(p)
  }

  const set = (patch: Partial<OnboardingProfile>) => setP((prev) => ({ ...prev, ...patch }))

  function pickMode(mode: 'local' | 'cloud') {
    const m = OLLABRIDGE_PAIRING.modes.find((x) => x.id === mode) ?? OLLABRIDGE_PAIRING.modes[0]
    set({ aiProvider: mode, aiBaseUrl: m.endpoint, aiReady: false })
    setTest('idle')
    setTestMsg('')
  }

  /** Really connect the provider via the backend — not a generic health probe. */
  async function testConnection() {
    setTest('testing')
    if (p.aiProvider === 'cloud') {
      setTestMsg('Signing in to Ollabridge Cloud…')
      const res = await providersApi.cloudLogin(p.cloudEmail.trim(), p.cloudPassword)
      if (res.ok && res.data.code === 'connected') {
        await providersApi.setActive('ollabridge_cloud')
        set({ aiReady: true }); patchSetup({ aiReady: true, completedSteps: { ...defaultSteps(), provider: true } })
        setTest('ok'); setTestMsg('Ollabridge Cloud is connected and active.')
      } else {
        set({ aiReady: false })
        setTest('fail'); setTestMsg(localErrorText(res.ok ? res.data.code : res.error))
      }
      return
    }
    setTestMsg('Connecting to Ollabridge…')
    const res = await providersApi.localConnect(p.aiBaseUrl.trim(), p.aiApiKey.trim() || undefined)
    if (res.ok && res.data.code === 'connected') {
      await providersApi.setActive('local')
      set({ aiReady: true }); patchSetup({ aiReady: true, completedSteps: { ...defaultSteps(), provider: true } })
      setTest('ok'); setTestMsg('Local Ollabridge is connected and active.')
    } else {
      set({ aiReady: false })
      setTest('fail'); setTestMsg(localErrorText(res.ok ? res.data.code : res.error))
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
          {step > 0 && <button className="dp-onb__skip" onClick={skip}>Skip for now</button>}
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
            {p.aiProvider === 'local' ? (
              <>
                <label className="dp-onb__field">
                  <span>Provider URL</span>
                  <input value={p.aiBaseUrl} onChange={(e) => { set({ aiBaseUrl: e.target.value, aiReady: false }); setTest('idle') }} placeholder="http://localhost:11435/v1" />
                </label>
                <label className="dp-onb__field">
                  <span>API key (optional)</span>
                  <input type="password" value={p.aiApiKey} onChange={(e) => { set({ aiApiKey: e.target.value, aiReady: false }); setTest('idle') }} placeholder="Leave blank for a local gateway" />
                </label>
              </>
            ) : (
              <>
                <label className="dp-onb__field">
                  <span>Cloud account email</span>
                  <input type="email" value={p.cloudEmail} onChange={(e) => { set({ cloudEmail: e.target.value, aiReady: false }); setTest('idle') }} placeholder="you@company.com" />
                </label>
                <label className="dp-onb__field">
                  <span>Password</span>
                  <input type="password" value={p.cloudPassword} onChange={(e) => { set({ cloudPassword: e.target.value, aiReady: false }); setTest('idle') }} placeholder="Your Ollabridge Cloud password" />
                </label>
                <p className="dp-onb__hint">Sign-in happens on the DayPilot server; your password is never stored. Cloud inference is used only when you make Cloud the active provider.</p>
              </>
            )}
            <div className="dp-onb__testrow">
              <button className="dp-onb__test" onClick={testConnection}
                disabled={test === 'testing' || (p.aiProvider === 'cloud' ? !p.cloudEmail || !p.cloudPassword : !p.aiBaseUrl)}>
                {test === 'testing' ? 'Connecting…' : 'Test connection'}
              </button>
              {test !== 'idle' && (
                <span className={'dp-onb__teststatus dp-onb__teststatus--' + test} role="status">
                  {test === 'ok' ? '✓ ' : test === 'fail' ? '✕ ' : ''}{testMsg}
                </span>
              )}
            </div>
            {test !== 'ok' && (
              <p className="dp-onb__hint">Until a provider is verified, DayPilot runs in <strong>limited mode</strong> — planning and chat still work with the built-in planner, without an AI narrative.</p>
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
            <button className="dp-onb__next" onClick={finish}>Enter DayPilot</button>
          ) : (
            <button className="dp-onb__next" onClick={() => setStep(step + 1)}>Continue</button>
          )}
        </footer>
      </div>
    </div>
  )
}

function defaultSteps() {
  return { provider: false, profile: false, mailbox: false, knowledge: false }
}

function prev(current: string, fallback: string): string {
  return current || fallback
}
