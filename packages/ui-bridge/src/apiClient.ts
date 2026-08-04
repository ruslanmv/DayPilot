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
  // For multipart/FormData, let the browser set Content-Type (with its
  // boundary) — forcing application/json would corrupt the upload.
  const isForm = typeof FormData !== 'undefined' && init?.body instanceof FormData
  try {
    const res = await fetch(url, {
      ...init,
      headers: {
        ...(isForm ? {} : { 'Content-Type': 'application/json' }),
        'X-Workspace-Id': workspaceId(),
        ...(init?.headers || {}),
      },
    })
    const contentType = res.headers.get('content-type') || ''
    const isJson = contentType.includes('application/json')
    const text = await res.text()

    // A misrouted request (e.g. the dev server answering instead of the API)
    // returns HTML — surface a structured error, never a raw JSON parse crash
    // and never the returned HTML itself.
    if (!isJson && /^\s*</.test(text)) {
      return { ok: false, error: 'gateway_html_response', status: res.status }
    }
    if (!res.ok) {
      // Prefer FastAPI's `detail` field when present.
      let detail = `HTTP ${res.status}`
      if (isJson && text) {
        try {
          const body = JSON.parse(text) as { detail?: unknown }
          if (typeof body.detail === 'string') detail = body.detail
        } catch { /* keep the status text */ }
      }
      return { ok: false, error: detail, status: res.status }
    }
    if (!text) return { ok: true, data: undefined as unknown as T }
    try {
      return { ok: true, data: JSON.parse(text) as T }
    } catch {
      return { ok: false, error: 'invalid_json', status: res.status }
    }
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'network_error' }
  }
}

type CallOpts = { headers?: Record<string, string> }

export const api = {
  get: <T>(path: string, opts?: CallOpts) => request<T>(path, { headers: opts?.headers }),
  post: <T>(path: string, body?: unknown, opts?: CallOpts) =>
    request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body), headers: opts?.headers }),
  put: <T>(path: string, body?: unknown, opts?: CallOpts) =>
    request<T>(path, { method: 'PUT', body: body === undefined ? undefined : JSON.stringify(body), headers: opts?.headers }),
  postForm: <T>(path: string, form: FormData) =>
    request<T>(path, { method: 'POST', body: form }),
  patch: <T>(path: string, body?: unknown, opts?: CallOpts) =>
    request<T>(path, { method: 'PATCH', body: body === undefined ? undefined : JSON.stringify(body), headers: opts?.headers }),
  del: <T>(path: string, opts?: CallOpts) => request<T>(path, { method: 'DELETE', headers: opts?.headers }),
}
