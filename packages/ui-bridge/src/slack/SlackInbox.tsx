import React from 'react'
import {
  INBOX_FILTERS,
  badgeFor,
  clockTime,
  conversationTitle,
  type InboxGroup,
  type SlackCounts,
  type SlackInboxItem,
} from './slackTypes'

/**
 * The decision inbox — one row per conversation, not per message.
 *
 * Slack is already a list of messages; a second list of messages would be a
 * worse Slack. What this column adds is a verdict: what kind of thing each
 * conversation is, and whether DayPilot already prepared something.
 */

export type InboxTab = 'inbox' | 'drafts' | 'sent'

export function Avatar({ name, kind }: { name: string; kind: string }) {
  if (kind === 'channel' || kind === 'group') {
    return <span className="dp-slack__avatar dp-slack__avatar--channel" aria-hidden="true">#</span>
  }
  const initials = (name || '?')
    .split(/\s+/).filter(Boolean).slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('')
  // A stable hue per person, so the same face keeps the same colour between
  // sessions and the eye can find a thread before it reads the name.
  let hash = 0
  for (let i = 0; i < name.length; i += 1) hash = (hash * 31 + name.charCodeAt(i)) % 360
  return (
    <span
      className="dp-slack__avatar"
      style={{ background: `linear-gradient(150deg, hsl(${hash} 62% 46%), hsl(${(hash + 38) % 360} 58% 34%))` }}
      aria-hidden="true"
    >
      {initials || '?'}
    </span>
  )
}

function FilterChips({ counts, active, onSelect }: {
  counts: Partial<SlackCounts>
  active: 'all' | InboxGroup
  onSelect: (id: 'all' | InboxGroup) => void
}) {
  const total = (counts.needs_reply || 0) + (counts.action || 0) + (counts.fyi || 0) + (counts.done || 0)
  return (
    <div className="dp-slack__chips" role="tablist" aria-label="Inbox filters">
      {INBOX_FILTERS.map((filter) => {
        const count = filter.id === 'all' ? total : (counts[filter.id] || 0)
        return (
          <button
            key={filter.id}
            type="button"
            role="tab"
            aria-selected={active === filter.id}
            className={'dp-slack__chip' + (active === filter.id ? ' is-active' : '')}
            onClick={() => onSelect(filter.id)}
          >
            {filter.label}
            {count > 0 && <span className="dp-slack__chip-count">{count}</span>}
          </button>
        )
      })}
    </div>
  )
}

const GROUP_HEADINGS: Record<InboxGroup, string> = {
  needs_reply: 'NEEDS YOUR REPLY',
  action: 'ACTION',
  fyi: 'FYI',
  done: 'DONE',
}

const GROUP_ORDER: InboxGroup[] = ['needs_reply', 'action', 'fyi', 'done']

export type SlackInboxProps = {
  tab: InboxTab
  onTab: (tab: InboxTab) => void
  filter: 'all' | InboxGroup
  onFilter: (filter: 'all' | InboxGroup) => void
  counts: Partial<SlackCounts>
  items: SlackInboxItem[]
  selectedId: string | null
  onSelect: (item: SlackInboxItem) => void
  /** A one-line read of the thread, when the caller has one (demo mode does). */
  subjectFor?: (conversationId: string) => string
  replyCountFor?: (conversationId: string) => number
  loading?: boolean
}

export function SlackInbox({
  tab, onTab, filter, onFilter, counts, items, selectedId, onSelect,
  subjectFor, replyCountFor, loading = false,
}: SlackInboxProps) {
  const grouped = GROUP_ORDER
    .map((group) => ({ group, rows: items.filter((item) => item.group === group) }))
    .filter((section) => section.rows.length > 0)

  return (
    <section className="dp-slack__inbox" aria-label="Slack inbox">
      <div className="dp-slack__inbox-head">
        <div className="dp-slack__tabs" role="tablist" aria-label="Slack views">
          {(['inbox', 'drafts', 'sent'] as InboxTab[]).map((id) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={tab === id}
              className={'dp-slack__tab' + (tab === id ? ' is-active' : '')}
              onClick={() => onTab(id)}
            >
              {id === 'inbox' ? 'Inbox' : id === 'drafts' ? 'Drafts' : 'Sent'}
            </button>
          ))}
        </div>
        <button type="button" className="dp-slack__iconbtn" aria-label="Filter conversations">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 5h16l-6.2 7.3v5.4L10.2 20v-7.7Z" />
          </svg>
        </button>
      </div>

      <FilterChips counts={counts} active={filter} onSelect={onFilter} />

      <div className="dp-slack__list">
        {loading && <p className="dp-slack__hint">Loading conversations…</p>}
        {!loading && items.length === 0 && (
          <p className="dp-slack__hint">
            {tab === 'inbox'
              ? 'Nothing waiting. DayPilot will surface a conversation here when one needs you.'
              : tab === 'drafts' ? 'No prepared drafts right now.' : 'Nothing sent from DayPilot yet.'}
          </p>
        )}

        {grouped.map((section) => (
          <div key={section.group} className="dp-slack__group">
            <div className="dp-slack__group-head">
              <span>{GROUP_HEADINGS[section.group]}</span>
              <span className="dp-slack__group-count">{section.rows.length}</span>
            </div>
            {section.rows.map((item) => {
              const conversation = item.conversation
              const badge = badgeFor(item)
              const subject = subjectFor?.(conversation?.id || '') || ''
              const replies = replyCountFor?.(conversation?.id || '') || 0
              const active = conversation?.id === selectedId
              return (
                <button
                  key={item.message.id}
                  type="button"
                  className={'dp-slack__row' + (active ? ' is-active' : '')}
                  aria-current={active ? 'true' : undefined}
                  onClick={() => onSelect(item)}
                >
                  <Avatar name={conversationTitle(conversation)} kind={conversation?.kind || 'im'} />
                  <div className="dp-slack__row-body">
                    <div className="dp-slack__row-top">
                      <span className="dp-slack__row-who">{conversationTitle(conversation)}</span>
                      <span className="dp-slack__row-time">{clockTime(item.message.occurredAt)}</span>
                    </div>
                    {subject && <div className="dp-slack__row-subject">{subject}</div>}
                    <p className="dp-slack__row-preview">{item.message.text}</p>
                    <div className="dp-slack__row-foot">
                      {badge && <span className={'dp-slack__badge dp-slack__badge--' + badge.tone}>{badge.label}</span>}
                      {item.message.flagged && (
                        <span
                          className="dp-slack__badge dp-slack__badge--flagged"
                          title="This message contains text that looks like an instruction to the AI. DayPilot shows it; it never follows it."
                        >
                          Screened
                        </span>
                      )}
                      {replies > 0 && (
                        <span className="dp-slack__row-replies">
                          {replies}
                          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M20 15a3 3 0 0 1-3 3H8l-4 3v-4H7a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3h10a3 3 0 0 1 3 3Z" />
                          </svg>
                        </span>
                      )}
                    </div>
                  </div>
                </button>
              )
            })}
          </div>
        ))}
      </div>
    </section>
  )
}
