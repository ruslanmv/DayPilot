import React, { useEffect, useRef, useState } from 'react'
import type { SlackDraft, SlackProposal } from './slackTypes'

/**
 * The AI Assistant panel, scoped to one conversation and one draft.
 *
 * Two rules it exists to enforce:
 *
 * 1. **It proposes; it never replaces.** Every answer arrives with
 *    *[Use this] [Insert] [Try again]*. Nothing it says reaches the draft until
 *    one of those is clicked, and *Use this* keeps the old text so Undo works.
 * 2. **It cannot reach Slack.** There is no send affordance here at all. The
 *    only path out is the draft's own Send button, which opens an approval.
 *
 * The context list at the bottom is the same allow-list the server enforces,
 * shown here so "what does it know about me?" has an answer on screen rather
 * than in documentation.
 */

export type AssistantTurn =
  | { role: 'user'; body: string; time: string }
  | { role: 'assistant'; body: string; time: string; proposal: SlackProposal | null }

const SUGGESTIONS = ['More formal', 'Add risks', 'Add timeline', 'Ask a question']

function now(): string {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
}

export type SlackAssistantPanelProps = {
  draft: SlackDraft | null
  turns: AssistantTurn[]
  onAsk: (instruction: string) => void
  onUseThis: (proposal: SlackProposal) => void
  onInsert: (proposal: SlackProposal) => void
  onTryAgain: (proposal: SlackProposal) => void
  onClose: () => void
  onManageContext: () => void
  busy?: boolean
}

export function SlackAssistantPanel({
  draft, turns, onAsk, onUseThis, onInsert, onTryAgain, onClose, onManageContext,
  busy = false,
}: SlackAssistantPanelProps) {
  const [tab, setTab] = useState<'chat' | 'history'>('chat')
  const [input, setInput] = useState('')
  const [showAll, setShowAll] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => { endRef.current?.scrollIntoView({ block: 'end' }) }, [turns.length])

  function submit(event: React.FormEvent) {
    event.preventDefault()
    const instruction = input.trim()
    if (!instruction || !draft) return
    setInput('')
    onAsk(instruction)
  }

  const sources = draft?.sources ?? []
  const shown = showAll ? sources : sources.slice(0, 4)

  return (
    <aside className="dp-slack__assistant" aria-label="AI Assistant">
      <header className="dp-slack__assistant-head">
        <span className="dp-slack__assistant-title">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M5 12h9" /><path d="m11 8 4 4-4 4" /><path d="M19 6v12" />
          </svg>
          AI Assistant
        </span>
        <button type="button" className="dp-slack__iconbtn" aria-label="Close AI Assistant" onClick={onClose}>✕</button>
      </header>

      <div className="dp-slack__assistant-tabs" role="tablist" aria-label="Assistant views">
        {(['chat', 'history'] as const).map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            className={'dp-slack__assistant-tab' + (tab === id ? ' is-active' : '')}
            onClick={() => setTab(id)}
          >
            {id === 'chat' ? 'Chat' : 'History'}
          </button>
        ))}
      </div>

      <div className="dp-slack__assistant-body">
        {tab === 'history' ? (
          <div className="dp-slack__history">
            {turns.filter((t) => t.role === 'user').length === 0 ? (
              <p className="dp-slack__hint">Nothing asked for this draft yet.</p>
            ) : (
              <ul>
                {turns.filter((t) => t.role === 'user').map((turn, index) => (
                  <li key={`${turn.time}-${index}`}>
                    <span className="dp-slack__history-time">{turn.time}</span> {turn.body}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : (
          <>
            {!draft && <p className="dp-slack__hint">Open a draft and the assistant can rewrite it with you.</p>}
            {turns.length === 0 && draft && (
              <p className="dp-slack__hint">
                Ask for a change in your own words — “make it more concise and add a clear next
                step”. Nothing is applied until you choose it.
              </p>
            )}
            {turns.map((turn, index) => (
              turn.role === 'user' ? (
                <div key={index} className="dp-slack__bubble dp-slack__bubble--user">
                  <p>{turn.body}</p>
                  <span className="dp-slack__bubble-time">{turn.time}</span>
                </div>
              ) : (
                <div key={index} className="dp-slack__bubble dp-slack__bubble--ai">
                  <div className="dp-slack__bubble-head">
                    <span className="dp-slack__ai-avatar" aria-hidden="true">✦</span>
                    <span>AI Assistant</span>
                    <span className="dp-slack__bubble-time">{turn.time}</span>
                  </div>
                  <p className="dp-slack__bubble-body">{turn.body}</p>
                  {turn.proposal && (
                    <div className="dp-slack__proposal-actions">
                      <button type="button" className="dp-btn dp-btn--ghost" onClick={() => onUseThis(turn.proposal!)} disabled={busy}>
                        👍 Use this
                      </button>
                      <button type="button" className="dp-btn dp-btn--ghost" onClick={() => onInsert(turn.proposal!)} disabled={busy}>
                        ✎ Insert
                      </button>
                      <button type="button" className="dp-btn dp-btn--ghost" onClick={() => onTryAgain(turn.proposal!)} disabled={busy}>
                        ↻ Try again
                      </button>
                    </div>
                  )}
                </div>
              )
            ))}
            <div ref={endRef} />
          </>
        )}
      </div>

      {tab === 'chat' && (
        <div className="dp-slack__assistant-foot">
          <div className="dp-slack__suggestions">
            <span className="dp-slack__suggestions-label">Suggestions</span>
            <div className="dp-slack__suggestion-row">
              {SUGGESTIONS.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  className="dp-slack__suggestion"
                  onClick={() => onAsk(suggestion)}
                  disabled={!draft || busy}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>

          <form className="dp-slack__ask" onSubmit={submit}>
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Ask AI to refine the message…"
              aria-label="Ask AI to refine the message"
              disabled={!draft || busy}
            />
            <button type="submit" className="dp-slack__ask-send" aria-label="Send to assistant" disabled={!draft || busy || !input.trim()}>
              <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                <path d="m4 12 16-8-6 8 6 8Z" />
              </svg>
            </button>
          </form>

          <section className="dp-slack__context" aria-label="Context used">
            <header>
              <span>Context used ({sources.length})</span>
              <button type="button" className="dp-slack__link" onClick={onManageContext}>Manage</button>
            </header>
            <ul>
              {shown.map((source) => (
                <li key={source.label}>
                  <span className="dp-slack__context-label">{source.label}</span>
                  {source.facts.length > 1 && (
                    <span className="dp-slack__context-count">{source.facts.length}</span>
                  )}
                  <span className="dp-slack__context-ok" aria-label="Authorized">✓</span>
                </li>
              ))}
              {sources.length === 0 && <li className="dp-slack__hint">No sources were used for this draft.</li>}
            </ul>
            {sources.length > 4 && (
              <button type="button" className="dp-slack__link" onClick={() => setShowAll((open) => !open)}>
                {showAll ? 'Show fewer sources' : 'Show all sources'}
              </button>
            )}
            {draft && draft.withheldCount > 0 && (
              <p className="dp-slack__context-withheld">
                {draft.withheldCount} withheld from this recipient
              </p>
            )}
          </section>
        </div>
      )}
    </aside>
  )
}

/** The panel's local turn helpers, exported so the workspace can build turns. */
export function userTurn(body: string): AssistantTurn {
  return { role: 'user', body, time: now() }
}

export function assistantTurn(body: string, proposal: SlackProposal | null): AssistantTurn {
  return { role: 'assistant', body, time: now(), proposal }
}
