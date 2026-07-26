import React from 'react'

import { filterIcon } from './agentIcons'
import { AGENT_FILTERS, type AgentFilterId } from './useAgents'

/**
 * Filter chips above the grid: each carries an icon and a live count; the
 * selected chip is clearly highlighted (Batch A2, restyled to the product
 * design).
 */
export function AgentFilters({
  active,
  onChange,
  counts,
}: {
  active: AgentFilterId
  onChange: (id: AgentFilterId) => void
  counts?: Record<AgentFilterId, number>
}) {
  return (
    <div className="dp-agentfilters" role="tablist" aria-label="Filter agents">
      {AGENT_FILTERS.map((f) => {
        const n = counts?.[f.id]
        return (
          <button
            key={f.id}
            type="button"
            role="tab"
            aria-selected={active === f.id}
            className={'dp-agentfilters__chip' + (active === f.id ? ' is-active' : '')}
            onClick={() => onChange(f.id)}
          >
            <span className="dp-agentfilters__icon">{filterIcon[f.id]}</span>
            {f.label}
            {typeof n === 'number' && <span className="dp-agentfilters__count">{n}</span>}
          </button>
        )
      })}
    </div>
  )
}
