import React, { useEffect, useRef, useState } from 'react'

import { AddAgentPanel } from './AddAgentPanel'
import { AgentCard } from './AgentCard'
import { AgentFilters } from './AgentFilters'
import { useAgents } from './useAgents'
import { AgentWorkspace } from './workspace/AgentWorkspace'

/**
 * Agents landing page — a staff directory (Batch A2, UX §1–2, §11–12).
 *
 * "Choose the agent first. Work with the agent on a separate page." The grid
 * never contains an open conversation: clicking a card opens the agent's own
 * dedicated workspace page (AgentWorkspace, Batch A4). Responsive ≤4-column
 * grid, six text+colour statuses, search / filter / favorites, and honest
 * empty / loading / error / runtime-off states. Fully keyboard-operable with an
 * accessible live region.
 */
/**
 * `openAgentId` / `onOpenAgent` are route-controlled (Batch A3): the open agent
 * lives in the URL (`#/agents/:agentId`) so it survives refresh and browser
 * back / forward. Opening records the current scroll offset so returning to the
 * directory restores the reader's place in the grid.
 */
export function AgentsLandingPage({
  onAddAgent,
  openAgentId = null,
  onOpenAgent,
}: {
  onAddAgent: () => void
  openAgentId?: string | null
  onOpenAgent?: (agentId: string | null) => void
}) {
  const { load, visible, agents, filter, search, setFilter, setSearch, reload, toggleFavorite, toggleEnabled, filterCounts } = useAgents()
  const liveRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<number>(0)
  const [bannerOpen, setBannerOpen] = useState(true)

  useEffect(() => {
    if (liveRef.current && load === 'ready') {
      liveRef.current.textContent = `${visible.length} agent${visible.length === 1 ? '' : 's'} shown.`
    }
  }, [load, visible.length])

  const openId = openAgentId
  const open = (agentId: string | null) => { if (onOpenAgent) onOpenAgent(agentId) }

  // `#/agents/add` — the HomePilot-centric add flow (A10). Reserved id; no real
  // agent uses it.
  if (openId === 'add') {
    return (
      <AddAgentPanel
        onBack={() => open(null)}
        onManageConnection={onAddAgent}
        onRefreshed={() => { open(null); reload() }}
      />
    )
  }

  const openAgent = agents.find((a) => a.id === openId) || null
  if (openAgent) {
    return <AgentWorkspace agent={openAgent} onBack={() => { open(null); requestAnimationFrame(() => window.scrollTo(0, scrollRef.current)) }} />
  }

  return (
    <section className="dp-agents" aria-label="Agents">
      <header className="dp-agents__head">
        <div>
          <h2 className="dp-agents__title">Agents</h2>
          <p className="dp-agents__sub">Choose an agent to open their workspace.</p>
        </div>
        <div className="dp-agents__actions">
          <div className="dp-agents__searchwrap">
            <svg className="dp-agents__searchicon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
            <input
              className="dp-agents__search"
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search agents by name, role, or specialty…"
              aria-label="Search agents"
            />
            <span className="dp-agents__kbd" aria-hidden="true">⌘K</span>
          </div>
          <button type="button" className="dp-agents__iconbtn" aria-label="Filter agents">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M3 5h18M6 12h12M10 19h4" /></svg>
          </button>
          <button type="button" className="dp-primary-button dp-agents__add" onClick={() => open('add')}>
            <span aria-hidden="true">+</span> Add agent
          </button>
        </div>
      </header>

      <AgentFilters active={filter} onChange={setFilter} counts={filterCounts} />

      {bannerOpen && (
        <div className="dp-agents__banner" role="note">
          <span className="dp-agents__banner-icon" aria-hidden="true">ⓘ</span>
          <span>Click any agent card to open their dedicated chat workspace on a separate page.</span>
          <button type="button" className="dp-agents__banner-x" aria-label="Dismiss" onClick={() => setBannerOpen(false)}>✕</button>
        </div>
      )}

      {load === 'loading' && (
        <div className="dp-agents__grid" aria-hidden="true">
          {Array.from({ length: 8 }).map((_, i) => <div key={i} className="dp-agentcard dp-agentcard--skeleton" />)}
        </div>
      )}

      {load === 'error' && (
        <div className="dp-agents__state">
          <p>We couldn’t load your agents.</p>
          <button type="button" className="dp-ghost-button" onClick={reload}>Try again</button>
        </div>
      )}

      {load === 'runtime_off' && (
        <div className="dp-agents__state">
          <h3>Build your AI staff</h3>
          <p>Connect a HomePilot installation to bring its agents into DayPilot. HomePilot owns the agents; DayPilot manages their work.</p>
          <button type="button" className="dp-primary-button" onClick={onAddAgent}>Connect HomePilot</button>
        </div>
      )}

      {load === 'ready' && agents.length === 0 && (
        <div className="dp-agents__state">
          <h3>Build your AI staff</h3>
          <p>Add a HomePilot agent or import a persona to start delegating work.</p>
          <div className="dp-agents__state-actions">
            <button type="button" className="dp-primary-button" onClick={() => open('add')}>Add your first agent</button>
          </div>
        </div>
      )}

      {load === 'ready' && agents.length > 0 && visible.length === 0 && (
        <div className="dp-agents__state"><p>No agents match “{search || filter}”. <button type="button" className="dp-linkbtn" onClick={() => { setSearch(''); setFilter('all') }}>Clear filters</button></p></div>
      )}

      {load === 'ready' && visible.length > 0 && (
        <div className="dp-agents__grid">
          {visible.map((a) => (
            <AgentCard
              key={a.id}
              agent={a}
              onOpen={(agent) => { scrollRef.current = window.scrollY; open(agent.id) }}
              onToggleFavorite={toggleFavorite}
              onToggleEnabled={toggleEnabled}
            />
          ))}
        </div>
      )}

      {load === 'ready' && visible.length > 0 && (
        <p className="dp-agents__footer">
          <span className="dp-agents__banner-icon" aria-hidden="true">ⓘ</span>
          Agents are HomePilot personas you can install or import to extend your team.
          <button type="button" className="dp-linkbtn" onClick={() => open('add')}>Learn more</button>
        </p>
      )}

      <div className="dp-sr-live" role="status" aria-live="polite" ref={liveRef} />
    </section>
  )
}
