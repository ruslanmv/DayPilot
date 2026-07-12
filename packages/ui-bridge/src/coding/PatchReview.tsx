import React, { useEffect, useState } from 'react'
import type { DayPilotCodingReviewDecision, DayPilotCodingRun } from '@daypilot/shared-types'
import { CODING_RUNS } from './codingData'

type PatchReviewProps = {
  runs?: DayPilotCodingRun[]
  onClose: () => void
}

function riskTone(risk: string): 'healthy' | 'degraded' | 'offline' {
  return risk === 'low' ? 'healthy' : risk === 'medium' ? 'degraded' : 'offline'
}

/**
 * Patch review: the human-readable summary of an AI change, its files, tests,
 * and risk, with Approve / Request changes / Reject. A repository write is
 * approval-gated server-side; this is where the human decides.
 */
export function PatchReview({ runs = CODING_RUNS, onClose }: PatchReviewProps) {
  const [items, setItems] = useState(runs)
  const [activeId, setActiveId] = useState(runs[0]?.id)
  const active = items.find((r) => r.id === activeId)

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  function decide(decision: DayPilotCodingReviewDecision) {
    if (!active) return
    const nextStatus =
      decision === 'approve' ? 'approved' : decision === 'reject' ? 'rejected' : 'needs_review'
    setItems((current) =>
      current.map((r) => (r.id === active.id ? { ...r, status: nextStatus } : r)),
    )
  }

  return (
    <div className="dp-modal-backdrop" onMouseDown={onClose}>
      <div
        className="dp-patch"
        role="dialog"
        aria-modal="true"
        aria-label="Patch review"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="dp-settings-panel__head">
          <h3>Patch review · {items.length} awaiting</h3>
          <button className="dp-icon-button" aria-label="Close" onClick={onClose}>✕</button>
        </header>
        <div className="dp-patch__body">
          <ul className="dp-patch__list" aria-label="Coding runs">
            {items.map((run) => (
              <li key={run.id}>
                <button
                  className={'dp-patch__item' + (run.id === activeId ? ' is-active' : '')}
                  onClick={() => setActiveId(run.id)}
                >
                  <span className="dp-patch__repo">{run.repo}</span>
                  <span className={'dp-tag dp-tag--' + riskTone(run.risk)}>{run.risk}</span>
                  <span className="dp-patch__status">{run.status.replace('_', ' ')}</span>
                </button>
              </li>
            ))}
          </ul>
          {active && (
            <div className="dp-patch__detail">
              <div className="dp-patch__eyebrow">{active.executor.toUpperCase()} · {active.branch}</div>
              <p className="dp-patch__summary">{active.diffSummary}</p>
              <div className="dp-patch__facts">
                <span>{active.filesChanged} files</span>
                <span>
                  tests {active.testsPassed ?? '–'}/{active.testsTotal ?? '–'}
                </span>
                <span className={'dp-tag dp-tag--' + riskTone(active.risk)}>
                  risk {active.risk} · {active.riskScore ?? '–'}
                </span>
              </div>
              <div className="dp-patch__actions">
                <button className="dp-send-button" onClick={() => decide('approve')}>Approve</button>
                <button className="dp-ghost-button" onClick={() => decide('request_changes')}>Request changes</button>
                <button className="dp-ghost-button" onClick={() => decide('reject')}>Reject</button>
              </div>
              <p className="dp-muted dp-patch__note">
                Approving does not write the repo. The write is a separate,
                approval-gated action enforced by the API.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
