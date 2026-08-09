import React, { useEffect, useRef, useState } from 'react'
import { TRANSFORMS, type SlackDraft, type TransformId } from './slackTypes'

/**
 * The draft, its provenance, and the one button that leaves the building.
 *
 * Three things here are load-bearing rather than decorative:
 *
 * * **"Based on N sources"** — a draft you cannot trace is a draft you should
 *   not send, so the chips are always visible, not behind a disclosure.
 * * **"AI draft — not sent. You remain in control."** — stated on the draft
 *   itself, where the decision happens, not once in onboarding.
 * * **Send opens an approval.** The button says so, and the server would refuse
 *   anyway; the label just stops it being a surprise.
 */

const TRANSFORM_ICONS: Record<TransformId, React.ReactNode> = {
  shorter: <><path d="M4 7h16" /><path d="M4 12h11" /><path d="M4 17h7" /></>,
  direct: <><path d="M3 12h13" /><path d="m13 7 5 5-5 5" /><path d="M21 5v14" /></>,
  detailed: <><path d="M4 6h16" /><path d="M4 10h16" /><path d="M4 14h16" /><path d="M4 18h10" /></>,
  friendly: <><circle cx="12" cy="12" r="9" /><path d="M8.5 14.5a4.5 4.5 0 0 0 7 0" /><path d="M9 9.5h.01M15 9.5h.01" /></>,
}

function SourceIcon({ type }: { type: string }) {
  const glyph = type === 'github' ? '' : type === 'email' ? '✉' : type === 'project' ? '📁'
    : type === 'tasks' ? '☑' : type === 'documents' ? '📄' : '💬'
  return <span className="dp-slack__source-ic" aria-hidden="true">{glyph}</span>
}

export type SlackDraftEditorProps = {
  draft: SlackDraft | null
  /** Null while there is no draft — the button offers to prepare one. */
  onPrepare: () => void
  onChangeText: (text: string) => void
  onTransform: (kind: TransformId) => void
  onSend: () => void
  onDiscard: () => void
  onOpenInSlack: () => void
  onUndo: () => void
  /** True right after "Use this", so Undo is offered where the change happened. */
  canUndo: boolean
  busy?: boolean
  /** The gateway's answer to the last send: an approval id, never a Slack ts. */
  approvalNote?: string | null
  error?: string | null
}

export function SlackDraftEditor({
  draft, onPrepare, onChangeText, onTransform, onSend, onDiscard, onOpenInSlack,
  onUndo, canUndo, busy = false, approvalNote = null, error = null,
}: SlackDraftEditorProps) {
  const [text, setText] = useState(draft?.text ?? '')
  const [showSources, setShowSources] = useState(false)
  const areaRef = useRef<HTMLTextAreaElement>(null)

  // Follow the draft when the server changes it (transform, accept, undo), but
  // never clobber what the user is typing on an unrelated re-render.
  useEffect(() => { setText(draft?.text ?? '') }, [draft?.id, draft?.updatedAt, draft?.text])

  // Grow to fit. Counting newlines was not enough — on a phone every bullet
  // wraps to two or three lines, and the clipped line was the closing one that
  // says what happens next. Measuring the content is the only honest answer.
  useEffect(() => {
    const area = areaRef.current
    if (!area) return
    area.style.height = 'auto'
    area.style.height = `${area.scrollHeight}px`
  }, [text])

  if (!draft) {
    return (
      <div className="dp-slack__draft dp-slack__draft--empty">
        <p className="dp-slack__hint">
          DayPilot did not prepare a reply for this one — it read as something that does not
          need an answer. If you disagree, ask for a draft.
        </p>
        <button type="button" className="dp-btn dp-btn--ghost" onClick={onPrepare} disabled={busy}>
          Draft a reply
        </button>
      </div>
    )
  }

  const locked = draft.status === 'sent' || draft.status === 'discarded'
  const pending = draft.status === 'sending'

  return (
    <div className="dp-slack__draft">
      <div className="dp-slack__draft-eyebrow">
        <SparkIcon />
        <span>AI SUGGESTED REPLY ({draft.kind === 'compose' ? 'NEW MESSAGE' : 'DRAFT'})</span>
        {canUndo && (
          <button type="button" className="dp-slack__undo" onClick={onUndo}>Undo</button>
        )}
      </div>

      {/* The draft is editable in place. An earlier version showed it once as
          read-only text and again in a composer below, which meant two copies of
          the same message on screen and no way to tell which one would be sent. */}
      <article className="dp-slack__draft-card">
        <div className="dp-slack__format" role="group" aria-label="Formatting">
          {['B', 'I', '</>', '•', '1.', '⌗', '🔗', '☺'].map((glyph, index) => (
            <button
              key={glyph}
              type="button"
              className={'dp-slack__format-btn' + (index === 0 ? ' is-bold' : index === 1 ? ' is-italic' : '')}
              aria-label={`Format: ${glyph}`}
              onClick={() => areaRef.current?.focus()}
            >
              {glyph}
            </button>
          ))}
        </div>
        <textarea
          ref={areaRef}
          className="dp-slack__draft-text"
          placeholder="Edit the draft or ask AI to improve it…"
          rows={3}
          value={text}
          disabled={locked}
          onChange={(event) => setText(event.target.value)}
          onBlur={() => { if (text !== draft.text) onChangeText(text) }}
          aria-label="Draft message"
        />

        <div className="dp-slack__transforms" role="group" aria-label="Quick rewrites">
          {TRANSFORMS.map((t) => (
            <button
              key={t.id}
              type="button"
              className="dp-slack__transform"
              onClick={() => onTransform(t.id)}
              disabled={busy || locked}
            >
              <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                {TRANSFORM_ICONS[t.id]}
              </svg>
              {t.label}
            </button>
          ))}
        </div>

        <div className="dp-slack__sources">
          <span className="dp-slack__sources-label">
            Based on {draft.sources.length} source{draft.sources.length === 1 ? '' : 's'}
          </span>
          <button
            type="button"
            className="dp-slack__sources-toggle"
            aria-expanded={showSources}
            onClick={() => setShowSources((open) => !open)}
          >
            {showSources ? 'Hide sources' : 'View sources'}
          </button>
        </div>
        <div className="dp-slack__source-chips">
          {draft.sources.slice(0, 3).map((source) => (
            <span key={source.label} className="dp-slack__source-chip" title={source.facts.join('\n')}>
              <SourceIcon type={source.type} />
              {source.label}
            </span>
          ))}
          {draft.sources.length > 3 && (
            <span className="dp-slack__source-chip dp-slack__source-chip--more">
              +{draft.sources.length - 3}
            </span>
          )}
        </div>

        {showSources && (
          <ul className="dp-slack__source-detail">
            {draft.sources.map((source) => (
              <li key={source.label}>
                <b>{source.label}</b>
                <ul>{source.facts.map((fact) => <li key={fact}>{fact}</li>)}</ul>
              </li>
            ))}
          </ul>
        )}

        {draft.withheldCount > 0 && (
          <p className="dp-slack__withheld">
            {draft.withheldCount} fact{draft.withheldCount === 1 ? ' was' : 's were'} withheld from
            this draft because the recipient should not be told{draft.withheldCount === 1 ? ' it' : ' them'}.
            DayPilot used them to avoid over-promising, and did not quote them.
          </p>
        )}
      </article>

      <p className="dp-slack__notice">
        <InfoIcon />
        AI draft — not sent. You remain in control.
      </p>

      {error && <p className="dp-slack__error">{error}</p>}
      {approvalNote && <p className="dp-slack__approval">{approvalNote}</p>}

      <footer className="dp-slack__draft-foot">
        <button type="button" className="dp-btn dp-btn--ghost" onClick={onOpenInSlack}>
          Open in Slack
        </button>
        {/* Discard sits with the other secondary action rather than welded to
            Send: a destructive button one pixel from the one you meant to press
            is a mistake waiting for a distracted morning. */}
        <button
          type="button"
          className="dp-btn dp-btn--ghost"
          onClick={onDiscard}
          disabled={busy || locked}
        >
          Discard
        </button>
        <span className="dp-slack__foot-spacer" />
        <button
          type="button"
          className="dp-btn dp-btn--primary"
          onClick={() => { if (text !== draft.text) onChangeText(text); onSend() }}
          disabled={busy || locked || pending || !text.trim()}
          title="Sending opens an approval in the Approval Center. DayPilot never posts on its own."
        >
          <SendIcon />
          {pending ? 'Waiting for approval' : 'Send in Slack'}
        </button>
      </footer>
    </div>
  )
}

function SparkIcon() {
  return (
    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 12h9" /><path d="m11 8 4 4-4 4" /><path d="M19 6v12" />
    </svg>
  )
}

function InfoIcon() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" />
    </svg>
  )
}

function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="m4 12 16-8-6 8 6 8Z" />
    </svg>
  )
}
