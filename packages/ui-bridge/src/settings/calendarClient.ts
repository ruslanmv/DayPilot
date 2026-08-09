/**
 * Calendar connections, behaviour, and the meeting-context allow-list.
 *
 * The source catalogue is **served, not hardcoded**: `/v1/calendar/settings`
 * returns which context sources exist, which are available right now (Slack
 * context means nothing without Slack connected), and which are always on. A
 * client-side list would drift from what the server will actually honour, and
 * this particular list is a permission — it has to be the same list in both
 * places or the checkbox is a lie.
 */
import { api } from '../apiClient'
import { workspaceId } from '../env'

export type PrepareScope = 'external' | 'important' | 'every'
export type PrivateMode = 'metadata_only' | 'full' | 'skip'

export type CalendarSettings = {
  prepareEnabled: boolean
  prepareScope: PrepareScope
  prepMinutes: number
  autoPrepBlocks: boolean
  contextSources: string[]
  privateEvents: PrivateMode
  acceptedAreFixed: boolean
  ignoreDeclined: boolean
  tentativeBlocks: boolean
  bufferBeforeMinutes: number
  bufferAfterMinutes: number
}

export type ContextSource = {
  id: string
  label: string
  requires: string | null
  available: boolean
  alwaysOn: boolean
}

export type CalendarConnection = {
  id: string
  provider: string
  label: string
  status: string
  account: string | null
  capabilities: string[]
  lastSyncAt: string | null
  freshness: 'fresh' | 'stale' | 'never'
  writesRequireApproval: boolean
}

export type CalendarStatus = {
  connected: boolean
  providers: string[]
  connections: CalendarConnection[]
  lastSyncAt: string | null
  freshness: 'fresh' | 'stale' | 'never'
  available: Array<{ provider: string; label: string }>
}

export type SettingsPayload = {
  settings: CalendarSettings
  sources: ContextSource[]
  effectiveSources: string[]
}

/** "2m ago" / "just now" — the calendar chip has room for about that much. */
export function relativeTime(iso: string | null, now: Date = new Date()): string {
  if (!iso) return 'never'
  const then = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`)
  if (Number.isNaN(then.getTime())) return 'never'
  const seconds = Math.max(0, Math.round((now.getTime() - then.getTime()) / 1000))
  if (seconds < 45) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}

/** The chip's one line: "Outlook · Synced 2m ago". */
export function syncLabel(status: CalendarStatus | null, now: Date = new Date()): string {
  if (!status || !status.connected) return 'No calendar connected'
  const first = status.connections.find((c) => c.status === 'connected')
  const name = (first?.label || 'Calendar').replace('Microsoft ', '')
  if (status.freshness === 'never') return `${name} · Not synced yet`
  return `${name} · Synced ${relativeTime(status.lastSyncAt, now)}`
}

export const calendarApi = {
  async status(): Promise<{ ok: true; data: CalendarStatus } | { ok: false; error: string }> {
    const r = await api.get<CalendarStatus>(`/v1/calendar/status?workspaceId=${workspaceId()}`)
    return r.ok ? { ok: true, data: r.data } : { ok: false, error: r.error }
  },

  async settings(): Promise<{ ok: true; data: SettingsPayload } | { ok: false; error: string }> {
    const r = await api.get<SettingsPayload>(`/v1/calendar/settings?workspaceId=${workspaceId()}`)
    return r.ok ? { ok: true, data: r.data } : { ok: false, error: r.error }
  },

  async save(
    patch: Partial<CalendarSettings>,
  ): Promise<{ ok: true; data: CalendarSettings } | { ok: false; error: string }> {
    const r = await api.put<{ settings: CalendarSettings }>(
      `/v1/calendar/settings?workspaceId=${workspaceId()}`, patch,
    )
    return r.ok ? { ok: true, data: r.data.settings } : { ok: false, error: r.error }
  },

  /** Begin OAuth. Returns the provider URL to send the browser to. */
  async connect(
    provider: string,
  ): Promise<{ ok: true; url: string } | { ok: false; error: string }> {
    const returnTo = encodeURIComponent(window.location.href)
    const r = await api.post<{ available: boolean; authorizationUrl?: string; reason?: string }>(
      `/v1/calendar/connect/${provider}?workspaceId=${workspaceId()}&returnTo=${returnTo}`,
    )
    if (!r.ok) return { ok: false, error: r.error }
    if (!r.data.available || !r.data.authorizationUrl) {
      return { ok: false, error: r.data.reason || 'This calendar is not configured on this deployment.' }
    }
    return { ok: true, url: r.data.authorizationUrl }
  },

  async sync(): Promise<{ ok: true } | { ok: false; error: string }> {
    const r = await api.post(`/v1/calendar/sync?workspaceId=${workspaceId()}`, {})
    return r.ok ? { ok: true } : { ok: false, error: r.error }
  },
}
