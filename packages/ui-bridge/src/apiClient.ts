/**
 * Thin fetch client for the DayPilot API gateway.
 *
 * Everything the "connected" experience needs — the assistant asking the
 * backend real questions, the planner chat updating the scheduler, persistent
 * chat sessions — goes through here. It never throws for offline/unreachable
 * backends; callers get a typed `{ ok, data | error }` result and render a
 * calm empty/error state instead of crashing. No credentials are ever placed
 * in query strings or logged.
 */
import { apiBase, workspaceId } from './env'

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: string; status?: number }

async function request<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  const url = `${apiBase()}${path.startsWith('/') ? path : `/${path}`}`
  try {
    const res = await fetch(url, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        'X-Workspace-Id': workspaceId(),
        ...(init?.headers || {}),
      },
    })
    if (!res.ok) {
      return { ok: false, error: `HTTP ${res.status}`, status: res.status }
    }
    const text = await res.text()
    const data = text ? (JSON.parse(text) as T) : (undefined as unknown as T)
    return { ok: true, data }
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'network error' }
  }
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PATCH', body: body === undefined ? undefined : JSON.stringify(body) }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}
