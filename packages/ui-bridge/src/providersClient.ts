/**
 * Client for backend-owned AI provider connections (Batch 2).
 *
 * Provider state comes entirely from `/v1/providers/status` — the browser never
 * decides whether a provider is connected, and never stores keys/tokens. Local
 * Ollabridge is detected by real backend probes; Cloud is authenticated
 * server-side (the password or API key is sent once over the API call and
 * never retained client-side).
 */
import { api } from './apiClient'
import { apiBase, workspaceId } from './env'

export type ProviderState = 'unconfigured' | 'testing' | 'connected' | 'degraded' | 'offline' | 'unauthorized' | 'expired'
export type ProviderKind = 'local' | 'ollabridge_cloud'
/** How the stored credential was obtained — never the credential itself. */
export type ProviderAuthMethod = 'api_key' | 'account' | null

export type ProviderConnection = {
  kind: ProviderKind
  baseUrl: string
  state: ProviderState
  active: boolean
  account: { subject?: string | null; email?: string | null; displayName?: string | null } | null
  defaultModel: string | null
  modelsCount: number
  lastLatencyMs: number | null
  lastErrorCode: string | null
  lastTestedAt?: string | null
  authMethod?: ProviderAuthMethod
}
export type ProviderStatus = {
  connections: ProviderConnection[]
  active: ProviderKind | null
  /** Deep link to the OllaBridge Cloud web login page (Google/SSO, reset). */
  cloudLoginUrl?: string
  /** Deep link to the OllaBridge Cloud "create an account" page. */
  cloudRegisterUrl?: string
}
/** Public facts from an Ollabridge gateway's `/health` (no credentials). */
export type GatewayInfo = {
  status: string | null
  mode: string | null
  defaultModel: string | null
  authMode: string | null
  version?: string | null
}
export type LocalModels = {
  models: string[]
  state: ProviderState
  defaultModel: string | null
  gateway: GatewayInfo | null
}
/** One row of the per-agent-role routing policy (`daypilot_models/routing.py`). */
export type RoutePolicy = {
  role: string
  model: string
  tier: string
  latencyBudgetMs: number
  fallback: string[]
}

/** Fallback web endpoints when the backend status hasn't loaded yet. Points at
 *  the live OllaBridge Cloud space (…-ollabridge.hf.space), whose /login and
 *  /register pages are deployed; the backend status may override these. */
export const CLOUD_WEB_LOGIN_URL = 'https://ruslanmv-ollabridge.hf.space/login'
export const CLOUD_WEB_REGISTER_URL = 'https://ruslanmv-ollabridge.hf.space/register'

const ws = () => workspaceId()

/**
 * Fired whenever a provider connection changes (connect, sign in/out, activate,
 * default model) so already-mounted views — chiefly the assistant availability
 * badge — re-sync immediately instead of waiting for a remount. Without this
 * the assistant stays "Limited mode" until reload even though a provider was
 * just connected.
 */
export const PROVIDERS_CHANGED_EVENT = 'daypilot:providers-changed'
export function notifyProvidersChanged(): void {
  try { window.dispatchEvent(new Event(PROVIDERS_CHANGED_EVENT)) } catch { /* non-browser */ }
}

type ProbeResult = { code: string; models: string[]; connection: ProviderConnection }

export const providersApi = {
  status: () => api.get<ProviderStatus>(`/v1/providers/status?workspaceId=${ws()}`),
  localDiscover: async () => {
    const r = await api.post<ProbeResult>('/v1/providers/local/discover', { workspaceId: ws() })
    if (r.ok && r.data.code === 'connected') notifyProvidersChanged()
    return r
  },
  /** Probe an endpoint without changing which key is stored. With no key the
   *  backend re-uses the stored one, so this doubles as "Re-check". */
  localTest: (baseUrl: string, apiKey?: string) => api.post<ProbeResult>('/v1/providers/local/test', { workspaceId: ws(), baseUrl, apiKey }),
  localConnect: async (baseUrl: string, apiKey?: string) => {
    const r = await api.post<{ code: string; connection: ProviderConnection }>('/v1/providers/local/connect', { workspaceId: ws(), baseUrl, apiKey })
    if (r.ok && r.data.code === 'connected') notifyProvidersChanged()
    return r
  },
  /** Models the connected local gateway serves right now, listed server-side
   *  with the stored key, plus the gateway's public health facts. */
  localModels: () => api.get<LocalModels>(`/v1/providers/local/models?workspaceId=${ws()}`),
  cloudLogin: async (email: string, password: string) => {
    const r = await api.post<{ code: string; connection?: ProviderConnection }>('/v1/providers/cloud/login', { workspaceId: ws(), email, password })
    if (r.ok && r.data.code === 'connected') notifyProvidersChanged()
    return r
  },
  /** Connect Ollabridge Cloud with a dashboard API key (ob_live_… / ob_test_…)
   *  instead of an email/password sign-in. */
  cloudConnectKey: async (apiKey: string) => {
    const r = await api.post<{ code: string; models?: string[]; connection?: ProviderConnection }>('/v1/providers/cloud/connect-key', { workspaceId: ws(), apiKey })
    if (r.ok && r.data.code === 'connected') notifyProvidersChanged()
    return r
  },
  cloudModels: () => api.get<{ models: string[] }>(`/v1/providers/cloud/models?workspaceId=${ws()}`),
  cloudLogout: async () => {
    const r = await api.post<{ loggedOut: boolean; connection: ProviderConnection }>('/v1/providers/cloud/logout', { workspaceId: ws() })
    if (r.ok) notifyProvidersChanged()
    return r
  },
  setActive: async (kind: ProviderKind) => {
    const r = await api.patch<{ active: ProviderKind }>('/v1/providers/active', { workspaceId: ws(), kind })
    if (r.ok) notifyProvidersChanged()
    return r
  },
  setDefaultModel: async (kind: ProviderKind, model: string) => {
    const r = await api.patch<{ connection: ProviderConnection }>('/v1/providers/default-model', { workspaceId: ws(), kind, model })
    if (r.ok) notifyProvidersChanged()
    return r
  },
  /** The live per-role routing policy (preferred model, tier, budget, fallbacks). */
  routes: () => api.get<{ routes: RoutePolicy[] }>('/v1/providers/routes'),
}

/** The gateway root for any shape of Ollabridge base URL (`…/v1`, `…/ollama/v1`
 *  or the bare origin), mirroring the backend's `normalize_gateway_root`. */
export function gatewayRoot(baseUrl: string): string {
  let u = (baseUrl || '').trim().replace(/\/+$/, '')
  for (const suffix of ['/ollama/v1', '/v1']) {
    if (u.endsWith(suffix)) { u = u.slice(0, -suffix.length); break }
  }
  return u
}

/** The OllaBridge dashboard that ships with every local gateway (`/ui`). */
export function gatewayDashboardUrl(baseUrl: string): string {
  return `${gatewayRoot(baseUrl)}/ui`
}

/** `email_sentinel` → `Email Sentinel` for the routing table. */
export function humanizeRole(role: string): string {
  return role
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

/** Human-readable text for a local-detection error code. */
export function localErrorText(code: string): string {
  switch (code) {
    case 'connection_refused': return 'Ollabridge isn’t running at that address.'
    case 'not_installed': return 'Ollabridge doesn’t appear to be installed. Install it, then detect again.'
    case 'timeout': return 'The local gateway didn’t respond in time.'
    case 'unauthorized': return 'The local gateway rejected that key. Check the sk-ollabridge-… key from the gateway startup output.'
    case 'key_required': return 'Ollabridge is running, but this connection needs its API key. Paste the sk-ollabridge-… key shown when the gateway started into the API key field.'
    case 'no_models': return 'The gateway is reachable but has no usable models.'
    case 'invalid_response': return 'That address didn’t respond like Ollabridge.'
    default: return 'Couldn’t reach the local gateway.'
  }
}

/** Human-readable text for an Ollabridge Cloud sign-in error code. */
export function cloudErrorText(code: string): string {
  switch (code) {
    case 'unauthorized': return 'That email or password was rejected by Ollabridge Cloud. If you use Google sign-in, open the web login page instead.'
    case 'connection_refused': return 'Couldn’t reach Ollabridge Cloud.'
    case 'timeout': return 'Ollabridge Cloud didn’t respond in time.'
    case 'invalid_response': return 'Ollabridge Cloud returned an unexpected response.'
    default: return 'Sign-in failed. Please try again.'
  }
}

/** Human-readable text for an Ollabridge Cloud API-key connect error code. */
export function cloudKeyErrorText(code: string): string {
  switch (code) {
    case 'unauthorized': return 'Ollabridge Cloud rejected that API key. Create a new key in the Cloud dashboard and paste it here.'
    case 'key_required': return 'Paste an Ollabridge Cloud API key (ob_live_… or ob_test_…).'
    case 'connection_refused': return 'Couldn’t reach Ollabridge Cloud.'
    case 'timeout': return 'Ollabridge Cloud didn’t respond in time.'
    case 'invalid_response': return 'Ollabridge Cloud returned an unexpected response for that key.'
    default: return 'Couldn’t connect with that key. Please try again.'
  }
}

export type ProviderLoadError = { title: string; detail: string; hint?: string }

/**
 * Explain why `/v1/providers/status` could not be read, in terms the person at
 * the keyboard can act on. The classic case is `make run`: the web server is
 * up a few seconds before the API gateway finishes importing, so the first
 * call fails with a network error or an HTML page — not a provider problem.
 */
export function providerLoadError(error: string, status?: number): ProviderLoadError {
  const base = apiBase()
  if (error === 'gateway_html_response') {
    return {
      title: `The DayPilot API isn’t answering at ${base}`,
      detail: 'The web server returned a page instead of JSON, so /api is not being proxied to the gateway.',
      hint: 'Start the API gateway (make run or make run-api) and keep VITE_DAYPILOT_API_BASE / DAYPILOT_API_TARGET pointing at it.',
    }
  }
  if (error === 'gateway_unreachable') {
    return {
      title: `Can’t reach the DayPilot API behind ${base}`,
      detail: 'The web server is up, but the API gateway it proxies to is not answering (connection refused).',
      hint: 'Start the gateway with make run or make run-api — this page reconnects as soon as it is up. Ollabridge itself may be running fine; this is the DayPilot server.',
    }
  }
  if (status === 404) {
    return { title: `The API at ${base} has no provider endpoints`, detail: 'An older gateway build is answering.', hint: 'Restart the gateway from this checkout.' }
  }
  if (status === 401 || status === 403) {
    return { title: 'Sign in to manage AI providers', detail: `The gateway refused the request (HTTP ${status}).` }
  }
  if (status !== undefined && status >= 500) {
    const detail = error && !/^HTTP \d+$/.test(error) ? error : 'The gateway hit an internal error while reading provider state.'
    return { title: `The DayPilot API returned an error (HTTP ${status})`, detail, hint: 'Check the gateway log for the traceback.' }
  }
  if (status !== undefined) {
    return { title: `Unexpected response from the DayPilot API (HTTP ${status})`, detail: error }
  }
  return {
    title: `Can’t reach the DayPilot API at ${base}`,
    detail: 'The gateway is not running yet, or this origin cannot reach it.',
    hint: 'Start it with make run (or make run-api). Ollabridge itself may be running fine — this is the DayPilot server.',
  }
}
