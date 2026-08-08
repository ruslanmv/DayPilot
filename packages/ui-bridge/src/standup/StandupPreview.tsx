import React from 'react'

import { bulletKindLabel, type Bullet } from './standupClient'

/**
 * One section of the Slack update: read it, trace it, or edit it.
 *
 * Two modes, never both at once. Reading shows the bullets as buttons — click
 * one to see the evidence behind it. Editing swaps in a textarea holding the
 * literal text that will be posted.
 *
 * They are exclusive because showing both renders every line twice, which
 * reads as duplication and makes the section twice as tall for no information.
 * Reading is the default: the point of the 18:00 review is to check claims
 * against evidence, and most days end with approving them unchanged.
 */
export function StandupPreview({
  index,
  heading,
  question,
  value,
  bullets,
  editable,
  onChange,
  onSelectBullet,
  selectedEvidenceIds,
}: {
  index: 1 | 2 | 3
  heading: string
  question: string
  value: string
  bullets: Bullet[]
  editable: boolean
  onChange: (next: string) => void
  onSelectBullet: (evidenceIds: string[]) => void
  selectedEvidenceIds: string[]
}) {
  const [editing, setEditing] = React.useState(false)
  const id = `standup-section-${index}`
  const unsupported = bullets.filter((b) => b.kind !== 'observed')
  const selected = new Set(selectedEvidenceIds)

  // A draft that can no longer be edited (sent, skipped) must not show an
  // editor that silently does nothing.
  const showEditor = editing && editable

  return (
    <section className="dp-standup__section">
      <div className="dp-standup__section-head">
        <span className="dp-standup__section-num" aria-hidden="true">{index}</span>
        <label className="dp-standup__section-label" htmlFor={showEditor ? id : undefined}>
          {heading}
        </label>
        <span className="dp-standup__section-q">{question}</span>
        {editable && (
          <button
            type="button"
            className="dp-standup__section-edit"
            aria-pressed={showEditor}
            onClick={() => setEditing((v) => !v)}
          >
            {showEditor ? 'Done' : 'Edit'}
          </button>
        )}
      </div>

      {showEditor ? (
        <textarea
          id={id}
          className="dp-standup__textarea"
          value={value}
          autoFocus
          aria-describedby={unsupported.length ? `${id}-warn` : undefined}
          rows={Math.max(3, value.split('\n').length + 1)}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : bullets.length > 0 ? (
        <ul className="dp-standup__bullets">
          {bullets.map((b, i) => {
            const label = bulletKindLabel(b.kind)
            const isSelected = b.evidenceIds.some((eid) => selected.has(eid))
            return (
              <li key={`${id}-b${i}`}>
                <button
                  type="button"
                  className={'dp-standup__bullet' + (isSelected ? ' is-selected' : '')}
                  aria-pressed={isSelected}
                  onClick={() => onSelectBullet(b.evidenceIds)}
                  disabled={b.evidenceIds.length === 0}
                  title={b.evidenceIds.length ? 'Show supporting evidence' : 'No evidence behind this line'}
                >
                  <span className="dp-standup__bullet-text">{b.text}</span>
                  {label && <span className="dp-standup__bullet-flag">{label}</span>}
                </button>
              </li>
            )
          })}
        </ul>
      ) : (
        /* Text the user typed by hand has no bullet provenance to render. */
        <pre className="dp-standup__plain">{value || '—'}</pre>
      )}

      {unsupported.length > 0 && (
        <p id={`${id}-warn`} className="dp-standup__warn" role="status">
          {unsupported.length === 1 ? '1 line has' : `${unsupported.length} lines have`} no
          supporting activity. Confirm or rewrite before approving.
        </p>
      )}
    </section>
  )
}
