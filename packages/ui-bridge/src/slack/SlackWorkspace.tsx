import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { isDemoMode } from '../env'
import { SlackAssistantPanel, assistantTurn, userTurn, type AssistantTurn } from './SlackAssistantPanel'
import { SlackCompose } from './SlackCompose'
import { SlackConversationView } from './SlackConversation'
import { SlackInbox, type InboxTab } from './SlackInbox'
import { DISABLED, explain, slackApi } from './slackClient'
import {
  DEMO_COUNTS,
  DEMO_IMPROVED,
  DEMO_ITEMS,
  DEMO_STATUS,
  DEMO_WORKSPACE_NAME,
  demoReplyCount,
  demoSubject,
  demoThread,
} from './slackDemoData'
import {
  conversationTitle,
  type InboxGroup,
  type SlackCounts,
  type SlackDraft,
  type SlackInboxItem,
  type SlackProposal,
  type SlackStatus,
  type SlackThread,
  type TransformId,
} from './slackTypes'

/**
 * Slack as a place to work, in four columns: DayPilot nav (the shell's), the
 * decision inbox, the conversation with its prepared reply, and the assistant.
 *
 * The whole surface is optional. When `/v1/slack/status` says the feature is
 * off, or Slack is not connected, this renders an honest state rather than
 * sample data — production never falls back to the demo scenario, because a
 * fictional message that looks real is the fastest way to lose someone's trust
 * in something that writes on their behalf.
 */

export type SlackWorkspaceProps = {
  /** Opens Settings → Slack, which owns connection and context permissions. */
  onOpenSettings: () => void
}

export function SlackWorkspace({ onOpenSettings }: SlackWorkspaceProps) {
  return isDemoMode()
    ? <DemoSlackWorkspace onOpenSettings={onOpenSettings} />
    : <ConnectedSlackWorkspace onOpenSettings={onOpenSettings} />
}

// --- shared chrome ------------------------------------------------------------

function SlackHeader({ onNewMessage, connected }: { onNewMessage: () => void; connected: boolean }) {
  return (
    <header className="dp-slack__head">
      <div>
        <h2>Slack · AI Assistant</h2>
        <p>Stay on top of Slack without living in Slack.</p>
      </div>
      <button type="button" className="dp-btn dp-btn--primary" onClick={onNewMessage} disabled={!connected}>
        + New message
      </button>
    </header>
  )
}

function SlackState({ title, body, actionLabel, onAction }: {
  title: string
  body: string
  actionLabel?: string
  onAction?: () => void
}) {
  return (
    <div className="dp-slack__state">
      <div>
        <h3>{title}</h3>
        <p>{body}</p>
        {actionLabel && onAction && (
          <button type="button" className="dp-btn dp-btn--primary" onClick={onAction}>{actionLabel}</button>
        )}
      </div>
    </div>
  )
}

/** The rail footer chip: which workspace, and whether it is really connected. */
export function SlackConnectionChip({ status, onManage }: {
  status: SlackStatus | null
  onManage: () => void
}) {
  const connected = Boolean(status?.connected)
  return (
    <div className="dp-slack__conn">
      <span className={'dp-slack__conn-dot' + (connected ? ' is-on' : '')} aria-hidden="true" />
      <span className="dp-slack__conn-state">{connected ? 'Slack connected' : 'Slack not connected'}</span>
      {status?.account && <span className="dp-slack__conn-account">{status.account}</span>}
      <button type="button" className="dp-btn dp-btn--ghost" onClick={onManage}>
        {connected ? 'Manage connection' : 'Connect Slack'}
      </button>
    </div>
  )
}

// --- live ---------------------------------------------------------------------

function ConnectedSlackWorkspace({ onOpenSettings }: SlackWorkspaceProps) {
  const [status, setStatus] = useState<SlackStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [fatal, setFatal] = useState<string | null>(null)

  const [tab, setTab] = useState<InboxTab>('inbox')
  const [filter, setFilter] = useState<'all' | InboxGroup>('all')
  const [items, setItems] = useState<SlackInboxItem[]>([])
  const [counts, setCounts] = useState<Partial<SlackCounts>>({})

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [thread, setThread] = useState<SlackThread | null>(null)

  const [turns, setTurns] = useState<AssistantTurn[]>([])
  const [assistantOpen, setAssistantOpen] = useState(true)
  const [canUndo, setCanUndo] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [approvalNote, setApprovalNote] = useState<string | null>(null)

  const [composeOpen, setComposeOpen] = useState(false)
  const [recipients, setRecipients] = useState<SlackInboxItem['conversation'][]>([])
  // On a phone the inbox and the thread take turns; on a desktop this is inert.
  const [pane, setPane] = useState<'inbox' | 'thread'>('inbox')

  const refreshInbox = useCallback(async (group: 'all' | InboxGroup) => {
    const r = await slackApi.inbox(group)
    if (!r.ok) { setError(explain(r.error, r.status)); return }
    setItems(r.data.items)
    setCounts(r.data.counts)
    return r.data.items
  }, [])

  const openConversation = useCallback(async (conversationId: string) => {
    setSelectedId(conversationId)
    setPane('thread')
    setTurns([])
    setCanUndo(false)
    setApprovalNote(null)
    const r = await slackApi.conversation(conversationId)
    if (!r.ok) { setError(explain(r.error, r.status)); return }
    setThread(r.data)
  }, [])

  useEffect(() => {
    let cancelled = false
    async function boot() {
      const s = await slackApi.status()
      if (cancelled) return
      if (!s.ok) { setFatal(explain(s.error, s.status)); setLoading(false); return }
      setStatus(s.data)
      if (!s.data.enabled || !s.data.connected) { setLoading(false); return }
      const loaded = await refreshInbox('all')
      if (cancelled) return
      const first = loaded?.[0]?.conversation?.id
      if (first) await openConversation(first)
      setLoading(false)
    }
    void boot()
    return () => { cancelled = true }
  }, [refreshInbox, openConversation])

  useEffect(() => { if (status?.connected) void refreshInbox(filter) }, [filter, status?.connected, refreshInbox])

  const reloadThread = useCallback(async () => {
    if (!selectedId) return
    const r = await slackApi.conversation(selectedId)
    if (r.ok) setThread(r.data)
  }, [selectedId])

  const draft: SlackDraft | null = thread?.draft ?? null

  async function withBusy<T>(work: () => Promise<T>): Promise<T | undefined> {
    setBusy(true); setError(null)
    try { return await work() } finally { setBusy(false) }
  }

  const draftProps = {
    onPrepare: () => withBusy(async () => {
      if (!thread) return
      const latest = thread.messages[thread.messages.length - 1]
      const r = await slackApi.draftReply(thread.conversation.id, latest?.id ?? null)
      if (!r.ok) { setError(explain(r.error, r.status)); return }
      await reloadThread()
    }),
    onChangeText: (text: string) => withBusy(async () => {
      if (!draft) return
      const r = await slackApi.saveDraft(draft.id, text)
      if (!r.ok) { setError(explain(r.error, r.status)); return }
      setCanUndo(true)
      await reloadThread()
    }),
    onTransform: (kind: TransformId) => withBusy(async () => {
      if (!draft) return
      const r = await slackApi.transform(draft.id, kind)
      if (!r.ok) { setError(explain(r.error, r.status)); return }
      setCanUndo(true)
      await reloadThread()
    }),
    onSend: () => withBusy(async () => {
      if (!draft) return
      const r = await slackApi.send(draft.id)
      if (!r.ok) { setError(explain(r.error, r.status)); return }
      setApprovalNote(
        r.data.status === 'approval_required'
          ? 'Waiting for your approval in the Approval Center. Nothing has been posted to Slack.'
          : `Send requested (${r.data.status}).`,
      )
      await reloadThread()
      await refreshInbox(filter)
    }),
    onDiscard: () => withBusy(async () => {
      if (!draft) return
      const r = await slackApi.discard(draft.id)
      if (!r.ok) { setError(explain(r.error, r.status)); return }
      await reloadThread()
    }),
    onUndo: () => withBusy(async () => {
      if (!draft) return
      const r = await slackApi.undo(draft.id)
      if (!r.ok) { setError(explain(r.error, r.status)); return }
      setCanUndo(false)
      await reloadThread()
    }),
    onOpenInSlack: () => {
      const channel = thread?.conversation.channelId
      if (channel) window.open(`slack://channel?id=${encodeURIComponent(channel)}`, '_blank')
    },
    canUndo,
    busy,
    approvalNote,
    error,
  }

  async function ask(instruction: string) {
    if (!draft) return
    setTurns((prev) => [...prev, userTurn(instruction)])
    await withBusy(async () => {
      const r = await slackApi.refine(draft.id, instruction)
      if (!r.ok) { setError(explain(r.error, r.status)); return }
      setTurns((prev) => [...prev, assistantTurn(
        r.data.changed ? "Here's an improved version:\n\n" + r.data.proposed
          : "I couldn't find a change to make from that. Try naming what should be different — shorter, no commitment to a date, add a next step.",
        r.data.changed ? r.data : null,
      )])
    })
  }

  async function useProposal(proposal: SlackProposal) {
    if (!draft) return
    await withBusy(async () => {
      const r = await slackApi.accept(draft.id, proposal.proposed, proposal.instruction)
      if (!r.ok) { setError(explain(r.error, r.status)); return }
      setCanUndo(true)
      await reloadThread()
    })
  }

  if (loading) {
    return (
      <div className="dp-slack dp-slack--state" aria-busy="true">
        <SlackState title="Loading Slack…" body="Reading your traced conversations." />
      </div>
    )
  }

  if (fatal || !status) {
    return (
      <div className="dp-slack dp-slack--state">
        <SlackState
          title="Slack is unavailable"
          body={fatal || 'DayPilot could not read the Slack workspace status.'}
          actionLabel="Open Slack settings"
          onAction={onOpenSettings}
        />
      </div>
    )
  }

  if (!status.enabled) {
    return (
      <div className="dp-slack dp-slack--state">
        <SlackState
          title="The Slack workspace is not enabled"
          body={`Turn it on with DAYPILOT_SLACK_WORKSPACE_ENABLED on the server and VITE_DAYPILOT_SLACK_WORKSPACE_ENABLED in the web app. DayPilot works fully without it. (${DISABLED})`}
        />
      </div>
    )
  }

  if (!status.connected) {
    return (
      <div className="dp-slack dp-slack--state">
        <SlackState
          title="Connect Slack to get started"
          body="DayPilot will trace the conversations you choose, tell you which ones need you, and prepare replies. It never posts anything without your approval."
          actionLabel="Connect Slack"
          onAction={onOpenSettings}
        />
      </div>
    )
  }

  return (
    <div className={'dp-slack dp-slack--pane-' + pane + (assistantOpen ? '' : ' dp-slack--no-assistant')}>
      <SlackHeader connected onNewMessage={async () => {
        const r = await slackApi.recipients()
        setRecipients(r.ok ? r.data : [])
        setComposeOpen(true)
      }} />

      <div className="dp-slack__cols">
        <SlackInbox
          tab={tab}
          onTab={setTab}
          filter={filter}
          onFilter={setFilter}
          counts={counts}
          items={items}
          selectedId={selectedId}
          onSelect={(item) => item.conversation && openConversation(item.conversation.id)}
        />

        <SlackConversationView
          thread={thread}
          draftProps={draftProps}
          assistantOpen={assistantOpen}
          onOpenAssistant={() => setAssistantOpen(true)}
          onBack={() => setPane('inbox')}
        />

        {assistantOpen && (
          <SlackAssistantPanel
            draft={draft}
            turns={turns}
            busy={busy}
            onAsk={ask}
            onUseThis={useProposal}
            onInsert={useProposal}
            onTryAgain={(proposal) => ask(proposal.instruction)}
            onClose={() => setAssistantOpen(false)}
            onManageContext={onOpenSettings}
          />
        )}
      </div>

      {composeOpen && (
        <SlackCompose
          recipients={recipients.filter(Boolean) as NonNullable<SlackInboxItem['conversation']>[]}
          busy={busy}
          error={error}
          onCancel={() => setComposeOpen(false)}
          onCompose={({ conversationId, instruction }) => withBusy(async () => {
            const r = await slackApi.compose({ conversationId, instruction })
            if (!r.ok) { setError(explain(r.error, r.status)); return }
            setComposeOpen(false)
            await openConversation(r.data.conversation.id)
          })}
        />
      )}
    </div>
  )
}

// --- demo ---------------------------------------------------------------------

/** Local versions of the four transforms, so the showcase needs no backend. */
function demoTransform(text: string, kind: TransformId): string {
  if (kind === 'shorter') {
    const lines = text.split('\n').filter(Boolean)
    return lines.slice(0, Math.max(1, Math.ceil(lines.length / 2))).join('\n')
  }
  if (kind === 'direct') return text.replace(/I expect we can/g, "we'll").replace(/still looks achievable/g, 'works')
  if (kind === 'detailed') return text.includes('Happy to walk through') ? text : `${text}\n\nHappy to walk through the detail if that's useful.`
  return text.startsWith('Hi') ? text : `Hi — ${text[0].toLowerCase()}${text.slice(1)}`
}

function DemoSlackWorkspace({ onOpenSettings }: SlackWorkspaceProps) {
  const [filter, setFilter] = useState<'all' | InboxGroup>('needs_reply')
  const [tab, setTab] = useState<InboxTab>('inbox')
  const [selectedId, setSelectedId] = useState('c-jane')
  const [thread, setThread] = useState<SlackThread>(() => demoThread('c-jane'))
  const [turns, setTurns] = useState<AssistantTurn[]>([])
  const [assistantOpen, setAssistantOpen] = useState(true)
  const [history, setHistory] = useState<string[]>([])
  const [approvalNote, setApprovalNote] = useState<string | null>(null)
  const [composeOpen, setComposeOpen] = useState(false)
  const [pane, setPane] = useState<'inbox' | 'thread'>('inbox')

  const items = useMemo(
    () => (filter === 'all' ? DEMO_ITEMS : DEMO_ITEMS.filter((item) => item.group === filter)),
    [filter],
  )

  function select(conversationId: string) {
    setSelectedId(conversationId)
    setPane('thread')
    setThread(demoThread(conversationId))
    setTurns([])
    setHistory([])
    setApprovalNote(null)
  }

  function setDraftText(text: string) {
    setThread((prev) => {
      if (!prev.draft) return prev
      setHistory((h) => [...h, prev.draft!.text])
      return { ...prev, draft: { ...prev.draft, text, updatedAt: new Date().toISOString() } }
    })
  }

  const draft = thread.draft

  const draftProps = {
    onPrepare: () => setThread((prev) => ({
      ...prev,
      draft: {
        ...(DEMO_ITEMS[0].draft as SlackDraft),
        id: `d-${prev.conversation.id}`,
        conversationId: prev.conversation.id,
        messageId: prev.messages[prev.messages.length - 1]?.id ?? null,
        text: "Thanks — I'll take a look and come back to you with a clear answer shortly.",
      },
    })),
    onChangeText: setDraftText,
    onTransform: (kind: TransformId) => { if (draft) setDraftText(demoTransform(draft.text, kind)) },
    onSend: () => setApprovalNote(
      'Waiting for your approval in the Approval Center. Nothing has been posted to Slack.',
    ),
    onDiscard: () => setThread((prev) => ({ ...prev, draft: null })),
    onUndo: () => setHistory((h) => {
      const previous = h[h.length - 1]
      if (previous === undefined) return h
      setThread((prev) => (prev.draft ? { ...prev, draft: { ...prev.draft, text: previous } } : prev))
      return h.slice(0, -1)
    }),
    onOpenInSlack: () => { /* the showcase has no workspace to open */ },
    canUndo: history.length > 0,
    busy: false,
    approvalNote,
    error: null,
  }

  function ask(instruction: string) {
    if (!draft) return
    const proposal: SlackProposal = {
      draftId: draft.id, instruction, current: draft.text,
      proposed: DEMO_IMPROVED, changed: true,
    }
    setTurns((prev) => [
      ...prev,
      userTurn(instruction),
      assistantTurn("Here's an improved version:\n\n" + DEMO_IMPROVED, proposal),
    ])
  }

  return (
    <div className={'dp-slack dp-slack--pane-' + pane + (assistantOpen ? '' : ' dp-slack--no-assistant')}>
      <SlackHeader connected onNewMessage={() => setComposeOpen(true)} />
      <div className="dp-slack__cols">
        <SlackInbox
          tab={tab}
          onTab={setTab}
          filter={filter}
          onFilter={setFilter}
          counts={DEMO_COUNTS}
          items={items}
          selectedId={selectedId}
          onSelect={(item) => item.conversation && select(item.conversation.id)}
          subjectFor={demoSubject}
          replyCountFor={demoReplyCount}
        />
        <SlackConversationView
          thread={thread}
          draftProps={draftProps}
          assistantOpen={assistantOpen}
          onOpenAssistant={() => setAssistantOpen(true)}
          onBack={() => setPane('inbox')}
        />
        {assistantOpen && (
          <SlackAssistantPanel
            draft={draft}
            turns={turns}
            onAsk={ask}
            onUseThis={(proposal) => setDraftText(proposal.proposed)}
            onInsert={(proposal) => setDraftText(proposal.proposed)}
            onTryAgain={(proposal) => ask(proposal.instruction)}
            onClose={() => setAssistantOpen(false)}
            onManageContext={onOpenSettings}
          />
        )}
      </div>
      {composeOpen && (
        <SlackCompose
          recipients={DEMO_ITEMS.map((item) => item.conversation!).filter(Boolean)}
          onCancel={() => setComposeOpen(false)}
          onCompose={({ conversationId }) => { setComposeOpen(false); select(conversationId) }}
        />
      )}
    </div>
  )
}

/** Exported for the rail chip in demo mode. */
export const DEMO_SLACK_STATUS = DEMO_STATUS
export const DEMO_SLACK_WORKSPACE = DEMO_WORKSPACE_NAME
export { conversationTitle }
