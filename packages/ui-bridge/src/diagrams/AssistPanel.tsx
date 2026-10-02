import React, { useEffect, useRef, useState } from 'react'
import { diagramsApi, type AssistAction, type CreditSummary } from './diagramsClient'
import type { Diagram } from './dmind'
import { applyPatch, type Patch } from './patch'

export type AssistTrigger = { nonce: number; action: AssistAction; options?: { count?: number; mode?: string; language?: string }; prompt?: string }
type Line = { role: 'user' | 'assistant'; content: string }
type Proposal = { patch: Patch; lines: string[] }

const CHIPS: { label: string; action: AssistAction; options?: AssistTrigger['options']; needsTopic: boolean; prompt?: string }[] = [
  { label: 'Suggest subtopics', action: 'grow', options: { count: 4 }, needsTopic: true },
  { label: 'Explain this topic', action: 'explain', needsTopic: true },
  { label: 'Tidy structure', action: 'reorganize', needsTopic: false },
  { label: 'Polish wording', action: 'refine', options: { mode: 'polish' }, needsTopic: true },
  { label: 'Shorten', action: 'refine', options: { mode: 'shorten' }, needsTopic: true },
  { label: 'Break into tasks', action: 'chat', needsTopic: true, prompt: 'Break the selected topic into concrete, actionable to-do tasks as child topics. Start each with a verb and keep each small enough to finish in a day or two.' },
  { label: 'Find gaps and risks', action: 'chat', needsTopic: false, prompt: 'What is missing from this map? Add the most important missing topics, including risks.' },
]

/**
 * Ask AI (batch C2): chat and one-click actions. The model only ever proposes changes; each one is
 * shown as a list of differences and applied to the map only when the person presses Apply, and only
 * if the map has not changed since it was proposed. Undo restores the previous state afterwards.
 */
export function AssistPanel({
  diagram,
  focus,
  onApply,
  trigger,
}: {
  diagram: Diagram
  focus: string[]
  onApply: (next: Diagram) => void
  trigger: AssistTrigger | null
}) {
  const [available, setAvailable] = useState<boolean | null>(null)
  const [credits, setCredits] = useState<CreditSummary | null>(null)
  const [lines, setLines] = useState<Line[]>([])
  const [text, setText] = useState('')
  const [language, setLanguage] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [proposal, setProposal] = useState<Proposal | null>(null)
  const latest = useRef({ diagram, focus, lines })
  latest.current = { diagram, focus, lines }
  const handled = useRef(0)

  useEffect(() => {
    let live = true
    void diagramsApi.assistStatus().then((r) => {
      if (!live) return
      setAvailable(r.ok ? r.data.available : false)
      if (r.ok) setCredits(r.data.credits)
    })
    return () => {
      live = false
    }
  }, [])

  async function run(action: AssistAction, prompt = '', options?: AssistTrigger['options'], shown?: string) {
    const { diagram: d, focus: f, lines: history } = latest.current
    setError('')
    setProposal(null)
    setBusy(true)
    const asked = shown ?? prompt
    if (asked) setLines((l) => [...l, { role: 'user', content: asked }])
    try {
      const result = await diagramsApi.assist({ action, document: d, focus: f, prompt, history: history.slice(-6), options })
      if (!result.ok) {
        setError(result.status === 402 ? result.error + ' Credits refill monthly.' : result.error)
        return
      }
      const reply = result.data
      if (reply.credits) setCredits((c) => (c ? { ...c, balance: reply.credits!.balance } : c))
      setLines((l) => [...l, ...(reply.message ? [{ role: 'assistant' as const, content: reply.message }] : [])])
      if (reply.patch) {
        const check = await applyPatch(d, reply.patch)
        if (check.ok) setProposal({ patch: reply.patch, lines: check.diff.summary })
        else setError(check.reason === 'stale' ? 'The map changed while the AI was working. Ask again.' : check.message)
      } else if (reply.mode === 'model' && !reply.message) setLines((l) => [...l, { role: 'assistant', content: 'No changes suggested.' }])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The AI request failed.')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    if (trigger && trigger.nonce !== handled.current) {
      handled.current = trigger.nonce
      void run(trigger.action, trigger.prompt ?? '', trigger.options, trigger.prompt ? undefined : label(trigger))
    }
  }, [trigger])

  async function apply() {
    if (!proposal) return
    const result = await applyPatch(latest.current.diagram, proposal.patch)
    if (!result.ok) {
      setError(result.reason === 'stale' ? 'The map changed after this suggestion. Ask again.' : result.message)
      setProposal(null)
      return
    }
    onApply(result.diagram)
    setProposal(null)
    setLines((l) => [...l, { role: 'assistant', content: 'Applied. Undo brings the previous version back.' }])
  }

  const hasTopic = focus.length > 0
  const off = available === false
  return (
    <section className="dmind-ai" aria-label="Ask AI">
      <h4>
        Ask AI
        {credits?.enabled && (
          <small className="dmind-ai-credits" title="AI actions use your workspace's credits; they refill monthly">
            {' '}
            · {credits.balance} credits
          </small>
        )}
      </h4>
      {off && (
        <p className="dmind-ai-note">
          AI is not connected. Connect a provider in Settings to use these actions; everything else works without it.
        </p>
      )}
      <div className="dmind-ai-chips">
        {CHIPS.map((c) => (
          <button key={c.label} title={credits?.enabled ? `${credits.costs[c.action] ?? 1} credit(s)` : undefined} disabled={busy || off || (c.needsTopic && !hasTopic)} onClick={() => void run(c.action, c.prompt ?? '', c.options, c.label)}>
            {c.label}
          </button>
        ))}
        <span className="dmind-ai-translate">
          <input aria-label="Translate to" placeholder="Language" maxLength={40} value={language} onChange={(e) => setLanguage(e.target.value)} />
          <button disabled={busy || off || !hasTopic || !language.trim()} onClick={() => void run('refine', '', { mode: 'translate', language: language.trim() }, `Translate to ${language.trim()}`)}>
            Translate
          </button>
        </span>
      </div>
      {!hasTopic && !off && <p className="dmind-ai-note">Select a topic to use topic actions.</p>}
      {lines.length > 0 && (
        <ol className="dmind-ai-log" aria-live="polite">
          {lines.slice(-8).map((l, i) => (
            <li key={i} data-role={l.role}>
              {l.content}
            </li>
          ))}
        </ol>
      )}
      {busy && <p role="status">Thinking…</p>}
      {error && <p role="alert">{error}</p>}
      {proposal && (
        <div aria-label="Suggested changes" className="dmind-ai-proposal">
          <strong>Suggested changes</strong>
          <ul>
            {proposal.lines.slice(0, 30).map((line, i) => (
              <li key={i}>{line}</li>
            ))}
            {proposal.lines.length > 30 && <li>…and {proposal.lines.length - 30} more</li>}
          </ul>
          <button onClick={() => void apply()}>Apply suggestions</button>
          <button onClick={() => setProposal(null)}>Discard</button>
        </div>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault()
          const t = text.trim()
          if (!t || busy || off) return
          setText('')
          void run('chat', t)
        }}
      >
        <input aria-label="Message to AI" placeholder={off ? 'AI is not connected' : 'Ask for changes, e.g. “add a launch checklist under Marketing”'} maxLength={4000} value={text} disabled={off} onChange={(e) => setText(e.target.value)} />
        <button disabled={busy || off || !text.trim()}>Send</button>
      </form>
    </section>
  )
}

function label(t: AssistTrigger): string {
  return t.action === 'grow' ? 'Suggest subtopics' : t.action === 'explain' ? 'Explain this topic' : t.options?.mode === 'polish' ? 'Polish wording' : 'AI action'
}
