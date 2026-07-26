import React from 'react'

/**
 * Trust card (Batch A4, restyled). Sits to the right of the agent header and
 * restates the propose-only contract on every agent page: the agent prepares
 * work; nothing is sent or changed without your approval. Always visible, never
 * dismissable.
 */
export function AgentTrustCard({ agentName }: { agentName?: string }) {
  const who = agentName || 'This agent'
  return (
    <aside className="dp-agentws__trust" role="note" aria-label="How this agent works">
      <span className="dp-agentws__trust-mark" aria-hidden="true">🛡️</span>
      <div>
        <p className="dp-agentws__trust-title">DayPilot drafts, you approve.</p>
        <p className="dp-agentws__trust-text">
          {who} prepares emails, documents, and actions for your review — nothing is sent, changed, or delegated
          without your approval in the Approval Center.
        </p>
      </div>
    </aside>
  )
}
