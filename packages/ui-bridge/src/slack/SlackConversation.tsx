import React from 'react'
import { Avatar } from './SlackInbox'
import { SlackDraftEditor, type SlackDraftEditorProps } from './SlackDraftEditor'
import { clockTime, conversationSubtitle, type SlackThread } from './slackTypes'

/**
 * The middle column: what was said, then what DayPilot suggests saying back.
 *
 * The order matters. Putting the draft above the message would let someone send
 * a reply without having read what they are replying to, which is precisely the
 * failure mode a drafting assistant makes easy.
 */

export type SlackConversationProps = {
  thread: SlackThread | null
  draftProps: Omit<SlackDraftEditorProps, 'draft'>
  onOpenAssistant: () => void
  assistantOpen: boolean
  /** Back to the inbox. Only rendered on a phone, where they take turns. */
  onBack: () => void
}

export function SlackConversationView({
  thread, draftProps, onOpenAssistant, assistantOpen, onBack,
}: SlackConversationProps) {
  if (!thread) {
    return (
      <section className="dp-slack__thread dp-slack__thread--empty" aria-label="Conversation">
        <p className="dp-slack__hint">Pick a conversation to see it and its prepared reply.</p>
      </section>
    )
  }

  const { conversation, messages, draft } = thread
  const external = conversation.audience === 'external'

  return (
    <section className="dp-slack__thread" aria-label="Conversation">
      <header className="dp-slack__thread-head">
        <button
          type="button"
          className="dp-slack__iconbtn dp-slack__back"
          aria-label="Back to the inbox"
          onClick={onBack}
        >
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M15 5l-7 7 7 7" />
          </svg>
        </button>
        <Avatar name={conversation.counterpart || conversation.name} kind={conversation.kind} />
        <div className="dp-slack__thread-title">
          <span>{conversationSubtitle(conversation)}</span>
          {external && (
            <span
              className="dp-slack__badge dp-slack__badge--external"
              title="This conversation includes people outside your organisation. Internal-only facts are removed before the draft is written."
            >
              External
            </span>
          )}
        </div>
        <div className="dp-slack__thread-actions">
          {!assistantOpen && (
            <button type="button" className="dp-slack__iconbtn" aria-label="Open AI Assistant" onClick={onOpenAssistant}>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 12h9" /><path d="m11 8 4 4-4 4" /><path d="M19 6v12" />
              </svg>
            </button>
          )}
          <button type="button" className="dp-slack__iconbtn" aria-label="Conversation details">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" />
            </svg>
          </button>
          <button type="button" className="dp-slack__iconbtn" aria-label="Open in Slack" onClick={draftProps.onOpenInSlack}>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 4h6v6" /><path d="M20 4 10 14" /><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5" />
            </svg>
          </button>
          <button type="button" className="dp-slack__iconbtn" aria-label="More actions">⋮</button>
        </div>
      </header>

      <div className="dp-slack__messages">
        {messages.length === 0 && <p className="dp-slack__hint">No messages traced yet.</p>}
        {messages.map((message) => (
          <article
            key={message.id}
            className={'dp-slack__msg' + (message.direction === 'outgoing' ? ' dp-slack__msg--mine' : '')}
          >
            <Avatar name={message.author} kind="im" />
            <div className="dp-slack__msg-body">
              <div className="dp-slack__msg-top">
                <span className="dp-slack__msg-who">{message.author || 'Someone'}</span>
                <span className="dp-slack__msg-time">{clockTime(message.occurredAt)}</span>
              </div>
              <p className="dp-slack__msg-text">{message.text}</p>
              {message.flagged && (
                <p className="dp-slack__msg-flag">
                  This message contains text shaped like an instruction to an AI. DayPilot shows
                  it and does not act on it.
                </p>
              )}
            </div>
          </article>
        ))}
      </div>

      <SlackDraftEditor draft={draft} {...draftProps} />
    </section>
  )
}
