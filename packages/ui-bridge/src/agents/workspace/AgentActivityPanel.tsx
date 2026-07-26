import React from 'react'

import type { AgentActivityEntry } from './types'

/**
 * Activity tab (Batch A4). An audit-style timeline of what the agent proposed
 * and what you approved or declined — newest first. Read-only; entries are
 * appended by the approval + delegation flows in later batches.
 */
export function AgentActivityPanel({ agentName, entries }: { agentName: string; entries: AgentActivityEntry[] }) {
  if (entries.length === 0) {
    return (
      <div className="dp-agentws__empty">
        <p><b>No activity yet.</b></p>
        <p>Once {agentName} proposes work and you approve or decline it, a timeline of every action appears here.</p>
      </div>
    )
  }
  return (
    <ol className="dp-agentws__activity" aria-label={`${agentName} activity`}>
      {entries.map((e) => (
        <li key={e.id} className="dp-agentws__activity-item">
          <span className={'dp-agentws__activity-dot dp-agentws__activity-dot--' + (e.kind || 'note')} aria-hidden="true" />
          <div>
            <p className="dp-agentws__activity-summary">{e.summary}</p>
            {e.at && <span className="dp-agentws__activity-time">{e.at}</span>}
          </div>
        </li>
      ))}
    </ol>
  )
}
