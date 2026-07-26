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
import { PROVIDERS_CHANGED_EVENT } from './providersClient'

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

/** React hook: re-checks on mount, when a provider connection changes, and when
 *  the tab regains focus — so connecting a provider flips the assistant out of
 *  "Limited mode" immediately, without a reload. Also exposes a manual retry. */
export function useAssistantAvailability(): { state: AssistantAvailability; retry: () => void } {
  const [state, setState] = React.useState<AssistantAvailability>('checking')
  const aliveRef = React.useRef(true)
  const run = React.useCallback(() => {
    setState('checking')
    checkAssistantAvailability().then((s) => { if (aliveRef.current) setState(s) })
  }, [])
  React.useEffect(() => {
    aliveRef.current = true
    run()
    // Re-sync when a provider is connected/activated elsewhere (onboarding wizard
    // or Settings → AI providers), or when the user returns to the tab.
    const onChange = () => run()
    const onVisible = () => { if (document.visibilityState === 'visible') run() }
    window.addEventListener(PROVIDERS_CHANGED_EVENT, onChange)
    window.addEventListener('focus', onChange)
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      aliveRef.current = false
      window.removeEventListener(PROVIDERS_CHANGED_EVENT, onChange)
      window.removeEventListener('focus', onChange)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [run])
  return { state, retry: run }
}
