import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { isDemoMode } from '../env'
import { emailApi, folderType, type EmailAccount, type EmailDetail, type EmailStatus, type EmailSummary, type OnboardingProvider } from './emailClient'
import { MailSetupWizard } from './MailSetupWizard'
import { sanitizeEmailHtml, textToSafeHtml } from './sanitizeEmailHtml'
import { EMAIL_FOLDERS, EMAIL_ITEMS, type MailMessage } from './emailMockData'

/**
 * Email workspace. In production (default) this is fully connected to real
 * accounts, folders, messages, drafts, and AI replies via `/v1/email/*` — no
 * placeholder data, with genuine onboarding/empty/loading/error states. Demo
 * mode keeps the offline sample experience for showcases.
 */
export function EmailWorkspace() {
  return isDemoMode() ? <DemoEmailWorkspace /> : <ConnectedEmailWorkspace />
}

type AiTab = 'draft' | 'chat'
type Tone = 'Professional' | 'Concise' | 'Friendly' | 'Direct' | 'Executive' | 'Empathetic'
type ChatTurn = { role: 'user' | 'assistant'; body: string; time?: string; draftCard?: { label: string; content: string } }

type AIDraftState = {
  content: string
  summary: string
  tone: Tone
  status: 'idle' | 'generating' | 'ready' | 'updating' | 'error'
  version: number
  insertedVersion?: number
}

const TONES: Tone[] = ['Professional', 'Concise', 'Friendly', 'Direct', 'Executive', 'Empathetic']
const SUGGESTED = ['Make it shorter', 'Use a more formal tone', 'Mention the weekly reporting requirement', 'Ask them to confirm the new delivery date']
const SUBSTANTIAL = 40

function nowTime(): string {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function baseDraft(msg: MailMessage | undefined, tone: Tone): string {
  const who = msg?.senderName?.split(' ')[0] ?? 'there'
  const opener = tone === 'Executive' ? `${who},\n\nNoted.` : `Hi ${who},\n\nThank you for the update.`
  const body =
    msg?.intent === 'scheduling'
      ? 'We understand the need to adjust the deadline due to the additional scope and dependencies on the design review.\n\nPlease confirm the new target date so we can realign resources and ensure the revised timeline does not impact key milestones.'
      : "I'll review this and follow up shortly with next steps."
  return `${opener}\n\n${body}\n\nBest regards,\nRuslan M.`
}

function summaryFor(msg: MailMessage | undefined): string {
  return msg?.intent === 'scheduling'
    ? 'Responds to the delivery-date change, acknowledges the added scope, and asks the sender to confirm the revised milestone.'
    : 'Acknowledges the message and proposes clear next steps.'
}

/** Deterministic revision until Ollabridge phrases the response. */
function revise(content: string, instruction: string): { content: string; label: string; note: string } {
  const l = instruction.toLowerCase()
  if (l.includes('short')) {
    const lines = content.split('\n').filter(Boolean)
    return { content: [lines[0], lines[1] ?? '', 'Best regards,\nRuslan M.'].filter(Boolean).join('\n\n'), label: 'Draft (shorter)', note: "I've updated the draft to be shorter and more concise." }
  }
  if (l.includes('formal') || l.includes('confident')) {
    return { content: content.replace('Thank you for the update.', 'Thank you for the detailed update.'), label: 'Draft (formal)', note: "I've made the tone more formal." }
  }
  if (l.includes('report')) {
    return { content: content.replace('Best regards,', 'We will include the weekly reporting requirement in the plan.\n\nBest regards,'), label: 'Draft (updated)', note: 'I mentioned the weekly reporting requirement.' }
  }
  if (l.includes('confirm') || l.includes('deadline') || l.includes('delivery date')) {
    return { content: content.replace('Best regards,', 'Could you confirm the new delivery date so we can plan around it?\n\nBest regards,'), label: 'Draft (updated)', note: 'I added a request to confirm the new delivery date.' }
  }
  if (l.includes('remove') && l.includes('paragraph')) {
    const lines = content.split('\n\n')
    return { content: [...lines.slice(0, -2), lines[lines.length - 1]].join('\n\n'), label: 'Draft (updated)', note: 'I removed the final paragraph.' }
  }
  return { content: content + `\n\n(Adjusted per: "${instruction}")`, label: 'Draft (updated)', note: 'Draft updated per your instruction.' }
}

/**
 * Demo Email workspace (offline sample, demo mode only). Outlook-familiar five
 * regions. Not shown in production — the connected workspace replaces it.
 */
function DemoEmailWorkspace() {
  const [folder, setFolder] = useState('Inbox')
  const [query, setQuery] = useState('')
  const [activeId, setActiveId] = useState(EMAIL_ITEMS[0]?.id)
  const [aiTab, setAiTab] = useState<AiTab>('draft')

  const active = EMAIL_ITEMS.find((m) => m.id === activeId)

  const [ai, setAi] = useState<AIDraftState>(() => ({
    content: baseDraft(active, 'Professional'),
    summary: summaryFor(active),
    tone: 'Professional',
    status: 'ready',
    version: 1,
  }))
  const [chat, setChat] = useState<ChatTurn[]>([])
  const [chatInput, setChatInput] = useState('')

  const [composerOpen, setComposerOpen] = useState(true)
  const [composerText, setComposerText] = useState('')
  const [inserted, setInserted] = useState(false)
  const [savedAt, setSavedAt] = useState<string | null>(null)
  const undoRef = useRef<string | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const liveRef = useRef<HTMLDivElement>(null)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return EMAIL_ITEMS
    return EMAIL_ITEMS.filter((m) => (m.subject + ' ' + m.sender + ' ' + m.preview).toLowerCase().includes(q))
  }, [query])

  const unreadCount = EMAIL_ITEMS.filter((m) => m.unread).length

  function selectMessage(id: string) {
    setActiveId(id)
    const msg = EMAIL_ITEMS.find((m) => m.id === id)
    setAi({ content: baseDraft(msg, ai.tone), summary: summaryFor(msg), tone: ai.tone, status: 'ready', version: 1 })
    setChat([])
    setComposerText('')
    setInserted(false)
    setSavedAt(null)
  }

  function announce(text: string) {
    if (liveRef.current) liveRef.current.textContent = text
  }

  function setTone(tone: Tone) {
    setAi((s) => ({ ...s, tone, content: baseDraft(active, tone), status: 'ready', version: s.version + 1 }))
  }

  function addToEmail() {
    if (!composerOpen) setComposerOpen(true)
    const current = composerText
    if (current.trim().length >= SUBSTANTIAL && current.trim() !== ai.content.trim()) {
      const ok = window.confirm('Your reply already contains text. Replace it with the AI draft? (Cancel keeps your text; OK replaces it.)')
      if (!ok) return
    }
    undoRef.current = current
    setComposerText(ai.content)
    setInserted(true)
    setAi((s) => ({ ...s, insertedVersion: s.version }))
    setSavedAt(nowTime())
    announce('AI draft added to the reply composer. Undo is available.')
    window.requestAnimationFrame(() => {
      const el = textareaRef.current
      if (el) { el.focus(); el.setSelectionRange(ai.content.length, ai.content.length) }
    })
  }

  function undoAdd() {
    if (undoRef.current !== null) {
      setComposerText(undoRef.current)
      undoRef.current = null
      setInserted(false)
      announce('Undid AI draft insertion.')
    }
  }

  function sendChat(text: string) {
    const instruction = text.trim()
    if (!instruction) return
    setChat((c) => [...c, { role: 'user', body: instruction, time: nowTime() }])
    setChatInput('')
    setAi((s) => ({ ...s, status: 'updating' }))
    window.setTimeout(() => {
      const r = revise(ai.content, instruction)
      setAi((s) => ({ ...s, content: r.content, status: 'ready', version: s.version + 1 }))
      setChat((c) => [...c, { role: 'assistant', body: r.note, time: nowTime(), draftCard: { label: r.label, content: r.content } }])
      announce('AI draft updated. Review it in the Draft tab or add it to the email.')
    }, 400)
  }

  const addLabel = inserted && ai.insertedVersion === ai.version ? 'Update email' : inserted ? 'Replace inserted draft' : 'Add to email'

  return (
    <div className="dp-mail">
      <div ref={liveRef} aria-live="polite" className="dp-sr-only" />

      {/* Region 2 — Mailboxes */}
      <nav className="dp-mbx" aria-label="Mailboxes">
        <div className="dp-mbx__search">
          <span className="dp-mbx__search-icon" aria-hidden="true">⌕</span>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search emails" aria-label="Search emails" />
        </div>
        <div className="dp-mbx__heading">
          <span>Mailboxes</span>
          <button className="dp-mbx__add" aria-label="Add mailbox">＋</button>
        </div>
        <div className="dp-mbx__list">
          {EMAIL_FOLDERS.map((f) => (
            <button key={f.name} className={'dp-mbx__folder' + (folder === f.name ? ' is-active' : '')} onClick={() => setFolder(f.name)}>
              <span className="dp-mbx__folder-icon" aria-hidden="true">{f.icon}</span>
              <span className="dp-mbx__folder-label">{f.name}</span>
              {f.count != null && <span className="dp-mbx__folder-count">{f.count}</span>}
            </button>
          ))}
        </div>
        <button className="dp-mbx__filter">⚟ Filter</button>
      </nav>

      {/* Region 3 — Message list */}
      <section className="dp-msglist" aria-label="Messages">
        <header className="dp-msglist__head">
          <div className="dp-msglist__folder">{folder} <span className="dp-msglist__count">{unreadCount}</span> <span aria-hidden="true">⌄</span></div>
          <button className="dp-msglist__sort">Sort: Newest <span aria-hidden="true">⌄</span></button>
        </header>
        <ul className="dp-msglist__rows">
          {filtered.map((m) => (
            <li key={m.id}>
              <button className={'dp-msgrow' + (m.id === activeId ? ' is-selected' : '') + (m.unread ? ' is-unread' : '')} onClick={() => selectMessage(m.id)}>
                <span className="dp-msgrow__dot" aria-hidden="true" />
                <span className="dp-msgrow__main">
                  <span className="dp-msgrow__top">
                    <span className="dp-msgrow__sender">{m.sender}</span>
                    <span className="dp-msgrow__time">{m.time}</span>
                  </span>
                  <span className="dp-msgrow__subject">{m.subject}{m.hasAttachment && <span className="dp-msgrow__clip" aria-label="has attachment"> 📎</span>}</span>
                  <span className="dp-msgrow__preview">{m.preview}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      {/* Region 4 — Reading + composer */}
      <section className="dp-read" aria-label="Message">
        <header className="dp-read__toolbar">
          <div className="dp-read__tools">
            <button className="dp-read__tool">🗄 Archive</button>
            <button className="dp-read__tool">📁 Move <span aria-hidden="true">⌄</span></button>
            <button className="dp-read__tool">✉ Mark unread</button>
            <button className="dp-read__tool">⋯ More</button>
          </div>
          <div className="dp-read__nav">
            <button className="dp-icon-button" aria-label="Previous message">‹</button>
            <button className="dp-icon-button" aria-label="Next message">›</button>
          </div>
        </header>

        {active && (
          <div className="dp-read__scroll">
            <div className="dp-read__headrow">
              <h1 className="dp-read__subject">{active.subject}</h1>
              <button className="dp-icon-button" aria-label="Mark important">☆</button>
            </div>
            <div className="dp-read__meta">
              <span className="dp-read__avatar" aria-hidden="true">{active.senderName.split(' ').map((p) => p[0]).slice(0, 2).join('')}</span>
              <div className="dp-read__from">
                <strong>{active.sender}</strong>
                <span className="dp-read__to">To: me</span>
              </div>
              <span className="dp-read__time">{active.time}</span>
              <button className="dp-icon-button" aria-label="Reply" onClick={() => setComposerOpen(true)}>↩</button>
              <button className="dp-icon-button" aria-label="More">⋯</button>
            </div>

            <div className="dp-read__body">
              {active.body.map((p, i) => (
                <p key={i}>{p.split('\n').map((line, j) => <React.Fragment key={j}>{j > 0 && <br />}{line}</React.Fragment>)}</p>
              ))}
            </div>

            {composerOpen && (
              <div className="dp-composer">
                <div className="dp-composer__head">
                  <span>Replying to {active.sender}</span>
                  {inserted && (
                    <span className="dp-composer__status">
                      <span className="dp-composer__added">Added to draft</span>
                      {undoRef.current !== null && <> · <button className="dp-linkbtn" onClick={undoAdd}>Undo</button></>}
                    </span>
                  )}
                </div>
                <textarea
                  ref={textareaRef}
                  className="dp-composer__text"
                  value={composerText}
                  onChange={(e) => { setComposerText(e.target.value); setSavedAt(nowTime()) }}
                  placeholder="Write your reply, or use the AI assistant to draft it…"
                  aria-label="Reply body"
                />
                <div className="dp-composer__format" role="toolbar" aria-label="Formatting">
                  {['📎', '🙂', 'B', 'I', 'U', '•', '1.', '🔗', '⋯'].map((g, i) => (
                    <button key={i} className="dp-composer__fmt" aria-label={g}>{g}</button>
                  ))}
                </div>
                <div className="dp-composer__foot">
                  <div className="dp-composer__send">
                    <button className="dp-send-button">➤ Send</button>
                    <button className="dp-send-button dp-send-button--split" aria-label="Send options">⌄</button>
                  </div>
                  <button className="dp-ghost-button" onClick={() => { setComposerText(''); setInserted(false); setSavedAt(null) }}>Discard</button>
                  <div className="dp-composer__extras">
                    <button className="dp-icon-button" aria-label="Schedule send">🗓</button>
                    <button className="dp-icon-button" aria-label="Set reminder">🔔</button>
                    <button className="dp-icon-button" aria-label="Encrypt">🔒</button>
                  </div>
                  {savedAt && <span className="dp-composer__saved">Draft saved {savedAt}</span>}
                  <button className="dp-icon-button" aria-label="Delete draft">🗑</button>
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Region 5 — AI assistant */}
      <aside className="dp-ai" aria-label="AI Email Assistant">
        <header className="dp-ai__head">
          <div className="dp-ai__title"><span className="dp-ai__spark" aria-hidden="true">✦</span> AI Email Assistant</div>
          <div className="dp-ai__head-actions">
            <button className="dp-icon-button" aria-label="About the assistant">ⓘ</button>
            <button className="dp-icon-button" aria-label="Close assistant">✕</button>
          </div>
        </header>
        <div className="dp-ai__tabs" role="tablist" aria-label="Assistant">
          <button role="tab" aria-selected={aiTab === 'draft'} className={'dp-ai__tab' + (aiTab === 'draft' ? ' is-active' : '')} onClick={() => setAiTab('draft')}>Draft</button>
          <button role="tab" aria-selected={aiTab === 'chat'} className={'dp-ai__tab' + (aiTab === 'chat' ? ' is-active' : '')} onClick={() => setAiTab('chat')}>Chat</button>
        </div>

        {aiTab === 'draft' && (
          <div className="dp-ai__scroll" role="tabpanel" aria-label="Draft">
            <div className="dp-ai__label">Draft summary</div>
            <p className="dp-ai__summary">{ai.summary}</p>
            <div className="dp-ai__label">Suggested tone</div>
            <select className="dp-ai__tone" value={ai.tone} onChange={(e) => setTone(e.target.value as Tone)} aria-label="Suggested tone">
              {TONES.map((t) => <option key={t}>{t}</option>)}
            </select>
            <div className="dp-ai__label dp-ai__label--row">AI draft {ai.status === 'updating' && <span className="dp-ai__spin">Generating…</span>}</div>
            <textarea className="dp-ai__draft" value={ai.content} onChange={(e) => setAi((s) => ({ ...s, content: e.target.value }))} aria-label="AI draft preview" />
            <div className="dp-ai__draft-actions">
              <button className="dp-ai__add" onClick={addToEmail}><span aria-hidden="true">＋</span> {addLabel}</button>
              <button className="dp-icon-button" aria-label="Copy draft" onClick={() => navigator.clipboard?.writeText(ai.content).catch(() => undefined)}>⧉</button>
              <button className="dp-icon-button" aria-label="Good draft">👍</button>
              <button className="dp-icon-button" aria-label="Bad draft">👎</button>
            </div>
          </div>
        )}

        {aiTab === 'chat' && (
          <div className="dp-ai__chat" role="tabpanel" aria-label="Chat">
            <div className="dp-ai__log">
              {chat.length === 0 && (
                <div className="dp-ai__suggest">
                  {SUGGESTED.map((s) => <button key={s} className="dp-ai__chip" onClick={() => sendChat(s)}>{s}</button>)}
                </div>
              )}
              {chat.map((t, i) => (
                <div key={i} className={'dp-ai__turn dp-ai__turn--' + t.role}>
                  {t.role === 'assistant' && <span className="dp-ai__spark dp-ai__turn-spark" aria-hidden="true">✦</span>}
                  <div className="dp-ai__bubble">
                    <p>{t.body}</p>
                    {t.time && <span className="dp-ai__turn-time">{t.time}</span>}
                    {t.draftCard && (
                      <div className="dp-ai__draftcard">
                        <div className="dp-ai__draftcard-label">{t.draftCard.label}</div>
                        <div className="dp-ai__draftcard-body">{t.draftCard.content.split('\n').map((l, j) => <React.Fragment key={j}>{j > 0 && <br />}{l}</React.Fragment>)}</div>
                        <div className="dp-ai__draft-actions">
                          <button className="dp-ai__add" onClick={addToEmail}><span aria-hidden="true">＋</span> Add to email</button>
                          <button className="dp-icon-button" aria-label="Copy" onClick={() => navigator.clipboard?.writeText(t.draftCard!.content).catch(() => undefined)}>⧉</button>
                          <button className="dp-icon-button" aria-label="Good">👍</button>
                          <button className="dp-icon-button" aria-label="Bad">👎</button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {ai.status === 'updating' && <div className="dp-ai__turn dp-ai__turn--assistant"><span className="dp-ai__spark dp-ai__turn-spark" aria-hidden="true">✦</span><div className="dp-ai__bubble dp-ai__bubble--loading">Generating…</div></div>}
            </div>
            <form className="dp-ai__input" onSubmit={(e) => { e.preventDefault(); sendChat(chatInput) }}>
              <input
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(chatInput) } }}
                placeholder="Ask AI to modify the draft…"
                aria-label="Ask AI to modify the draft"
              />
              <button className="dp-ai__send" type="submit" aria-label="Send" disabled={!chatInput.trim()}>➤</button>
            </form>
          </div>
        )}
        <div className="dp-ai__foot">AI-generated content may be incorrect.</div>
      </aside>
    </div>
  )
}

// ============================================================================
// Connected (production) email workspace — real accounts, folders, messages,
// drafts, and AI replies. No placeholder data; genuine states throughout.
// ============================================================================

const CONN_TONES: Tone[] = ['Professional', 'Concise', 'Friendly', 'Direct', 'Executive', 'Empathetic']
const FOLDER_ICON: Record<string, string> = {
  inbox: '📥', drafts: '📝', sent: '📤', archive: '🗄', important: '⭐', spam: '🚫', trash: '🗑', custom: '📁',
}

type LoadState = 'loading' | 'ready' | 'empty' | 'error'

function ConnectedEmailWorkspace() {
  const [status, setStatus] = useState<EmailStatus | null>(null)
  const [statusState, setStatusState] = useState<'loading' | 'ready' | 'error'>('loading')

  const loadStatus = useCallback(() => {
    setStatusState('loading')
    emailApi.status().then((r) => {
      if (r.ok) { setStatus(r.data); setStatusState('ready') }
      else { setStatusState('error') }
    })
  }, [])
  useEffect(() => { loadStatus() }, [loadStatus])

  if (statusState === 'loading') return <EmailShellSkeleton label="Loading your mailbox…" />
  if (statusState === 'error') {
    return (
      <div className="dp-mail dp-mail--state">
        <div className="dp-mailstate">
          <h2>Email is temporarily unavailable.</h2>
          <p>Your drafts remain saved.</p>
          <button className="dp-send-button" onClick={loadStatus}>Try again</button>
        </div>
      </div>
    )
  }
  if (!status?.connected || !status.account) {
    return <EmailOnboarding providers={status?.providers ?? []} onRetry={loadStatus} />
  }
  return <EmailMain account={status.account} onReconnect={loadStatus} />
}

function EmailOnboarding({ providers, onRetry }: { providers: OnboardingProvider[]; onRetry: () => void }) {
  return (
    <div className="dp-mail dp-mail--state">
      <div className="dp-onbmail">
        <MailSetupWizard providers={providers} onConnected={onRetry} />
      </div>
    </div>
  )
}

function EmailShellSkeleton({ label }: { label: string }) {
  return (
    <div className="dp-mail dp-mail--state" aria-busy="true">
      <div className="dp-mailstate"><span className="dp-spinner" aria-hidden="true" /><p>{label}</p></div>
    </div>
  )
}

function EmailMain({ account, onReconnect }: { account: EmailAccount; onReconnect: () => void }) {
  const [folders, setFolders] = useState<string[]>([])
  const [folder, setFolder] = useState('INBOX')
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  const [messages, setMessages] = useState<EmailSummary[]>([])
  const [listState, setListState] = useState<LoadState>('loading')
  const [activeUid, setActiveUid] = useState<string | null>(null)
  const [detail, setDetail] = useState<EmailDetail | null>(null)
  const [detailState, setDetailState] = useState<LoadState>('empty')
  const reqRef = useRef(0)
  const liveRef = useRef<HTMLDivElement>(null)

  // AI draft (generated from the real selected message)
  const [aiTab, setAiTab] = useState<AiTab>('draft')
  const [tone, setToneState] = useState<Tone>('Professional')
  const [ai, setAi] = useState<{ body: string; draftUid: string | null; status: 'idle' | 'generating' | 'ready' | 'error' }>({ body: '', draftUid: null, status: 'idle' })
  const [chat, setChat] = useState<ChatTurn[]>([])
  const [chatInput, setChatInput] = useState('')

  // Composer (real reply)
  const [composerText, setComposerText] = useState('')
  const [inserted, setInserted] = useState(false)
  const [sendState, setSendState] = useState<'idle' | 'sending' | 'sent' | 'needs_approval' | 'error'>('idle')
  const [sendMsg, setSendMsg] = useState('')
  const undoRef = useRef<string | null>(null)

  const announce = (t: string) => { if (liveRef.current) liveRef.current.textContent = t }

  useEffect(() => { emailApi.folders().then((r) => { if (r.ok) setFolders(r.data.folders) }) }, [])

  // Debounce search typing; cancel stale queries via a request id.
  useEffect(() => { const id = window.setTimeout(() => setDebounced(query.trim()), 300); return () => window.clearTimeout(id) }, [query])

  const loadMessages = useCallback(() => {
    const my = ++reqRef.current
    setListState('loading')
    emailApi.messages(debounced || undefined).then((r) => {
      if (my !== reqRef.current) return // stale
      if (!r.ok) { setListState('error'); return }
      setMessages(r.data.items)
      setListState(r.data.items.length === 0 ? 'empty' : 'ready')
    })
  }, [debounced])
  useEffect(() => { loadMessages() }, [loadMessages])

  const selectMessage = useCallback((uid: string) => {
    setActiveUid(uid)
    setDetailState('loading')
    setComposerText(''); setInserted(false); setSendState('idle'); setSendMsg(''); setChat([])
    setAi({ body: '', draftUid: null, status: 'idle' })
    emailApi.message(uid).then((r) => {
      if (r.ok) { setDetail(r.data); setDetailState('ready') }
      else { setDetail(null); setDetailState('error') }
    })
  }, [])

  const generate = useCallback((uid: string, t: Tone) => {
    setAi((s) => ({ ...s, status: 'generating' }))
    emailApi.draftReply(uid, t.toLowerCase()).then((r) => {
      if (r.ok) { setAi({ body: r.data.body, draftUid: r.data.draftUid, status: 'ready' }); announce('AI draft ready.') }
      else setAi((s) => ({ ...s, status: 'error' }))
    })
  }, [])

  function setTone(t: Tone) { setToneState(t); if (activeUid) generate(activeUid, t) }

  function reviseDraft(instruction: string) {
    const q = instruction.trim()
    if (!q || !activeUid || !ai.body) return
    setChat((c) => [...c, { role: 'user', body: q, time: nowTime() }])
    setChatInput('')
    setAi((s) => ({ ...s, status: 'generating' }))
    emailApi.revise(activeUid, ai.body, q, tone.toLowerCase()).then((r) => {
      if (r.ok) {
        setAi((s) => ({ ...s, body: r.data.body, status: 'ready' }))
        setChat((c) => [...c, { role: 'assistant', body: 'Updated the draft.', time: nowTime(), draftCard: { label: 'Draft (updated)', content: r.data.body } }])
        announce('AI draft updated.')
      } else setAi((s) => ({ ...s, status: 'error' }))
    })
  }

  function addToEmail() {
    if (ai.status !== 'ready' || !ai.body) return
    const current = composerText
    if (current.trim().length >= 40 && current.trim() !== ai.body.trim()) {
      if (!window.confirm('Your reply already contains text. Replace it with the AI draft? (Cancel keeps your text.)')) return
    }
    undoRef.current = current
    setComposerText(ai.body); setInserted(true)
    announce('AI draft inserted into the reply composer. Undo is available.')
  }
  function undoAdd() { if (undoRef.current !== null) { setComposerText(undoRef.current); undoRef.current = null; setInserted(false); announce('Undid AI draft insertion.') } }

  function send() {
    if (!detail || !ai.draftUid || sendState === 'sending') return
    if (!composerText.trim()) { setSendState('error'); setSendMsg('Write a reply before sending.'); return }
    if (!window.confirm(`Send this reply to ${detail.from}?`)) return
    setSendState('sending')
    emailApi.send(ai.draftUid, [detail.from], `Re: ${detail.subject}`, composerText, true).then((r) => {
      if (r.ok) { setSendState('sent'); setSendMsg('Message sent.'); announce('Message sent successfully.') }
      else if (r.status === 403) { setSendState('needs_approval'); setSendMsg('This send needs approval. Open the Approval Center to approve it — DayPilot never sends without your approval.') }
      else { setSendState('error'); setSendMsg(`Could not send (${r.error}).`) }
    })
  }

  const inboxCount = messages.length
  const activeSummary = messages.find((m) => m.externalId === activeUid)

  return (
    <div className="dp-mail">
      <div ref={liveRef} aria-live="polite" className="dp-sr-only" />

      {/* Mailboxes */}
      <nav className="dp-mbx" aria-label="Mailboxes">
        <div className="dp-mbx__search">
          <span className="dp-mbx__search-icon" aria-hidden="true">⌕</span>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search emails" aria-label="Search emails" />
        </div>
        <div className="dp-mbx__heading"><span>{account.emailAddress || account.provider}</span></div>
        <div className="dp-mbx__list">
          {folders.length === 0 && <p className="dp-mbx__empty">No folders yet.</p>}
          {folders.map((f) => {
            const t = folderType(f)
            return (
              <button key={f} className={'dp-mbx__folder' + (folder === f ? ' is-active' : '')} onClick={() => setFolder(f)}>
                <span className="dp-mbx__folder-icon" aria-hidden="true">{FOLDER_ICON[t]}</span>
                <span className="dp-mbx__folder-label">{f}</span>
                {t === 'inbox' && listState === 'ready' && <span className="dp-mbx__folder-count">{inboxCount}</span>}
              </button>
            )
          })}
        </div>
      </nav>

      {/* Message list */}
      <section className="dp-msglist" aria-label="Messages">
        <header className="dp-msglist__head">
          <div className="dp-msglist__folder">{folder}{listState === 'ready' && <span className="dp-msglist__count">{inboxCount}</span>}</div>
        </header>
        {listState === 'loading' && <ul className="dp-msglist__rows">{[0, 1, 2, 3].map((i) => <li key={i} className="dp-skelrow" />)}</ul>}
        {listState === 'error' && <div className="dp-liststate"><p>We couldn’t load your messages.</p><button className="dp-linkbtn" onClick={loadMessages}>Try again</button></div>}
        {listState === 'empty' && <div className="dp-liststate"><p>{debounced ? 'No emails match your search.' : 'Your inbox is empty.'}</p></div>}
        {listState === 'ready' && (
          <ul className="dp-msglist__rows">
            {messages.map((m) => (
              <li key={m.id}>
                <button className={'dp-msgrow' + (m.externalId === activeUid ? ' is-selected' : '') + (m.status !== 'read' ? ' is-unread' : '')} onClick={() => selectMessage(m.externalId)}>
                  <span className="dp-msgrow__dot" aria-hidden="true" />
                  <span className="dp-msgrow__main">
                    <span className="dp-msgrow__top">
                      <span className="dp-msgrow__sender">{m.sender}</span>
                      {m.urgency === 'high' && <span className="dp-msgrow__time dp-msgrow__urgent">urgent</span>}
                    </span>
                    <span className="dp-msgrow__subject">{m.subject}</span>
                    {m.actionItems.length > 0 && <span className="dp-msgrow__preview">{m.actionItems[0]}</span>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Reading + composer */}
      <section className="dp-read" aria-label="Message">
        <header className="dp-read__toolbar">
          <div className="dp-read__tools">
            <button className="dp-read__tool" disabled={!detail}>🗄 Archive</button>
            <button className="dp-read__tool" disabled={!detail}>✉ Mark unread</button>
            <button className="dp-read__tool" disabled={!detail}>⋯ More</button>
          </div>
        </header>

        {detailState === 'empty' && <div className="dp-read__placeholder"><p>Select an email to read it here.</p></div>}
        {detailState === 'loading' && <div className="dp-read__placeholder" aria-busy="true"><span className="dp-spinner" aria-hidden="true" /><p>Loading message…</p></div>}
        {detailState === 'error' && <div className="dp-read__placeholder"><p>We couldn’t load this message.</p><button className="dp-linkbtn" onClick={() => activeUid && selectMessage(activeUid)}>Try again</button></div>}
        {detailState === 'ready' && detail && (
          <div className="dp-read__scroll">
            <div className="dp-read__headrow"><h1 className="dp-read__subject">{detail.subject}</h1></div>
            <div className="dp-read__meta">
              <span className="dp-read__avatar" aria-hidden="true">{(detail.from[0] || '?').toUpperCase()}</span>
              <div className="dp-read__from"><strong>{detail.from}</strong><span className="dp-read__to">To: {detail.to.join(', ') || 'me'}</span></div>
              {detail.receivedAt && <span className="dp-read__time">{detail.receivedAt}</span>}
            </div>
            <EmailBody detail={detail} />
            {detail.hasAttachments && <p className="dp-read__attn">📎 This message has attachments. Attachments are fetched from the provider only when you open them.</p>}

            <div className="dp-composer">
              <div className="dp-composer__head">
                <span>Replying to {detail.from}</span>
                {inserted && <span className="dp-composer__status"><span className="dp-composer__added">AI draft added</span>{undoRef.current !== null && <> · <button className="dp-linkbtn" onClick={undoAdd}>Undo</button></>}</span>}
              </div>
              <textarea className="dp-composer__text" value={composerText} onChange={(e) => setComposerText(e.target.value)} placeholder="Write your reply, or use the AI assistant to draft it…" aria-label="Reply body" />
              <div className="dp-composer__foot">
                <div className="dp-composer__send">
                  <button className="dp-send-button" onClick={send} disabled={sendState === 'sending' || !account.capabilities.send}>{sendState === 'sending' ? 'Sending…' : '➤ Send'}</button>
                </div>
                <button className="dp-ghost-button" onClick={() => { setComposerText(''); setInserted(false) }}>Discard</button>
                {!account.capabilities.send && <span className="dp-composer__saved">DayPilot does not have permission to send email.</span>}
                {sendState !== 'idle' && sendMsg && <span className={'dp-composer__sendmsg dp-composer__sendmsg--' + sendState}>{sendMsg}</span>}
              </div>
            </div>
          </div>
        )}
      </section>

      {/* AI assistant — uses the real selected message */}
      <aside className="dp-ai" aria-label="AI Email Assistant">
        <header className="dp-ai__head"><div className="dp-ai__title"><span className="dp-ai__spark" aria-hidden="true">✦</span> AI Email Assistant</div></header>
        <div className="dp-ai__tabs" role="tablist" aria-label="Assistant">
          <button role="tab" aria-selected={aiTab === 'draft'} className={'dp-ai__tab' + (aiTab === 'draft' ? ' is-active' : '')} onClick={() => setAiTab('draft')}>Draft</button>
          <button role="tab" aria-selected={aiTab === 'chat'} className={'dp-ai__tab' + (aiTab === 'chat' ? ' is-active' : '')} onClick={() => setAiTab('chat')}>Chat</button>
        </div>

        {aiTab === 'draft' && (
          <div className="dp-ai__scroll" role="tabpanel" aria-label="Draft">
            {!activeUid && <p className="dp-ai__empty">Select an email to create a response.</p>}
            {activeUid && (
              <>
                <div className="dp-ai__label">Suggested tone</div>
                <select className="dp-ai__tone" value={tone} onChange={(e) => setTone(e.target.value as Tone)} aria-label="Suggested tone">{CONN_TONES.map((t) => <option key={t}>{t}</option>)}</select>
                <div className="dp-ai__label dp-ai__label--row">AI draft {ai.status === 'generating' && <span className="dp-ai__spin">Generating…</span>}</div>
                {ai.status === 'idle' && <button className="dp-ai__add" onClick={() => activeUid && generate(activeUid, tone)}>✦ Generate reply</button>}
                {ai.status === 'error' && <p className="dp-ai__empty">Draft generation failed. <button className="dp-linkbtn" onClick={() => activeUid && generate(activeUid, tone)}>Try again</button></p>}
                {(ai.status === 'ready' || ai.status === 'generating') && ai.body && (
                  <>
                    <textarea className="dp-ai__draft" value={ai.body} onChange={(e) => setAi((s) => ({ ...s, body: e.target.value }))} aria-label="AI draft preview" />
                    <div className="dp-ai__draft-actions">
                      <button className="dp-ai__add" onClick={addToEmail}><span aria-hidden="true">＋</span> {inserted ? 'Update email' : 'Add to email'}</button>
                      <button className="dp-icon-button" aria-label="Copy draft" onClick={() => navigator.clipboard?.writeText(ai.body).catch(() => undefined)}>⧉</button>
                    </div>
                  </>
                )}
              </>
            )}
          </div>
        )}

        {aiTab === 'chat' && (
          <div className="dp-ai__chat" role="tabpanel" aria-label="Chat">
            <div className="dp-ai__log">
              {!activeUid && <p className="dp-ai__empty">Select an email and generate a draft to refine it here.</p>}
              {activeUid && chat.length === 0 && ai.body && (
                <div className="dp-ai__suggest">{SUGGESTED.map((s) => <button key={s} className="dp-ai__chip" onClick={() => reviseDraft(s)}>{s}</button>)}</div>
              )}
              {chat.map((t, i) => (
                <div key={i} className={'dp-ai__turn dp-ai__turn--' + t.role}>
                  {t.role === 'assistant' && <span className="dp-ai__spark dp-ai__turn-spark" aria-hidden="true">✦</span>}
                  <div className="dp-ai__bubble"><p>{t.body}</p>{t.draftCard && <div className="dp-ai__draftcard"><div className="dp-ai__draftcard-body">{t.draftCard.content.split('\n').map((l, j) => <React.Fragment key={j}>{j > 0 && <br />}{l}</React.Fragment>)}</div><div className="dp-ai__draft-actions"><button className="dp-ai__add" onClick={addToEmail}><span aria-hidden="true">＋</span> Add to email</button></div></div>}</div>
                </div>
              ))}
              {ai.status === 'generating' && chat.length > 0 && <div className="dp-ai__turn dp-ai__turn--assistant"><span className="dp-ai__spark dp-ai__turn-spark" aria-hidden="true">✦</span><div className="dp-ai__bubble dp-ai__bubble--loading">Generating…</div></div>}
            </div>
            <form className="dp-ai__input" onSubmit={(e) => { e.preventDefault(); reviseDraft(chatInput) }}>
              <input value={chatInput} onChange={(e) => setChatInput(e.target.value)} placeholder="Ask AI to modify the draft…" aria-label="Ask AI to modify the draft" disabled={!ai.body} />
              <button className="dp-ai__send" type="submit" aria-label="Send" disabled={!chatInput.trim() || !ai.body}>➤</button>
            </form>
          </div>
        )}
        <div className="dp-ai__foot">The assistant uses only the selected email. AI-generated content may be incorrect.</div>
      </aside>
    </div>
  )
}

/** Render an email body safely: sanitized HTML or escaped plain text. */
function EmailBody({ detail }: { detail: EmailDetail }) {
  const rendered = useMemo(() => {
    if (detail.html && detail.html.trim()) {
      const r = sanitizeEmailHtml(detail.html)
      return { html: r.html, blocked: r.blockedImages }
    }
    return { html: textToSafeHtml(detail.text), blocked: 0 }
  }, [detail])
  return (
    <div className="dp-read__body">
      {rendered.blocked > 0 && <p className="dp-read__imgblock">🚫 {rendered.blocked} remote image(s) blocked to protect your privacy.</p>}
      <div className="dp-read__html" dangerouslySetInnerHTML={{ __html: rendered.html }} />
    </div>
  )
}
