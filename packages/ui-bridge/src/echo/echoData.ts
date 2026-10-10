/**
 * Echo Show display mode — data.
 *
 * One way in and out for every request the Echo dashboard makes:
 *
 *   * the same gateway, base path, workspace header and session cookie as the
 *     desktop shell (`apiClient`), so the server enforces exactly the same
 *     permissions — the Echo never gets a wider or private API;
 *   * a timeout on every request, because a wall display on Wi-Fi must not sit
 *     on a request that will never answer;
 *   * the CSRF double-submit header on writes, like `authClient`;
 *   * failures classified once (`classifyFailure`) so every section explains
 *     an outage the same way.
 *
 * `useEchoData` schedules refreshes in two tiers, pauses while the page is
 * hidden, backs off after failures, slows down when nobody has touched the
 * screen for a while, and keeps the last good data — labelled with its age —
 * instead of blanking the display or substituting numbers.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import type { DayPilotProject, DayPilotTask } from '@daypilot/shared-types'

import { api, type ApiResult } from '../apiClient'
import { csrfToken } from '../authClient'
import { workspaceId } from '../env'
import { orderQueue, toApprovalRow, type ApprovalRow } from '../approvals/approvalsQueue'
import { planDateKey, type PlanBlockDTO, type TodayTask } from '../home/homeDay'
import { toDayPilotProject } from '../projectsClient'
import type { CalendarStatus } from '../settings/calendarClient'
import type { AgentProfile } from '../settings/homepilotClient'
import { toDayPilotTask, type ServerTask } from '../tasksMap'
import {
  ECHO_TIMING,
  classifyFailure,
  isRetryable,
  nextRefreshIn,
  sameData,
  type AgentRunDTO,
  type CalendarEventDTO,
  type EchoFailure,
} from './echoModel'

// ---------------------------------------------------------------- requests

export type EchoResult<T> = { ok: true; data: T } | { ok: false; failure: EchoFailure }

function online(): boolean {
  return typeof navigator === 'undefined' || navigator.onLine !== false
}

async function call<T>(method: 'GET' | 'POST', path: string, body?: unknown, outer?: AbortSignal): Promise<EchoResult<T>> {
  const ctrl = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => { timedOut = true; ctrl.abort() }, ECHO_TIMING.timeoutMs)
  const onOuterAbort = () => ctrl.abort()
  outer?.addEventListener('abort', onOuterAbort)
  const headers: Record<string, string> = {}
  if (method !== 'GET') {
    const token = csrfToken()
    if (token) headers['X-CSRF-Token'] = token
  }
  let r: ApiResult<T>
  try {
    r = method === 'GET'
      ? await api.get<T>(path, { signal: ctrl.signal, headers })
      : await api.post<T>(path, body, { signal: ctrl.signal, headers })
  } finally {
    clearTimeout(timer)
    outer?.removeEventListener('abort', onOuterAbort)
  }
  if (r.ok) return r
  return { ok: false, failure: classifyFailure(r, { online: online(), timedOut }) }
}

const ws = () => encodeURIComponent(workspaceId())

type ServerApproval = Parameters<typeof toApprovalRow>[0]
type ServerProject = Parameters<typeof toDayPilotProject>[0]
type Page<T> = { items?: T[]; hasMore?: boolean }

export type TodayCounts = {
  aiRunning: number
  approvals: number
  blockers: number
  projectsActive: number
  projectsNeedAttention: number
}
export type TodayDTO = {
  now?: TodayTask | null
  next?: TodayTask | null
  later?: TodayTask[]
  counts?: Partial<TodayCounts>
}
export type AssistantTurnDTO = {
  reply: string
  action?: { kind: string; target?: string } | null
  limited?: boolean
  error?: string | null
}

/**
 * The calendar window the Echo asks for: today and the next six days, plus a
 * day of margin on each side because the server compares times without an
 * offset as UTC. `eventsOnDay` trims to exact local days.
 */
export function calendarWindow(now: Date = new Date()): { start: string; end: string } {
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1)
  const end = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 8)
  return { start: start.toISOString(), end: end.toISOString() }
}

/** Every endpoint the Echo reads or writes. All existed for the desktop shell. */
export const echoApi = {
  today: (s?: AbortSignal) => call<TodayDTO>('GET', `/v1/today?workspaceId=${ws()}`, undefined, s),
  plan: (s?: AbortSignal) =>
    call<{ blocks?: PlanBlockDTO[]; state?: string }>('GET', `/v1/plans/${planDateKey()}?workspaceId=${ws()}`, undefined, s),
  approvals: (s?: AbortSignal) =>
    call<Page<ServerApproval>>('GET', `/v1/approvals?workspaceId=${ws()}&limit=50`, undefined, s),
  /** The server's vocabulary is `approve` / `reject` (approvals/center.py). */
  decide: (id: string, decision: 'approve' | 'reject') =>
    call<{ status?: string }>('POST', `/v1/approvals/${encodeURIComponent(id)}/decide`, { decision }),
  tasks: (s?: AbortSignal) =>
    call<Page<ServerTask>>('GET', `/v1/tasks?workspaceId=${ws()}&limit=200`, undefined, s),
  projects: (s?: AbortSignal) =>
    call<Page<ServerProject>>('GET', `/v1/projects?workspaceId=${ws()}&limit=100`, undefined, s),
  calendar: (s?: AbortSignal) => {
    const w = calendarWindow()
    return call<{ items?: CalendarEventDTO[]; conflicts?: Array<{ a: string; b: string }> }>(
      'GET',
      `/v1/calendar/events?workspaceId=${ws()}&start=${encodeURIComponent(w.start)}&end=${encodeURIComponent(w.end)}`,
      undefined, s,
    )
  },
  calendarStatus: (s?: AbortSignal) => call<CalendarStatus>('GET', `/v1/calendar/status?workspaceId=${ws()}`, undefined, s),
  agentProfiles: (s?: AbortSignal) => call<{ profiles?: AgentProfile[] }>('GET', `/v1/agents/profiles?workspaceId=${ws()}`, undefined, s),
  agentRuns: (s?: AbortSignal) => call<Page<AgentRunDTO>>('GET', `/v1/agents?workspaceId=${ws()}&limit=30`, undefined, s),
  health: (s?: AbortSignal) => call<{ ok?: boolean }>('GET', '/health', undefined, s),
  /** Most data endpoints do not check the session cookie themselves; this does. */
  me: (s?: AbortSignal) => call<{ user?: unknown }>('GET', '/v1/auth/me', undefined, s),
  providers: (s?: AbortSignal) =>
    call<{ connections?: Array<{ state?: string }> }>('GET', '/v1/providers/status', undefined, s),
  ask: (message: string) =>
    call<AssistantTurnDTO>('POST', '/v1/assistant/turn', { message, workspaceId: workspaceId(), sessionId: null }),
}

// ---------------------------------------------------------------- view data

export type TodayView = {
  now: TodayTask | null
  next: TodayTask | null
  later: TodayTask[]
  /** Exactly what the server counted; `null` when it did not send counts. */
  counts: TodayCounts | null
}
export type PlanView = { planned: boolean; blocks: PlanBlockDTO[] }
export type ListView<T> = { items: T[]; more: boolean }
export type CalendarView = {
  events: CalendarEventDTO[]
  conflicts: Array<{ a: string; b: string }>
  status: CalendarStatus | null
}
export type AgentsView = {
  /** `null` when the HomePilot agent runtime is off on this server. */
  profiles: AgentProfile[] | null
  runs: AgentRunDTO[]
  runsFailure: EchoFailure | null
}
export type AssistantAvailability = 'ready' | 'limited' | 'down'

export type EchoSlots = {
  today: TodayView
  plan: PlanView
  approvals: ListView<ApprovalRow>
  tasks: ListView<DayPilotTask>
  projects: ListView<DayPilotProject>
  calendar: CalendarView
  agents: AgentsView
  assistant: AssistantAvailability
}
export type SlotKey = keyof EchoSlots

export type Slot<T> = {
  /** Last good data, kept through later failures. */
  data: T | null
  /** The most recent failure, cleared by the next success. */
  failure: EchoFailure | null
}

type Outcome<T> = { ok: true; data: T } | { ok: false; failure: EchoFailure }
type Loader<K extends SlotKey> = (s: AbortSignal) => Promise<Outcome<EchoSlots[K]>>

function toCounts(c: TodayDTO['counts']): TodayCounts | null {
  if (!c) return null
  const keys: (keyof TodayCounts)[] = ['aiRunning', 'approvals', 'blockers', 'projectsActive', 'projectsNeedAttention']
  if (!keys.every((k) => typeof c[k] === 'number')) return null
  return c as TodayCounts
}

const LOADERS: { [K in SlotKey]: Loader<K> } = {
  today: async (s) => {
    const r = await echoApi.today(s)
    if (!r.ok) return r
    return { ok: true, data: { now: r.data.now || null, next: r.data.next || null, later: r.data.later || [], counts: toCounts(r.data.counts) } }
  },
  plan: async (s) => {
    const r = await echoApi.plan(s)
    // No plan for today is a 404, not a failure — the day has not been planned yet.
    if (!r.ok) return r.failure.kind === 'not_found' ? { ok: true, data: { planned: false, blocks: [] } } : r
    const blocks = (r.data.blocks || []).slice().sort((a, b) => (a.orderIndex ?? 0) - (b.orderIndex ?? 0))
    return { ok: true, data: { planned: true, blocks } }
  },
  approvals: async (s) => {
    const r = await echoApi.approvals(s)
    if (!r.ok) return r
    return { ok: true, data: { items: orderQueue((r.data.items || []).map(toApprovalRow)), more: !!r.data.hasMore } }
  },
  tasks: async (s) => {
    const r = await echoApi.tasks(s)
    if (!r.ok) return r
    return { ok: true, data: { items: (r.data.items || []).map((t) => toDayPilotTask(t)), more: !!r.data.hasMore } }
  },
  projects: async (s) => {
    const r = await echoApi.projects(s)
    if (!r.ok) return r
    return { ok: true, data: { items: (r.data.items || []).map(toDayPilotProject), more: !!r.data.hasMore } }
  },
  calendar: async (s) => {
    const [events, status] = await Promise.all([echoApi.calendar(s), echoApi.calendarStatus(s)])
    if (!events.ok) return events
    return {
      ok: true,
      data: { events: events.data.items || [], conflicts: events.data.conflicts || [], status: status.ok ? status.data : null },
    }
  },
  agents: async (s) => {
    const [profiles, runs] = await Promise.all([echoApi.agentProfiles(s), echoApi.agentRuns(s)])
    // The agent directory 404s when the HomePilot runtime is off: that is a
    // state to explain, not an error.
    if (!profiles.ok && profiles.failure.kind !== 'not_found' && !runs.ok) return profiles
    return {
      ok: true,
      data: {
        profiles: profiles.ok ? profiles.data.profiles || [] : null,
        runs: runs.ok ? runs.data.items || [] : [],
        runsFailure: runs.ok ? null : runs.failure,
      },
    }
  },
  // Same rule as assistantAvailability.ts: API up + a connected provider.
  assistant: async (s) => {
    const health = await echoApi.health(s)
    if (!health.ok) {
      return health.failure.kind === 'auth' || health.failure.kind === 'misrouted' ? health : { ok: true, data: 'down' }
    }
    if (health.data?.ok === false) return { ok: true, data: 'down' }
    const status = await echoApi.providers(s)
    if (!status.ok && status.failure.kind === 'auth') return status
    const connected = status.ok && (status.data.connections || []).some((c) => c.state === 'connected')
    return { ok: true, data: connected ? 'ready' : 'limited' }
  },
}

export const LIVE_SLOTS: SlotKey[] = ['today', 'plan', 'approvals']
export const SLOW_SLOTS: SlotKey[] = ['tasks', 'projects', 'calendar', 'agents', 'assistant']

type Tier = 'live' | 'slow'
const TIER_SLOTS: Record<Tier, SlotKey[]> = { live: LIVE_SLOTS, slow: SLOW_SLOTS }

const EMPTY_SLOTS = Object.fromEntries(
  [...LIVE_SLOTS, ...SLOW_SLOTS].map((k) => [k, { data: null, failure: null }]),
) as { [K in SlotKey]: Slot<EchoSlots[K]> }

export type EchoData = {
  slots: { [K in SlotKey]: Slot<EchoSlots[K]> }
  /** When each tier last finished a refresh with at least one success. */
  updated: Record<Tier, number | null>
  refreshing: boolean
  online: boolean
  /** The server answered 401: the session ended. Polling stops until sign-in. */
  sessionEnded: boolean
  /** Failures in a row for the live tier (drives the "Reconnecting" label). */
  liveFailures: number
  refreshAll: () => void
  refresh: (keys: SlotKey[]) => Promise<void>
  decide: (id: string, decision: 'approve' | 'reject') => Promise<EchoResult<{ status?: string }>>
  ask: (message: string) => Promise<EchoResult<AssistantTurnDTO>>
}

/**
 * The dashboard's data. One instance per page; every section reads from it so
 * a number shown in a tile and the list behind it come from the same response.
 */
export function useEchoData(opts: { enabled?: boolean; checkSession?: boolean } = {}): EchoData {
  const enabled = opts.enabled !== false
  // Signed-in displays confirm the session on the slow tier, so an expired or
  // revoked session is noticed even though the data endpoints keep answering.
  const checkSession = useRef(!!opts.checkSession)
  checkSession.current = !!opts.checkSession
  const [slots, setSlots] = useState(EMPTY_SLOTS)
  const [updated, setUpdated] = useState<Record<Tier, number | null>>({ live: null, slow: null })
  const [inFlight, setInFlight] = useState(0)
  const [isOnline, setOnline] = useState(online())
  const [sessionEnded, setSessionEnded] = useState(false)
  const [liveFailures, setLiveFailures] = useState(0)

  const alive = useRef(true)
  const rootAbort = useRef<AbortController | null>(null)
  const timers = useRef<Record<Tier, ReturnType<typeof setTimeout> | null>>({ live: null, slow: null })
  const running = useRef<Record<Tier, boolean>>({ live: false, slow: false })
  const failures = useRef<Record<Tier, number>>({ live: 0, slow: 0 })
  const lastRun = useRef<Record<Tier, number>>({ live: 0, slow: 0 })
  const lastTouch = useRef(Date.now())
  const ended = useRef(false)
  // `schedule` and `runTier` call each other; the ref breaks the cycle.
  const runTierRef = useRef<(tier: Tier) => Promise<void>>(async () => {})

  const commit = useCallback(<K extends SlotKey>(key: K, out: Outcome<EchoSlots[K]>) => {
    setSlots((cur) => {
      const prev = cur[key]
      const next: Slot<EchoSlots[K]> = out.ok
        ? { data: sameData(prev.data, out.data) ? prev.data : out.data, failure: null }
        : { data: prev.data, failure: out.failure }
      if (next.data === prev.data && sameData(next.failure, prev.failure)) return cur
      return { ...cur, [key]: next }
    })
  }, [])

  /** Load some slots now. Resolves to whether any of them hit a retryable failure. */
  const load = useCallback(async (keys: SlotKey[]): Promise<{ retry: boolean; anyOk: boolean }> => {
    const signal = rootAbort.current?.signal
    if (!signal || ended.current) return { retry: false, anyOk: false }
    setInFlight((n) => n + 1)
    try {
      const results = await Promise.all(keys.map(async (key) => {
        const out = await (LOADERS[key] as Loader<typeof key>)(signal)
        return { key, out }
      }))
      if (!alive.current || signal.aborted) return { retry: false, anyOk: false }
      let retry = false
      let anyOk = false
      for (const { key, out } of results) {
        if (!out.ok && out.failure.kind === 'auth') {
          ended.current = true
          setSessionEnded(true)
        }
        if (!out.ok && isRetryable(out.failure)) retry = true
        if (out.ok) anyOk = true
        commit(key, out as Outcome<EchoSlots[typeof key]>)
      }
      return { retry, anyOk }
    } finally {
      if (alive.current) setInFlight((n) => Math.max(0, n - 1))
    }
  }, [commit])

  const schedule = useCallback((tier: Tier) => {
    const t = timers.current[tier]
    if (t) clearTimeout(t)
    timers.current[tier] = null
    if (ended.current || (typeof document !== 'undefined' && document.hidden)) return
    const idle = Date.now() - lastTouch.current > ECHO_TIMING.idleAfterMs
    const delay = nextRefreshIn(tier, failures.current[tier], idle)
    timers.current[tier] = setTimeout(() => { void runTierRef.current(tier) }, delay)
  }, [])

  const runTier = useCallback(async (tier: Tier) => {
    if (running.current[tier] || ended.current) return
    running.current[tier] = true
    lastRun.current[tier] = Date.now()
    try {
      if (tier === 'slow' && checkSession.current && rootAbort.current) {
        const me = await echoApi.me(rootAbort.current.signal)
        if (!me.ok && me.failure.kind === 'auth') {
          ended.current = true
          if (alive.current) setSessionEnded(true)
          return
        }
      }
      const { retry, anyOk } = await load(TIER_SLOTS[tier])
      failures.current[tier] = retry ? failures.current[tier] + 1 : 0
      if (tier === 'live' && alive.current) setLiveFailures(failures.current.live)
      if (anyOk && alive.current) setUpdated((u) => ({ ...u, [tier]: Date.now() }))
    } finally {
      running.current[tier] = false
      if (alive.current) schedule(tier)
    }
  }, [load, schedule])
  runTierRef.current = runTier

  const refreshAll = useCallback(() => {
    failures.current = { live: 0, slow: 0 }
    void runTier('live')
    void runTier('slow')
  }, [runTier])

  const refresh = useCallback(async (keys: SlotKey[]) => { await load(keys) }, [load])

  useEffect(() => {
    if (!enabled) return
    alive.current = true
    ended.current = false
    // A run left over from a previous mount (React dev remounts) must not block this one;
    // its results are dropped because its signal is aborted.
    running.current = { live: false, slow: false }
    rootAbort.current = new AbortController()
    refreshAll()

    // A tier that has been waiting longer than its interval runs on return.
    const catchUp = () => {
      const now = Date.now()
      if (now - lastRun.current.live >= ECHO_TIMING.liveMs) void runTier('live')
      else schedule('live')
      if (now - lastRun.current.slow >= ECHO_TIMING.slowMs) void runTier('slow')
      else schedule('slow')
    }
    const onVisibility = () => {
      if (document.hidden) {
        for (const tier of ['live', 'slow'] as Tier[]) {
          const t = timers.current[tier]
          if (t) clearTimeout(t)
          timers.current[tier] = null
        }
      } else catchUp()
    }
    const onOnline = () => { setOnline(true); refreshAll() }
    const onOffline = () => setOnline(false)
    const onTouch = () => {
      const wasIdle = Date.now() - lastTouch.current > ECHO_TIMING.idleAfterMs
      lastTouch.current = Date.now()
      if (wasIdle) catchUp()
    }
    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('online', onOnline)
    window.addEventListener('offline', onOffline)
    window.addEventListener('pointerdown', onTouch, { passive: true })
    window.addEventListener('keydown', onTouch, { passive: true })
    // Silk restores pages from the back/forward cache after an interruption
    // (a call, a timer, an Alexa answer); refresh instead of showing old state.
    const onPageShow = (e: PageTransitionEvent) => { if (e.persisted) refreshAll() }
    window.addEventListener('pageshow', onPageShow)
    return () => {
      alive.current = false
      rootAbort.current?.abort()
      for (const tier of ['live', 'slow'] as Tier[]) {
        const t = timers.current[tier]
        if (t) clearTimeout(t)
        timers.current[tier] = null
      }
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('online', onOnline)
      window.removeEventListener('offline', onOffline)
      window.removeEventListener('pointerdown', onTouch)
      window.removeEventListener('keydown', onTouch)
      window.removeEventListener('pageshow', onPageShow)
    }
  }, [enabled, refreshAll, runTier, schedule])

  const decide = useCallback(async (id: string, decision: 'approve' | 'reject') => {
    const r = await echoApi.decide(id, decision)
    if (!r.ok && r.failure.kind === 'auth') { ended.current = true; setSessionEnded(true) }
    // Decided, or decided elsewhere (409): either way the queue has changed.
    if (r.ok || r.failure.kind === 'conflict') void load(['approvals', 'today', 'tasks'])
    return r
  }, [load])

  const ask = useCallback(async (message: string) => {
    const r = await echoApi.ask(message)
    if (!r.ok && r.failure.kind === 'auth') { ended.current = true; setSessionEnded(true) }
    return r
  }, [])

  return {
    slots, updated, refreshing: inFlight > 0, online: isOnline, sessionEnded, liveFailures,
    refreshAll, refresh, decide, ask,
  }
}
