import React, { useEffect, useRef, useState } from 'react'
import { isDemoMode } from '../env'
import { chatPlan, generatePlan, loadPlan, type PlannerBlock } from '../plannerClient'
import { PlannerBoard, type PlannerNav } from './PlannerBoard'
import {
  INITIAL_FOCUS_MINUTES,
  INITIAL_PLAN,
  INITIAL_SCORE,
  KIND_LABEL,
  PLAN_CHAT_SEED,
  PLAN_SUGGESTIONS,
  minutesOf,
  type PlanTurn,
  type PlanUIBlock,
} from './planData'

const DEMO = isDemoMode()

/** Map a backend planner block to the UI block shape. */
function toUiBlock(b: PlannerBlock, i: number): PlanUIBlock {
  return {
    id: b.id || `blk-${i}`,
    title: b.title,
    kind: b.kind,
    start: b.start || '00:00',
    end: b.end || '00:00',
    status: b.status === 'done' ? 'done' : 'scheduled',
  }
}

/**
 * Planning — the multi-agent day planner surface. A timeline of clickable
 * blocks (every box opens an action popover), a one-tap Replan, and a chat
 * panel to converse with the plan ("move admin to the afternoon" replans).
 * Mirrors the backend graph: deep work mornings, meetings after lunch, admin
 * last, lunch protected; the score badge is the critic's verdict.
 */
/** Planning dispatches to the connected Day Planner board in production; demo
 *  mode keeps the offline sample timeline below. */
export function PlanningWorkspace({ onStartFocus, onNavigate }: { onStartFocus?: () => void; onNavigate?: (t: PlannerNav) => void }) {
  return DEMO ? <DemoPlanning onStartFocus={onStartFocus} /> : <PlannerBoard onStartFocus={onStartFocus} onNavigate={onNavigate} />
}

function DemoPlanning({ onStartFocus }: { onStartFocus?: () => void }) {
  const [blocks, setBlocks] = useState<PlanUIBlock[]>(DEMO ? INITIAL_PLAN : [])
  const [score, setScore] = useState(DEMO ? INITIAL_SCORE : 0)
  const [focusMinutes, setFocusMinutes] = useState(DEMO ? INITIAL_FOCUS_MINUTES : 0)
  const [selected, setSelected] = useState<string | null>(null)
  const [turns, setTurns] = useState<PlanTurn[]>(DEMO ? PLAN_CHAT_SEED : [])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(DEMO)
  const logRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = logRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [turns])

  // Load the real, persisted plan for today (connected mode).
  useEffect(() => {
    if (DEMO) return
    let cancelled = false
    loadPlan().then((plan) => {
      if (cancelled) return
      if (plan) {
        const ui = plan.blocks.map(toUiBlock)
        setBlocks(ui)
        recompute(ui)
      }
      setLoaded(true)
    })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function applyPlan(next: PlannerBlock[], summary?: string, apiScore?: number) {
    const ui = next.map(toUiBlock)
    setBlocks(ui)
    if (typeof apiScore === 'number') { setScore(apiScore); recomputeFocus(ui) } else { recompute(ui) }
    if (summary) setTurns((t) => [...t, { role: 'assistant', body: summary }])
  }

  function recomputeFocus(next: PlanUIBlock[]) {
    const deep = next.filter((b) => b.kind === 'deep' && b.status !== 'done')
    setFocusMinutes(deep.reduce((acc, b) => acc + (minutesOf(b.end) - minutesOf(b.start)), 0))
  }

  // Backend-connected replan: runs the graph and persists (connected mode).
  async function replanRemote(instruction?: string) {
    setBusy(true)
    const plan = await generatePlan(undefined, instruction)
    setBusy(false)
    if (plan) applyPlan(plan.blocks, plan.summary, plan.score)
    else setTurns((t) => [...t, { role: 'assistant', body: "I couldn't reach the planner. Check that the backend is running." }])
  }

  function recompute(next: PlanUIBlock[]) {
    const work = next.filter((b) => b.kind !== 'break' && b.status !== 'done')
    const deep = work.filter((b) => b.kind === 'deep')
    const fm = deep.reduce((acc, b) => acc + (minutesOf(b.end) - minutesOf(b.start)), 0)
    const switches = work.slice(1).reduce((acc, b, i) => acc + (b.kind !== work[i].kind ? 1 : 0), 0)
    const total = work.reduce((acc, b) => acc + (minutesOf(b.end) - minutesOf(b.start)), 0)
    const s = Math.round(100 * (0.45 * (total ? fm / total : 0) + 0.25 * (1 - switches / Math.max(work.length - 1, 1)) + 0.3))
    setFocusMinutes(fm)
    setScore(Math.min(s, 98))
  }

  function replan(reason: string) {
    // Mirror the scheduler pass: deep first (morning), then meetings/reviews,
    // admin last; times re-flowed with buffers, lunch fixed.
    const order: Record<string, number> = { deep: 0, review: 1, meeting: 1, admin: 2 }
    const work = blocks.filter((b) => b.kind !== 'break')
    work.sort((a, b) => (order[a.kind] ?? 1) - (order[b.kind] ?? 1))
    let cursor = minutesOf('08:30')
    const lunchStart = minutesOf('12:30')
    const rescheduled: PlanUIBlock[] = []
    for (const b of work) {
      const dur = b.kind === 'deep' ? 90 : b.kind === 'admin' ? 30 : 45
      if (cursor < lunchStart && cursor + dur > lunchStart) cursor = minutesOf('13:15')
      if (b.kind === 'admin' && cursor < minutesOf('16:00')) cursor = minutesOf('16:00')
      const start = cursor
      cursor += dur + 15
      const fmt = (m: number) => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
      rescheduled.push({ ...b, start: fmt(start), end: fmt(start + dur) })
    }
    rescheduled.push({ id: 'lunch', title: 'Lunch & recharge', kind: 'break', start: '12:30', end: '13:15', status: 'scheduled' })
    rescheduled.sort((a, b) => a.start.localeCompare(b.start))
    setBlocks(rescheduled)
    recompute(rescheduled)
    setTurns((t) => [...t, { role: 'assistant', body: `Replanned (${reason}): deep work re-protected in the morning, meetings batched after lunch, admin moved to the end of the day.` }])
  }

  function send(text: string) {
    const q = text.trim()
    if (!q) return
    setTurns((t) => [...t, { role: 'user', body: q }])
    setInput('')
    const lowered = q.toLowerCase()

    // Demo mode: local simulation. Connected mode: real planner chat that
    // replans on the backend and dynamically updates the scheduler.
    if (DEMO) {
      window.setTimeout(() => {
        if (['move', 'replan', 'push', 'batch', 'protect', 'reschedule'].some((k) => lowered.includes(k))) {
          replan('your request')
        } else if (lowered.includes('focus')) {
          setTurns((t) => [...t, { role: 'assistant', body: `You have ${focusMinutes} focused minutes across ${blocks.filter((b) => b.kind === 'deep').length} deep-work blocks. Score ${score}/100.` }])
        } else {
          setTurns((t) => [...t, { role: 'assistant', body: 'I can replan your day, move blocks, or report focus time — just ask.' }])
        }
      }, 350)
      return
    }

    setBusy(true)
    chatPlan(q).then((res) => {
      setBusy(false)
      if (!res) {
        setTurns((t) => [...t, { role: 'assistant', body: "I couldn't reach the planner. Check that the backend is running." }])
        return
      }
      setTurns((t) => [...t, { role: 'assistant', body: res.reply }])
      // A replan returns the freshly persisted plan — update the timeline live.
      if (res.replanned && res.plan) applyPlan(res.plan.blocks, undefined, res.plan.score)
    })
  }

  function updateBlock(id: string, patch: Partial<PlanUIBlock>) {
    setBlocks((cur) => {
      const next = cur.map((b) => (b.id === id ? { ...b, ...patch } : b))
      recompute(next)
      return next
    })
    setSelected(null)
  }

  function moveBlock(id: string, deltaMin: number) {
    setBlocks((cur) => {
      const next = cur
        .map((b) => {
          if (b.id !== id) return b
          const fmt = (m: number) => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
          return { ...b, start: fmt(minutesOf(b.start) + deltaMin), end: fmt(minutesOf(b.end) + deltaMin) }
        })
        .sort((a, b) => a.start.localeCompare(b.start))
      return next
    })
    setSelected(null)
  }

  return (
    <div className="dp-plan">
      <div className="dp-plan__main">
        <header className="dp-plan__head">
          <div>
            <h3 className="dp-plan__title">Today's optimized plan</h3>
            <p className="dp-plan__sub">Multi-agent planner · deep work protected · meetings batched</p>
          </div>
          <div className="dp-plan__head-right">
            <span className="dp-plan__score" title="Critic score">✦ {score}/100</span>
            <span className="dp-plan__focus">{focusMinutes} min focus</span>
            <button className="dp-plan__replan" disabled={busy} onClick={() => (DEMO ? replan('one-tap replan') : replanRemote())}>
              {busy ? '…' : '↻ Replan'}
            </button>
          </div>
        </header>

        {!DEMO && loaded && blocks.length === 0 && (
          <div className="dp-plan__empty">
            <p>No plan yet for today. Generate an optimized plan from your open tasks.</p>
            <button className="dp-plan__replan" disabled={busy} onClick={() => replanRemote()}>{busy ? 'Planning…' : '✦ Generate plan'}</button>
          </div>
        )}

        <div className="dp-plan__timeline">
          {blocks.map((b) => (
            <div key={b.id} className="dp-plan__row">
              <span className="dp-plan__time">{b.start}</span>
              <button
                type="button"
                className={`dp-plan__block dp-plan__block--${b.kind}${b.status === 'done' ? ' is-done' : ''}${selected === b.id ? ' is-selected' : ''}`}
                onClick={() => setSelected(selected === b.id ? null : b.id)}
                aria-expanded={selected === b.id}
              >
                <span className="dp-plan__block-title">{b.title}</span>
                <span className="dp-plan__block-meta">{KIND_LABEL[b.kind]} · {b.start}–{b.end}</span>
              </button>
              {selected === b.id && b.kind !== 'break' && (
                <div className="dp-plan__popover" role="menu">
                  <button role="menuitem" onClick={() => { onStartFocus?.(); setSelected(null) }}>▶ Start focus</button>
                  <button role="menuitem" onClick={() => updateBlock(b.id, { status: 'done' })}>✓ Mark done</button>
                  <button role="menuitem" onClick={() => moveBlock(b.id, 30)}>↓ Move +30 min</button>
                  <button role="menuitem" onClick={() => moveBlock(b.id, -30)}>↑ Move −30 min</button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <aside className="dp-plan__chat" aria-label="Chat with your day plan">
        <header className="dp-plan__chat-head"><span aria-hidden="true">✦</span> Chat with your plan</header>
        <div className="dp-plan__chat-log" ref={logRef}>
          {turns.map((t, i) => (
            <div key={i} className={'dp-home-ai__turn dp-home-ai__turn--' + t.role}>
              <div className="dp-home-ai__bubble"><p style={{ margin: 0 }}>{t.body}</p></div>
            </div>
          ))}
        </div>
        <div className="dp-plan__chips">
          {PLAN_SUGGESTIONS.map((s) => (
            <button key={s} className="dp-home-ai__chip" onClick={() => send(s)}>{s}</button>
          ))}
        </div>
        <form className="dp-home-ai__input dp-plan__input" onSubmit={(e) => { e.preventDefault(); send(input) }}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask or replan — e.g. move admin to the afternoon"
            aria-label="Chat with your day plan"
          />
          <button className="dp-home-ai__send" type="submit" aria-label="Send" disabled={!input.trim()}>➤</button>
        </form>
      </aside>
    </div>
  )
}
