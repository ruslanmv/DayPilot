import React, { useState } from 'react'

const STORAGE_KEY = 'daypilot.onboarded'
const PROFILE_KEY = 'daypilot.profile'

export type OnboardingProfile = {
  name: string
  email: string
  mailbox: string
  sourceKind: 'folder' | 'box'
  source: string
}

const EMPTY: OnboardingProfile = { name: '', email: '', mailbox: '', sourceKind: 'folder', source: '' }

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

/**
 * A minimalist first-run wizard, in the spirit of ChatGPT/Claude onboarding:
 * just the essentials to get value on day one — who you are, one mailbox, and
 * one place to read from for RAG. Everything else lives in Settings. Renders
 * nothing once completed (or skipped).
 */
export function OnboardingWizard({ onFinish }: { onFinish?: (profile: OnboardingProfile | null) => void }) {
  const [open, setOpen] = useState(() => !alreadyOnboarded())
  const [step, setStep] = useState(0)
  const [p, setP] = useState<OnboardingProfile>(EMPTY)

  if (!open) return null

  const steps = ['You', 'Mailbox', 'Knowledge']
  const last = step === steps.length - 1

  function close(profile: OnboardingProfile | null) {
    try {
      localStorage.setItem(STORAGE_KEY, 'true')
      if (profile) localStorage.setItem(PROFILE_KEY, JSON.stringify(profile))
    } catch {
      /* ignore storage failures */
    }
    setOpen(false)
    onFinish?.(profile)
  }

  const set = (patch: Partial<OnboardingProfile>) => setP((prev) => ({ ...prev, ...patch }))

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
          <button className="dp-onb__skip" onClick={() => close(null)}>Skip for now</button>
        </header>

        <div className="dp-onb__steps" aria-hidden="true">
          {steps.map((s, i) => (
            <span key={s} className={'dp-onb__dot' + (i === step ? ' is-active' : i < step ? ' is-done' : '')} />
          ))}
        </div>

        {step === 0 && (
          <div className="dp-onb__body">
            <h2 className="dp-onb__title">Welcome to DayPilot</h2>
            <p className="dp-onb__sub">Your local-first AI operator workspace. Two quick steps and you're set.</p>
            <label className="dp-onb__field">
              <span>Your name</span>
              <input value={p.name} onChange={(e) => set({ name: e.target.value })} placeholder="Ruslan M." autoFocus />
            </label>
            <label className="dp-onb__field">
              <span>Work email</span>
              <input type="email" value={p.email} onChange={(e) => set({ email: e.target.value, mailbox: prev(p.mailbox, e.target.value) })} placeholder="you@company.com" />
            </label>
          </div>
        )}

        {step === 1 && (
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

        {step === 2 && (
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
          {last ? (
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
