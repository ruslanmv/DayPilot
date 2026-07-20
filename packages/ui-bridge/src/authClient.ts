/**
 * Client for DayPilot identity & login (Batch 1).
 *
 * Sessions are HttpOnly cookies set by the backend — no token ever touches
 * localStorage. Cookie-authenticated writes send the readable CSRF cookie back
 * in an X-CSRF-Token header (double-submit). Identity (who you are) is kept
 * separate from AI-provider activation.
 */
import { apiBase } from './env'

export type AuthConfig = {
  authRequired: boolean
  bootstrapRequired: boolean
  cloudLoginAvailable: boolean
  ssoAvailable: boolean
}
export type AuthUser = { id: string; email: string; displayName: string; role: string; workspaceId: string; mfaState: string }
export type AuthResult<T> = { ok: true; data: T } | { ok: false; error: string; status?: number }

function csrfToken(): string {
  const m = typeof document !== 'undefined' && document.cookie.match(/(?:^|;\s*)dp_csrf=([^;]+)/)
  return m ? decodeURIComponent(m[1]) : ''
}

async function call<T>(path: string, init?: RequestInit): Promise<AuthResult<T>> {
  try {
    const res = await fetch(`${apiBase()}${path}`, {
      ...init,
      credentials: 'include', // send/receive the session cookie
      headers: {
        'Content-Type': 'application/json',
        ...(init?.method && init.method !== 'GET' ? { 'X-CSRF-Token': csrfToken() } : {}),
        ...(init?.headers || {}),
      },
    })
    const text = await res.text()
    const isJson = (res.headers.get('content-type') || '').includes('application/json')
    if (!isJson && /^\s*</.test(text)) return { ok: false, error: 'gateway_html_response', status: res.status }
    const body = text && isJson ? JSON.parse(text) : undefined
    if (!res.ok) return { ok: false, error: (body && body.detail) || `HTTP ${res.status}`, status: res.status }
    return { ok: true, data: body as T }
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'network_error' }
  }
}

export const authApi = {
  config: () => call<AuthConfig>('/v1/auth/config'),
  me: () => call<{ user: AuthUser }>('/v1/auth/me'),
  bootstrap: (email: string, password: string, displayName: string, workspaceName: string) =>
    call<{ user: AuthUser }>('/v1/auth/bootstrap', { method: 'POST', body: JSON.stringify({ email, password, displayName, workspaceName }) }),
  login: (email: string, password: string) =>
    call<{ user: AuthUser }>('/v1/auth/local/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  logout: () => call<{ loggedOut: boolean }>('/v1/auth/logout', { method: 'POST' }),
}

/** Human-readable message for a backend auth error code. */
export function authErrorText(code: string): string {
  switch (code) {
    case 'invalid_credentials': return 'That email or password is incorrect.'
    case 'account_locked': return 'Too many attempts. Please wait a few minutes and try again.'
    case 'weak_password': return 'Choose a password of at least 10 characters.'
    case 'csrf_failed': return 'Your session expired. Please sign in again.'
    case 'gateway_html_response': return 'Couldn’t reach the DayPilot server. Check that the API is running.'
    case 'network_error': return 'Network error — check your connection and try again.'
    default: return 'Something went wrong. Please try again.'
  }
}
