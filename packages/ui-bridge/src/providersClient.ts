/**
 * Client for backend-owned AI provider connections (Batch 2).
 *
 * Provider state comes entirely from `/v1/providers/status` — the browser never
 * decides whether a provider is connected, and never stores keys/tokens. Local
 * Ollabridge is detected by real backend probes; Cloud is authenticated
 * server-side (the password is sent once over the API call and never retained
 * client-side).
 */
import { api } from './apiClient'
import { workspaceId } from './env'

export type ProviderState = 'unconfigured' | 'testing' | 'connected' | 'degraded' | 'offline' | 'unauthorized' | 'expired'
export type ProviderKind = 'local' | 'ollabridge_cloud'

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
}
export type ProviderStatus = {
  connections: ProviderConnection[]
  active: ProviderKind | null
  /** Deep link to the OllaBridge Cloud web login page (Google/SSO, reset). */
  cloudLoginUrl?: string
  /** Deep link to the OllaBridge Cloud "create an account" page. */
  cloudRegisterUrl?: string
}

/** Fallback web endpoints when the backend status hasn't loaded yet. Points at
 *  the live OllaBridge Cloud space (…-ollabridge.hf.space), whose /login and
 *  /register pages are deployed; the backend status may override these. */
export const CLOUD_WEB_LOGIN_URL = 'https://ruslanmv-ollabridge.hf.space/login'
export const CLOUD_WEB_REGISTER_URL = 'https://ruslanmv-ollabridge.hf.space/register'

const ws = () => workspaceId()

/**
 * Fired whenever a provider connection changes (connect, sign in/out, activate)
 * so already-mounted views — chiefly the assistant availability badge — re-sync
 * immediately instead of waiting for a remount. Without this the assistant stays
 * "Limited mode" until reload even though a provider was just connected.
 */
export const PROVIDERS_CHANGED_EVENT = 'daypilot:providers-changed'
export function notifyProvidersChanged(): void {
  try { window.dispatchEvent(new Event(PROVIDERS_CHANGED_EVENT)) } catch { /* non-browser */ }
}

export const providersApi = {
  status: () => api.get<ProviderStatus>(`/v1/providers/status?workspaceId=${ws()}`),
  localDiscover: async () => {
    const r = await api.post<{ code: string; models: string[]; connection: ProviderConnection }>('/v1/providers/local/discover', { workspaceId: ws() })
    if (r.ok && r.data.code === 'connected') notifyProvidersChanged()
    return r
  },
  localTest: (baseUrl: string, apiKey?: string) => api.post<{ code: string; models: string[]; connection: ProviderConnection }>('/v1/providers/local/test', { workspaceId: ws(), baseUrl, apiKey }),
  localConnect: async (baseUrl: string, apiKey?: string) => {
    const r = await api.post<{ code: string; connection: ProviderConnection }>('/v1/providers/local/connect', { workspaceId: ws(), baseUrl, apiKey })
    if (r.ok && r.data.code === 'connected') notifyProvidersChanged()
    return r
  },
  cloudLogin: async (email: string, password: string) => {
    const r = await api.post<{ code: string; connection?: ProviderConnection }>('/v1/providers/cloud/login', { workspaceId: ws(), email, password })
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
  setDefaultModel: (kind: ProviderKind, model: string) => api.patch<{ connection: ProviderConnection }>('/v1/providers/default-model', { workspaceId: ws(), kind, model }),
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
