import React, { useEffect, useState } from 'react'

type ApprovalRow = {
  id: string
  action: string
  summary: string
  risk: 'low' | 'medium' | 'high'
  resourceType: string
  status: 'pending' | 'approved' | 'rejected'
}

const SEED: ApprovalRow[] = [
  { id: 'a1', action: 'git.write', summary: 'Merge GitPilot patch → ruslanmv/DayPilot (6 files, risk medium)', risk: 'medium', resourceType: 'coding_run', status: 'pending' },
  { id: 'a2', action: 'email.send', summary: 'Send reply to pm@clientalpha.com — Re: deadline change', risk: 'medium', resourceType: 'email_draft', status: 'pending' },
  { id: 'a3', action: 'calendar.create', summary: "Create '15:30 Review block'", risk: 'low', resourceType: 'calendar_event', status: 'pending' },
]

type ApprovalCenterProps = { rows?: ApprovalRow[]; onClose: () => void }

function riskTone(r: string): 'healthy' | 'degraded' | 'offline' {
  return r === 'low' ? 'healthy' : r === 'medium' ? 'degraded' : 'offline'
}

/**
 * Central Approval Center: one queue for every sensitive action. The model
 * proposes; the human decides. Decisions are audited server-side.
 */
export function ApprovalCenter({ rows = SEED, onClose }: ApprovalCenterProps) {
  const [items, setItems] = useState(rows)

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  function decide(id: string, decision: 'approved' | 'rejected') {
    setItems((cur) => cur.map((r) => (r.id === id ? { ...r, status: decision } : r)))
  }

  const pending = items.filter((r) => r.status === 'pending')

  return (
    <div className="dp-modal-backdrop" onMouseDown={onClose}>
      <div className="dp-settings-panel" role="dialog" aria-modal="true" aria-label="Approval Center" onMouseDown={(e) => e.stopPropagation()}>
        <header className="dp-settings-panel__head">
          <h3>Approval Center · {pending.length} pending</h3>
          <button className="dp-icon-button" aria-label="Close" onClick={onClose}>✕</button>
        </header>
        <div className="dp-settings-panel__body">
          <div className="dp-settings-list">
            {items.map((row) => (
              <div key={row.id} className="dp-settings-row">
                <div className="dp-settings-row__head">
                  <span className={'dp-tag dp-tag--' + riskTone(row.risk)}>{row.risk}</span>
                  <strong>{row.action}</strong>
                  <span className="dp-pill dp-pill--muted">{row.resourceType}</span>
                </div>
                <p>{row.summary}</p>
                {row.status === 'pending' ? (
                  <div className="dp-email__actions">
                    <button className="dp-send-button" onClick={() => decide(row.id, 'approved')}>Approve</button>
                    <button className="dp-ghost-button" onClick={() => decide(row.id, 'rejected')}>Reject</button>
                  </div>
                ) : (
                  <span className={'dp-tag dp-tag--' + (row.status === 'approved' ? 'healthy' : 'offline')}>{row.status}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
