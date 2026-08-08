import React, { useEffect, useRef, useState } from 'react'

import { homepilotApi, type AgentProfile, type AgentTurnMessage } from '../../settings/homepilotClient'
import { AgentPortrait } from '../AgentPortrait'
import type { AgentMessage } from './types'

/**
 * Live conversation panel (Batch A6, UX §4–6).
 *
 * Loads the agent's persisted conversation and sends turns through DayPilot's
 * own backend (the browser never calls HomePilot). Every turn is propose-only:
 * the persona replies and may PROPOSE work, but nothing is sent or executed —
 * proposals are surfaced here and, in a later batch, routed to the Approval
 * Center. Degrades gracefully: if the chat feature is off (404) the panel drops
 * to a read-only notice; a failed turn keeps the user's message (persisted
 * server-side) and offers a retry. New replies are announced via `aria-live`.
 */
function fmtTime(iso?: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return isNaN(d.getTime()) ? '' : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function toMessage(m: AgentTurnMessage): AgentMessage {
  const proposals = ((m.action?.x_directives as { items?: unknown[] } | undefined)?.items?.length) || 0
  return {
    id: m.id,
    role: m.role === 'assistant' ? 'agent' : 'you',
    body: m.body,
    createdAt: m.createdAt ?? null,
    proposal: m.role === 'assistant' && proposals > 0,
  }
}

type Load = 'loading' | 'ready' | 'unavailable' | 'error'

export function AgentChatPanel({ agent, onTurn }: { agent: AgentProfile; onTurn?: () => void }) {
  const [load, setLoad] = useState<Load>('loading')
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [retry, setRetry] = useState<string | null>(null)   // last failed text (A11)
  const [mode, setMode] = useState<string>('unknown')
  const [degraded, setDegraded] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)
  const liveRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let alive = true
    setLoad('loading')
    homepilotApi.getAgentSession(agent.id).then((r) => {
      if (!alive) return
      if (r.ok) {
        setMessages(r.data.messages.map(toMessage))
        setMode(r.data.mode || 'unknown')
        setDegraded(!!r.data.degraded)
        setLoad('ready')
      } else if (r.status === 404) {
        setLoad('unavailable')  // chat feature off, or agent gone
      } else {
        setLoad('error')
      }
    })
    return () => { alive = false }
  }, [agent.id])

  useEffect(() => { endRef.current?.scrollIntoView({ block: 'end' }) }, [messages.length])

  async function deliver(text: string, tempId: string) {
    const r = await homepilotApi.sendTurn(agent.id, text)
    setSending(false)
    if (r.ok) {
      setRetry(null)
      setDegraded(false)
      setMessages((cur) => [
        ...cur.filter((m) => m.id !== tempId),
        toMessage(r.data.userMessage),
        toMessage(r.data.reply),
      ])
      onTurn?.()  // let the workspace refresh the task panel
      if (liveRef.current) {
        liveRef.current.textContent =
          r.data.proposals > 0
            ? `${agent.name} replied and proposed ${r.data.proposals} action${r.data.proposals === 1 ? '' : 's'} for your approval.`
            : `${agent.name} replied.`
      }
    } else {
      // The backend persisted the user's message even on failure; keep it shown
      // and offer Retry (A11 failure matrix: timeout/unreachable retain + Retry).
      setRetry(text)
      const timedOut = r.status === 504
      setNotice(
        r.status === 404
          ? `${agent.name} can’t be reached right now.`
          : timedOut
            ? `${agent.name} took too long to respond. Your message was saved — retry when ready.`
            : `Couldn’t reach ${agent.name}. Your message was saved — retry when ready.`,
      )
      if (liveRef.current) liveRef.current.textContent = `Message to ${agent.name} could not be delivered — retry available.`
    }
  }

  async function send() {
    const text = draft.trim()
    if (!text || sending) return
    setSending(true)
    setNotice(null)
    const tempId = `local-${Date.now()}`
    setMessages((cur) => [...cur, { id: tempId, role: 'you', body: text }])
    setDraft('')
    await deliver(text, tempId)
  }

  async function retrySend() {
    if (!retry || sending) return
    setSending(true)
    setNotice(null)
    await deliver(retry, `local-retry-${Date.now()}`)
  }

  if (load === 'unavailable') {
    return (
      <section className="dp-agentws__chat" aria-label={`Conversation with ${agent.name}`}>
        <div className="dp-agentws__empty">
          <p><b>Conversation isn’t available.</b></p>
          <p>Chatting with agents is turned off for this workspace. An admin can enable it in the HomePilot settings.</p>
        </div>
      </section>
    )
  }

  const avatar = (
    <AgentPortrait
      name={agent.name}
      avatarUrl={agent.avatarUrl}
      className="dp-chat__avatar"
      initialsClassName=""
      maxInitials={1}
    />
  )

  return (
    <section className="dp-chat" aria-label={`Conversation with ${agent.name}`}>
      <div className="dp-chat__banner">
        <span className="dp-chat__banner-icon" aria-hidden="true">ⓘ</span>
        <div>
          <p className="dp-chat__banner-title">You are chatting with {agent.name}.</p>
          <p className="dp-chat__banner-sub">Assign tasks, ask for updates, or request help. {agent.name} can delegate to other agents when it saves you time.</p>
        </div>
        <button type="button" className="dp-ghost-button dp-chat__banner-btn">How delegation works</button>
      </div>

      <div className="dp-chat__log" role="log">
        {load === 'loading' && <p className="dp-taskrail__empty">Loading conversation…</p>}
        {load === 'error' && <p className="dp-taskrail__empty">Couldn’t load this conversation.</p>}
        {load === 'ready' && messages.length === 0 && (
          <div className="dp-agentws__empty">
            <p><b>Start the conversation.</b></p>
            <p>Send {agent.name} a directive. They’ll reply and propose work — nothing is sent or changed without your approval.</p>
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={'dp-chat__turn dp-chat__turn--' + m.role}>
            {m.role === 'agent' && avatar}
            <div className="dp-chat__bubblewrap">
              <div className={'dp-chat__bubble dp-chat__bubble--' + m.role}>
                {m.proposal && <span className="dp-chat__badge">Proposal · needs approval</span>}
                <p className="dp-chat__text">{m.body}</p>
              </div>
              <span className="dp-chat__stamp">
                {m.role === 'you' ? '' : `${agent.name} · `}{fmtTime(m.createdAt)}{m.role === 'you' ? ' ✓✓' : ''}
              </span>
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>

      {degraded && (
        <p className="dp-chat__degraded" role="status">
          <span aria-hidden="true">⚠</span> {agent.name} is offline — showing your saved conversation. New messages will send when it’s reachable again.
        </p>
      )}
      {mode === 'chat_only' && (
        <p className="dp-chat__mode" role="status">This HomePilot is chat-only — {agent.name} can reply, but can’t propose tasks or actions.</p>
      )}

      {notice && (
        <p className="dp-agentws__notice" role="alert">
          {notice}
          {retry && <button type="button" className="dp-linkbtn dp-chat__retry" onClick={retrySend} disabled={sending}>Retry</button>}
        </p>
      )}

      <form className="dp-chat__composer" onSubmit={(e) => { e.preventDefault(); void send() }}>
        <div className="dp-chat__composer-tools" aria-hidden="true">
          <span className="dp-chat__tool">📎</span>
          <span className="dp-chat__tool">✦</span>
          <span className="dp-chat__tool">@</span>
        </div>
        <input
          className="dp-chat__composer-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={`Ask ${agent.name} to handle a task…`}
          aria-label={`Message ${agent.name}`}
          disabled={sending || load !== 'ready'}
        />
        <button type="submit" className="dp-chat__send" aria-label="Send" disabled={sending || !draft.trim() || load !== 'ready'}>
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4z" /></svg>
        </button>
      </form>

      <div className="dp-sr-live" role="status" aria-live="polite" ref={liveRef} />
    </section>
  )
}
