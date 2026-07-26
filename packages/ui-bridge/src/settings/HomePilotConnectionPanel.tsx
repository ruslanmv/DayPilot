import React, { useCallback, useEffect, useState } from 'react'

import {
  homepilotApi,
  homepilotStatusText,
  type AgentProfile,
  type HomePilotConnection,
} from './homepilotClient'

/**
 * Settings → HomePilot agents (Batch A1).
 *
 * Connect an existing, side-by-side HomePilot install. DayPilot uses its agents
 * without copying their identity, memory, or configuration — it stores remote
 * references only. The API key is posted once and held server-side; it is never
 * shown here. When the HomePilot runtime flag is off, the endpoints 404 and this
 * panel explains how to turn it on.
 */
const DEFAULT_BASE = 'http://homepilot:7860/api'

type Load = 'loading' | 'runtime_off' | 'ready' | 'error'

export function HomePilotConnectionPanel() {
  const [load, setLoad] = useState<Load>('loading')
  const [connection, setConnection] = useState<HomePilotConnection | null>(null)
  const [profiles, setProfiles] = useState<AgentProfile[]>([])
  const [baseUrl, setBaseUrl] = useState(DEFAULT_BASE)
  const [apiKey, setApiKey] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    const r = await homepilotApi.listConnections()
    if (!r.ok) {
      setLoad(r.status === 404 ? 'runtime_off' : 'error')
      return
    }
    const conn = r.data.connections[0] ?? null
    setConnection(conn)
    if (conn) {
      const p = await homepilotApi.listProfiles()
      setProfiles(p.ok ? p.data.profiles : [])
    } else {
      setProfiles([])
    }
    setLoad('ready')
  }, [])
  useEffect(() => { refresh() }, [refresh])

  async function connect() {
    setBusy('connect'); setNote(null)
    const r = await homepilotApi.connect(baseUrl.trim(), apiKey.trim() || undefined)
    setBusy(null); setApiKey('')
    if (r.ok) {
      setNote(r.data.code === 'connected' ? 'Connected to HomePilot.' : `Couldn’t verify HomePilot (${homepilotStatusText(r.data.code)}).`)
      refresh()
    } else setNote(r.status === 404 ? null : 'Couldn’t reach DayPilot to save the connection.')
  }

  async function test() {
    if (!connection) return
    setBusy('test'); setNote(null)
    const r = await homepilotApi.test(connection.id)
    setBusy(null)
    if (r.ok) { setNote(`HomePilot is ${homepilotStatusText(r.data.code).toLowerCase()}.`); refresh() }
    else setNote('Couldn’t reach DayPilot.')
  }

  async function sync() {
    if (!connection) return
    setBusy('sync'); setNote(null)
    const r = await homepilotApi.sync(connection.id)
    setBusy(null)
    if (r.ok) { setNote(`Synced ${r.data.total ?? 0} agent(s) from HomePilot.`); refresh() }
    else if (r.status === 409) setNote('Syncing is turned off (set DAYPILOT_HOMEPILOT_SYNC_ENABLED=true).')
    else setNote('Couldn’t sync agents.')
  }

  async function disconnect() {
    if (!connection) return
    setBusy('disconnect'); setNote(null)
    await homepilotApi.disconnect(connection.id)
    setBusy(null); refresh()
  }

  async function toggle(p: AgentProfile) {
    const r = await homepilotApi.setEnabled(p.id, !p.enabled)
    if (r.ok) setProfiles((cur) => cur.map((x) => (x.id === p.id ? r.data : x)))
  }

  if (load === 'loading') return <div className="dp-settings-list"><p className="dp-muted"><span className="dp-spinner" aria-hidden="true" /> Loading…</p></div>
  if (load === 'error') return <div className="dp-settings-list"><p className="dp-muted">Couldn’t reach DayPilot. <button className="dp-linkbtn" onClick={refresh}>Retry</button></p></div>
  if (load === 'runtime_off') {
    return (
      <div className="dp-settings-list">
        <p className="dp-muted">HomePilot agents are turned off on this deployment.</p>
        <p className="dp-muted">Enable them by setting <code>DAYPILOT_HOMEPILOT_RUNTIME_ENABLED=true</code> (and <code>DAYPILOT_HOMEPILOT_SYNC_ENABLED=true</code> to sync personas), then reload.</p>
        <p className="dp-muted">HomePilot owns the agents; DayPilot connects to them and manages their work — it never copies their identity, memory, or configuration.</p>
      </div>
    )
  }

  const connected = connection?.status === 'connected'

  return (
    <div className="dp-settings-list">
      <p className="dp-muted">Connect an existing HomePilot installation. DayPilot uses its agents without copying their identity, memory, or configuration.</p>

      {!connection ? (
        <div className="dp-provcard__advbox">
          <label className="dp-settings-field"><span className="dp-settings-field__label">HomePilot API base URL</span></label>
          <input className="dp-provcard__input" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder={DEFAULT_BASE} aria-label="HomePilot base URL" />
          <p className="dp-muted">Side-by-side install: <code>http://homepilot:7860/api</code> · host install: <code>http://host.docker.internal:7860/api</code></p>
          <input className="dp-provcard__input" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="HomePilot API key (X-API-Key / Bearer)" aria-label="HomePilot API key" type="password" />
          <div className="dp-settings-actions">
            <button className="dp-primary-button" type="button" disabled={busy !== null || !baseUrl.trim()} onClick={connect}>{busy === 'connect' ? 'Connecting…' : 'Connect HomePilot'}</button>
          </div>
        </div>
      ) : (
        <>
          <div className="dp-settings-row dp-settings-row--split">
            <div className="dp-settings-row__head">
              <span className={'dp-statedot ' + (connected ? 'dp-statedot--connected' : 'dp-statedot--degraded')} aria-hidden="true" />
              <strong>{connection.baseUrl}</strong>
            </div>
            <span className={'dp-tag ' + (connected ? 'dp-tag--healthy' : 'dp-tag--degraded')}>{homepilotStatusText(connection.status)}</span>
          </div>
          {connection.accountLabel && (
            <p className="dp-muted">
              Signed in as <strong>{connection.accountLabel}</strong>
              {connection.remoteKind === 'cloud' ? ' · Cloud HomePilot' : ' · Local HomePilot'}.
              {' '}Only this account’s agents are shown.
            </p>
          )}
          {connection.chatMode === 'chat_only' && (
            <p className="dp-muted">This HomePilot is <strong>chat-only</strong> — agents reply, but can’t propose tasks or actions (no bridge).</p>
          )}
          {connection.lastError && <p className="dp-muted">{connection.lastError}</p>}
          <div className="dp-settings-actions">
            <button className="dp-ghost-button" type="button" disabled={busy !== null} onClick={test}>{busy === 'test' ? 'Testing…' : 'Test connection'}</button>
            <button className="dp-ghost-button" type="button" disabled={busy !== null} onClick={sync}>{busy === 'sync' ? 'Refreshing…' : 'Refresh agents'}</button>
            <button className="dp-ghost-button dp-ghost-button--danger" type="button" disabled={busy !== null} onClick={disconnect}>Disconnect</button>
          </div>

          <p className="dp-muted">{profiles.length} agent(s) synced · enable the ones you want to use in DayPilot. Enabling never changes HomePilot.</p>
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
          {profiles.length === 0 && <p className="dp-muted">No agents yet. Install personas in HomePilot and enable their shared API, then press “Refresh agents”.</p>}
        </>
      )}

      {note && <p className="dp-muted">{note}</p>}
    </div>
  )
}
