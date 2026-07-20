/**
 * Assistant availability — checked before the chat composer is enabled, so the
 * user never types a message only to discover the service is unreachable (the
 * classic HTTP 404 from a stale/ misconfigured backend).
 *
 * Three states, matching the backend's capabilities:
 *   - 'down'    → the DayPilot API is unreachable; disable the assistant.
 *   - 'limited' → API is up but no AI provider is connected; the assistant still
 *                 answers deterministically (planner, status, approvals). Show a
 *                 "Limited mode" badge.
 *   - 'ready'   → API up and a provider connected; full assistant.
 */
import React from 'react'
import { api } from './apiClient'
import { isDemoMode } from './env'

export type AssistantAvailability = 'checking' | 'down' | 'limited' | 'ready'

export async function checkAssistantAvailability(): Promise<AssistantAvailability> {
  // Demo mode is self-contained and never calls the backend.
  if (isDemoMode()) return 'ready'
  const health = await api.get<{ ok?: boolean; service?: string }>('/health')
  if (!health.ok || health.data?.ok === false) return 'down'
  // Backend is up. Is a provider connected? Read the backend-owned status.
  const status = await api.get<{ connections?: Array<{ state?: string }> }>('/v1/providers/status')
  const connected = status.ok && (status.data.connections || []).some((c) => c.state === 'connected')
  return connected ? 'ready' : 'limited'
}

/** React hook: re-checks on mount and exposes a manual retry. */
export function useAssistantAvailability(): { state: AssistantAvailability; retry: () => void } {
  const [state, setState] = React.useState<AssistantAvailability>('checking')
  const run = React.useCallback(() => {
    let alive = true
    setState('checking')
    checkAssistantAvailability().then((s) => { if (alive) setState(s) })
    return () => { alive = false }
  }, [])
  React.useEffect(() => run(), [run])
  return { state, retry: run }
}
