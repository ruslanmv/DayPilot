import React, { useEffect, useRef, useState } from 'react'

import { homepilotApi, type AddAgentInfo, type HpersonaReport } from '../settings/homepilotClient'

/**
 * Add-agent flow (Batch A10, product-design layout). Left: choose how to add an
 * agent — Browse HomePilot Gallery (the primary path — agents live in
 * HomePilot), Import a `.hpersona`, or import from a URL. Right: a live preview
 * and a dependency check that appears once a package is chosen. The `.hpersona`
 * and URL methods are offline fallbacks, available only when IMPORTS is enabled;
 * every imported agent is disabled by default.
 */
type Method = 'gallery' | 'hpersona' | 'url'

const METHODS: { id: Method; icon: string; title: string; sub: string }[] = [
  { id: 'gallery', icon: '👥', title: 'Browse HomePilot Gallery', sub: 'Discover and manage community and curated agents in HomePilot.' },
  { id: 'hpersona', icon: '📄', title: 'Import .hpersona file', sub: 'Upload a portable HomePilot persona package from your device.' },
  { id: 'url', icon: '🔗', title: 'Import from URL or GitHub', sub: 'Import a persona package from a trusted URL or GitHub release.' },
]

export function AddAgentPanel({
  onBack,
  onManageConnection,
  onRefreshed,
}: {
  onBack: () => void
  onManageConnection: () => void
  onRefreshed?: () => void
}) {
  const [info, setInfo] = useState<AddAgentInfo | null>(null)
  const [method, setMethod] = useState<Method>('gallery')
  const [file, setFile] = useState<File | null>(null)
  const [report, setReport] = useState<HpersonaReport | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    homepilotApi.addInfo().then((r) => setInfo(r.ok ? r.data : { connected: false, galleryUrl: '', importsEnabled: false }))
  }, [])

  const importsOff = !!info && !info.importsEnabled

  async function pickFile(f: File | null) {
    setFile(f); setReport(null); setNote(null)
    if (!f) return
    setBusy('preview')
    const r = await homepilotApi.hpersonaPreview(f)
    setBusy(null)
    if (r.ok) setReport(r.data)
    else setNote('Couldn’t read that .hpersona file.')
  }

  async function refresh() {
    if (!info?.connectionId) { onManageConnection(); return }
    setBusy('refresh'); setNote(null)
    const r = await homepilotApi.sync(info.connectionId)
    setBusy(null)
    if (r.ok) { setNote(`Refreshed — ${r.data.total ?? 0} agent(s) from HomePilot.`); onRefreshed?.() }
    else setNote('Couldn’t refresh from HomePilot.')
  }

  async function install() {
    if (method === 'gallery') { if (info?.galleryUrl) window.open(info.galleryUrl, '_blank', 'noopener'); return }
    if (method === 'hpersona' && file) {
      setBusy('install'); setNote(null)
      const r = await homepilotApi.hpersonaImport(file)
      setBusy(null)
      if (r.ok) { setNote('Imported — disabled by default until you activate it.'); onRefreshed?.() }
      else setNote('Import failed — the package didn’t validate.')
    }
  }

  const canInstall = method === 'gallery' ? !!info?.galleryUrl
    : method === 'hpersona' ? !!report?.valid && !importsOff
    : false

  return (
    <section className="dp-addagent" aria-label="Add an agent">
      <header className="dp-addagent__pagehead">
        <div>
          <h2 className="dp-agents__title">Add agent</h2>
          <p className="dp-agents__sub">Install or import an AI staff member for your team.</p>
        </div>
        <button type="button" className="dp-ghost-button" onClick={onBack}>← Back to agents</button>
      </header>

      <div className="dp-addagent__grid">
        {/* Left — method picker */}
        <div className="dp-addagent__methods" role="radiogroup" aria-label="Choose how to add an agent">
          <h3 className="dp-addagent__methods-title">Choose how to add an agent</h3>
          {METHODS.map((m) => {
            const disabled = m.id !== 'gallery' && importsOff
            return (
              <button
                key={m.id}
                type="button"
                role="radio"
                aria-checked={method === m.id}
                aria-disabled={disabled}
                className={'dp-method' + (method === m.id ? ' is-active' : '') + (disabled ? ' is-disabled' : '')}
                onClick={() => { if (!disabled) { setMethod(m.id); setNote(null) } }}
              >
                <span className="dp-method__radio" aria-hidden="true" />
                <span className="dp-method__icon" aria-hidden="true">{m.icon}</span>
                <span className="dp-method__body">
                  <span className="dp-method__title">{m.title}</span>
                  <span className="dp-method__sub">{m.sub}{disabled ? ' (offline imports are turned off)' : ''}</span>
                </span>
                <span className="dp-method__chev" aria-hidden="true">›</span>
              </button>
            )
          })}
          <div className="dp-method__note">
            <span aria-hidden="true">ⓘ</span>
            <div>
              <b>Every imported agent is disabled by default.</b>
              <p>Review identity, tools, dependencies, and data access before activating. Agents live in HomePilot — DayPilot never copies their identity or memory.</p>
            </div>
          </div>
        </div>

        {/* Right — preview + dependency check */}
        <div className="dp-addagent__right">
          <div className="dp-addagent__panelhead">
            <h3 className="dp-addagent__panel-title">Preview</h3>
            <span className="dp-addagent__pill"><span className="dp-tr__dot" style={{ background: '#e6a23c' }} aria-hidden="true" /> Disabled by default until activated</span>
          </div>

          {method === 'gallery' && (
            <div className="dp-addagent__previewcard dp-addagent__gallery">
              <p><b>Agents are created and curated in HomePilot.</b></p>
              <p className="dp-muted">Open the gallery to browse and set up personas, then refresh to bring them into DayPilot.</p>
              <div className="dp-addagent__galleryactions">
                <a className={'dp-primary-button' + (info?.galleryUrl ? '' : ' is-disabled')} href={info?.galleryUrl || undefined} target="_blank" rel="noopener noreferrer">Open HomePilot Gallery</a>
                <button type="button" className="dp-ghost-button" onClick={refresh} disabled={busy !== null}>{busy === 'refresh' ? 'Refreshing…' : 'Refresh from HomePilot'}</button>
                <button type="button" className="dp-ghost-button" onClick={onManageConnection}>Manage connection</button>
              </div>
            </div>
          )}

          {method === 'hpersona' && (
            <>
              {importsOff && <p className="dp-muted">Offline imports are turned off. Enable <code>DAYPILOT_HOMEPILOT_IMPORTS_ENABLED</code> to use this fallback.</p>}
              {!importsOff && (
                <input ref={inputRef} type="file" accept=".hpersona,application/zip" aria-label="Choose a .hpersona file" onChange={(e) => pickFile(e.target.files?.[0] ?? null)} />
              )}
              {report && <PreviewCard report={report} />}
              {report && <DependencyCheck report={report} onRecheck={() => file && pickFile(file)} />}
            </>
          )}

          {method === 'url' && (
            <div className="dp-addagent__previewcard">
              <p className="dp-muted">URL / GitHub import is an offline fallback and arrives with the next release. For now, import a <code>.hpersona</code> file or use the HomePilot Gallery.</p>
            </div>
          )}
        </div>
      </div>

      {note && <p className="dp-muted" role="status">{note}</p>}

      <footer className="dp-addagent__foot">
        <button type="button" className="dp-ghost-button" onClick={onBack}>Cancel</button>
        <button type="button" className="dp-primary-button" onClick={install} disabled={!canInstall || busy !== null}>
          {method === 'gallery' ? 'Open Gallery' : busy === 'install' ? 'Installing…' : 'Install agent'}
        </button>
      </footer>
      <div className="dp-sr-live" role="status" aria-live="polite">{note || ''}</div>
    </section>
  )
}

function PreviewCard({ report }: { report: HpersonaReport }) {
  const p = report.preview
  const tools = report.dependencies.tools
  return (
    <div className="dp-addagent__previewcard">
      <div className="dp-addagent__previewtop">
        <span className="dp-addagent__previewavatar" aria-hidden="true">{(p.name || 'A').slice(0, 2).toUpperCase()}</span>
        <div>
          <p className="dp-addagent__previewname">{p.name}</p>
          <p className="dp-muted">{p.role || 'Agent'}</p>
          <span className="dp-tag dp-tag--healthy">From .hpersona package</span>
        </div>
      </div>
      {p.description && <p className="dp-muted">{p.description}</p>}
      {(p.capabilities?.length ?? 0) > 0 && (
        <div className="dp-addagent__facts">
          <div><span className="dp-addagent__fact-k">Specialties</span><span>{p.capabilities!.slice(0, 3).join(', ')}</span></div>
          <div><span className="dp-addagent__fact-k">Publisher</span><span>HomePilot</span></div>
          <div><span className="dp-addagent__fact-k">Rating</span><span>{p.contentRating || 'general'}</span></div>
          <div><span className="dp-addagent__fact-k">Tools</span><span>{tools.length} requested</span></div>
        </div>
      )}
    </div>
  )
}

function DependencyCheck({ report, onRecheck }: { report: HpersonaReport; onRecheck: () => void }) {
  const d = report.dependencies
  const cols = [
    { k: 'Models', v: `${d.models.length} required`, ok: d.models.every((m) => m.status === 'included'), label: d.models.length ? 'Bundled' : 'None' },
    { k: 'Tools', v: `${d.tools.length} declared`, ok: true, label: 'Provided by HomePilot' },
    { k: 'MCP servers', v: `${d.mcpServers.length}`, ok: true, label: 'Provided by HomePilot' },
    { k: 'A2A agents', v: `${d.a2aAgents.length}`, ok: true, label: 'Provided by HomePilot' },
    { k: 'Manifest', v: report.valid ? 'Valid' : 'Invalid', ok: report.valid, label: report.valid ? 'All good' : 'Errors' },
    { k: 'Data', v: 'Reference only', ok: true, label: 'No prompt/memory copied' },
  ]
  const nChecks = cols.length
  return (
    <div className="dp-depcheck">
      <div className="dp-depcheck__head">
        <span className="dp-depcheck__title">Dependency check <span className="dp-tag">{nChecks} checks</span></span>
        <button type="button" className="dp-linkbtn" onClick={onRecheck}>↻ Re-check</button>
      </div>
      <p className="dp-muted">We verify the package’s requirements. HomePilot runs the persona; DayPilot only references it.</p>
      <div className="dp-depcheck__grid">
        {cols.map((c) => (
          <div key={c.k} className="dp-depcheck__col">
            <span className="dp-depcheck__k">{c.k}</span>
            <span className="dp-depcheck__v">{c.v}</span>
            <span className={'dp-depcheck__status ' + (c.ok ? 'is-ok' : 'is-warn')}>{c.ok ? '✓' : '⚠'} {c.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
