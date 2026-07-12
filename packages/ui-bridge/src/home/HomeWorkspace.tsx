import React, { useEffect, useRef, useState } from 'react'
import { askAssistant, type AssistantAction } from '../assistant'
import {
  appendMessage,
  clearSession,
  createSession,
  deleteSession,
  getSession,
  listSessions,
  type ChatSessionSummary,
} from '../chatSessions'
import { isDemoMode } from '../env'
import {
  AI_PLAN_BULLETS,
  AI_SEED,
  AI_WELCOME,
  CONTINUE_ITEMS,
  HOME_SUGGESTIONS,
  NEXT_PRIORITY,
  TODAY_PLAN,
  aiReply,
  type HomeTurn,
} from './homeData'

type HomeWorkspaceProps = {
  userName?: string
  onStartFocus: () => void
  onNavigate: (view: 'calendar' | 'projects' | 'planning' | 'agents') => void
  onOpenPalette: () => void
  onOpenProjectWizard?: () => void
  onOpenApprovals?: () => void
}

function nowTime(): string {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

/**
 * Home — a calm, enterprise Home workspace. Three regions (nav lives in the
 * shell): a readable main column (Next priority · Today's plan · Continue from
 * yesterday) and a single, collapsible conversational AI Assistant on the
 * right. There is one place to talk to AI (this panel) and one place to
 * navigate (the top search / command palette). The assistant can be closed to
 * give the main workspace full width and reopened from the header, ChatGPT /
 * Claude / Gemini style.
 */
const SESSION_KEY = 'daypilot.chat.session'

export function HomeWorkspace({ onStartFocus, onNavigate, onOpenPalette, onOpenProjectWizard, onOpenApprovals }: HomeWorkspaceProps) {
  const [turns, setTurns] = useState<HomeTurn[]>(AI_SEED)
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  // Persistent conversation history (ChatGPT/Claude-style), off in demo mode.
  const persistent = !isDemoMode()
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([])
  const [historyOpen, setHistoryOpen] = useState(false)
  // On phones/tablets the assistant is a slide-over drawer, so it starts
  // collapsed to keep the main workspace visible; on desktop it is docked open.
  const [aiOpen, setAiOpen] = useState(() =>
    typeof window === 'undefined' ? true : !window.matchMedia('(max-width: 1200px)').matches,
  )
  const logRef = useRef<HTMLDivElement>(null)

  // Keep the conversation pinned to the latest message as it grows.
  useEffect(() => {
    const el = logRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [turns, thinking, aiOpen])

  // Load the history list and resume the last conversation across refreshes.
  useEffect(() => {
    if (!persistent) return
    let cancelled = false
    listSessions().then((s) => { if (!cancelled) setSessions(s) })
    const saved = (() => { try { return localStorage.getItem(SESSION_KEY) } catch { return null } })()
    if (saved) {
      getSession(saved).then((detail) => {
        if (cancelled || !detail) return
        setSessionId(detail.id)
        setTurns(detail.messages.map((m) => ({ role: m.role, body: m.body, time: undefined })))
      })
    }
    return () => { cancelled = true }
  }, [persistent])

  function rememberSession(id: string | null) {
    setSessionId(id)
    try { if (id) localStorage.setItem(SESSION_KEY, id); else localStorage.removeItem(SESSION_KEY) } catch { /* ignore */ }
  }

  async function ensureSession(firstMessage: string): Promise<string | null> {
    if (sessionId) return sessionId
    const created = await createSession(firstMessage.slice(0, 60))
    if (created) {
      rememberSession(created.id)
      setSessions((prev) => [created, ...prev])
      return created.id
    }
    return null
  }

  function runAction(action?: AssistantAction) {
    if (!action) return
    if (action.kind === 'navigate') onNavigate(action.target)
    else if (action.kind === 'openProjectWizard') onOpenProjectWizard?.()
    else if (action.kind === 'openApprovals') onOpenApprovals?.()
  }

  function newConversation() {
    rememberSession(null)
    setTurns([])
    setHistoryOpen(false)
  }

  async function resumeConversation(id: string) {
    const detail = await getSession(id)
    if (!detail) return
    rememberSession(id)
    setTurns(detail.messages.map((m) => ({ role: m.role, body: m.body })))
    setHistoryOpen(false)
  }

  async function removeConversation(id: string) {
    await deleteSession(id)
    setSessions((prev) => prev.filter((s) => s.id !== id))
    if (id === sessionId) newConversation()
  }

  async function clearCurrent() {
    if (sessionId) await clearSession(sessionId)
    setTurns([])
    setHistoryOpen(false)
  }

  function send(text: string) {
    const q = text.trim()
    if (!q) return
    setTurns((t) => [...t, { role: 'user', body: q, time: nowTime() }])
    setInput('')
    setThinking(true)
    // Demo mode keeps the deterministic offline reply; the real product routes
    // every question to the connected backend assistant and persists the turns.
    if (isDemoMode()) {
      window.setTimeout(() => {
        setTurns((t) => [...t, { role: 'assistant', body: aiReply(q), time: nowTime() }])
        setThinking(false)
      }, 400)
      return
    }
    ;(async () => {
      const sid = persistent ? await ensureSession(q) : null
      if (sid) await appendMessage(sid, 'user', q)
      try {
        const reply = await askAssistant(q)
        setTurns((t) => [...t, { role: 'assistant', body: reply.text, time: nowTime() }])
        runAction(reply.action)
        if (sid) {
          await appendMessage(sid, 'assistant', reply.text, reply.action ?? null)
          listSessions().then(setSessions)
        }
      } catch {
        setTurns((t) => [...t, { role: 'assistant', body: "I couldn't reach the backend just now. Please try again.", time: nowTime() }])
      } finally {
        setThinking(false)
      }
    })()
  }

  return (
    <div className={'dp-home' + (aiOpen ? '' : ' dp-home--ai-collapsed')}>
      {/* Main workspace */}
      <div className="dp-home__main">
        <header className="dp-home__header">
          <div>
            <h1 className="dp-home__title">Home</h1>
            <p className="dp-home__subtitle">Overview of your work and priorities.</p>
          </div>
          <div className="dp-home__header-right">
            <button className="dp-home__search" onClick={onOpenPalette} aria-label="Search or jump to">
              <span className="dp-home__search-icon" aria-hidden="true">⌕</span>
              <span className="dp-home__search-text">Search or jump to…</span>
              <kbd className="dp-kbd">⌘K</kbd>
            </button>
            {!aiOpen && (
              <button className="dp-home__openai" onClick={() => setAiOpen(true)} aria-label="Open AI Assistant">
                <span className="dp-home__openai-spark" aria-hidden="true">✦</span> Open AI
              </button>
            )}
          </div>
        </header>

        <div className="dp-home__scroll">
          {/* Your day is ready + Next priority */}
          <section className="dp-home__ready">
            {NEXT_PRIORITY ? (
              <>
                <h2 className="dp-home__ready-title"><span className="dp-home__ready-icon" aria-hidden="true">☼</span> Your day is ready</h2>
                <p className="dp-home__ready-sub">Focus on your top priority and keep the momentum.</p>
                <div className="dp-home__priority">
                  <div className="dp-home__priority-label">Next priority</div>
                  <div className="dp-home__priority-row">
                    <span className="dp-home__priority-icon" aria-hidden="true">🖥</span>
                    <div className="dp-home__priority-body">
                      <div className="dp-home__priority-title">{NEXT_PRIORITY.title}</div>
                      <div className="dp-home__priority-meta">
                        <span>🗓 {NEXT_PRIORITY.time}</span>
                        <span className="dp-home__dot-sep">·</span>
                        <span className="dp-chip">{NEXT_PRIORITY.project}</span>
                      </div>
                    </div>
                    <div className="dp-home__priority-actions">
                      <button className="dp-home__cta" onClick={onStartFocus}>▶ Start focus</button>
                      <button className="dp-home__ghost" onClick={() => onNavigate('projects')}>View project ↗</button>
                    </div>
                  </div>
                  <p className="dp-home__priority-support">{NEXT_PRIORITY.support}</p>
                </div>
              </>
            ) : (
              <div className="dp-home__empty">
                <h2 className="dp-home__ready-title"><span className="dp-home__ready-icon" aria-hidden="true">☼</span> Ready when you are</h2>
                <p className="dp-home__ready-sub">No plan yet for today. Ask the assistant to generate one, or open the planner.</p>
                <div className="dp-home__priority-actions">
                  <button className="dp-home__cta" onClick={() => onNavigate('planning')}>Open planner ↗</button>
                </div>
              </div>
            )}
          </section>

          {/* Today's plan + Continue from yesterday */}
          <div className="dp-home__grid">
            <section className="dp-home__card">
              <h3 className="dp-home__card-title"><span className="dp-home__card-icon" aria-hidden="true">🗓</span> Today's plan</h3>
              {TODAY_PLAN.length > 0 ? (
                <ul className="dp-agenda">
                  {TODAY_PLAN.map((item) => (
                    <li key={item.time} className="dp-agenda__row">
                      <span className="dp-agenda__bullet" aria-hidden="true" />
                      <span className="dp-agenda__time">{item.time}</span>
                      <span className="dp-agenda__title">{item.title}</span>
                      <span className="dp-agenda__tag">{item.tag}</span>
                      {item.end && <span className="dp-agenda__end">{item.end}</span>}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="dp-home__card-empty">No blocks scheduled yet. Generate a plan from the assistant or the planner.</p>
              )}
              <button className="dp-linkbtn dp-home__morelink" onClick={() => onNavigate('planning')}>Open planner →</button>
            </section>

            <section className="dp-home__card">
              <h3 className="dp-home__card-title"><span className="dp-home__card-icon" aria-hidden="true">⟳</span> Continue from yesterday</h3>
              <div className="dp-continue">
                {CONTINUE_ITEMS.length === 0 && <p className="dp-home__card-empty">Nothing carried over. New projects will show up here.</p>}
                {CONTINUE_ITEMS.map((c) => (
                  <button key={c.id} className="dp-continue__item" onClick={() => onNavigate('projects')}>
                    <span className={'dp-continue__icon dp-continue__icon--' + c.accent} aria-hidden="true">{c.icon}</span>
                    <span className="dp-continue__body">
                      <span className="dp-continue__name">{c.name}</span>
                      <span className="dp-continue__status">{c.status}</span>
                      <span className="dp-continue__bar"><span className={'dp-continue__fill dp-continue__fill--' + c.accent} style={{ width: `${c.progress}%` }} /></span>
                      <span className="dp-continue__next">Next: {c.next}</span>
                    </span>
                    <span className="dp-continue__pct">{c.progress}%</span>
                    <span className="dp-continue__chev" aria-hidden="true">›</span>
                  </button>
                ))}
              </div>
              <button className="dp-linkbtn dp-home__morelink" onClick={() => onNavigate('projects')}>View all projects →</button>
            </section>
          </div>
        </div>
      </div>

      {/* Backdrop for the slide-over drawer on phones/tablets. */}
      {aiOpen && <div className="dp-home-ai__backdrop" onClick={() => setAiOpen(false)} aria-hidden="true" />}

      {/* AI Assistant — the single conversational panel (collapsible) */}
      {aiOpen && (
        <aside className="dp-home-ai" aria-label="AI Assistant">
          <header className="dp-home-ai__head">
            <div className="dp-home-ai__title"><span className="dp-home-ai__spark" aria-hidden="true">✦</span> AI Assistant</div>
            <div className="dp-home-ai__head-actions">
              {persistent && (
                <>
                  <button className="dp-icon-button" aria-label="New conversation" title="New conversation" onClick={newConversation}>✎</button>
                  <button className="dp-icon-button" aria-label="Conversation history" title="History" aria-expanded={historyOpen} onClick={() => setHistoryOpen((o) => !o)}>🕑</button>
                </>
              )}
              <button className="dp-icon-button" aria-label="Close AI Assistant" onClick={() => setAiOpen(false)}>✕</button>
            </div>
            {historyOpen && (
              <div className="dp-home-ai__history" role="menu">
                <div className="dp-home-ai__history-head">
                  <span>Conversations</span>
                  <button className="dp-linkbtn" onClick={clearCurrent}>Clear current</button>
                </div>
                {sessions.length === 0 && <p className="dp-home-ai__history-empty">No saved conversations yet.</p>}
                {sessions.map((s) => (
                  <div key={s.id} className={'dp-home-ai__history-item' + (s.id === sessionId ? ' is-active' : '')}>
                    <button className="dp-home-ai__history-open" onClick={() => resumeConversation(s.id)} title={s.title}>
                      <span className="dp-home-ai__history-title">{s.title}</span>
                      <span className="dp-home-ai__history-count">{s.messageCount}</span>
                    </button>
                    <button className="dp-icon-button" aria-label={'Delete ' + s.title} onClick={() => removeConversation(s.id)}>🗑</button>
                  </div>
                ))}
              </div>
            )}
          </header>
          <div className="dp-home-ai__log" ref={logRef}>
            <div className="dp-home-ai__turn dp-home-ai__turn--assistant">
              <div className="dp-home-ai__bubble">
                <p style={{ whiteSpace: 'pre-line', margin: 0 }}>{AI_WELCOME}</p>
                {AI_PLAN_BULLETS.length > 0 && <ul className="dp-home-ai__plan">{AI_PLAN_BULLETS.map((b) => <li key={b}>{b}</li>)}</ul>}
              </div>
            </div>
            {turns.map((t, i) => (
              <div key={i} className={'dp-home-ai__turn dp-home-ai__turn--' + t.role}>
                <div className="dp-home-ai__bubble">
                  <p style={{ margin: 0 }}>{t.body}</p>
                  {t.action && <button className="dp-home-ai__inline" onClick={() => onNavigate(t.action!.target as 'projects')}>↗ {t.action.label}</button>}
                  {t.time && <span className="dp-home-ai__time">{t.time}</span>}
                </div>
              </div>
            ))}
            {thinking && <div className="dp-home-ai__turn dp-home-ai__turn--assistant"><div className="dp-home-ai__bubble dp-home-ai__bubble--loading">Thinking…</div></div>}
          </div>

          <div className="dp-home-ai__suggest">
            {HOME_SUGGESTIONS.map((s) => (
              <button key={s.label} className="dp-home-ai__chip" onClick={() => send(s.label)}>
                <span aria-hidden="true">{s.icon}</span> {s.label}
              </button>
            ))}
          </div>

          <form className="dp-home-ai__input" onSubmit={(e) => { e.preventDefault(); send(input) }}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) } }}
              placeholder="Ask anything or give an instruction…"
              aria-label="Ask anything or give an instruction"
            />
            <button className="dp-home-ai__send" type="submit" aria-label="Send" disabled={!input.trim()}>➤</button>
          </form>
          <div className="dp-home-ai__foot">
            <span>AI responses may be incorrect.</span>
            <span className="dp-home-ai__fb"><button className="dp-icon-button" aria-label="Good">👍</button><button className="dp-icon-button" aria-label="Bad">👎</button></span>
          </div>
        </aside>
      )}
    </div>
  )
}
