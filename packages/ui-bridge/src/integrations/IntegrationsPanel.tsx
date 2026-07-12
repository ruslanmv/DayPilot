import React, { useState } from 'react'
import { INTEGRATIONS, type IntegrationRow } from '../settings/settingsData'

const CONNECTED = new Set(['connected', 'default'])

/**
 * The live Integrations page (batch I0). Lists providers with connection status;
 * connected ones show granted capabilities, last activity, and a Disconnect
 * button. Connect/Disconnect mutate the view here — in a wired deployment they
 * call POST /v1/integrations/connect and /{id}/disconnect. Reads are immediate;
 * every write flows through the Approval Center, so connecting is safe.
 */
export function IntegrationsPanel() {
  const [rows, setRows] = useState<IntegrationRow[]>(INTEGRATIONS)

  function setState(name: string, patch: Partial<IntegrationRow>) {
    setRows((cur) => cur.map((r) => (r.name === name ? { ...r, ...patch } : r)))
  }

  function connect(row: IntegrationRow) {
    setState(row.name, { state: 'connected', lastActivity: 'just now', capabilities: row.capabilities ?? [] })
  }
  function disconnect(row: IntegrationRow) {
    // 'default' providers (Ollabridge, GitPilot) are core and can't be removed.
    if (row.state === 'default') return
    setState(row.name, { state: 'available', lastActivity: undefined })
  }

  return (
    <div className="dp-integrations">
      <p className="dp-muted">Connect external providers. Reads run immediately; writes and sends always require approval.</p>
      {rows.map((row) => {
        const connected = CONNECTED.has(row.state)
        return (
          <div key={row.name} className="dp-integration-row">
            <div className="dp-integration-row__main">
              <span className={'dp-dot dp-dot--' + (connected ? 'ok' : 'idle')} aria-hidden="true" />
              <div className="dp-integration-row__body">
                <div className="dp-integration-row__head">
                  <strong>{row.name}</strong>
                  <span className="dp-pill dp-pill--muted">{row.role}</span>
                  {row.authType && <span className="dp-integration-row__auth">{row.authType}</span>}
                </div>
                <p className="dp-integration-row__detail">{row.detail}</p>
                {connected && row.capabilities && row.capabilities.length > 0 && (
                  <div className="dp-integration-caps">
                    {row.capabilities.map((c) => <span key={c} className="dp-cap-chip">{c}</span>)}
                  </div>
                )}
                {connected && row.lastActivity && (
                  <div className="dp-integration-row__activity">Last activity: {row.lastActivity}</div>
                )}
              </div>
            </div>
            <div className="dp-integration-row__actions">
              {connected ? (
                <>
                  <span className="dp-tag dp-tag--healthy">Connected</span>
                  {row.state !== 'default' && (
                    <button className="dp-ghost-button" onClick={() => disconnect(row)}>Disconnect</button>
                  )}
                </>
              ) : (
                <button className="dp-ghost-button" onClick={() => connect(row)}>Connect</button>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
