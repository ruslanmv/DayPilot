import React, { useEffect, useState } from 'react'
import type { DayPilotDesignBundle, DayPilotDesignReview } from '@daypilot/shared-types'
import { DESIGN_BUNDLE, DESIGN_REVIEW } from './designData'

type DesignReviewProps = {
  bundle?: DayPilotDesignBundle
  review?: DayPilotDesignReview
  onClose: () => void
}

function severityTone(severity: string): 'healthy' | 'degraded' | 'offline' {
  return severity === 'info' || severity === 'minor' ? 'healthy' : severity === 'major' ? 'degraded' : 'offline'
}

/**
 * Matrix Designer surface: the ordered batch roadmap (the plan Matrix Designer
 * produces before GitPilot builds) and the design-quality review with findings.
 */
export function DesignReview({ bundle = DESIGN_BUNDLE, review = DESIGN_REVIEW, onClose }: DesignReviewProps) {
  const [tab, setTab] = useState<'roadmap' | 'review'>('roadmap')

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="dp-modal-backdrop" onMouseDown={onClose}>
      <div
        className="dp-design"
        role="dialog"
        aria-modal="true"
        aria-label="Matrix Designer"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="dp-settings-panel__head">
          <h3>Matrix Designer · {bundle.title}</h3>
          <button className="dp-icon-button" aria-label="Close" onClick={onClose}>✕</button>
        </header>
        <div className="dp-design__tabs" role="tablist">
          <button role="tab" aria-selected={tab === 'roadmap'} className={'dp-ghost-button' + (tab === 'roadmap' ? ' is-active' : '')} onClick={() => setTab('roadmap')}>Batch roadmap</button>
          <button role="tab" aria-selected={tab === 'review'} className={'dp-ghost-button' + (tab === 'review' ? ' is-active' : '')} onClick={() => setTab('review')}>Design review</button>
        </div>
        <div className="dp-design__body">
          {tab === 'roadmap' && (
            <div className="dp-settings-list">
              <p className="dp-muted">{bundle.framework} · {bundle.visualTarget}</p>
              <ol className="dp-design__batches">
                {bundle.batches.map((batch) => (
                  <li key={batch.id} className="dp-settings-row">
                    <div className="dp-settings-row__head">
                      <strong>[{batch.id}] {batch.title}</strong>
                      {batch.dependsOn.length > 0 && (
                        <span className="dp-pill dp-pill--muted">after {batch.dependsOn.join(', ')}</span>
                      )}
                      {batch.estimateHours != null && <span className="dp-pill dp-pill--muted">{batch.estimateHours}h</span>}
                    </div>
                    <p>{batch.description}</p>
                  </li>
                ))}
              </ol>
            </div>
          )}
          {tab === 'review' && (
            <div className="dp-settings-list">
              <div className="dp-settings-row dp-settings-row--split">
                <span>{review.target}</span>
                <span className={'dp-tag dp-tag--' + (review.score >= 75 ? 'healthy' : review.score >= 60 ? 'degraded' : 'offline')}>
                  {review.grade} · {review.score}/100
                </span>
              </div>
              {review.findings.map((finding, i) => (
                <div key={i} className="dp-settings-row">
                  <div className="dp-settings-row__head">
                    <span className={'dp-tag dp-tag--' + severityTone(finding.severity)}>{finding.severity}</span>
                    <strong>{finding.area}</strong>
                  </div>
                  <p>{finding.note}</p>
                </div>
              ))}
              {review.suggestions.length > 0 && (
                <p className="dp-muted">Suggestions: {review.suggestions.join(' · ')}</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
