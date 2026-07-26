import React, { useEffect, useState } from 'react'

import { homepilotApi, type AgentDelegationRow, type AgentProfile } from '../../settings/homepilotClient'

/**
 * Delegation view (Batch A9, UX §8). Shows the responsibility chain for every
 * delegation this agent is part of — ``You → Scarlett → Atlas`` — so it's always
 * clear who handed work to whom. Read-only: DayPilot governs delegation (depth,
 * cycles, worker limits, worker-permissions ≤ manager) on the backend; anything
 * a worker proposes still flows through the Approval Center.
 */
export function DelegationEvent({ row }: { row: AgentDelegationRow }) {
  return (
    <li className="dp-deleg">
      <div className="dp-deleg__chain" aria-label="Responsibility chain">
        {row.chain.map((name, i) => (
          <React.Fragment key={i}>
            {i > 0 && <span className="dp-deleg__arrow" aria-hidden="true">→</span>}
            <span className={'dp-deleg__node' + (i === 0 ? ' dp-deleg__node--you' : '')}>{name}</span>
          </React.Fragment>
        ))}
      </div>
      <p className="dp-deleg__meta">
        {row.manager} delegated to <strong>{row.worker}</strong>
        {row.capability ? <> · {row.capability}</> : null}
        {' '}<span className={'dp-deleg__status dp-deleg__status--' + row.status}>{row.status}</span>
      </p>
    </li>
  )
}

/** The Delegation panel for one agent — loads and lists its delegation chains. */
export function DelegationPanel({ agent }: { agent: AgentProfile }) {
  const [rows, setRows] = useState<AgentDelegationRow[]>([])
  const [load, setLoad] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    let alive = true
    homepilotApi.getAgentDelegations(agent.id).then((r) => {
      if (!alive) return
      if (r.ok) { setRows(r.data.delegations); setLoad('ready') }
      else setLoad('error')
    })
    return () => { alive = false }
  }, [agent.id])

  if (load === 'loading') return <p className="dp-agentws__col-empty">Loading…</p>
  if (load === 'error') return <p className="dp-agentws__col-empty">Couldn’t load delegations.</p>
  if (rows.length === 0) {
    return (
      <div className="dp-agentws__empty">
        <p><b>No delegations yet.</b></p>
        <p>When {agent.name} hands a sub-task to another agent, the responsibility chain (You → {agent.name} → …) appears here. You approve every action along the chain.</p>
      </div>
    )
  }
  return <ul className="dp-deleg-list" aria-label={`${agent.name} delegations`}>{rows.map((d) => <DelegationEvent key={d.id} row={d} />)}</ul>
}
