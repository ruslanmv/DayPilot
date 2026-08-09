import React, { useEffect, useState } from 'react'
import { INTEGRATIONS, type IntegrationRow } from '../settings/settingsData'
import { StandupSetup } from '../standup/StandupSetup'
import { standupApi, type StandupWorkflow } from '../standup/standupClient'

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

      <AutomationsSection />
    </div>
  )
}

/**
 * Automations that run on a schedule, configured against the live API.
 *
 * The provider rows above are still local view state; this section is not.
 * A standup posts into a public channel on a timer, so its channel, signature
 * and timing have to be the ones the server will actually act on — a seeded
 * setting that looks configured but is not would post to the wrong place.
 */
function AutomationsSection() {
  const [workflow, setWorkflow] = useState<StandupWorkflow | null>(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    void standupApi.listWorkflows().then((r) => {
      if (r.ok) setWorkflow(r.data.workflows[0] ?? null)
      setLoaded(true)
    })
  }, [])

  if (!loaded) return null
  return (
    <section className="dp-integrations__automations" aria-label="Automations">
      <h3 className="dp-integrations__automations-title">Automations</h3>
      <StandupSetup workflow={workflow} onSaved={setWorkflow} />
    </section>
  )
}
