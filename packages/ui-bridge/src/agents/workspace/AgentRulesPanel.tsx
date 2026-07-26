import React from 'react'

import type { AgentProfile } from '../../settings/homepilotClient'

/**
 * Rules tab (Batch A4, UX §7). The guardrails governing this agent: propose-only
 * tool mode, approval-gated actions, and the fact that HomePilot owns the
 * persona while DayPilot never copies its identity, prompt, or memory. These are
 * the fixed contract rules — shown so the user always knows the boundaries.
 */
export function AgentRulesPanel({ agent }: { agent: AgentProfile }) {
  const rules = [
    {
      title: 'Propose-only',
      body: `${agent.name} can draft messages, tasks, and plans, but every action is a proposal. Nothing is sent or executed automatically.`,
    },
    {
      title: 'You approve every action',
      body: 'Sending email, changing files, or delegating work all route through the Approval Center. You are always the last step.',
    },
    {
      title: 'HomePilot owns the agent',
      body: `The persona, prompt, and memory live in HomePilot. DayPilot connects to ${agent.name} and manages their work — it never copies their identity.`,
    },
    {
      title: 'Scoped capabilities',
      body: agent.capabilities.length > 0
        ? `Limited to: ${agent.capabilities.join(', ')}.`
        : 'Capabilities are defined in HomePilot and honored here.',
    },
  ]
  return (
    <dl className="dp-agentws__rules" aria-label={`${agent.name} rules`}>
      {rules.map((r) => (
        <div key={r.title} className="dp-agentws__rule">
          <dt className="dp-agentws__rule-title">{r.title}</dt>
          <dd className="dp-agentws__rule-body">{r.body}</dd>
        </div>
      ))}
    </dl>
  )
}
