import React, { useEffect, useRef, useState } from 'react'
import { diagramsApi } from './diagramsClient'
import type { DiagramKind } from './dmind'
import { BRAINSTORM_MODES, TEMPLATES, modeById, templateById } from './templates'
import { speechSupported, startDictation, transcriptToOutline, type Dictation } from './voice'

/**
 * Ways to begin without typing everything (batch C3): templates, brainstorming modes, dictation and
 * an AI draft. All of them only fill the outline box; the person reviews it and the normal preview
 * decides what becomes a map.
 */
export function QuickStart({
  topic,
  content,
  onFill,
  onMessage,
  disabled,
}: {
  topic: string
  content: string
  onFill: (next: { topic?: string; content: string; kind?: DiagramKind }) => void
  onMessage: (text: string) => void
  disabled?: boolean
}) {
  const [aiReady, setAiReady] = useState(false)
  const [busy, setBusy] = useState(false)
  const [listening, setListening] = useState(false)
  const dictation = useRef<Dictation | null>(null)
  const base = useRef('')
  const canSpeak = speechSupported()

  useEffect(() => {
    let live = true
    void diagramsApi.assistStatus().then((r) => live && setAiReady(r.ok && r.data.available))
    return () => {
      live = false
      dictation.current?.stop()
    }
  }, [])

  function pickTemplate(id: string) {
    const t = templateById(id)
    if (!t) return
    onFill({ topic: topic.trim() ? undefined : t.name, content: t.outline, kind: t.kind })
    onMessage(`Template “${t.name}” loaded. Edit the lines, then press Next.`)
  }
  function pickMode(id: string) {
    const m = modeById(id)
    if (!m || !topic.trim()) return
    const lines = m.build(topic)
    onFill({ content: content.trim() ? content.replace(/\s+$/, '') + '\n' + lines : lines })
    onMessage(`${m.name} prompts added. Replace them with your own answers.`)
  }
  function dictate() {
    if (listening) return dictation.current?.stop()
    base.current = content.trim() ? content.replace(/\s+$/, '') + '\n' : ''
    const d = startDictation(
      navigator.language || 'en-US',
      (text) => onFill({ content: base.current + transcriptToOutline(text) }),
      (error) => {
        setListening(false)
        dictation.current = null
        if (error) onMessage(error)
      },
    )
    if (!d) return onMessage('Dictation is not available in this browser.')
    dictation.current = d
    setListening(true)
  }
  async function draft() {
    const prompt = [topic.trim(), content.trim()].filter(Boolean).join('\n\n')
    if (!prompt) return onMessage('Type a topic or a few words first.')
    setBusy(true)
    const r = await diagramsApi.assist({ action: 'generate', prompt })
    setBusy(false)
    if (!r.ok) return onMessage(r.error)
    if (!r.data.outline) return onMessage(r.data.message || 'The AI had no draft to offer.')
    onFill({ topic: topic.trim() ? undefined : r.data.title || undefined, content: r.data.outline })
    onMessage('AI draft added. Check it, edit freely, then press Next.')
  }

  return (
    <div className="dmind-quick" role="group" aria-label="Quick start">
      <label>
        Start from a template
        <select value="" disabled={disabled} onChange={(e) => pickTemplate(e.target.value)}>
          <option value="">Choose…</option>
          {TEMPLATES.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name} · {t.blurb}
            </option>
          ))}
        </select>
      </label>
      <label>
        Brainstorm this topic
        <select value="" disabled={disabled || !topic.trim()} onChange={(e) => pickMode(e.target.value)}>
          <option value="">{topic.trim() ? 'Choose a method…' : 'Type a topic first'}</option>
          {BRAINSTORM_MODES.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name} · {m.blurb}
            </option>
          ))}
        </select>
      </label>
      <div className="dmind-quick-buttons">
        {canSpeak && (
          <button type="button" aria-pressed={listening} disabled={disabled} onClick={dictate}>
            {listening ? 'Stop dictating' : 'Dictate'}
          </button>
        )}
        <button type="button" disabled={disabled || busy || !aiReady} title={aiReady ? undefined : 'Connect an AI provider in Settings to draft with AI'} onClick={() => void draft()}>
          {busy ? 'Drafting…' : 'Draft with AI'}
        </button>
      </div>
    </div>
  )
}
