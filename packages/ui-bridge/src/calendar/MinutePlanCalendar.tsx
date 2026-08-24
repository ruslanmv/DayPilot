import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { DayPilotTask } from '@daypilot/shared-types'
import {
  DAY_END_MIN,
  DAY_START_MIN,
  GRID_HEIGHT,
  PX_PER_MIN,
  SLOT_HEIGHT,
  calendarEvents,
  heightPx,
  layoutColumns,
  minutesOf,
  mondayIndex,
  slotLabels,
  topPx,
  weekDates,
  type CalCategory,
  type CalEvent,
} from './calendarData'
import {
  calendarApi,
  relativeTime,
  syncLabel,
  type CalendarStatus,
} from '../settings/calendarClient'

type Mode = 'day' | 'week'

const CATEGORY_ICON: Record<CalCategory, string> = {
  calendar: '🗓', deep: '🧠', review: '📋', meeting: '👥', personal: '🕑',
}

/** Once-a-minute clock so the current-time indicator advances live. */
function useNow(): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 60_000)
    return () => window.clearInterval(id)
  }, [])
  return now
}

function fmt(min: number): string {
  const hh = String(Math.floor(min / 60)).padStart(2, '0')
  const mm = String(min % 60).padStart(2, '0')
  return `${hh}:${mm}`
}

/** Build a DayPilotTask-shaped object so demo events can open the detail drawer. */
function eventToTask(e: CalEvent): DayPilotTask {
  if (e.task) return e.task
  const owner = e.owner === 'You' ? 'you' : e.owner === 'Team' ? 'team' : e.owner === 'AI' ? 'ai' : 'you'
  return {
    id: e.id, title: e.title,
    day: (['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][e.dayIndex]) as DayPilotTask['day'],
    start: e.start, end: e.end, owner: owner as DayPilotTask['owner'], executor: e.owner || 'You',
    priority: 'medium', status: e.status === 'pending' ? 'needs_approval' : 'scheduled',
    context: `${e.title} · ${e.start}–${e.end}`, source: e.source, risk: 'low',
  }
}

function StatusDot({ status }: { status?: CalEvent['status'] }) {
  if (status === 'confirmed') return <span className="dp-ev__dot dp-ev__dot--ok" aria-hidden="true" />
  if (status === 'pending') return <span className="dp-ev__dot dp-ev__dot--pending" aria-hidden="true" />
  return null
}

// ---- current-time indicator -------------------------------------------------

function nowMinutes(now: Date): number {
  return now.getHours() * 60 + now.getMinutes()
}
function inRange(now: Date): boolean {
  const m = nowMinutes(now)
  return m >= DAY_START_MIN && m <= DAY_END_MIN
}

function DayNow({ now }: { now: Date }) {
  if (!inRange(now)) return null
  const y = (nowMinutes(now) - DAY_START_MIN) * PX_PER_MIN
  const label = `Now ${fmt(nowMinutes(now))}`
  return (
    <div className="dp-now" style={{ top: y }} role="img" aria-label={`Current time ${fmt(nowMinutes(now))}`}>
      <span className="dp-now__label">{label}</span>
      <span className="dp-now__dot" aria-hidden="true" />
      <span className="dp-now__line" aria-hidden="true" />
    </div>
  )
}

// ---- day view ---------------------------------------------------------------

function EventBlock({ e, col, cols, onSelect }: { e: CalEvent; col: number; cols: number; onSelect: (t: DayPilotTask) => void }) {
  const s = minutesOf(e.start)
  const en = minutesOf(e.end)
  const width = 100 / cols
  return (
    <button
      type="button"
      className={`dp-ev dp-ev--${e.category}`}
      style={{ top: topPx(s), height: heightPx(s, en), left: `calc(${col * width}% + 2px)`, width: `calc(${width}% - 4px)` }}
      onClick={() => onSelect(eventToTask(e))}
      aria-label={`${e.title}, ${e.start} to ${e.end}${e.source ? ', ' + e.source : ''}`}
    >
      <span className="dp-ev__bar" aria-hidden="true" />
      <span className="dp-ev__body">
        <span className="dp-ev__title">
          <span className="dp-ev__icon" aria-hidden="true">{CATEGORY_ICON[e.category]}</span>
          {e.title}
        </span>
        <span className="dp-ev__time">{e.start} – {e.end}</span>
        {(e.owner || e.source) && (
          <span className="dp-ev__meta">{[e.owner, e.source].filter(Boolean).join(' · ')}</span>
        )}
      </span>
      <StatusDot status={e.status} />
    </button>
  )
}

function DayView({ events, now, onSelect }: { events: CalEvent[]; now: Date; onSelect: (t: DayPilotTask) => void }) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const autoScrolled = useRef(false)
  const labels = useMemo(slotLabels, [])
  const layout = useMemo(() => layoutColumns(events), [events])

  // Auto-scroll near the current time when the view opens (once, and never
  // after the user has scrolled manually).
  useLayoutEffect(() => {
    const el = scrollRef.current
    if (!el || autoScrolled.current || !inRange(now)) return
    const y = (nowMinutes(now) - DAY_START_MIN) * PX_PER_MIN
    el.scrollTop = Math.max(0, y - el.clientHeight / 3)
    autoScrolled.current = true
  }, [now])

  return (
    <div className="dp-cal__scroll" ref={scrollRef} onWheel={() => { autoScrolled.current = true }} onTouchMove={() => { autoScrolled.current = true }}>
      <div className="dp-cal__day" style={{ height: GRID_HEIGHT }}>
        <div className="dp-cal__gutter">
          {labels.map((s) => (
            <div key={s.min} className="dp-cal__slotlabel" style={{ height: SLOT_HEIGHT }}>{s.label}</div>
          ))}
        </div>
        <div className="dp-cal__col" style={{ height: GRID_HEIGHT }}>
          {labels.map((s) => (
            <div key={s.min} className={'dp-cal__line' + (s.hour ? ' dp-cal__line--hour' : '')} style={{ top: topPx(s.min) }} aria-hidden="true" />
          ))}
          {events.length === 0 && <div className="dp-cal__free">No events scheduled — your day is open.</div>}
          {events.map((e) => {
            const pos = layout.get(e.id) ?? { col: 0, cols: 1 }
            return <EventBlock key={e.id} e={e} col={pos.col} cols={pos.cols} onSelect={onSelect} />
          })}
          <DayNow now={now} />
        </div>
      </div>
    </div>
  )
}

// ---- week view --------------------------------------------------------------

function WeekNow({ now, todayIndex }: { now: Date; todayIndex: number }) {
  if (!inRange(now) || todayIndex < 0) return null
  const y = (nowMinutes(now) - DAY_START_MIN) * PX_PER_MIN
  return (
    <div className="dp-wnow" style={{ top: y }} role="img" aria-label={`Current time ${fmt(nowMinutes(now))}`}>
      <span className="dp-wnow__line" aria-hidden="true" />
      <span className="dp-wnow__dot" style={{ left: `${(todayIndex / 7) * 100}%` }} aria-hidden="true" />
    </div>
  )
}

function WeekView({ timed, allDay, now, onSelect }: { timed: CalEvent[]; allDay: CalEvent[]; now: Date; onSelect: (t: DayPilotTask) => void }) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const autoScrolled = useRef(false)
  const labels = useMemo(slotLabels, [])
  const days = useMemo(() => weekDates(now), [now])
  const todayIndex = days.findIndex((d) => d.isToday)

  const byDay = useMemo(() => {
    const map = new Map<number, { e: CalEvent; col: number; cols: number }[]>()
    for (let i = 0; i < 7; i++) {
      const dayEvents = timed.filter((e) => e.dayIndex === i)
      const layout = layoutColumns(dayEvents)
      map.set(i, dayEvents.map((e) => ({ e, ...(layout.get(e.id) ?? { col: 0, cols: 1 }) })))
    }
    return map
  }, [timed])

  useLayoutEffect(() => {
    const el = scrollRef.current
    if (!el || autoScrolled.current || !inRange(now)) return
    const y = (nowMinutes(now) - DAY_START_MIN) * PX_PER_MIN
    el.scrollTop = Math.max(0, y - el.clientHeight / 3)
    autoScrolled.current = true
  }, [now])

  return (
    <div className="dp-week">
      <div className="dp-cal__scroll dp-week__scroll" ref={scrollRef} onWheel={() => { autoScrolled.current = true }} onTouchMove={() => { autoScrolled.current = true }}>
        <div className="dp-week__top">
          <div className="dp-week__head">
            <div className="dp-week__corner" />
            <div className="dp-week__cols dp-week__cols--head">
              {days.map((d) => (
                <div key={d.index} className={'dp-week__dayhead' + (d.isToday ? ' is-today' : '') + (d.weekend ? ' is-weekend' : '')}>
                  <span className="dp-week__dayname">{d.short}</span>
                  <span className="dp-week__daydate">{d.date}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="dp-week__allday">
            <div className="dp-week__allday-label">All day</div>
            <div className="dp-week__cols">
              {days.map((d) => (
                <div key={d.index} className={'dp-week__allday-cell' + (d.isToday ? ' is-today' : '')}>
                  {allDay.filter((e) => e.dayIndex === d.index).map((e) => (
                    <button key={e.id} type="button" className={`dp-allday dp-allday--${e.category}`} onClick={() => onSelect(eventToTask(e))} aria-label={`All day: ${e.title}`}>
                      <span className="dp-allday__dot" aria-hidden="true" />
                      <span className="dp-allday__title">{e.title}</span>
                    </button>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="dp-week__body" style={{ height: GRID_HEIGHT }}>
          <div className="dp-cal__gutter">
            {labels.map((s) => (
              <div key={s.min} className="dp-cal__slotlabel" style={{ height: SLOT_HEIGHT }}>{s.label}</div>
            ))}
          </div>
          <div className="dp-week__cols" style={{ position: 'relative', height: GRID_HEIGHT }}>
            {days.map((d) => (
              <div key={d.index} className={'dp-week__col' + (d.isToday ? ' is-today' : '') + (d.weekend ? ' is-weekend' : '')} style={{ height: GRID_HEIGHT }}>
                {labels.map((s) => (
                  <div key={s.min} className={'dp-cal__line' + (s.hour ? ' dp-cal__line--hour' : '')} style={{ top: topPx(s.min) }} aria-hidden="true" />
                ))}
                {(byDay.get(d.index) ?? []).map(({ e, col, cols }) => {
                  const s = minutesOf(e.start)
                  const en = minutesOf(e.end)
                  const width = 100 / cols
                  return (
                    <button
                      key={e.id}
                      type="button"
                      className={`dp-ev dp-ev--week dp-ev--${e.category}`}
                      style={{ top: topPx(s), height: heightPx(s, en), left: `calc(${col * width}% + 2px)`, width: `calc(${width}% - 4px)` }}
                      onClick={() => onSelect(eventToTask(e))}
                      aria-label={`${e.title}, ${d.short} ${d.date}, ${e.start} to ${e.end}${e.source ? ', ' + e.source : ''}`}
                    >
                      <span className="dp-ev__bar" aria-hidden="true" />
                      <span className="dp-ev__body">
                        <span className="dp-ev__title"><span className="dp-ev__icon" aria-hidden="true">{CATEGORY_ICON[e.category]}</span>{e.title}</span>
                        <span className="dp-ev__time">{e.start} – {e.end}</span>
                        {(e.owner || e.source) && <span className="dp-ev__meta">{[e.owner, e.source].filter(Boolean).join(' · ')}</span>}
                      </span>
                      <StatusDot status={e.status} />
                    </button>
                  )
                })}
              </div>
            ))}
            <WeekNow now={now} todayIndex={todayIndex} />
          </div>
        </div>
      </div>
    </div>
  )
}

// ---- shell ------------------------------------------------------------------

/**
 * Connect-your-calendar, shown in place of the grid.
 *
 * An empty grid is the wrong empty state: it says "you have nothing on" when
 * the truth is "DayPilot cannot see your calendar". The offer lives here rather
 * than in Settings because connecting is the thing worth doing, and making a
 * user find a settings page first is how features go unused.
 */
/** The four-colour Google "G". Inline so it needs no network request. */
function GoogleMark() {
  return (
    <svg viewBox="0 0 48 48" width="20" height="20" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5Z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65Z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.28-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19Z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48Z" />
    </svg>
  )
}

/** The Outlook "O" badge over a mail card — recognisable at 20px, no network. */
function OutlookMark() {
  return (
    <svg viewBox="0 0 32 32" width="20" height="20" aria-hidden="true">
      <rect x="12.5" y="7.5" width="16.5" height="17" rx="1.5" fill="#fff" stroke="#0F6CBD" strokeWidth="1.1" />
      <path d="M13 9.5 20.75 15 29 9.5" fill="none" stroke="#0F6CBD" strokeWidth="1.4" strokeLinejoin="round" />
      <rect x="2" y="8.5" width="15" height="15" rx="3" fill="#0F6CBD" />
      <ellipse cx="9.5" cy="16" rx="4" ry="4.6" fill="none" stroke="#fff" strokeWidth="2.1" />
    </svg>
  )
}

//: provider id -> how the connect button presents it. Google leads because the
//  mockup does, and because a stacked list reads top-down.
const CALENDAR_BRANDS: Record<string, { label: string; mark: React.ReactNode }> = {
  google_calendar: { label: 'Google Calendar', mark: <GoogleMark /> },
  microsoft_calendar: { label: 'Outlook Calendar', mark: <OutlookMark /> },
}
const CALENDAR_BRAND_ORDER = ['google_calendar', 'microsoft_calendar']

function ConnectCalendar({ status, onOpenSettings }: {
  status: CalendarStatus | null
  onOpenSettings?: () => void
}) {
  const [error, setError] = useState<string | null>(null)
  const available = status?.available || [
    { provider: 'microsoft_calendar', label: 'Microsoft Outlook' },
    { provider: 'google_calendar', label: 'Google Calendar' },
  ]
  // Present a stable order regardless of what the API returns first: Google,
  // then Outlook, then anything else the deployment offers.
  const providers = [...available].sort(
    (a, b) => {
      const ai = CALENDAR_BRAND_ORDER.indexOf(a.provider)
      const bi = CALENDAR_BRAND_ORDER.indexOf(b.provider)
      return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi)
    },
  )
  const connect = async (provider: string) => {
    const r = await calendarApi.connect(provider)
    if (!r.ok) { setError(r.error); return }
    window.location.assign(r.url)
  }
  return (
    <div className="dp-calconnect">
      <div className="dp-calconnect__card">
        <span className="dp-calconnect__spark" aria-hidden="true">✦</span>
        <h3>Show up prepared for every meeting</h3>
        <p>
          Connect your work calendar so DayPilot can plan around real meetings and
          prepare context, research and talking points before you join.
        </p>
        <div className="dp-calconnect__actions">
          {providers.map((p) => {
            const brand = CALENDAR_BRANDS[p.provider]
            const label = brand ? brand.label : p.label.replace('Microsoft ', '')
            return (
              <button key={p.provider} type="button" className="dp-calconnect__cta"
                      onClick={() => void connect(p.provider)}>
                <span className="dp-calconnect__cta-mark" aria-hidden="true">
                  {brand?.mark}
                </span>
                <span className="dp-calconnect__cta-label">Connect to {label}</span>
              </button>
            )
          })}
        </div>
        {error && <p className="dp-standupcard__error" role="alert">{error}</p>}
        <p className="dp-calconnect__foot">
          Read-only to start. You control what DayPilot may use as AI context, and
          every calendar change is approved by you.
        </p>
        {onOpenSettings && (
          <button type="button" className="dp-linkbtn" onClick={onOpenSettings}>
            Calendar settings →
          </button>
        )}
      </div>
    </div>
  )
}

/** The connection chip in the header: "Outlook · Synced 2m ago ✓". */
function SyncChip({ status, onOpenSettings, onSynced }: {
  status: CalendarStatus
  onOpenSettings?: () => void
  onSynced: () => void
}) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const conn = status.connections.find((c) => c.status === 'connected')
  const tone = status.freshness === 'fresh' ? 'ok' : status.freshness === 'stale' ? 'warn' : 'muted'
  return (
    <div className="dp-syncchip">
      <button type="button" className={'dp-syncchip__btn dp-syncchip__btn--' + tone}
              aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="dp-syncchip__mark" aria-hidden="true">🗓</span>
        {syncLabel(status)}
        <span className="dp-syncchip__tick" aria-hidden="true">
          {status.freshness === 'fresh' ? '✓' : '⚠'}
        </span>
      </button>
      {open && (
        <div className="dp-syncchip__pop" role="dialog" aria-label="Calendar connection">
          <strong>{conn?.label || 'Calendar'}</strong>
          {conn?.account && <span className="dp-syncchip__meta">{conn.account}</span>}
          <span className="dp-syncchip__meta">Last sync {relativeTime(status.lastSyncAt)}</span>
          <button type="button" className="dp-linkbtn" disabled={busy} onClick={async () => {
            setBusy(true); await calendarApi.sync(); onSynced(); setBusy(false); setOpen(false)
          }}>{busy ? 'Syncing…' : 'Sync now'}</button>
          {onOpenSettings && (
            <button type="button" className="dp-linkbtn"
                    onClick={() => { setOpen(false); onOpenSettings() }}>Calendar settings</button>
          )}
        </div>
      )}
    </div>
  )
}

export function MinutePlanCalendar({ tasks, onSelect, onOpenSettings }: {
  tasks: DayPilotTask[]
  onSelect: (task: DayPilotTask) => void
  onOpenSettings?: () => void
}) {
  const [mode, setMode] = useState<Mode>('day')
  const now = useNow()
  const { timed, allDay } = useMemo(() => calendarEvents(tasks), [tasks])
  const todayIdx = mondayIndex(now)
  const dayEvents = useMemo(() => timed.filter((e) => e.dayIndex === todayIdx), [timed, todayIdx])

  // Connection state decides whether this page shows a grid or an offer.
  const [status, setStatus] = useState<CalendarStatus | null>(null)
  const [checked, setChecked] = useState(false)
  const loadStatus = React.useCallback(() => {
    calendarApi.status().then((r) => {
      if (r.ok) setStatus(r.data)
      setChecked(true)
    })
  }, [])
  useEffect(() => { loadStatus() }, [loadStatus])

  // Only offer the connection once we know there isn't one — flashing the
  // onboarding card at a connected user on every page load is worse than a
  // moment of empty grid.
  const showConnect = checked && !status?.connected && dayEvents.length === 0

  const longDate = now.toLocaleDateString(undefined, {
    weekday: 'long', month: 'long', day: 'numeric',
  })

  return (
    <section className="dp-calendar-screen dp-cal">
      <div className="dp-calendar-controls">
        <div>
          <h3>Calendar</h3>
          <p>Your meetings and AI-planned work in one place. · {longDate}</p>
        </div>
        <div className="dp-calendar-controls__right">
          {status?.connected && (
            <SyncChip status={status} onOpenSettings={onOpenSettings} onSynced={loadStatus} />
          )}
          <div className="dp-calendar-toggle" role="tablist" aria-label="Calendar view">
            <button type="button" role="tab" aria-selected={mode === 'day'} className={mode === 'day' ? 'is-active' : ''} onClick={() => setMode('day')}>Day</button>
            <button type="button" role="tab" aria-selected={mode === 'week'} className={mode === 'week' ? 'is-active' : ''} onClick={() => setMode('week')}>Week</button>
          </div>
        </div>
      </div>
      <div className="dp-cal__area">
        {showConnect
          ? <ConnectCalendar status={status} onOpenSettings={onOpenSettings} />
          : mode === 'day'
            ? <DayView events={dayEvents} now={now} onSelect={onSelect} />
            : <WeekView timed={timed} allDay={allDay} now={now} onSelect={onSelect} />}
      </div>
    </section>
  )
}
