import React from 'react'

import type { StandupEvidence } from './standupClient'

const SOURCE_LABEL: Record<string, string> = {
  daypilot: 'DayPilot',
  github: 'GitHub',
  calendar: 'Calendar',
  agents: 'Agent',
  manual: 'Your note',
}

function when(iso?: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? ''
    : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

/**
 * The provenance line, with nothing repeated and nothing empty.
 *
 * A project called "DayPilot" tracked by the DayPilot source would otherwise
 * render "DayPilot · DayPilot", and an item with no reference would leave a
 * trailing separator. Both are small, and both make the drawer look careless
 * in exactly the place the user goes to check whether to trust a claim.
 */
function meta(item: StandupEvidence): string[] {
  const source = SOURCE_LABEL[item.source] || item.source
  const parts = [source]
  if (item.projectName && item.projectName !== source) parts.push(item.projectName)
  const time = when(item.occurredAt)
  if (time) parts.push(time)
  if (item.sourceRef) parts.push(item.sourceRef)
  return parts
}

/**
 * The answer to "why does it say I did that?".
 *
 * Every bullet in the update traces back to rows shown here, each with its
 * source, its time and a reference to the real object. Excluding an item is
 * how a user removes personal or irrelevant activity without editing prose —
 * and the exclusion survives a regenerate, so it never has to be repeated.
 */
export function EvidenceDrawer({
  evidence,
  highlightedIds,
  busyId,
  onToggleInclude,
  onAddNote,
}: {
  evidence: StandupEvidence[]
  highlightedIds: string[]
  busyId?: string | null
  onToggleInclude: (item: StandupEvidence) => void
  onAddNote: (text: string) => void
}) {
  const [note, setNote] = React.useState('')
  const highlighted = new Set(highlightedIds)
  const shown = highlightedIds.length
    ? evidence.filter((e) => highlighted.has(e.id))
    : evidence

  return (
    <aside className="dp-standup__evidence" aria-label="Supporting evidence">
      <h3 className="dp-standup__evidence-title">Evidence</h3>
      <p className="dp-standup__evidence-hint">
        {highlightedIds.length
          ? 'Showing what this line is based on.'
          : 'Select a line to see what it is based on.'}
      </p>

      {shown.length === 0 && (
        <p className="dp-standup__evidence-empty">
          No activity was recorded for this day. Add a note below rather than
          letting the update claim work that was not tracked.
        </p>
      )}

      <ul className="dp-standup__evidence-list">
        {shown.map((item) => (
          <li
            key={item.id}
            className={
              'dp-standup__evidence-item'
              + (item.included ? '' : ' is-excluded')
              + (highlighted.has(item.id) ? ' is-highlighted' : '')
            }
          >
            <div className="dp-standup__evidence-main">
              <span className="dp-standup__evidence-summary">{item.summary}</span>
              <span className="dp-standup__evidence-meta">
                {meta(item).join(' · ')}
              </span>
            </div>
            <button
              type="button"
              className="dp-standup__evidence-toggle"
              aria-pressed={!item.included}
              disabled={busyId === item.id}
              onClick={() => onToggleInclude(item)}
            >
              {item.included ? 'Exclude' : 'Include'}
            </button>
          </li>
        ))}
      </ul>

      <form
        className="dp-standup__note"
        onSubmit={(e) => {
          e.preventDefault()
          const text = note.trim()
          if (!text) return
          onAddNote(text)
          setNote('')
        }}
      >
        <label className="dp-standup__note-label" htmlFor="standup-note">
          Add work DayPilot could not see
        </label>
        <textarea
          id="standup-note"
          className="dp-standup__note-input"
          value={note}
          rows={3}
          placeholder="A conversation, a decision, anything outside the connected tools…"
          onChange={(e) => setNote(e.target.value)}
        />
        <button type="submit" className="dp-standup__note-add" disabled={!note.trim()}>
          Add note
        </button>
      </form>
    </aside>
  )
}
