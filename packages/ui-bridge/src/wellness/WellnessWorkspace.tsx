import React, { useEffect, useRef, useState } from 'react'
import './wellness.css'

const WORK_MS = 120 * 60 * 1000
const BREAK_MS = 15 * 60 * 1000
const STORE_KEY = 'daypilot-workplace-wellness-v1'
type Saved = { enabled: boolean; workStartedAt: number; breakStartedAt: number | null; completed: number; snoozedUntil: number; lastSeenAt: number }
export type WellnessMonitor = {
  enabled: boolean; breakDue: boolean; onBreak: boolean; remainingMs: number
  completed: number; notifications: string; startBreak: () => void
  setEnabled: (enabled: boolean) => void; snooze: () => void; reset: () => void
  requestNotifications: () => void
}
function readSaved(): Saved {
  const now = Date.now()
  const fresh: Saved = { enabled: true, workStartedAt: now, breakStartedAt: null, completed: 0, snoozedUntil: 0, lastSeenAt: now }
  try {
    const raw = localStorage.getItem(STORE_KEY)
    if (!raw) return fresh
    const stored = JSON.parse(raw) as Partial<Saved>
    if (typeof stored.lastSeenAt !== 'number' || now - stored.lastSeenAt > 60 * 60 * 1000 || stored.lastSeenAt > now) return fresh
    return { ...fresh, ...stored, lastSeenAt: now }
  } catch { return fresh }
}
function formatRemaining(ms: number) {
  const seconds = Math.max(0, Math.ceil(ms / 1000))
  return `${String(Math.floor(seconds / 3600)).padStart(2, '0')}:${String(Math.floor(seconds % 3600 / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
}
export function useWellnessMonitor(): WellnessMonitor {
  const [saved, setSaved] = useState<Saved>(readSaved)
  const [now, setNow] = useState(Date.now)
  const lastNotified = useRef<number | null>(null)
  const [notifications, setNotifications] = useState(() => typeof Notification === 'undefined' ? 'unsupported' : Notification.permission)
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])
  useEffect(() => {
    try { localStorage.setItem(STORE_KEY, JSON.stringify({ ...saved, lastSeenAt: now })) } catch { /* storage may be disabled */ }
  }, [saved, Math.floor(now / 60000)])
  useEffect(() => {
    if (saved.enabled && saved.breakStartedAt !== null && now - saved.breakStartedAt >= BREAK_MS) {
      setSaved(previous => ({ ...previous, breakStartedAt: null, completed: previous.completed + 1, workStartedAt: Date.now(), snoozedUntil: 0 }))
    }
  }, [now, saved.enabled, saved.breakStartedAt])
  const onBreak = saved.enabled && saved.breakStartedAt !== null
  const remainingMs = onBreak ? BREAK_MS - (now - (saved.breakStartedAt ?? now)) : WORK_MS - (now - saved.workStartedAt)
  const breakDue = saved.enabled && !onBreak && remainingMs <= 0
  useEffect(() => {
    if (!breakDue || saved.snoozedUntil > now || lastNotified.current === saved.workStartedAt) return
    lastNotified.current = saved.workStartedAt
    if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
      try { new Notification('DayPilot · Time for a screen break', { body: 'After 120 minutes, take 15 minutes away from the screen.' }) } catch { /* platform blocks notifications */ }
    }
  }, [breakDue, now, saved.snoozedUntil, saved.workStartedAt])
  return {
    enabled: saved.enabled, breakDue, onBreak, remainingMs, completed: saved.completed, notifications,
    startBreak: () => setSaved(prev => ({ ...prev, breakStartedAt: Date.now(), snoozedUntil: 0 })),
    setEnabled: (enabled) => setSaved(prev => ({ ...prev, enabled, workStartedAt: Date.now(), breakStartedAt: null, snoozedUntil: 0 })),
    snooze: () => setSaved(prev => ({ ...prev, snoozedUntil: Date.now() + 10 * 60 * 1000 })),
    reset: () => setSaved(prev => ({ ...prev, workStartedAt: Date.now(), breakStartedAt: null, completed: 0, snoozedUntil: 0 })),
    requestNotifications: () => { if (typeof Notification !== 'undefined' && Notification.permission === 'default') void Notification.requestPermission().then(setNotifications) },
  }
}
export function WellnessReminder({ monitor, onOpen }: { monitor: WellnessMonitor; onOpen: () => void }) {
  if (!monitor.enabled || (!monitor.breakDue && !monitor.onBreak)) return null
  return <div className="dp-wellness-reminder" role="status" aria-live="polite">
    <strong>{monitor.onBreak ? 'Your screen break is in progress' : 'Time for a screen break'}</strong>
    <span>{monitor.onBreak ? `${formatRemaining(monitor.remainingMs)} remaining of 15 minutes` : '120 minutes elapsed · plan a 15-minute VDT break.'}</span>
    <button type="button" onClick={onOpen}>Open Wellness</button>
    {monitor.breakDue && <button type="button" onClick={monitor.startBreak}>Begin 15-min break</button>}
  </div>
}
const STEPS = [
  { icon: '🧘', title: 'Shoulder release', text: 'Gently roll shoulders back and down. Avoid forcing the range of motion.', seconds: '30 seconds', motion: 'shoulder' },
  { icon: '👀', title: 'Look into the distance', text: 'Rest your eyes by looking at something far away. Blink naturally.', seconds: '20 seconds', motion: 'eyes' },
  { icon: '👐', title: 'Wrist and hand reset', text: 'Relax your hands, open and close your fingers, and shake out tension.', seconds: '30 seconds', motion: 'hands' },
  { icon: '🚶', title: 'Walk away from the display', text: 'Stand up and walk if you can, or switch to a non-screen task.', seconds: '15-minute VDT break', motion: 'walk' },
]
function ErgonomicDrawing() {
  return <svg className="dp-wellness-desk-svg" viewBox="0 0 530 330" role="img" aria-label="Illustration of neutral desk posture: eyes 50 to 70 centimetres from a screen, forearms comfortably supported, feet on the floor.">
    <defs><linearGradient id="dp-wellness-desk-gradient" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#55b8cc"/><stop offset="1" stopColor="#5a78db"/></linearGradient></defs>
    <rect x="0" y="0" width="530" height="330" rx="20" fill="rgba(110,145,180,.08)"/>
    <path d="M15 285H515" stroke="currentColor" opacity=".2" strokeWidth="2"/>
    <path d="M298 166h194v13H298zM312 178v108M470 178v108" fill="#7d90ae"/>
    <rect x="377" y="74" width="93" height="82" rx="7" fill="#263b5a" stroke="#7bc1dc" strokeWidth="4"/>
    <path d="M385 82h77v66h-77z" fill="url(#dp-wellness-desk-gradient)" opacity=".7"/>
    <path d="M423 156v12m-31 0h64" stroke="#708bad" strokeWidth="5"/>
    <path d="M144 184v93m-37-15h74m-42-78h-32c-19 0-30-14-30-33V93" fill="none" stroke="#6480ac" strokeWidth="15" strokeLinecap="round"/>
    <path d="M90 181h125" stroke="#90aacb" strokeWidth="17" strokeLinecap="round"/>
    <path d="M150 64c-26 0-37 20-34 44 2 15 10 26 22 33v15" fill="#e0a77f"/>
    <circle cx="150" cy="79" r="33" fill="#e0a77f"/>
    <path d="M115 77c0-37 56-43 68-14 3 10-1 17-1 17-15-12-21-24-43-14-9 4-14 11-24 11Z" fill="#273d66"/>
    <path d="M143 113c-20 5-32 22-30 42l6 41h81l-6-51c-3-20-20-35-51-32Z" fill="#68a7c7"/>
    <path d="M175 151l31 27 64 1 28-6" fill="none" stroke="#e0a77f" strokeWidth="15" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M143 199h75l38 47-1 37h44" fill="none" stroke="#354e7b" strokeWidth="21" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M147 202l1 73 51 4" fill="none" stroke="#354e7b" strokeWidth="23" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M192 283h39m61 1h30" stroke="#203452" strokeWidth="10" strokeLinecap="round"/>
    <path d="M193 83h173" stroke="#80c7d3" strokeWidth="2" strokeDasharray="6 5"/>
    <path d="m200 77-9 6 9 6m160-12 9 6-9 6" fill="none" stroke="#80c7d3" strokeWidth="2"/>
    <rect x="237" y="57" width="96" height="24" rx="12" fill="#274963"/>
    <text x="285" y="73" textAnchor="middle" fill="#fff" fontSize="13" fontWeight="700">50–70 cm</text>
    <circle cx="203" cy="178" r="4" fill="#a9e6d3"/>
    <path d="M203 178h-4v-18" stroke="#a9e6d3" strokeWidth="2" fill="none"/>
    <text x="218" y="159" fill="currentColor" fontSize="12">Relaxed arms</text>
    <text x="30" y="309" fill="currentColor" fontSize="12" opacity=".85">Supported back · Feet grounded · Natural posture</text>
  </svg>
}
export function WellnessWorkspace({ monitor }: { monitor: WellnessMonitor }) {
  const [currentStep, setCurrentStep] = useState(0)
  const pct = Math.max(0, Math.min(100, (1 - Math.max(0, monitor.remainingMs) / (monitor.onBreak ? BREAK_MS : WORK_MS)) * 100))
  return <div className="dp-wellness-page">
    <div className="dp-wellness-heading"><div><span className="dp-wellness-kicker">WORKPLACE WELLNESS</span><h1>Take care of your workday</h1><p>Gentle reminders, guided movement, and an ergonomic workstation setup.</p></div><span className="dp-wellness-chip">Local on this device</span></div>
    <div className="dp-wellness-grid">
      <section className="dp-wellness-card dp-wellness-timer">
        <div className="dp-wellness-section-title"><h2>Screen-work reminder</h2><span>{monitor.enabled ? 'Monitoring on' : 'Paused'}</span></div>
        <div className="dp-wellness-meter" style={{ '--progress': `${pct}%` } as React.CSSProperties}><div><small>{monitor.onBreak ? 'Break remaining' : monitor.breakDue ? 'Break due' : 'Until next break'}</small><strong>{formatRemaining(monitor.remainingMs)}</strong></div></div>
        <p>{monitor.onBreak ? 'Give your eyes and body a rest. The next work interval starts when the 15 minutes finish.' : 'After 120 minutes at a videoterminal, plan a 15-minute break or switch to suitable non-screen duties.'}</p>
        <div className="dp-wellness-actions">
          {monitor.onBreak ? <button disabled type="button" className="dp-wellness-primary">Break in progress</button> : <button type="button" className="dp-wellness-primary" onClick={monitor.startBreak}>Start 15-minute break</button>}
          <button type="button" onClick={() => monitor.setEnabled(!monitor.enabled)}>{monitor.enabled ? 'Pause monitor' : 'Resume monitor'}</button>
          <button type="button" onClick={monitor.reset}>Reset</button>
        </div>
        <p className="dp-wellness-small">{monitor.completed} completed break{monitor.completed === 1 ? '' : 's'} this session. This is an elapsed-time reminder, not a detector of actual screen use or legal compliance.</p>
        {monitor.notifications === 'default' && <button type="button" className="dp-wellness-link" onClick={monitor.requestNotifications}>Enable optional desktop notifications</button>}
        {monitor.notifications === 'denied' && <p className="dp-wellness-small">Desktop notifications are blocked in your browser settings; in-app reminders still work.</p>}
      </section>
      <section className="dp-wellness-card dp-wellness-ergonomics">
        <div className="dp-wellness-section-title"><h2>Workstation setup</h2><span>Posture guide</span></div>
        <ErgonomicDrawing />
        <div className="dp-wellness-checks">
          <span>✓ Screen 50–70 cm away</span><span>✓ Screen near eye height</span><span>✓ Back supported</span><span>✓ Feet flat or footrest</span><span>✓ Elbows relaxed, wrists neutral</span><span>✓ Glare controlled</span>
        </div>
      </section>
    </div>
    <section className="dp-wellness-card dp-wellness-exercises">
      <div className="dp-wellness-section-title"><h2>Animated movement coach</h2><span>Move gently; stop if uncomfortable</span></div>
      <div className="dp-wellness-moves">
        {STEPS.map((step, index) => <button type="button" key={step.title} className={`dp-wellness-move ${currentStep === index ? 'is-selected' : ''}`} onClick={() => setCurrentStep(index)} aria-pressed={currentStep === index}><span className={`dp-wellness-move-icon dp-wellness-motion-${step.motion}`} aria-hidden="true">{step.icon}</span><strong>{step.title}</strong><small>{step.seconds}</small></button>)}
      </div>
      <div className="dp-wellness-coach" role="status"><strong>{STEPS[currentStep].title}</strong><span>{STEPS[currentStep].text}</span><button type="button" onClick={() => setCurrentStep((currentStep + 1) % STEPS.length)}>Next activity →</button></div>
    </section>
    <p className="dp-wellness-small">Guidance for screen-work ergonomics and general comfort only, not medical advice. Applicable workplace rules and occupational-health advice take priority. VDT breaks should not be accumulated at the start or end of work.</p>
  </div>
}
