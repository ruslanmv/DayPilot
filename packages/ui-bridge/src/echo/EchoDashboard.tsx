/**
 * Echo Show display mode (`/echo`).
 *
 * A landscape, touch-first dashboard for a 21-inch Amazon Echo Show running
 * the Silk browser: Today, Calendar, Tasks, Projects, the Assistant, Agents and
 * Approvals, read from the same API, session and permissions as the desktop
 * shell. It is additive — the desktop and mobile shells do not import it.
 *
 * Rules this screen keeps:
 *   * real data only — every number comes from a response; a value the server
 *     did not send is shown as "—", never filled in;
 *   * the last good data stays visible through an outage, labelled with its
 *     age, and every failure says what happened and offers Retry;
 *   * approvals are decided by the server (RBAC, audit). The Echo asks for a
 *     second tap before sending a decision and pauses decisions while offline;
 *   * no voice, background or kiosk APIs. Voice on Echo belongs to a future
 *     Alexa skill (docs/echo-show/alexa-skill-plan.md).
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react'
import type { DayPilotProject, DayPilotTask } from '@daypilot/shared-types'

import type { AuthUser } from '../authClient'
import { apiBase, isDemoMode } from '../env'
import type { ApprovalRow } from '../approvals/approvalsQueue'
import { portraitUrl } from '../agents/portraitUrl'
import { blockTag, timeRange, toPriority, type PlanBlockDTO, type TodayTask } from '../home/homeDay'
import { relativeTime, syncLabel } from '../settings/calendarClient'
import type { AgentProfile } from '../settings/homepilotClient'
import {
  ECHO_SECTIONS,
  clockText,
  echoHash,
  eventTime,
  eventsOnDay,
  failureText,
  greeting,
  groupTasks,
  msToNextMinute,
  needsAttention,
  parseEchoHash,
  rankProjects,
  splitRuns,
  updatedLabel,
  upcomingDays,
  type AgentRunDTO,
  type EchoEvent,
  type EchoFailure,
  type EchoSection,
} from './echoModel'
import { useEchoData, type EchoData, type EchoSlots, type Slot, type SlotKey } from './echoData'

type Refresh = (keys: SlotKey[]) => Promise<void>
type SlotOf<K extends SlotKey> = Slot<EchoSlots[K]>

// ---------------------------------------------------------------- hooks

function useSection(): [EchoSection, (s: EchoSection) => void] {
  const [section, setSection] = useState<EchoSection>(() => parseEchoHash(window.location.hash))
  useEffect(() => {
    const onHash = () => setSection(parseEchoHash(window.location.hash))
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  const go = useCallback((s: EchoSection) => {
    if (window.location.hash !== echoHash(s)) window.location.hash = echoHash(s)
    else setSection(s)
  }, [])
  return [section, go]
}

/** The time, re-rendered once a minute on the minute — not every second. */
function useMinute(): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    let t: ReturnType<typeof setTimeout>
    const tick = () => {
      setNow(new Date())
      t = setTimeout(tick, msToNextMinute(new Date()))
    }
    t = setTimeout(tick, msToNextMinute(new Date()))
    // A tab that slept (screen off) catches up as soon as it is visible again.
    const onVisible = () => { if (!document.hidden) setNow(new Date()) }
    document.addEventListener('visibilitychange', onVisible)
    return () => { clearTimeout(t); document.removeEventListener('visibilitychange', onVisible) }
  }, [])
  return now
}

function useFullscreen(): { supported: boolean; active: boolean; toggle: () => void } {
  const supported = typeof document !== 'undefined' && !!document.fullscreenEnabled && !!document.documentElement.requestFullscreen
  const [active, setActive] = useState(() => typeof document !== 'undefined' && !!document.fullscreenElement)
  useEffect(() => {
    const on = () => setActive(!!document.fullscreenElement)
    document.addEventListener('fullscreenchange', on)
    return () => document.removeEventListener('fullscreenchange', on)
  }, [])
  const toggle = useCallback(() => {
    // Best effort only: Silk may refuse or exit on any interruption.
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => {})
    else void document.documentElement.requestFullscreen().catch(() => {})
  }, [])
  return { supported, active, toggle }
}

// ---------------------------------------------------------------- icons

const ICONS: Record<string, React.ReactNode> = {
  today: <><circle cx="12" cy="12" r="4" /><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4" /></>,
  calendar: <><rect x="3.5" y="5" width="17" height="15.5" rx="3" /><path d="M3.5 10h17M8 3v4M16 3v4" /></>,
  tasks: <><rect x="3.5" y="3.5" width="17" height="17" rx="4" /><path d="m8 12.2 2.8 2.8L16.2 9.5" /></>,
  projects: <><path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2.5h7a2 2 0 0 1 2 2v8.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2Z" /></>,
  assistant: <><path d="M12 3.5c.6 3.9 2.6 5.9 6.5 6.5-3.9.6-5.9 2.6-6.5 6.5-.6-3.9-2.6-5.9-6.5-6.5 3.9-.6 5.9-2.6 6.5-6.5Z" /><path d="M18.5 15.5c.25 1.6 1.1 2.45 2.5 2.5-1.4.25-2.25 1.1-2.5 2.5-.25-1.4-1.1-2.25-2.5-2.5 1.4-.05 2.25-.9 2.5-2.5Z" /></>,
  agents: <><rect x="4.5" y="7.5" width="15" height="11.5" rx="3.5" /><path d="M12 4v3.5M9.2 12.5h.01M14.8 12.5h.01M9.5 16h5" /></>,
  approvals: <><path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.2 7.5 9.5 4.3-1.3 7.5-4.9 7.5-9.5V6Z" /><path d="m8.8 12 2.3 2.3 4.2-4.6" /></>,
  refresh: <><path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3" /><path d="M19.5 4.5v4h-4" /></>,
  expand: <><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" /></>,
  shrink: <><path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5" /></>,
  signout: <><path d="M14 4.5h3.5a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H14" /><path d="M10.5 16.5 6 12l4.5-4.5M6 12h9.5" /></>,
  send: <><path d="M12 19V5M5.5 11.5 12 5l6.5 6.5" /></>,
  offline: <><path d="M3 3l18 18" /><path d="M8.5 16.5a5 5 0 0 1 7 0M5 12.9a10 10 0 0 1 4-2.4M14.8 10.3A10 10 0 0 1 19 12.9M1.8 9.3a14.5 14.5 0 0 1 4.5-2.9M12 19.5h.01" /></>,
  lock: <><rect x="4.5" y="10.5" width="15" height="10" rx="2.5" /><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" /></>,
}

function Icon({ name, className }: { name: string; className?: string }) {
  return (
    <svg className={'echo-icon' + (className ? ` ${className}` : '')} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {ICONS[name]}
    </svg>
  )
}

// ---------------------------------------------------------------- shared pieces

function Card({ title, aside, className, children, labelId }: {
  title: string
  aside?: React.ReactNode
  className?: string
  children: React.ReactNode
  labelId?: string
}) {
  const id = labelId || `echo-card-${title.toLowerCase().replace(/[^a-z]+/g, '-')}`
  return (
    <section className={'echo-card' + (className ? ` ${className}` : '')} aria-labelledby={id}>
      <header className="echo-card__head">
        <h2 id={id} className="echo-card__title">{title}</h2>
        {aside}
      </header>
      {children}
    </section>
  )
}

function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="echo-skeleton" role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => <span key={i} className="echo-skeleton__row" />)}
    </div>
  )
}

function Problem({ failure, onRetry }: { failure: EchoFailure; onRetry?: () => void }) {
  return (
    <div className="echo-problem" role="alert">
      <p>{failureText(failure)}</p>
      {onRetry && failure.kind !== 'auth' && (
        <button type="button" className="echo-btn echo-btn--ghost" onClick={onRetry}>Retry</button>
      )}
    </div>
  )
}

function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="echo-empty">
      <p className="echo-empty__title">{title}</p>
      {hint && <p className="echo-empty__hint">{hint}</p>}
    </div>
  )
}

/** "Showing data from 10:42" when the latest refresh of this section failed. */
function Stale({ slot }: { slot: Slot<unknown> }) {
  if (!slot.failure || slot.data === null) return null
  return <span className="echo-chip echo-chip--warn" title={failureText(slot.failure)}>Not current</span>
}

/**
 * Loading / failed-with-nothing-to-show / content. Content renders whenever
 * there is data, even if the last refresh failed (the card is marked stale).
 */
function SlotBody<T>({ slot, rows, onRetry, children }: {
  slot: Slot<T>
  rows?: number
  onRetry: () => void
  children: (data: T) => React.ReactNode
}) {
  if (slot.data !== null) return <>{children(slot.data)}</>
  if (slot.failure) return <Problem failure={slot.failure} onRetry={onRetry} />
  return <Skeleton rows={rows} />
}

function StatTile({ label, value, sub, tone, onClick }: {
  label: string
  value: number | null | undefined
  sub?: string
  tone: 'amber' | 'red' | 'blue' | 'violet'
  onClick: () => void
}) {
  const known = typeof value === 'number'
  return (
    <button type="button" className={`echo-stat echo-stat--${tone}` + (known && value! > 0 ? ' is-active' : '')} onClick={onClick}
      aria-label={known ? `${label}: ${value}${sub ? ` ${sub}` : ''}` : `${label}: not available`}>
      <span className="echo-stat__value">{known ? value : '—'}</span>
      <span className="echo-stat__label">{label}</span>
      {known && sub && <span className="echo-stat__sub">{sub}</span>}
    </button>
  )
}

const OWNER_LABEL: Record<string, string> = { you: 'You', ai: 'AI', team: 'Team', system: 'System' }

function TaskRow({ task }: { task: DayPilotTask }) {
  const range = timeRange(task.start, task.end)
  return (
    <li className={'echo-row echo-row--task is-' + task.priority}>
      <span className="echo-row__dot" aria-hidden="true" />
      <span className="echo-row__main">
        <span className="echo-row__title">{task.title}</span>
        <span className="echo-row__meta">
          {range && <span>{range}</span>}
          <span>{OWNER_LABEL[task.owner] || task.owner}{task.executor && task.owner !== 'you' ? ` · ${task.executor}` : ''}</span>
          {(task.priority === 'critical' || task.priority === 'high') && <span className="echo-row__prio">{task.priority}</span>}
        </span>
      </span>
    </li>
  )
}

// ---------------------------------------------------------------- Today

function projectNames(projects: DayPilotProject[] | undefined): Record<string, string> {
  const names: Record<string, string> = {}
  for (const p of projects || []) names[p.id] = p.name
  return names
}

function blockIsNow(b: PlanBlockDTO, now: Date): boolean {
  if (!b.start || !b.end) return false
  const hm = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
  return b.start <= hm && hm < b.end
}

function PlanList({ blocks, now, limit }: { blocks: PlanBlockDTO[]; now: Date; limit?: number }) {
  const shown = limit ? blocks.slice(0, limit) : blocks
  return (
    <ol className="echo-list echo-plan">
      {shown.map((b) => {
        const done = (b.status || '').toLowerCase() === 'done'
        const current = !done && blockIsNow(b, now)
        return (
          <li key={b.id} className={'echo-plan__item' + (done ? ' is-done' : '') + (current ? ' is-now' : '')}>
            <span className="echo-plan__time">{(b.start || '').trim() || '—'}</span>
            <span className="echo-plan__title">{b.title}</span>
            <span className="echo-chip">{current ? 'Now' : blockTag(b)}</span>
          </li>
        )
      })}
    </ol>
  )
}

function EventList({ events, limit }: { events: EchoEvent[]; limit?: number }) {
  const shown = limit ? events.slice(0, limit) : events
  return (
    <ol className="echo-list">
      {shown.map((e) => (
        <li key={e.id} className={'echo-event' + (e.isPast ? ' is-past' : '') + (e.isNow ? ' is-now' : '')}>
          <span className="echo-event__time">{eventTime(e)}</span>
          <span className="echo-event__body">
            <span className="echo-event__title">{e.title}</span>
            {(e.isNow || e.conflict || e.tentative) && (
              <span className="echo-event__tags">
                {e.isNow && <span className="echo-chip echo-chip--live">Now</span>}
                {e.conflict && <span className="echo-chip echo-chip--danger">Overlaps</span>}
                {e.tentative && <span className="echo-chip">Tentative</span>}
              </span>
            )}
          </span>
        </li>
      ))}
    </ol>
  )
}

const TodayView = React.memo(function TodayView({ today, plan, projects, calendar, now, go, refresh }: {
  today: SlotOf<'today'>
  plan: SlotOf<'plan'>
  projects: SlotOf<'projects'>
  calendar: SlotOf<'calendar'>
  now: Date
  go: (s: EchoSection) => void
  refresh: Refresh
}) {
  const names = projectNames(projects.data?.items)
  const blocks = plan.data?.blocks || []
  const priority = today.data ? toPriority(today.data.now, blocks, names) : null
  const next: TodayTask | null = today.data?.next || null
  const counts = today.data?.counts
  const todaysEvents = calendar.data ? eventsOnDay(calendar.data.events, now, now, calendar.data.conflicts).filter((e) => !e.isPast) : []
  const retry = (keys: SlotKey[]) => () => { void refresh(keys) }

  return (
    <div className="echo-grid echo-grid--today">
      <Card title="Now" className="echo-card--now" aside={<Stale slot={today} />}>
        <SlotBody slot={today} rows={3} onRetry={retry(['today', 'plan'])}>
          {() => (
            <>
              {priority ? (
                <div className="echo-now">
                  <p className="echo-now__title">{priority.title}</p>
                  {(priority.project || priority.time) && (
                    <p className="echo-now__meta">{[priority.project, priority.time].filter(Boolean).join(' · ')}</p>
                  )}
                  {priority.support && <p className="echo-now__support">{priority.support}</p>}
                </div>
              ) : (
                <Empty title="Nothing in progress" hint="Start a task in DayPilot and it shows here." />
              )}
              <div className="echo-now__next">
                <span className="echo-label">Next</span>
                <span className="echo-now__next-title">{next ? next.title : 'Nothing else queued'}</span>
                {next && timeRange(next.start, next.end) && <span className="echo-now__next-time">{timeRange(next.start, next.end)}</span>}
              </div>
            </>
          )}
        </SlotBody>
      </Card>

      <div className="echo-stats" role="group" aria-label="At a glance">
        <StatTile label="Approvals waiting" value={counts?.approvals} tone="amber" onClick={() => go('approvals')} />
        <StatTile label="Blocked tasks" value={counts?.blockers} tone="red" onClick={() => go('tasks')} />
        <StatTile label="AI runs active" value={counts?.aiRunning} tone="blue" onClick={() => go('agents')} />
        <StatTile label="Projects need attention" value={counts?.projectsNeedAttention}
          sub={counts ? `of ${counts.projectsActive}` : undefined} tone="violet" onClick={() => go('projects')} />
      </div>

      <Card title="Today's plan" className="echo-card--plan" aside={<Stale slot={plan} />}>
        <SlotBody slot={plan} rows={4} onRetry={retry(['plan'])}>
          {(p) => p.blocks.length
            ? <div className="echo-scroll"><PlanList blocks={p.blocks} now={now} /></div>
            : <Empty title={p.planned ? 'The plan for today is empty' : 'No plan for today yet'}
                hint="Plan the day in DayPilot on a computer or phone." />}
        </SlotBody>
      </Card>

      <Card title="Coming up" className="echo-card--upcoming"
        aside={<button type="button" className="echo-link" onClick={() => go('calendar')}>Calendar</button>}>
        <SlotBody slot={calendar} rows={3} onRetry={retry(['calendar'])}>
          {(c) => todaysEvents.length
            ? <div className="echo-scroll"><EventList events={todaysEvents} limit={6} /></div>
            : <Empty title="Nothing else on the calendar today"
                hint={c.status && !c.status.connected ? 'No calendar is connected.' : undefined} />}
        </SlotBody>
      </Card>
    </div>
  )
})

// ---------------------------------------------------------------- Calendar

const CalendarView = React.memo(function CalendarView({ slot, now, refresh }: { slot: SlotOf<'calendar'>; now: Date; refresh: Refresh }) {
  const status = slot.data?.status || null
  const chip = slot.data
    ? <span className={'echo-chip' + (status?.freshness === 'stale' ? ' echo-chip--warn' : '')}>{syncLabel(status, now)}</span>
    : null
  const days = new Intl.DateTimeFormat(undefined, { weekday: 'long', day: 'numeric', month: 'short' })
  return (
    <div className="echo-grid echo-grid--two">
      <Card title="Today" aside={<>{chip}<Stale slot={slot} /></>}>
        <SlotBody slot={slot} rows={5} onRetry={() => { void refresh(['calendar']) }}>
          {(c) => {
            const list = eventsOnDay(c.events, now, now, c.conflicts)
            return list.length
              ? <div className="echo-scroll"><EventList events={list} /></div>
              : <Empty title="No events today"
                  hint={c.status && !c.status.connected ? 'Connect a calendar in DayPilot → Settings → Calendar.' : undefined} />
          }}
        </SlotBody>
      </Card>
      <Card title="Next days">
        <SlotBody slot={slot} rows={5} onRetry={() => { void refresh(['calendar']) }}>
          {(c) => {
            const groups = upcomingDays(c.events, now)
            return groups.length ? (
              <div className="echo-scroll">
                {groups.map((g) => (
                  <div key={g.day.toISOString()} className="echo-day">
                    <h3 className="echo-day__title">{days.format(g.day)}</h3>
                    <EventList events={g.events} />
                  </div>
                ))}
              </div>
            ) : <Empty title="Nothing scheduled in the next six days" />
          }}
        </SlotBody>
      </Card>
    </div>
  )
})

// ---------------------------------------------------------------- Tasks

const TasksView = React.memo(function TasksView({ slot, now, refresh }: { slot: SlotOf<'tasks'>; now: Date; refresh: Refresh }) {
  const retry = () => { void refresh(['tasks']) }
  if (slot.data === null) {
    return <Card title="Tasks"><SlotBody slot={slot} rows={6} onRetry={retry}>{() => null}</SlotBody></Card>
  }
  const g = groupTasks(slot.data.items, now)
  const needsYou = [...g.blocked, ...g.needsApproval]
  const column = (title: string, list: DayPilotTask[], empty: string, extra?: React.ReactNode) => (
    <Card title={title} aside={<span className="echo-count">{list.length}</span>}>
      {extra}
      {list.length
        ? <div className="echo-scroll"><ul className="echo-list">{list.map((t) => <TaskRow key={t.id} task={t} />)}</ul></div>
        : <Empty title={empty} />}
    </Card>
  )
  return (
    <div className="echo-tasks">
      <div className="echo-tasks__bar">
        <span>{g.open} open {g.open === 1 ? 'task' : 'tasks'}</span>
        {slot.data.more && <span className="echo-muted">Showing the newest 200 tasks</span>}
        <Stale slot={slot} />
      </div>
      <div className="echo-grid echo-grid--four">
        {column('Needs you', needsYou, 'Nothing blocked or waiting on you',
          g.blocked.length ? <p className="echo-note echo-note--danger">{g.blocked.length} blocked</p> : null)}
        {column('In progress', g.inProgress, 'Nothing running right now')}
        {column('Today', g.today, 'Nothing else scheduled today')}
        {column('Later', g.later, 'Nothing later this week')}
      </div>
    </div>
  )
})

// ---------------------------------------------------------------- Projects

const RISK_LABEL: Record<string, string> = { high: 'High risk', medium: 'Medium risk', low: 'On track' }

const ProjectsView = React.memo(function ProjectsView({ slot, refresh }: { slot: SlotOf<'projects'>; refresh: Refresh }) {
  return (
    <Card title="Projects" className="echo-card--fill" aside={<Stale slot={slot} />}>
      <SlotBody slot={slot} rows={6} onRetry={() => { void refresh(['projects']) }}>
        {(p) => p.items.length ? (
          <div className="echo-scroll">
            <ul className="echo-projects">
              {rankProjects(p.items).map((pr) => {
                const pct = Math.max(0, Math.min(100, Math.round(pr.progress || 0)))
                return (
                  <li key={pr.id} className={'echo-project is-' + (pr.risk || 'low')}>
                    <div className="echo-project__head">
                      <span className="echo-project__name">{pr.name}</span>
                      <span className={'echo-chip' + (needsAttention(pr) ? ' echo-chip--warn' : ' echo-chip--ok')}>{RISK_LABEL[pr.risk] || pr.risk}</span>
                    </div>
                    <div className="echo-progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}
                      aria-label={`${pr.name} progress`}>
                      <span style={{ width: `${pct}%` }} />
                    </div>
                    <p className="echo-project__meta">{pct}% · {pr.status}</p>
                    {pr.blocked[0] && <p className="echo-project__line echo-project__line--danger">Blocked: {pr.blocked[0]}</p>}
                    {pr.nextHumanAction && <p className="echo-project__line">Next: {pr.nextHumanAction}</p>}
                    {pr.aiActivity && <p className="echo-project__line echo-muted">AI: {pr.aiActivity}</p>}
                  </li>
                )
              })}
            </ul>
            {p.more && <p className="echo-muted echo-foot">Showing the first 100 projects.</p>}
          </div>
        ) : <Empty title="No projects yet" hint="Create a project in DayPilot and it appears here." />}
      </SlotBody>
    </Card>
  )
})

// ---------------------------------------------------------------- Assistant

export type EchoMessage = { id: number; role: 'user' | 'assistant' | 'error'; text: string; open?: EchoSection }

const SUGGESTIONS = ["What's next today?", 'What needs my approval?', 'Which projects are at risk?', 'Summarize my day']

const ASSISTANT_STATE: Record<string, { label: string; tone: string }> = {
  ready: { label: 'Ready', tone: 'ok' },
  limited: { label: 'Limited mode — no AI provider connected', tone: 'warn' },
  down: { label: 'Unavailable', tone: 'danger' },
}

function actionSection(action: { kind: string; target?: string } | null | undefined): EchoSection | undefined {
  if (!action) return undefined
  if (action.kind === 'openApprovals') return 'approvals'
  if (action.kind === 'navigate' && (action.target === 'projects' || action.target === 'calendar' || action.target === 'agents')) {
    return action.target
  }
  return undefined
}

function AssistantView({ slot, online, ask, refresh, messages, setMessages, go }: {
  slot: SlotOf<'assistant'>
  online: boolean
  ask: EchoData['ask']
  refresh: Refresh
  messages: EchoMessage[]
  setMessages: React.Dispatch<React.SetStateAction<EchoMessage[]>>
  go: (s: EchoSection) => void
}) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const availability = slot.data
  const canAsk = !busy && online && availability !== 'down' && availability !== null
  const listRef = React.useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = listRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, busy])

  async function send(raw: string) {
    const q = raw.trim()
    if (!q || !canAsk) return
    setText('')
    setBusy(true)
    // Bounded history: a display left on for days must not grow without limit.
    setMessages((m) => [...m, { id: Date.now(), role: 'user' as const, text: q }].slice(-20))
    const r = await ask(q)
    setBusy(false)
    setMessages((m) => [...m, r.ok
      ? { id: Date.now() + 1, role: 'assistant' as const, text: r.data.reply, open: actionSection(r.data.action) }
      : { id: Date.now() + 1, role: 'error' as const, text: failureText(r.failure) }].slice(-20))
  }

  const state = availability ? ASSISTANT_STATE[availability] : null
  return (
    <section className="echo-assistant" aria-labelledby="echo-assistant-title">
      <header className="echo-assistant__head">
        <h2 id="echo-assistant-title" className="echo-card__title">Assistant</h2>
        {state && <span className={`echo-chip echo-chip--${state.tone}`}>{state.label}</span>}
        {!state && slot.failure && <span className="echo-chip echo-chip--danger">{failureText(slot.failure)}</span>}
        {messages.length > 0 && (
          <button type="button" className="echo-link" onClick={() => setMessages([])}>Clear</button>
        )}
      </header>

      <div className="echo-assistant__log" ref={listRef} aria-live="polite">
        {messages.length === 0 ? (
          <div className="echo-assistant__hello">
            <p className="echo-assistant__prompt">What can I help with?</p>
            <div className="echo-suggest">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" className="echo-btn echo-btn--ghost" disabled={!canAsk} onClick={() => { void send(s) }}>{s}</button>
              ))}
            </div>
          </div>
        ) : messages.map((m) => (
          <div key={m.id} className={`echo-msg echo-msg--${m.role}`}>
            <p>{m.text}</p>
            {m.open && (
              <button type="button" className="echo-btn echo-btn--ghost" onClick={() => go(m.open!)}>
                Open {ECHO_SECTIONS.find((s) => s.id === m.open)?.label}
              </button>
            )}
          </div>
        ))}
        {busy && <div className="echo-msg echo-msg--assistant echo-msg--busy" role="status">Thinking…</div>}
      </div>

      <form className="echo-composer" onSubmit={(e) => { e.preventDefault(); void send(text) }}>
        <input className="echo-composer__input" value={text} onChange={(e) => setText(e.target.value)}
          placeholder={availability === 'down' ? 'The assistant is unavailable' : 'Ask DayPilot…'}
          aria-label="Message the DayPilot assistant" disabled={!canAsk && !busy} maxLength={2000}
          enterKeyHint="send" autoComplete="off" />
        <button type="submit" className="echo-composer__send" disabled={!canAsk || !text.trim()} aria-label="Send">
          <Icon name="send" />
        </button>
      </form>
      {availability === 'down' && (
        <p className="echo-muted echo-foot">
          The assistant needs the DayPilot server. <button type="button" className="echo-link" onClick={() => { void refresh(['assistant']) }}>Check again</button>
        </p>
      )}
    </section>
  )
}

// ---------------------------------------------------------------- Agents

const STATUS_LABEL: Record<string, string> = {
  available: 'Available', working: 'Working', busy: 'Busy', needs_approval: 'Needs approval', offline: 'Offline', disabled: 'Disabled',
}

function RunRow({ run }: { run: AgentRunDTO }) {
  return (
    <li className={'echo-row echo-row--run is-' + (run.state || 'unknown') + (/approval/i.test(run.status || '') ? ' is-approval' : '')}>
      <span className="echo-row__dot" aria-hidden="true" />
      <span className="echo-row__main">
        <span className="echo-row__title">{run.name}</span>
        <span className="echo-row__meta">
          {run.currentWork && <span>{run.currentWork}</span>}
          <span>{run.status || run.state}</span>
          {run.updatedAt && <span>{relativeTime(run.updatedAt)}</span>}
        </span>
        {run.lastError && (run.state || '') === 'failed' && <span className="echo-row__error">{run.lastError}</span>}
      </span>
    </li>
  )
}

function AgentTile({ agent }: { agent: AgentProfile }) {
  const [broken, setBroken] = useState(false)
  const src = portraitUrl(agent.avatarUrl, apiBase())
  return (
    <li className={'echo-agent is-' + agent.status}>
      {src && !broken
        ? <img className="echo-agent__avatar" src={src} alt="" width={56} height={56} loading="lazy" decoding="async" onError={() => setBroken(true)} />
        : <span className="echo-agent__avatar echo-agent__avatar--initial" aria-hidden="true">{agent.name.slice(0, 1)}</span>}
      <span className="echo-agent__body">
        <span className="echo-agent__name">{agent.name}</span>
        <span className="echo-agent__role">{agent.role}</span>
      </span>
      <span className={'echo-chip' + (agent.status === 'needs_approval' ? ' echo-chip--warn' : agent.status === 'working' || agent.status === 'busy' ? ' echo-chip--live' : '')}>
        {STATUS_LABEL[agent.status] || agent.status}
      </span>
    </li>
  )
}

const AgentsView = React.memo(function AgentsView({ slot, refresh }: { slot: SlotOf<'agents'>; refresh: Refresh }) {
  const retry = () => { void refresh(['agents']) }
  return (
    <div className="echo-grid echo-grid--two">
      <Card title="Agent runs" aside={<Stale slot={slot} />}>
        <SlotBody slot={slot} rows={5} onRetry={retry}>
          {(a) => {
            if (a.runsFailure) return <Problem failure={a.runsFailure} onRetry={retry} />
            const { running, attention, recent } = splitRuns(a.runs)
            if (!a.runs.length) return <Empty title="No agent runs yet" />
            return (
              <div className="echo-scroll">
                {running.length > 0 && <><h3 className="echo-day__title">Running · {running.length}</h3><ul className="echo-list">{running.map((r) => <RunRow key={r.id} run={r} />)}</ul></>}
                {attention.length > 0 && <><h3 className="echo-day__title">Need attention · {attention.length}</h3><ul className="echo-list">{attention.map((r) => <RunRow key={r.id} run={r} />)}</ul></>}
                {recent.length > 0 && <><h3 className="echo-day__title">Recent</h3><ul className="echo-list">{recent.slice(0, 10).map((r) => <RunRow key={r.id} run={r} />)}</ul></>}
              </div>
            )
          }}
        </SlotBody>
      </Card>
      <Card title="Agents">
        <SlotBody slot={slot} rows={5} onRetry={retry}>
          {(a) => a.profiles === null
            ? <Empty title="HomePilot agents are not enabled on this server" hint="An administrator can turn on the HomePilot runtime in DayPilot settings." />
            : a.profiles.length
              ? <div className="echo-scroll"><ul className="echo-agents">{a.profiles.filter((p) => p.enabled).map((p) => <AgentTile key={p.id} agent={p} />)}</ul></div>
              : <Empty title="No agents added yet" />}
        </SlotBody>
      </Card>
    </div>
  )
})

// ---------------------------------------------------------------- Approvals

const RISK_TEXT: Record<string, string> = { high: 'High risk', medium: 'Medium risk', low: 'Low risk' }

function ApprovalCard({ row, online, decide }: {
  row: ApprovalRow
  online: boolean
  decide: EchoData['decide']
}) {
  const [confirm, setConfirm] = useState<'approve' | 'reject' | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<EchoFailure | null>(null)

  async function send(decision: 'approve' | 'reject') {
    setBusy(true)
    setError(null)
    const r = await decide(row.id, decision)
    setBusy(false)
    setConfirm(null)
    if (!r.ok) setError(r.failure)
  }

  return (
    <li className={'echo-approval is-' + row.risk}>
      <div className="echo-approval__head">
        <span className={'echo-chip echo-chip--risk-' + row.risk}>{RISK_TEXT[row.risk]}</span>
        {row.resourceType && <span className="echo-chip">{row.resourceType.replace(/[_-]+/g, ' ')}</span>}
        {row.createdAt && <span className="echo-muted">{relativeTime(row.createdAt)}</span>}
      </div>
      <p className="echo-approval__action">{row.action}</p>
      {row.summary && <p className="echo-approval__summary">{row.summary}</p>}
      {error && <p className="echo-note echo-note--danger" role="alert">{failureText(error)}</p>}
      <div className="echo-approval__actions">
        {!online ? (
          <p className="echo-muted">Decisions need a live connection.</p>
        ) : confirm ? (
          <>
            <span className="echo-approval__confirm">{confirm === 'approve' ? 'Approve this request?' : 'Reject this request?'}</span>
            <button type="button" className={'echo-btn ' + (confirm === 'approve' ? 'echo-btn--primary' : 'echo-btn--danger')}
              disabled={busy} onClick={() => { void send(confirm) }}>
              {busy ? 'Sending…' : confirm === 'approve' ? 'Yes, approve' : 'Yes, reject'}
            </button>
            <button type="button" className="echo-btn echo-btn--ghost" disabled={busy} onClick={() => setConfirm(null)}>Cancel</button>
          </>
        ) : (
          <>
            <button type="button" className="echo-btn echo-btn--primary" onClick={() => setConfirm('approve')}
              aria-label={`Approve: ${row.action}`}>Approve</button>
            <button type="button" className="echo-btn echo-btn--ghost" onClick={() => setConfirm('reject')}
              aria-label={`Reject: ${row.action}`}>Reject</button>
          </>
        )}
      </div>
    </li>
  )
}

const ApprovalsView = React.memo(function ApprovalsView({ slot, online, decide, refresh }: {
  slot: SlotOf<'approvals'>
  online: boolean
  decide: EchoData['decide']
  refresh: Refresh
}) {
  return (
    <div className="echo-grid echo-grid--approvals">
      <Card title="Waiting for a decision" aside={<Stale slot={slot} />}>
        <SlotBody slot={slot} rows={4} onRetry={() => { void refresh(['approvals']) }}>
          {(a) => {
            const pending = a.items.filter((r) => r.status === 'pending')
            return pending.length ? (
              <div className="echo-scroll">
                <ul className="echo-approvals">
                  {pending.map((r) => <ApprovalCard key={r.id} row={r} online={online && !slot.failure} decide={decide} />)}
                </ul>
                {a.more && <p className="echo-muted echo-foot">Showing the newest 50 approvals. Open DayPilot on a computer for the full queue.</p>}
              </div>
            ) : <Empty title="Nothing waiting for you" hint="Requests from agents and integrations appear here." />
          }}
        </SlotBody>
      </Card>
      <Card title="Recently decided">
        <SlotBody slot={slot} rows={3} onRetry={() => { void refresh(['approvals']) }}>
          {(a) => {
            const done = a.items.filter((r) => r.status !== 'pending').slice(0, 8)
            return done.length ? (
              <div className="echo-scroll">
                <ul className="echo-list">
                  {done.map((r) => (
                    <li key={r.id} className="echo-row">
                      <span className="echo-row__main">
                        <span className="echo-row__title">{r.action}</span>
                        <span className="echo-row__meta">
                          <span className={r.status === 'approved' ? 'echo-ok' : 'echo-danger'}>{r.status === 'approved' ? 'Approved' : 'Rejected'}</span>
                          {r.decidedAt && <span>{relativeTime(r.decidedAt)}</span>}
                        </span>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : <Empty title="No decisions yet" />
          }}
        </SlotBody>
      </Card>
    </div>
  )
})

// ---------------------------------------------------------------- frame

function Header({ data, user, now, fullscreen }: {
  data: EchoData
  user: AuthUser | null
  now: Date
  fullscreen: ReturnType<typeof useFullscreen>
}) {
  const clock = clockText(now)
  const status = !data.online ? { text: 'Offline', tone: 'danger' }
    : data.liveFailures > 0 ? { text: 'Reconnecting…', tone: 'warn' }
      : { text: updatedLabel(data.updated.live, now.getTime()), tone: data.updated.live ? 'ok' : 'muted' }
  return (
    <header className="echo-header">
      <div className="echo-header__hello">
        <h1 className="echo-header__greeting">{greeting(now, user?.displayName)}</h1>
        <p className="echo-header__date">{clock.date}</p>
      </div>
      <div className="echo-header__tools">
        <span className={`echo-status echo-status--${status.tone}`} role="status">
          <span className="echo-status__dot" aria-hidden="true" />{status.text}
        </span>
        <button type="button" className={'echo-iconbtn' + (data.refreshing ? ' is-busy' : '')} onClick={data.refreshAll}
          aria-label="Refresh now" disabled={data.sessionEnded}>
          <Icon name="refresh" />
        </button>
        {fullscreen.supported && (
          <button type="button" className="echo-iconbtn" onClick={fullscreen.toggle}
            aria-label={fullscreen.active ? 'Exit full screen' : 'Full screen'}>
            <Icon name={fullscreen.active ? 'shrink' : 'expand'} />
          </button>
        )}
      </div>
      <time className="echo-clock" dateTime={now.toISOString()}>{clock.time}</time>
    </header>
  )
}

function Rail({ section, go, pending, user, onSignOut }: {
  section: EchoSection
  go: (s: EchoSection) => void
  pending: number | null
  user: AuthUser | null
  onSignOut: () => void
}) {
  return (
    <nav className="echo-rail" aria-label="Dashboard sections">
      <span className="echo-rail__logo" aria-label="DayPilot">
        <svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16 3.5 28.5 28 16 22.2 3.5 28Z" fill="currentColor" opacity=".45" /><path d="M16 3.5 28.5 28 16 22.2Z" fill="currentColor" /></svg>
      </span>
      <ul className="echo-rail__list">
        {ECHO_SECTIONS.map((s) => (
          <li key={s.id}>
            <button type="button" className={'echo-rail__item' + (section === s.id ? ' is-active' : '')}
              aria-current={section === s.id ? 'page' : undefined} onClick={() => go(s.id)}>
              <Icon name={s.id} />
              <span className="echo-rail__label">{s.label}</span>
              {s.id === 'approvals' && pending !== null && pending > 0 && (
                <span className="echo-rail__badge" aria-label={`${pending} waiting`}>{pending > 99 ? '99+' : pending}</span>
              )}
            </button>
          </li>
        ))}
      </ul>
      {user && (
        <button type="button" className="echo-rail__item echo-rail__signout" onClick={onSignOut}>
          <Icon name="signout" />
          <span className="echo-rail__label">Sign out</span>
        </button>
      )}
    </nav>
  )
}

function Banners({ data }: { data: EchoData }) {
  const insecure = typeof window !== 'undefined' && window.isSecureContext === false
  const misrouted = (Object.values(data.slots) as Slot<unknown>[]).some((s) => s.failure?.kind === 'misrouted')
  const time = data.updated.live
    ? new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' }).format(new Date(data.updated.live))
    : null
  return (
    <>
      {insecure && (
        <div className="echo-banner echo-banner--danger" role="alert">
          <Icon name="lock" />This page is not on a secure connection. Open DayPilot with its https:// address on this device.
        </div>
      )}
      {!data.online && (
        <div className="echo-banner echo-banner--warn" role="status">
          <Icon name="offline" />Offline{time ? ` — showing what was loaded at ${time}` : ''}. Approvals are paused until the connection returns.
        </div>
      )}
      {data.online && misrouted && (
        <div className="echo-banner echo-banner--danger" role="alert">
          The DayPilot API is not reachable from this address. Check that /api points to the DayPilot gateway.
        </div>
      )}
    </>
  )
}

/**
 * `/echo/?about` — what this browser reports, for the on-device checklist
 * (docs/echo-show/README.md). Silk has no developer tools on an Echo Show.
 */
function AboutDisplay() {
  const [size, setSize] = useState(() => `${window.innerWidth}×${window.innerHeight}`)
  useEffect(() => {
    const on = () => setSize(`${window.innerWidth}×${window.innerHeight}`)
    window.addEventListener('resize', on)
    return () => window.removeEventListener('resize', on)
  }, [])
  return (
    <div className="echo-banner echo-banner--info" role="note">
      CSS viewport {size} · pixel ratio {window.devicePixelRatio} · secure {String(window.isSecureContext)} ·
      online {String(navigator.onLine)} · full screen {String(!!document.fullscreenEnabled)} · {navigator.userAgent}
    </div>
  )
}

function SessionEnded({ onSignOut }: { onSignOut: () => void }) {
  return (
    <div className="echo-overlay">
      <div className="echo-overlay__card" role="alertdialog" aria-labelledby="echo-session-title" aria-describedby="echo-session-text">
        <Icon name="lock" className="echo-overlay__icon" />
        <h2 id="echo-session-title">Your session has ended</h2>
        <p id="echo-session-text">Sign in again to keep this display up to date. Nothing on this screen was changed.</p>
        <button type="button" className="echo-btn echo-btn--primary" onClick={onSignOut} autoFocus>Sign in again</button>
      </div>
    </div>
  )
}

function Notice({ title, text }: { title: string; text: string }) {
  return (
    <div className="echo echo--notice">
      <div className="echo-overlay__card">
        <h1>{title}</h1>
        <p>{text}</p>
      </div>
    </div>
  )
}

class EchoErrorBoundary extends React.Component<{ children: React.ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div className="echo echo--notice">
        <div className="echo-overlay__card" role="alert">
          <h1>The dashboard stopped</h1>
          <p>Something unexpected happened while drawing this screen.</p>
          <button type="button" className="echo-btn echo-btn--primary" onClick={() => window.location.reload()}>Reload</button>
        </div>
      </div>
    )
  }
}

function Dashboard({ user, onSignOut }: { user: AuthUser | null; onSignOut: () => void }) {
  const [section, go] = useSection()
  const now = useMinute()
  const data = useEchoData({ checkSession: user !== null })
  const { slots } = data
  const fullscreen = useFullscreen()
  const [messages, setMessages] = useState<EchoMessage[]>([])
  const about = useMemo(() => new URLSearchParams(window.location.search).has('about'), [])
  const counts = data.slots.today.data?.counts
  const pending = counts ? counts.approvals : null

  const title = useMemo(() => ECHO_SECTIONS.find((s) => s.id === section)?.label || 'Today', [section])
  useEffect(() => { document.title = `${title} · DayPilot` }, [title])

  return (
    <div className="echo" data-section={section}>
      <Rail section={section} go={go} pending={pending} user={user} onSignOut={onSignOut} />
      <div className="echo-main">
        <Header data={data} user={user} now={now} fullscreen={fullscreen} />
        <Banners data={data} />
        {about && <AboutDisplay />}
        <main className="echo-view" aria-label={title}>
          {section === 'today' && (
            <TodayView today={slots.today} plan={slots.plan} projects={slots.projects} calendar={slots.calendar}
              now={now} go={go} refresh={data.refresh} />
          )}
          {section === 'calendar' && <CalendarView slot={slots.calendar} now={now} refresh={data.refresh} />}
          {section === 'tasks' && <TasksView slot={slots.tasks} now={now} refresh={data.refresh} />}
          {section === 'projects' && <ProjectsView slot={slots.projects} refresh={data.refresh} />}
          {section === 'assistant' && (
            <AssistantView slot={slots.assistant} online={data.online} ask={data.ask} refresh={data.refresh}
              messages={messages} setMessages={setMessages} go={go} />
          )}
          {section === 'agents' && <AgentsView slot={slots.agents} refresh={data.refresh} />}
          {section === 'approvals' && (
            <ApprovalsView slot={slots.approvals} online={data.online} decide={data.decide} refresh={data.refresh} />
          )}
        </main>
      </div>
      {data.sessionEnded && <SessionEnded onSignOut={onSignOut} />}
    </div>
  )
}

/**
 * The Echo dashboard. Render it inside `AppGate`, which owns sign-in:
 *
 *   <AppGate>{(user, signOut) => <EchoDashboard user={user} onSignOut={signOut} />}</AppGate>
 */
export function EchoDashboard({ user, onSignOut }: { user: AuthUser | null; onSignOut: () => void }) {
  if (isDemoMode()) {
    return <Notice title="The Echo display needs a DayPilot server"
      text="This build runs in demo mode with sample data, which the Echo display does not show. Open /echo on a DayPilot server." />
  }
  return (
    <EchoErrorBoundary>
      <Dashboard user={user} onSignOut={onSignOut} />
    </EchoErrorBoundary>
  )
}
