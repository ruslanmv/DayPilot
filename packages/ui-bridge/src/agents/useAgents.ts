import { useCallback, useEffect, useMemo, useState } from 'react'

import { homepilotApi, type AgentProfile } from '../settings/homepilotClient'

/**
 * Agents directory data (Batch A2).
 *
 * Reads DayPilot's backend-owned agent references (`/v1/agents/profiles`). When
 * the HomePilot runtime is off the endpoint 404s and we surface a distinct
 * `runtime_off` state so the directory can point the user at Settings instead of
 * looking broken. Favorite/enable changes persist to the backend and update in
 * place (no full reload flicker).
 */
export type AgentsLoad = 'loading' | 'runtime_off' | 'ready' | 'error'
export type AgentFilterId = 'all' | 'installed' | 'homepilot' | 'imported' | 'favorites'

export const AGENT_FILTERS: { id: AgentFilterId; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'installed', label: 'Installed' },
  { id: 'homepilot', label: 'HomePilot' },
  { id: 'imported', label: 'Imported' },
  { id: 'favorites', label: 'Favorites' },
]

function matchesFilter(a: AgentProfile, filter: AgentFilterId): boolean {
  switch (filter) {
    case 'installed': return a.enabled
    case 'homepilot': return a.homepilotModelId.startsWith('persona:')
    case 'imported': return !a.homepilotModelId.startsWith('persona:')  // local .hpersona imports (none yet)
    case 'favorites': return a.favorite
    case 'all':
    default: return true
  }
}

function matchesSearch(a: AgentProfile, q: string): boolean {
  if (!q) return true
  const hay = `${a.name} ${a.role} ${a.description} ${a.capabilities.join(' ')}`.toLowerCase()
  return hay.includes(q.toLowerCase())
}

export function useAgents() {
  const [load, setLoad] = useState<AgentsLoad>('loading')
  const [agents, setAgents] = useState<AgentProfile[]>([])
  const [filter, setFilter] = useState<AgentFilterId>('all')
  const [search, setSearch] = useState('')

  const reload = useCallback(async () => {
    setLoad('loading')
    const r = await homepilotApi.listProfiles()
    if (!r.ok) { setLoad(r.status === 404 ? 'runtime_off' : 'error'); return }
    setAgents(r.data.profiles)
    setLoad('ready')
  }, [])
  useEffect(() => { reload() }, [reload])

  const patchLocal = useCallback((next: AgentProfile) => {
    setAgents((cur) => cur.map((a) => (a.id === next.id ? next : a)))
  }, [])

  const toggleFavorite = useCallback(async (a: AgentProfile) => {
    const r = await homepilotApi.setFavorite(a.id, !a.favorite)
    if (r.ok) patchLocal(r.data)
  }, [patchLocal])

  const toggleEnabled = useCallback(async (a: AgentProfile) => {
    const r = await homepilotApi.setEnabled(a.id, !a.enabled)
    if (r.ok) patchLocal(r.data)
  }, [patchLocal])

  const visible = useMemo(
    () => agents.filter((a) => matchesFilter(a, filter) && matchesSearch(a, search)),
    [agents, filter, search],
  )

  // Per-filter counts for the chip badges (independent of the active filter).
  const filterCounts = useMemo(() => {
    const c = {} as Record<AgentFilterId, number>
    for (const f of AGENT_FILTERS) c[f.id] = agents.filter((a) => matchesFilter(a, f.id)).length
    return c
  }, [agents])

  return {
    load, agents, visible, filter, search,
    setFilter, setSearch, reload, toggleFavorite, toggleEnabled,
    filterCounts,
    counts: { total: agents.length, shown: visible.length },
  }
}
