import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import {
  DAY_END_MIN, DAY_START_MIN, GRID_HEIGHT, PX_PER_MIN, SLOT_HEIGHT,
  heightPx, minutesOf, slotLabels, topPx,
} from '../calendar/calendarData'
import {
  applyProposal, chatPlan, dailyReview, discardProposal, generatePlan, loadPlan, loadReadiness, syncPlan,
  type PlanProposal, type PlannerBlock, type PlannerPlan, type PlannerQuality, type PlannerReadiness,
} from '../plannerClient'

/**
 * Connected Day Planner — the primary screen once DayPilot's AI has generated a
 * real plan. Everything (timeline blocks, quality score, focus time, task
 * counts, assistant suggestions) comes from the real backend plan + readiness;
 * nothing is placeholder. An explicit experience-state model drives the UI so
 * an empty plan is never mistaken for an error, and the wizard is not forced
 * every day — a ready user just sees their plan.
 */
type Experience = 'loading' | 'initial_setup_required' | 'ready_to_create' | 'creating' | 'plan_ready' | 'failed'

const TYPE_CAT: Record<string, string> = {
  focus: 'deep', calendar_event: 'calendar', task: 'calendar', meeting: 'review',
  admin: 'meeting', break: 'personal', buffer: 'personal',
}
const TYPE_ICON: Record<string, string> = {
  focus: '🧠', calendar_event: '🗓', task: '✅', meeting: '👥', admin: '🗂', break: '☕', buffer: '⏳',
}
const TYPE_LABEL: Record<string, string> = {
  focus: 'Focus', calendar_event: 'Fixed event', task: 'Task', meeting: 'Meeting',
  admin: 'Admin', break: 'Break', buffer: 'Buffer',
}

function typeOf(b: PlannerBlock): string {
  if (b.type) return b.type
  if (b.kind === 'deep') return 'focus'
  if (b.kind === 'meeting') return 'meeting'
  if (b.kind === 'review') return 'meeting'
  if (b.kind === 'admin') return 'admin'
  if (b.kind === 'break') return 'break'
  return 'task'
}

function useNowMinute(): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => { const id = window.setInterval(() => setNow(new Date()), 60_000); return () => window.clearInterval(id) }, [])
  return now
}
function fmtHM(min: number): string { return `${String(Math.floor(min / 60)).padStart(2, '0')}:${String(min % 60).padStart(2, '0')}` }

export function PlannerBoard({ onStartFocus }: { onStartFocus?: () => void }) {
  const [exp, setExp] = useState<Experience>('loading')
  const [readiness, setReadiness] = useState<PlannerReadiness | null>(null)
  const [plan, setPlan] = useState<PlannerPlan | null>(null)
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(() => {
    setExp('loading')
    // The daily review runs first: it reconciles yesterday's statuses and
    // auto-builds today's optimized plan when sources are ready, so opening
    // Planning on a new day never requires pressing Generate.
    dailyReview().then(() => Promise.all([loadReadiness(), loadPlan()])).then(([r, p]) => {
      setReadiness(r)
      if (p && p.blocks.length > 0) { setPlan(p); setExp('plan_ready') }
      else if (!r) setExp('failed')
      else if (r.sufficient) setExp('ready_to_create')
      else setExp('initial_setup_required')
    })
  }, [])
  useEffect(() => { refresh() }, [refresh])

  const create = useCallback((instruction?: string) => {
    setExp('creating')
    setBusy(true)
    generatePlan(undefined, instruction).then((p) => {
      setBusy(false)
      if (p && p.blocks.length > 0) { setPlan(p); setExp('plan_ready') }
      else setExp('failed')
    })
  }, [])

  if (exp === 'loading') return <PlannerState><span className="dp-spinner" aria-hidden="true" /><p>Loading your plan…</p></PlannerState>
  if (exp === 'creating') return <CreatingView />
  if (exp === 'failed') {
    return (
      <PlannerState>
        <h2>We couldn’t update your plan right now.</h2>
        <p>Your existing plan and preferences are safe.</p>
        <div className="dp-pl__staterow"><button className="dp-pl__primary" onClick={refresh}>Try again</button>{plan && <button className="dp-ghost-button" onClick={() => setExp('plan_ready')}>Continue with current plan</button>}</div>
      </PlannerState>
    )
  }
  if (exp === 'initial_setup_required' || exp === 'ready_to_create') {
    return <ReadinessView readiness={readiness} canCreate={exp === 'ready_to_create'} busy={busy} onCreate={() => create()} />
  }
  return <PlanReadyView plan={plan!} readiness={readiness} busy={busy} onReplan={() => create('replan the rest of today')} onChat={setPlan} onStartFocus={onStartFocus} />
}

// --- readiness (first-time / empty) -----------------------------------------

function ReadinessView({ readiness, canCreate, busy, onCreate }: { readiness: PlannerReadiness | null; canCreate: boolean; busy: boolean; onCreate: () => void }) {
  const r = readiness
  const rows: [string, boolean, string][] = [
    ['Working hours', !!r?.workingHoursConfigured, r?.workingHoursConfigured ? 'Set' : 'Using defaults'],
    ['Calendar', !!r?.calendarConnected, r?.calendarConnected ? 'Connected' : 'Not connected'],
    ['Tasks', (r?.tasksOpen ?? 0) > 0, `${r?.tasksOpen ?? 0} open · ${r?.tasksDueToday ?? 0} due today`],
    ['Projects', (r?.projectsActive ?? 0) > 0, `${r?.projectsActive ?? 0} active`],
    ['Focus preferences', !!r?.focusPrefsConfigured, r?.focusPrefsConfigured ? 'Configured' : 'Not configured'],
  ]
  return (
    <PlannerState wide>
      <h2>{canCreate ? 'DayPilot is ready to build your plan' : 'DayPilot is preparing your first plan'}</h2>
      <p>{canCreate ? 'DayPilot has enough information to build a realistic plan from your real work.' : 'Connect at least one work source so DayPilot can build a useful schedule.'}</p>
      <ul className="dp-pl__ready">
        {rows.map(([label, ok, detail]) => (
          <li key={label} className={ok ? 'is-ok' : 'is-missing'}>
            <span className="dp-pl__ready-icon" aria-hidden="true">{ok ? '✓' : '○'}</span>
            <span className="dp-pl__ready-label">{label}</span>
            <span className="dp-pl__ready-detail">{detail}</span>
          </li>
        ))}
      </ul>
      <div className="dp-pl__staterow">
        {canCreate
          ? <button className="dp-pl__primary" disabled={busy} onClick={onCreate}>{busy ? 'Creating…' : 'Create my plan'}</button>
          : (r?.tasksOpen ?? 0) > 0
            ? <button className="dp-pl__primary" disabled={busy} onClick={onCreate}>Create plan with tasks only</button>
            : <button className="dp-ghost-button" disabled>Connect a source to continue</button>}
      </div>
    </PlannerState>
  )
}

function CreatingView() {
  const stages = ['Reading your calendar', 'Reviewing open tasks', 'Checking project deadlines', 'Protecting focus time', 'Resolving schedule conflicts', 'Building your day']
  return (
    <PlannerState wide>
      <h2>Creating your plan…</h2>
      <ul className="dp-pl__stages">
        {stages.map((s) => (
          <li key={s}><span className="dp-spinner dp-spinner--sm" aria-hidden="true" /> {s}</li>
        ))}
      </ul>
    </PlannerState>
  )
}

function PlannerState({ children, wide }: { children: React.ReactNode; wide?: boolean }) {
  return <div className={'dp-pl dp-pl--state' + (wide ? ' dp-pl--wide' : '')}><div className="dp-pl__statecard">{children}</div></div>
}

// --- plan ready --------------------------------------------------------------

function PlanReadyView({ plan, readiness, busy, onReplan, onChat, onStartFocus }: {
  plan: PlannerPlan; readiness: PlannerReadiness | null; busy: boolean
  onReplan: () => void; onChat: (p: PlannerPlan) => void; onStartFocus?: () => void
}) {
  const now = useNowMinute()
  const [selected, setSelected] = useState<string | null>(null)
  const [aiOpen, setAiOpen] = useState(true)
  const [proposal, setProposal] = useState<PlanProposal | null>(null)
  const [notice, setNotice] = useState('')
  const labels = useMemo(slotLabels, [])
  const scrollRef = useRef<HTMLDivElement>(null)
  const autoScrolled = useRef(false)
  const liveRef = useRef<HTMLDivElement>(null)

  // Smart sync: a pass on open and every 3 minutes. Minor status updates apply
  // silently (the plan reloads); new work surfaces as a discardable proposal.
  useEffect(() => {
    let cancelled = false
    const pass = () => {
      syncPlan().then((res) => {
        if (cancelled || !res) return
        if (res.statusUpdates.length > 0) {
          loadPlan().then((p) => { if (!cancelled && p) onChat(p) })
          setNotice(res.statusUpdates[0])
        }
        if (res.proposal) {
          setProposal(res.proposal)
          if (liveRef.current) liveRef.current.textContent = 'DayPilot suggests a plan update. Review it above the timeline.'
        }
      })
    }
    pass()
    const id = window.setInterval(pass, 180_000)
    return () => { cancelled = true; window.clearInterval(id) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function acceptProposal() {
    if (!proposal) return
    const updated = await applyProposal(proposal)
    setProposal(null)
    if (updated) { onChat(updated); setNotice('Plan updated with the new work.') }
    else setNotice('We couldn’t apply the update. Your plan is unchanged.')
  }

  async function dismissProposal() {
    if (!proposal) return
    await discardProposal(proposal)
    setProposal(null)
    setNotice('Dismissed — your current plan is kept.')
  }

  const nowMin = now.getHours() * 60 + now.getMinutes()
  const inRange = nowMin >= DAY_START_MIN && nowMin <= DAY_END_MIN

  useLayoutEffect(() => {
    const el = scrollRef.current
    if (!el || autoScrolled.current || !inRange) return
    el.scrollTop = Math.max(0, (nowMin - DAY_START_MIN) * PX_PER_MIN - el.clientHeight / 3)
    autoScrolled.current = true
  }, [inRange, nowMin])

  const blocks = plan.blocks
  const focusMin = blocks.filter((b) => typeOf(b) === 'focus').reduce((a, b) => a + (minutesOf(b.end) - minutesOf(b.start)), 0)
  const taskBlocks = blocks.filter((b) => ['task', 'focus'].includes(typeOf(b))).length
  const tasksOpen = readiness?.tasksOpen ?? taskBlocks
  const quality: PlannerQuality | undefined = plan.quality

  const activeBlock = blocks.find((b) => minutesOf(b.start) <= nowMin && nowMin < minutesOf(b.end))
  const nextBlock = blocks.find((b) => minutesOf(b.start) > nowMin)

  return (
    <div className={'dp-pl' + (aiOpen ? '' : ' dp-pl--ai-collapsed')}>
      <div className="dp-pl__main">
        {/* Summary bar */}
        <header className="dp-pl__summary">
          <div className="dp-pl__summary-title">
            <h2>Today’s plan <span className="dp-pl__uptodate">Up to date</span></h2>
            <p>{new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}</p>
          </div>
          <div className="dp-pl__metrics">
            {quality && (
              <div className="dp-pl__metric dp-pl__quality" title={[...quality.strengths, ...quality.warnings].join(' · ')}>
                <span className="dp-pl__score">{quality.score}</span>
                <span className="dp-pl__metric-body"><strong>{quality.label}</strong><span>{quality.strengths[0] || 'Plan ready'}</span></span>
              </div>
            )}
            <div className="dp-pl__metric"><span className="dp-pl__metric-label">Focus time</span><strong>{Math.floor(focusMin / 60)}h {focusMin % 60}m</strong></div>
            <div className="dp-pl__metric"><span className="dp-pl__metric-label">Tasks</span><strong>{taskBlocks} of {tasksOpen} planned</strong></div>
          </div>
          <div className="dp-pl__summary-actions">
            <button className="dp-pl__primary" disabled={busy} onClick={onReplan}>{busy ? '…' : '↻ Replan'}</button>
            {!aiOpen && <button className="dp-ghost-button" onClick={() => setAiOpen(true)}>✦ Assistant</button>}
          </div>
        </header>

        {quality && (quality.strengths.length > 0 || quality.warnings.length > 0) && (
          <div className="dp-pl__explain">
            {quality.strengths.map((s) => <span key={s} className="dp-pl__explain-item is-ok">✓ {s}</span>)}
            {quality.warnings.map((w) => <span key={w} className="dp-pl__explain-item is-warn">△ {w}</span>)}
          </div>
        )}

        {/* Plan-update notifications: proposals never change the plan silently,
            and can be dismissed when the user is already on the new work. */}
        <div ref={liveRef} aria-live="polite" className="dp-sr-live" />
        {proposal && (
          <div className="dp-pl__notice" role="alert">
            <div className="dp-pl__notice-body">
              <strong>Suggested plan update — {proposal.title}</strong>
              <ul>{proposal.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            </div>
            <div className="dp-pl__notice-actions">
              <button className="dp-pl__primary" onClick={acceptProposal}>Apply update</button>
              <button className="dp-ghost-button" onClick={dismissProposal}>Dismiss — I’m already on it</button>
            </div>
          </div>
        )}
        {!proposal && notice && (
          <div className="dp-pl__notice dp-pl__notice--quiet" role="status">
            <span>{notice}</span>
            <button className="dp-icon-button" aria-label="Dismiss notice" onClick={() => setNotice('')}>✕</button>
          </div>
        )}

        {/* Timeline */}
        <div className="dp-pl__scroll" ref={scrollRef} onWheel={() => { autoScrolled.current = true }}>
          <div className="dp-pl__timeline" style={{ height: GRID_HEIGHT }}>
            <div className="dp-pl__gutter">
              {labels.map((s) => <div key={s.min} className="dp-cal__slotlabel" style={{ height: SLOT_HEIGHT }}>{s.label}</div>)}
            </div>
            <div className="dp-pl__col" style={{ height: GRID_HEIGHT }}>
              {labels.map((s) => <div key={s.min} className={'dp-cal__line' + (s.hour ? ' dp-cal__line--hour' : '')} style={{ top: topPx(s.min) }} aria-hidden="true" />)}
              {blocks.map((b, i) => {
                const t = typeOf(b)
                const cat = TYPE_CAT[t]
                const s = minutesOf(b.start); const e = minutesOf(b.end)
                const id = b.id || `b${i}`
                const isActive = activeBlock && (activeBlock.id || '') === (b.id || '') && !!b.id
                return (
                  <button
                    key={id}
                    type="button"
                    className={`dp-ev dp-ev--${cat} dp-pl__block${isActive ? ' is-active' : ''}${b.status === 'done' ? ' is-done' : ''}`}
                    style={{ top: topPx(s), height: heightPx(s, e), left: 2, right: 2, width: 'auto' }}
                    onClick={() => setSelected(selected === id ? null : id)}
                    aria-label={`${b.title}, ${b.start} to ${b.end}, ${TYPE_LABEL[t]}`}
                  >
                    <span className="dp-ev__bar" aria-hidden="true" />
                    <span className="dp-pl__block-body">
                      <span className="dp-pl__block-top">
                        <span className="dp-pl__block-time">{b.start} – {b.end}</span>
                        <span className="dp-pl__block-title">{b.title}</span>
                      </span>
                      <span className="dp-pl__block-tags">
                        {b.owner && b.owner !== 'you' && <span className="dp-pl__tag">{b.owner}</span>}
                        <span className="dp-pl__tag dp-pl__tag--type">{TYPE_ICON[t]} {TYPE_LABEL[t]}</span>
                        {isActive && <span className="dp-pl__tag dp-pl__tag--active">Active · {minutesOf(b.end) - nowMin} min left</span>}
                      </span>
                    </span>
                    {selected === id && (
                      <span className="dp-pl__popover" role="dialog">
                        <span className="dp-pl__pop-head">Why DayPilot scheduled this here</span>
                        <span className="dp-pl__pop-reason">{b.reason || 'Scheduled around your fixed commitments.'}</span>
                        <span className="dp-pl__pop-actions">
                          <button onClick={(ev) => { ev.stopPropagation(); onStartFocus?.() }}>▶ Start focus</button>
                        </span>
                      </span>
                    )}
                  </button>
                )
              })}
              {inRange && (
                <div className="dp-now" style={{ top: (nowMin - DAY_START_MIN) * PX_PER_MIN }} role="img" aria-label={`Current time ${fmtHM(nowMin)}`}>
                  <span className="dp-now__label">{fmtHM(nowMin)}</span>
                  <span className="dp-now__dot" aria-hidden="true" />
                  <span className="dp-now__line" aria-hidden="true" />
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {aiOpen && <PlannerAssistant plan={plan} readiness={readiness} activeTitle={activeBlock?.title} nextBlock={nextBlock} onClose={() => setAiOpen(false)} onPlan={onChat} />}
    </div>
  )
}

// --- assistant ---------------------------------------------------------------

function PlannerAssistant({ plan, readiness, activeTitle, nextBlock, onClose, onPlan }: {
  plan: PlannerPlan; readiness: PlannerReadiness | null; activeTitle?: string; nextBlock?: PlannerBlock
  onClose: () => void; onPlan: (p: PlannerPlan) => void
}) {
  const [turns, setTurns] = useState<{ role: 'user' | 'assistant'; body: string }[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const logRef = useRef<HTMLDivElement>(null)
  useEffect(() => { const el = logRef.current; if (el) el.scrollTop = el.scrollHeight }, [turns, busy])

  // Suggestions derived from the real plan/readiness — not placeholders.
  const suggestions = useMemo(() => {
    const out: string[] = []
    const noDue = (readiness?.tasksOpen ?? 0) - (readiness?.tasksDueToday ?? 0)
    if (noDue > 0) out.push(`Review ${noDue} task${noDue === 1 ? '' : 's'} without a due date`)
    if (plan.blocks.some((b) => typeOf(b) === 'admin')) out.push('Move email administration later in the day')
    out.push('Protect more focus time tomorrow morning')
    return out.slice(0, 3)
  }, [plan, readiness])

  function ask(q: string) {
    const query = q.trim(); if (!query) return
    setTurns((t) => [...t, { role: 'user', body: query }]); setInput(''); setBusy(true)
    chatPlan(query).then((res) => {
      setBusy(false)
      if (!res) { setTurns((t) => [...t, { role: 'assistant', body: 'I couldn’t reach the planner just now. Your plan is unchanged.' }]); return }
      setTurns((t) => [...t, { role: 'assistant', body: res.reply }])
      if (res.replanned && res.plan) onPlan(res.plan)
    })
  }

  return (
    <aside className="dp-pl__ai" aria-label="AI Planning Assistant">
      <header className="dp-pl__ai-head">
        <div className="dp-pl__ai-title"><span aria-hidden="true">✦</span> AI Planning Assistant</div>
        <button className="dp-icon-button" aria-label="Close assistant" onClick={onClose}>✕</button>
      </header>
      <div className="dp-pl__ai-status">
        <strong>Plan is up to date</strong>
        <p>I’ll keep monitoring your connected work and suggest updates when something important changes.</p>
        {activeTitle && <p className="dp-pl__ai-now">Now: {activeTitle}{nextBlock && ` · Next: ${nextBlock.title} at ${nextBlock.start}`}</p>}
      </div>
      <div className="dp-pl__ai-log" ref={logRef}>
        {turns.length === 0 && (
          <>
            <div className="dp-pl__ai-label">Suggestions for you</div>
            {suggestions.map((s) => <button key={s} className="dp-pl__ai-suggest" onClick={() => ask(s)}>{s}</button>)}
            <div className="dp-pl__ai-label">Ask about your plan</div>
            {['Why is this task scheduled here?', 'What can I deprioritize?', 'Replan the rest of today', 'Show my week overview'].map((s) => (
              <button key={s} className="dp-pl__ai-chip" onClick={() => ask(s)}>{s}</button>
            ))}
          </>
        )}
        {turns.map((t, i) => (
          <div key={i} className={'dp-home-ai__turn dp-home-ai__turn--' + t.role}><div className="dp-home-ai__bubble"><p style={{ margin: 0 }}>{t.body}</p></div></div>
        ))}
        {busy && <div className="dp-home-ai__turn dp-home-ai__turn--assistant"><div className="dp-home-ai__bubble dp-home-ai__bubble--loading">Updating your plan…</div></div>}
      </div>
      <form className="dp-pl__ai-input" onSubmit={(e) => { e.preventDefault(); ask(input) }}>
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask or request a change…" aria-label="Ask or request a change" />
        <button className="dp-ai__send" type="submit" aria-label="Send" disabled={!input.trim()}>➤</button>
      </form>
      <div className="dp-pl__ai-foot">AI can make mistakes. Review important changes before applying.</div>
    </aside>
  )
}
