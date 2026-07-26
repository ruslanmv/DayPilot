import { useCallback, useEffect, useState } from 'react'

/**
 * Lightweight hash routing for the DayPilot shell (Batch A3).
 *
 * The app was a `PortalView` enum with no URLs. This adds deep-linkable routes
 * (`#/planning`, `#/agents`, `#/agents/:agentId`) with working browser back /
 * forward, so a dedicated agent workspace can live at its own address. Hash
 * routing needs no server config and is safe for a static SPA. `navigate` is a
 * drop-in replacement for the old `setView` (its extra options are optional).
 */
export type PortalView =
  | 'home' | 'planning' | 'calendar' | 'tasks' | 'projects' | 'documents' | 'agents' | 'email'

const VIEWS: PortalView[] = ['home', 'planning', 'calendar', 'tasks', 'projects', 'documents', 'agents', 'email']

export type Route = { view: PortalView; agentId: string | null }

export function parseHash(hash: string): Route {
  const clean = (hash || '').replace(/^#\/?/, '')          // "agents/scarlett"
  const [seg0, seg1] = clean.split('/')
  const view = (VIEWS as string[]).includes(seg0) ? (seg0 as PortalView) : 'home'
  const agentId = view === 'agents' && seg1 ? decodeURIComponent(seg1) : null
  return { view, agentId }
}

export function routeToHash(route: Route): string {
  if (route.view === 'agents' && route.agentId) return `#/agents/${encodeURIComponent(route.agentId)}`
  return `#/${route.view}`
}

export type NavigateOptions = { agentId?: string | null; replace?: boolean }

export function useRoute() {
  const [route, setRoute] = useState<Route>(() =>
    parseHash(typeof window !== 'undefined' ? window.location.hash : ''),
  )

  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash))
    window.addEventListener('hashchange', onChange)
    window.addEventListener('popstate', onChange)
    return () => {
      window.removeEventListener('hashchange', onChange)
      window.removeEventListener('popstate', onChange)
    }
  }, [])

  const navigate = useCallback((view: PortalView, opts?: NavigateOptions) => {
    const next: Route = { view, agentId: opts?.agentId ?? null }
    const hash = routeToHash(next)
    if (opts?.replace) {
      window.history.replaceState(null, '', hash)
      setRoute(next)
      return
    }
    if (window.location.hash === hash) { setRoute(next); return }
    // Assigning location.hash pushes a history entry AND fires hashchange, which
    // the listener above turns into a state update.
    window.location.hash = hash
  }, [])

  const openAgent = useCallback((agentId: string | null) => navigate('agents', { agentId }), [navigate])

  return { route, view: route.view, agentId: route.agentId, navigate, openAgent }
}
