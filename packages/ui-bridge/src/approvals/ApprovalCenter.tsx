import React, { useCallback, useEffect, useState } from 'react'

import { approvalsApi, type ApprovalRow } from './approvalsClient'

type ApprovalCenterProps = { rows?: ApprovalRow[]; onClose: () => void }

function riskTone(r: string): 'healthy' | 'degraded' | 'offline' {
  return r === 'low' ? 'healthy' : r === 'medium' ? 'degraded' : 'offline'
}

/**
 * Central Approval Center: one queue for every sensitive action. The model
 * proposes; the human decides. Decisions are audited server-side.
 *
 * The queue and the decisions are the server's — `/v1/approvals` and
 * `/v1/approvals/{id}/decide`. That matters more here than anywhere else in the
 * product: a panel that kept its own list would show approvals the backend
 * never issued and record decisions nowhere, which is precisely the promise
 * this screen exists to keep. A rejected decision (RBAC, or an item someone
 * else already decided) is surfaced rather than swallowed, and the row stays
 * pending until the server says otherwise.
 *
 * `rows` is injectable for tests and previews; without it the real queue loads.
 */
export function ApprovalCenter({ rows, onClose }: ApprovalCenterProps) {
  const [items, setItems] = useState<ApprovalRow[]>(rows || [])
  const [loading, setLoading] = useState(!rows)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    const r = await approvalsApi.list()
    if (r.ok) { setItems(r.rows); setError(null) } else setError(r.error)
    setLoading(false)
  }, [])

  useEffect(() => { if (!rows) void load() }, [rows, load])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  async function decide(id: string, decision: 'approved' | 'rejected') {
    setBusy(id)
    setError(null)
    try {
      const r = await approvalsApi.decide(id, decision)
      if (!r.ok) { setError(r.error); return }
      // Re-read rather than patching locally: deciding one approval can execute
      // an agent action that creates or resolves others.
      await load()
    } finally { setBusy(null) }
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
          {error && <p className="dp-standupcard__error" role="alert">{error}</p>}
          <div className="dp-settings-list">
            {loading && <p className="dp-home__card-empty">Loading the queue…</p>}
            {!loading && items.length === 0 && (
              <p className="dp-home__card-empty">
                Nothing is waiting on you. Sensitive actions appear here before they run.
              </p>
            )}
            {items.map((row) => (
              <div key={row.id} className="dp-settings-row">
                <div className="dp-settings-row__head">
                  <span className={'dp-tag dp-tag--' + riskTone(row.risk)}>{row.risk}</span>
                  <strong>{row.action}</strong>
                  {row.resourceType && <span className="dp-pill dp-pill--muted">{row.resourceType}</span>}
                </div>
                <p>{row.summary}</p>
                {row.status === 'pending' ? (
                  <div className="dp-email__actions">
                    <button className="dp-send-button" disabled={busy === row.id}
                            onClick={() => void decide(row.id, 'approved')}>
                      {busy === row.id ? 'Working…' : 'Approve'}
                    </button>
                    <button className="dp-ghost-button" disabled={busy === row.id}
                            onClick={() => void decide(row.id, 'rejected')}>Reject</button>
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
