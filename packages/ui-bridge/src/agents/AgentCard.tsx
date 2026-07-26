import React from 'react'

import { agentStatusLabel, type AgentProfile } from '../settings/homepilotClient'
import { capabilityIcon } from './agentIcons'

/**
 * One agent card in the staff directory (Batch A2, restyled to the product
 * design). Avatar (with a status-coloured ring) sits top-left; the presence pill
 * and favourite star sit top-right; name, role, a two-line description and a row
 * of capability chips (each with a glyph) read left-aligned below.
 *
 * The whole card is a single button: click / Enter / Space opens the agent's
 * dedicated workspace on a separate page — never an inline chat or side panel.
 * Status is text AND colour (never colour alone).
 */
function initials(name: string): string {
  const parts = name.trim().split(/\s+/).slice(0, 2)
  return parts.map((p) => p[0]?.toUpperCase() || '').join('') || 'A'
}

export function AgentCard({
  agent,
  onOpen,
  onToggleFavorite,
}: {
  agent: AgentProfile
  onOpen: (a: AgentProfile) => void
  onToggleFavorite: (a: AgentProfile) => void
}) {
  const statusText = agentStatusLabel(agent.status)
  const chips = agent.capabilities.slice(0, 3)

  return (
    <div
      role="button"
      tabIndex={0}
      className="dp-agentcard"
      aria-label={`${agent.name}, ${agent.role || 'Agent'}. ${statusText}. Open workspace.`}
      onClick={() => onOpen(agent)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen(agent) }
      }}
    >
      <div className="dp-agentcard__top">
        <div className={'dp-agentcard__portrait dp-agentcard__portrait--' + agent.status} aria-hidden="true">
          {agent.avatarUrl
            ? <img src={agent.avatarUrl} alt="" loading="lazy" onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }} />
            : <span className="dp-agentcard__initials">{initials(agent.name)}</span>}
        </div>
        <div className="dp-agentcard__badges">
          <span className={'dp-agentcard__status dp-agentcard__status--' + agent.status}>
            <span className="dp-agentcard__status-dot" aria-hidden="true" />{statusText}
          </span>
          <button
            type="button"
            className={'dp-agentcard__fav' + (agent.favorite ? ' is-on' : '')}
            aria-pressed={agent.favorite}
            aria-label={agent.favorite ? `Unfavorite ${agent.name}` : `Favorite ${agent.name}`}
            onClick={(e) => { e.stopPropagation(); onToggleFavorite(agent) }}
          >
            {agent.favorite ? '★' : '☆'}
          </button>
        </div>
      </div>

      <div className="dp-agentcard__name">{agent.name}</div>
      <div className="dp-agentcard__role">{agent.role || 'Agent'}</div>
      {agent.description && <p className="dp-agentcard__desc">{agent.description}</p>}

      {chips.length > 0 && (
        <div className="dp-agentcard__chips">
          {chips.map((c) => (
            <span key={c} className="dp-agentcard__chip">
              <span className="dp-agentcard__chip-icon">{capabilityIcon(c)}</span>{c}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
