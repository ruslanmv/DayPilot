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
export type ProviderStatus = { connections: ProviderConnection[]; active: ProviderKind | null }

const ws = () => workspaceId()

export const providersApi = {
  status: () => api.get<ProviderStatus>(`/v1/providers/status?workspaceId=${ws()}`),
  localDiscover: () => api.post<{ code: string; models: string[]; connection: ProviderConnection }>('/v1/providers/local/discover', { workspaceId: ws() }),
  localTest: (baseUrl: string, apiKey?: string) => api.post<{ code: string; models: string[]; connection: ProviderConnection }>('/v1/providers/local/test', { workspaceId: ws(), baseUrl, apiKey }),
  localConnect: (baseUrl: string, apiKey?: string) => api.post<{ code: string; connection: ProviderConnection }>('/v1/providers/local/connect', { workspaceId: ws(), baseUrl, apiKey }),
  cloudLogin: (email: string, password: string) => api.post<{ code: string; connection?: ProviderConnection }>('/v1/providers/cloud/login', { workspaceId: ws(), email, password }),
  cloudModels: () => api.get<{ models: string[] }>(`/v1/providers/cloud/models?workspaceId=${ws()}`),
  cloudLogout: () => api.post<{ loggedOut: boolean; connection: ProviderConnection }>('/v1/providers/cloud/logout', { workspaceId: ws() }),
  setActive: (kind: ProviderKind) => api.patch<{ active: ProviderKind }>('/v1/providers/active', { workspaceId: ws(), kind }),
  setDefaultModel: (kind: ProviderKind, model: string) => api.patch<{ connection: ProviderConnection }>('/v1/providers/default-model', { workspaceId: ws(), kind, model }),
}

/** Human-readable text for a local-detection error code. */
export function localErrorText(code: string): string {
  switch (code) {
    case 'connection_refused': return 'Ollabridge isn’t running at that address.'
    case 'not_installed': return 'Ollabridge doesn’t appear to be installed. Install it, then detect again.'
    case 'timeout': return 'The local gateway didn’t respond in time.'
    case 'unauthorized': return 'The local gateway rejected the key.'
    case 'no_models': return 'The gateway is reachable but has no usable models.'
    case 'invalid_response': return 'That address didn’t respond like Ollabridge.'
    default: return 'Couldn’t reach the local gateway.'
  }
}
