import React, { useEffect, useState } from 'react'
import type { SlackConversation } from './slackTypes'
import { conversationTitle } from './slackTypes'

/**
 * "+ New message" — pick a recipient, say what it is about, get a draft.
 *
 * The recipient list is the conversations DayPilot has actually traced, not the
 * whole workspace directory. Offering someone DayPilot has never observed would
 * mean offering to write a confident message with no context behind it.
 *
 * External recipients are labelled here rather than at send time: the audience
 * decides which facts the draft may use, so it has to be a visible choice made
 * before anything is written.
 */

export type SlackComposeProps = {
  recipients: SlackConversation[]
  onCancel: () => void
  onCompose: (input: { conversationId: string; instruction: string }) => void
  busy?: boolean
  error?: string | null
}

export function SlackCompose({ recipients, onCancel, onCompose, busy = false, error = null }: SlackComposeProps) {
  const [selected, setSelected] = useState(recipients[0]?.id ?? '')
  const [instruction, setInstruction] = useState('')

  useEffect(() => {
    function onKey(event: KeyboardEvent) { if (event.key === 'Escape') onCancel() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onCancel])

  const recipient = recipients.find((r) => r.id === selected) || null

  return (
    <div className="dp-modal-backdrop" onMouseDown={onCancel}>
      <div
        className="dp-slack__compose"
        role="dialog"
        aria-modal="true"
        aria-label="New Slack message"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <h3>New message</h3>
          <button type="button" className="dp-icon-button" aria-label="Close" onClick={onCancel}>✕</button>
        </header>

        <label className="dp-slack__compose-field">
          <span>To</span>
          <select value={selected} onChange={(event) => setSelected(event.target.value)}>
            {recipients.length === 0 && <option value="">No traced conversations yet</option>}
            {recipients.map((r) => (
              <option key={r.id} value={r.id}>
                {conversationTitle(r)}{r.audience === 'external' ? ' · external' : ''}
              </option>
            ))}
          </select>
        </label>

        <label className="dp-slack__compose-field">
          <span>What is this about?</span>
          <textarea
            rows={3}
            value={instruction}
            placeholder="Ask about the PR #142 review before tomorrow's deploy"
            onChange={(event) => setInstruction(event.target.value)}
          />
        </label>

        {recipient?.audience === 'external' && (
          <p className="dp-slack__compose-note">
            This recipient is outside your organisation. Internal-only facts will be used to keep
            the message accurate, but will not appear in it.
          </p>
        )}

        {error && <p className="dp-slack__error">{error}</p>}

        <footer>
          <span className="dp-slack__compose-policy">DayPilot drafts it. You send it.</span>
          <div>
            <button type="button" className="dp-btn dp-btn--ghost" onClick={onCancel}>Cancel</button>
            <button
              type="button"
              className="dp-btn dp-btn--primary"
              disabled={busy || !selected}
              onClick={() => onCompose({ conversationId: selected, instruction: instruction.trim() })}
            >
              {busy ? 'Drafting…' : 'Draft message'}
            </button>
          </div>
        </footer>
      </div>
    </div>
  )
}
