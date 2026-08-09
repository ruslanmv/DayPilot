import React, { useEffect, useRef } from 'react'

import { agentStatusLabel, type AgentProfile } from '../../settings/homepilotClient'
import { AgentPortrait } from '../AgentPortrait'

/**
 * Agent workspace identity header (Batch A4, restyled). Large portrait with a
 * status ring, name + presence pill, "role · HomePilot persona", a short
 * description, and capability chips (with a "+N" overflow). The heading is
 * focused on mount so keyboard users land at the top of the new page. The
 * breadcrumb + tabs live in the workspace bar above this.
 */
export function AgentWorkspaceHeader({ agent }: { agent: AgentProfile }) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  useEffect(() => { headingRef.current?.focus() }, [agent.id])

  const shown = agent.capabilities.slice(0, 4)
  const extra = Math.max(0, agent.capabilities.length - shown.length)

  return (
    <header className="dp-agentws__head">
      <AgentPortrait
        name={agent.name}
        avatarUrl={agent.avatarUrl}
        className={'dp-agentws__portrait dp-agentcard__portrait--' + agent.status}
      />
      <div className="dp-agentws__ident">
        <h2 className="dp-agentws__name" tabIndex={-1} ref={headingRef}>
          {agent.name}
          <span className={'dp-agentcard__status dp-agentcard__status--' + agent.status}>
            <span className="dp-agentcard__status-dot" aria-hidden="true" />{agentStatusLabel(agent.status)}
          </span>
        </h2>
        <p className="dp-agentws__role">{agent.role || 'Agent'} <span className="dp-agentws__sep">·</span> <span aria-hidden="true">🏠</span> HomePilot persona</p>
        {agent.description && <p className="dp-agentws__desc">{agent.description}</p>}
        {shown.length > 0 && (
          <div className="dp-agentws__chips" aria-label="Capabilities">
            {shown.map((c) => <span key={c} className="dp-agentws__chip">{c}</span>)}
            {extra > 0 && <span className="dp-agentws__chip dp-agentws__chip--more">+{extra}</span>}
          </div>
        )}
      </div>
    </header>
  )
}
