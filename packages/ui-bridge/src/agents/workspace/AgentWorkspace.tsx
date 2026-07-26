import React, { useState } from 'react'

import type { AgentProfile } from '../../settings/homepilotClient'
import { AgentActivityPanel } from './AgentActivityPanel'
import { AgentChatPanel } from './AgentChatPanel'
import { AgentFilesPanel } from './AgentFilesPanel'
import { AgentRulesPanel } from './AgentRulesPanel'
import { AgentTaskPanel } from './AgentTaskPanel'
import { AgentTrustCard } from './AgentTrustCard'
import { AgentWorkspaceHeader } from './AgentWorkspaceHeader'
import { DelegationPanel } from './DelegationEvent'
import type { AgentActivityEntry, AgentFileRef } from './types'

type Detail = 'activity' | 'delegations' | 'files' | 'rules'
const TABS: { id: Detail; label: string }[] = [
  { id: 'activity', label: 'Activity' },
  { id: 'delegations', label: 'Delegations' },
  { id: 'files', label: 'Files' },
  { id: 'rules', label: 'Rules' },
]

/**
 * Dedicated agent workspace (Batch A4–A9, restyled to the product design).
 *
 * A genuinely separate page at `/agents/:id`. Top bar: breadcrumb (left) +
 * Activity / Delegations / Files / Rules (right). Header: the agent's identity
 * beside the always-on trust card. Body: a live, read-only conversation beside
 * the task rail (Overview / Active / Waiting for approval / Completed). Selecting
 * a tab swaps the body for that panel; "Conversation" returns to chat + tasks.
 */
export function AgentWorkspace({
  agent,
  onBack,
  activity = [],
  files = [],
}: {
  agent: AgentProfile
  onBack: () => void
  activity?: AgentActivityEntry[]
  files?: AgentFileRef[]
}) {
  const [detail, setDetail] = useState<Detail | null>(null)
  const [taskRefresh, setTaskRefresh] = useState(0)

  return (
    <section className="dp-agentws" aria-label={`${agent.name} workspace`}>
      <div className="dp-agentws__bar">
        <nav className="dp-agentws__crumbnav" aria-label="Breadcrumb">
          <button type="button" className="dp-agentws__backbtn" onClick={onBack} aria-label="Back to agents">←</button>
          <span className="dp-agentws__crumb"><button type="button" className="dp-linkbtn" onClick={onBack}>Agents</button> / <b>{agent.name}</b></span>
        </nav>
        <div className="dp-agentws__tabs" role="tablist" aria-label="Agent details">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={detail === t.id}
              className={'dp-agentws__tab' + (detail === t.id ? ' is-active' : '')}
              onClick={() => setDetail(detail === t.id ? null : t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="dp-agentws__top">
        <AgentWorkspaceHeader agent={agent} />
        <AgentTrustCard agentName={agent.name} />
      </div>

      {detail === null ? (
        <div className="dp-agentws__body">
          <AgentChatPanel agent={agent} onTurn={() => setTaskRefresh((k) => k + 1)} />
          <AgentTaskPanel agent={agent} refreshKey={taskRefresh} />
        </div>
      ) : (
        <div className="dp-agentws__detail" role="tabpanel" aria-label={detail}>
          <button type="button" className="dp-linkbtn dp-agentws__detail-back" onClick={() => setDetail(null)}>← Back to conversation</button>
          {detail === 'activity' && <AgentActivityPanel agentName={agent.name} entries={activity} />}
          {detail === 'delegations' && <DelegationPanel agent={agent} />}
          {detail === 'files' && <AgentFilesPanel agentName={agent.name} files={files} />}
          {detail === 'rules' && <AgentRulesPanel agent={agent} />}
        </div>
      )}
    </section>
  )
}
