import React, { useCallback, useEffect, useState } from 'react'

import { HomePilotSetupWizard } from './HomePilotSetupWizard'
import {
  homepilotApi,
  homepilotStatusText,
  type AgentProfile,
  type HomePilotPrefs,
  type HomePilotSetupStatus,
} from './homepilotClient'

/**
 * Settings → HomePilot agents.
 *
 * A guided connection between two apps, driven by the backend connection-state
 * machine (`/v1/homepilot/setup/status`) — never an env-var toggle. The
 * integration is enabled by default, so "not connected" is a setup prompt, not
 * an error; only an explicit admin lock shows "unavailable". The API key is
 * posted once through the wizard and held server-side; it is never shown here.
 */
const DOCS = {
  gettingStarted: 'https://ruslanmv.com/HomePilot/getting-started.html',
  docs: 'https://ruslanmv.com/HomePilot/',
  github: 'https://github.com/ruslanmv/HomePilot',
}

type Load = 'loading' | 'ready' | 'error'

/** A labelled on/off row that persists the change (optimistic). */
function Toggle({ label, hint, checked, onChange }: { label: string; hint?: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="dp-settings-row dp-settings-row--split dp-hp__pref">
      <span className="dp-settings-row__head"><strong>{label}</strong>{hint && <span className="dp-muted">{hint}</span>}</span>
      <span className={'dp-switch' + (checked ? ' is-on' : '')} role="switch" aria-checked={checked} tabIndex={0}
        onClick={() => onChange(!checked)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onChange(!checked) } }}>
        <span className="dp-switch__knob" />
      </span>
    </label>
  )
}

export function HomePilotConnectionPanel({ onOpenAgents }: { onOpenAgents?: () => void } = {}) {
  const [load, setLoad] = useState<Load>('loading')
  const [status, setStatus] = useState<HomePilotSetupStatus | null>(null)
  const [profiles, setProfiles] = useState<AgentProfile[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [wizard, setWizard] = useState(false)
  const [prefs, setPrefs] = useState<HomePilotPrefs | null>(null)
  const openAgents = onOpenAgents || (() => { window.location.hash = '#/agents' })

  async function setPref<K extends keyof HomePilotPrefs>(key: K, value: HomePilotPrefs[K]) {
    if (!status?.connection || !prefs) return
    setPrefs({ ...prefs, [key]: value })  // optimistic
    const r = await homepilotApi.patchPrefs(status.connection.id, { [key]: value })
    if (!r.ok) refresh()  // roll back to server truth on failure
  }

  const refresh = useCallback(async () => {
    const r = await homepilotApi.setupStatus()
    if (!r.ok) { setLoad('error'); return }
    setStatus(r.data)
    setPrefs(r.data.connection?.prefs ?? null)
    if (r.data.connectionState === 'connected') {
      const p = await homepilotApi.listProfiles()
      setProfiles(p.ok ? p.data.profiles : [])
    } else {
      setProfiles([])
    }
    setLoad('ready')
  }, [])
  useEffect(() => { refresh() }, [refresh])

  async function sync() {
    if (!status?.connection) return
    setBusy('sync'); setNote(null)
    const r = await homepilotApi.sync(status.connection.id)
    setBusy(null)
    if (r.ok) { setNote(`Synced ${r.data.total ?? 0} agent(s) from HomePilot.`); refresh() }
    else if (r.status === 409) setNote('Agent sync is turned off for this deployment.')
    else setNote('Couldn’t sync agents.')
  }

  async function test() {
    if (!status?.connection) return
    setBusy('test'); setNote(null)
    const r = await homepilotApi.test(status.connection.id)
    setBusy(null)
    if (r.ok) { setNote(`HomePilot is ${homepilotStatusText(r.data.code).toLowerCase()}.`); refresh() }
    else setNote('Couldn’t reach DayPilot.')
  }

  async function disconnect() {
    if (!status?.connection) return
    setBusy('disconnect'); setNote(null)
    await homepilotApi.disconnect(status.connection.id)
    setBusy(null); refresh()
  }

  async function toggle(p: AgentProfile) {
    const r = await homepilotApi.setEnabled(p.id, !p.enabled)
    if (r.ok) setProfiles((cur) => cur.map((x) => (x.id === p.id ? r.data : x)))
  }

  if (load === 'loading') return <div className="dp-settings-list"><p className="dp-muted"><span className="dp-spinner" aria-hidden="true" /> Loading…</p></div>
  if (load === 'error' || !status) return <div className="dp-settings-list"><p className="dp-muted">Couldn’t reach DayPilot. <button className="dp-linkbtn" onClick={refresh}>Retry</button></p></div>

  const footerLinks = (
    <p className="dp-muted dp-hp__links">
      <a href={DOCS.gettingStarted} target="_blank" rel="noreferrer">Getting Started</a> ·{' '}
      <a href={DOCS.docs} target="_blank" rel="noreferrer">Documentation</a> ·{' '}
      <a href={DOCS.github} target="_blank" rel="noreferrer">GitHub</a>
    </p>
  )

  // State: admin lock — the one hard-off state. Never reveal the variable name.
  if (status.connectionState === 'admin_disabled') {
    return (
      <div className="dp-settings-list">
        <h3 className="dp-hp__h">HomePilot agents are unavailable</h3>
        <p className="dp-muted">This integration has been disabled by your administrator.</p>
      </div>
    )
  }

  // State: not connected — a setup prompt, not an error.
  if (status.connectionState === 'not_connected') {
    return (
      <div className="dp-settings-list">
        <p className="dp-muted">Use agents already installed in HomePilot. Their identity, memory, appearance, and configuration remain in HomePilot — DayPilot only connects and manages their work.</p>
        <p><span className="dp-tag dp-tag--offline">Not connected</span></p>
        <div className="dp-settings-actions">
          <button type="button" className="dp-primary-button" onClick={() => setWizard(true)}>Set up HomePilot</button>
          <button type="button" className="dp-ghost-button" onClick={() => setWizard(true)}>I already have HomePilot</button>
        </div>
        {footerLinks}
        {wizard && <HomePilotSetupWizard onClose={() => { setWizard(false); refresh() }} onOpenAgents={openAgents} />}
      </div>
    )
  }

  const conn = status.connection
  const connected = status.connectionState === 'connected'

  // State: connection problem — a specific message, not a generic error.
  if (!connected) {
    const problem =
      status.connectionState === 'needs_attention'
        ? { title: 'Authentication failed', body: 'The HomePilot API key was not accepted.', fix: 'Update connection' }
        : { title: 'HomePilot is not running', body: `We could not reach HomePilot${conn ? ` at ${conn.apiUrl}` : ''}.`, fix: 'Change address' }
    return (
      <div className="dp-settings-list">
        <h3 className="dp-hp__h">{problem.title}</h3>
        <p className="dp-muted">{conn?.lastError || problem.body}</p>
        <div className="dp-settings-actions">
          <button type="button" className="dp-primary-button" onClick={() => setWizard(true)}>{problem.fix}</button>
          <button type="button" className="dp-ghost-button" disabled={busy !== null} onClick={test}>{busy === 'test' ? 'Testing…' : 'Try again'}</button>
          <a className="dp-ghost-button" href={DOCS.docs} target="_blank" rel="noreferrer">Installation help</a>
        </div>
        {footerLinks}
        {wizard && <HomePilotSetupWizard onClose={() => { setWizard(false); refresh() }} onOpenAgents={openAgents} />}
      </div>
    )
  }

  // State: connected.
  return (
    <div className="dp-settings-list">
      <div className="dp-settings-row dp-settings-row--split">
        <div className="dp-settings-row__head">
          <span className="dp-statedot dp-statedot--connected" aria-hidden="true" />
          <strong>HomePilot agents are connected</strong>
        </div>
        <span className="dp-tag dp-tag--healthy">Connected</span>
      </div>
      <p className="dp-muted">DayPilot uses agents from your HomePilot installation without copying their identity, memory, or configuration.</p>
      <p className="dp-hp__chips">
        <span className="dp-tag dp-tag--healthy">Connected</span>
        <span className="dp-tag">{conn?.agentCount ?? 0} agents found</span>
        {conn?.accountLabel && <span className="dp-tag">{conn.accountLabel} · {conn.remoteKind === 'cloud' ? 'Cloud HomePilot' : 'Local HomePilot'}</span>}
        {conn?.chatMode === 'chat_only' && <span className="dp-tag dp-tag--degraded">Chat-only</span>}
      </p>

      <div className="dp-settings-actions">
        <button type="button" className="dp-ghost-button" disabled={busy !== null} onClick={sync}>{busy === 'sync' ? 'Syncing…' : 'Sync now'}</button>
        <button type="button" className="dp-ghost-button" onClick={openAgents}>Open agents</button>
        <button type="button" className="dp-ghost-button" disabled={busy !== null} onClick={test}>{busy === 'test' ? 'Testing…' : 'Test connection'}</button>
        <button type="button" className="dp-ghost-button dp-ghost-button--danger" disabled={busy !== null} onClick={disconnect}>Disconnect</button>
      </div>

      {prefs && (
        <>
          <h4 className="dp-hp__subh">Synchronization</h4>
          <Toggle label="Automatically sync agents" checked={prefs.autoSync} onChange={(v) => setPref('autoSync', v)} />
          <Toggle label="Sync when DayPilot starts" checked={prefs.syncOnStart} onChange={(v) => setPref('syncOnStart', v)} />

          <h4 className="dp-hp__subh">Agent behavior</h4>
          <Toggle label="New agents start disabled" checked={prefs.newAgentsDisabled} onChange={(v) => setPref('newAgentsDisabled', v)} />
          <Toggle label="Show offline agents" checked={prefs.showOffline} onChange={(v) => setPref('showOffline', v)} />
          <Toggle label="Use HomePilot sessions and memory" checked={prefs.useSessions} onChange={(v) => setPref('useSessions', v)} />
          <Toggle label="Allow delegation between agents" hint="Off until the delegation backend is production-ready" checked={prefs.allowDelegation} onChange={(v) => setPref('allowDelegation', v)} />
        </>
      )}

      <div className="dp-hp__safety">
        <span aria-hidden="true">🔒</span>
        <span>External actions require DayPilot approval. Email sends, calendar changes, and coding operations always go through the Approval Center — this can’t be turned off.</span>
      </div>

      <p className="dp-muted">{profiles.length} agent(s) synced · enable the ones you want in DayPilot. Enabling never changes HomePilot.</p>
      {profiles.map((p) => (
        <div key={p.id} className="dp-settings-row dp-settings-row--split">
          <div className="dp-settings-row__head">
            <strong>{p.name}</strong>
            <span className="dp-pill dp-pill--muted">{p.role || 'Agent'}</span>
            <span className={'dp-tag ' + (p.status === 'available' ? 'dp-tag--healthy' : p.status === 'offline' ? 'dp-tag--offline' : 'dp-tag--degraded')}>{p.status}</span>
          </div>
          <button className="dp-ghost-button" type="button" onClick={() => toggle(p)}>{p.enabled ? 'Disable' : 'Enable'}</button>
        </div>
      ))}
      {profiles.length === 0 && <p className="dp-muted">No agents yet. Create personas in HomePilot and enable their shared API, then press “Sync now”.</p>}

      {note && <p className="dp-muted">{note}</p>}
      {footerLinks}
      {wizard && <HomePilotSetupWizard onClose={() => { setWizard(false); refresh() }} onOpenAgents={openAgents} />}
    </div>
  )
}
