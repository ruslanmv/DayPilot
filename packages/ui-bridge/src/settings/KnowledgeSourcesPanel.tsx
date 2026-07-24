import React, { useCallback, useEffect, useState } from 'react'

import { isDemoMode } from '../env'
import { KNOWLEDGE_SOURCES, SOURCES_SUMMARY } from './settingsData'
import { knowledgeApi, sourceStatusLabel, type KnowledgeSource } from './knowledgeSourcesClient'

/**
 * Settings → Knowledge sources (Issue 1).
 *
 * Real, backend-owned sources with working buttons: "Add folder" posts a
 * validated server path, "Re-index" enqueues a durable job, and each source can
 * be removed. Box is offered only when the deployment configured it. Demo mode
 * shows the sample sources for illustration.
 */
export function KnowledgeSourcesPanel() {
  const [sources, setSources] = useState<KnowledgeSource[]>([])
  const [boxAvailable, setBoxAvailable] = useState(false)
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [busy, setBusy] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  const load = useCallback(() => {
    if (isDemoMode()) { setState('ready'); return }
    setState('loading')
    knowledgeApi.list().then((r) => {
      if (r.ok) { setSources(r.data.sources); setBoxAvailable(r.data.boxAvailable); setState('ready') }
      else setState('error')
    })
  }, [])
  useEffect(() => { load() }, [load])

  async function addFolder() {
    const path = window.prompt('Enter a folder path on the DayPilot server (a browser can’t hand the server an arbitrary local folder):', '/data/projects')
    if (!path) return
    setBusy('add'); setNote(null)
    const r = await knowledgeApi.addLocal(path.trim())
    setBusy(null)
    if (r.ok) { setNote(`Added “${r.data.source.displayName}” — indexing queued.`); load() }
    else setNote(r.error === 'path_not_found' || (r.status === 404) ? `No folder found at ${path} on the server.` : 'Could not add that folder.')
  }

  async function connectBox() {
    setBusy('box'); setNote(null)
    const r = await knowledgeApi.boxStart()
    setBusy(null)
    setNote(r.ok ? (r.data.available ? 'Opening Box sign-in…' : r.data.message ?? 'Box isn’t configured on this deployment.') : 'Could not reach the server.')
  }

  async function reindex(id: string) {
    setBusy(id); setNote(null)
    const r = await knowledgeApi.reindex(id)
    setBusy(null)
    if (r.ok) { setNote('Re-index queued.'); load() } else setNote('Could not queue re-index.')
  }

  async function remove(id: string) {
    setBusy(id); setNote(null)
    const r = await knowledgeApi.remove(id)
    setBusy(null)
    if (r.ok) load(); else setNote('Could not remove that source.')
  }

  // Demo mode: show the illustrative sample list (read-only).
  if (isDemoMode()) {
    return (
      <div className="dp-settings-list">
        <p className="dp-muted">{SOURCES_SUMMARY.detail}</p>
        {KNOWLEDGE_SOURCES.map((s) => (
          <div key={s.label} className="dp-settings-row">
            <div className="dp-settings-row__head"><strong>{s.label}</strong><span className="dp-pill dp-pill--muted">{s.kind}</span></div>
          </div>
        ))}
      </div>
    )
  }

  if (state === 'loading') return <div className="dp-settings-list"><p className="dp-muted">Loading knowledge sources…</p></div>

  return (
    <div className="dp-settings-list">
      {state === 'error' && <p className="dp-muted">Couldn’t reach the knowledge service. <button className="dp-linkbtn" onClick={load}>Retry</button></p>}
      {sources.length === 0 && state === 'ready' && (
        <p className="dp-muted">No knowledge sources yet. Add a local folder so the AI can read and index it for RAG over your projects.</p>
      )}
      {sources.map((s) => (
        <div key={s.id} className="dp-settings-row">
          <div className="dp-settings-row__head">
            <span className={'dp-statedot ' + (s.status === 'indexed' ? 'dp-statedot--connected' : s.status === 'failed' ? 'dp-statedot--degraded' : '')} aria-hidden="true" />
            <strong>{s.displayName}</strong>
            <span className="dp-pill dp-pill--muted">{s.provider}</span>
            <span className={'dp-tag ' + (s.status === 'indexed' ? 'dp-tag--healthy' : s.status === 'failed' ? 'dp-tag--degraded' : '')}>{sourceStatusLabel(s.status)}</span>
          </div>
          <p className="dp-muted">{s.location}{s.lastError ? ` — ${s.lastError}` : ''}</p>
          <div className="dp-settings-actions">
            <button className="dp-ghost-button" type="button" disabled={busy !== null} onClick={() => reindex(s.id)}>{busy === s.id ? 'Working…' : 'Re-index'}</button>
            <button className="dp-ghost-button dp-ghost-button--danger" type="button" disabled={busy !== null} onClick={() => remove(s.id)}>Remove</button>
          </div>
        </div>
      ))}
      {note && <p className="dp-muted">{note}</p>}
      <div className="dp-settings-actions">
        <button className="dp-ghost-button" type="button" disabled={busy !== null} onClick={addFolder}>{busy === 'add' ? 'Adding…' : 'Add folder'}</button>
        <button className="dp-ghost-button" type="button" disabled={busy !== null || !boxAvailable} title={boxAvailable ? '' : 'Box isn’t configured on this deployment'} onClick={connectBox}>Connect Box</button>
      </div>
      <p className="dp-muted">Local folders are read + indexed only. Add them by a path that exists on the DayPilot server.</p>
    </div>
  )
}
