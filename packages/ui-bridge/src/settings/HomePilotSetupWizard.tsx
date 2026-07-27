import React, { useState } from 'react'

import {
  homepilotApi,
  type AgentProfile,
  type HomePilotDetectedInstance,
  type HomePilotTestResult,
} from './homepilotClient'

/**
 * Guided HomePilot setup (install → connect → choose agents → complete).
 *
 * Presents the integration as a connection between two apps, never as an
 * env-var to toggle. The browser never probes the network or runs shell/Docker
 * commands: detection and connection-testing happen on DayPilot's backend, and
 * install steps only *show* commands + link to HomePilot's official docs. The
 * API key is posted once to DayPilot and held server-side.
 *
 * The brief's per-step components are consolidated here behind one step machine;
 * the step names and 4-phase progress (Install · Connect · Choose agents ·
 * Complete) are preserved.
 */
const DOCS = {
  gettingStarted: 'https://ruslanmv.com/HomePilot/getting-started.html',
  docs: 'https://ruslanmv.com/HomePilot/',
  github: 'https://github.com/ruslanmv/HomePilot',
}

const DOCKER_RUN = `docker run -d \\
  --name homepilot \\
  -p 7860:7860 \\
  -v homepilot-data:/home/user/app/data \\
  ruslanmv/homepilot:latest`

const COMPOSE = `git clone https://github.com/ruslanmv/HomePilot.git
cd HomePilot
cp .env.example .env
make download-recommended
make install
make run`

type Step =
  | 'welcome'
  | 'installation_method'
  | 'detecting'
  | 'manual_connection'
  | 'testing'
  | 'agent_selection'
  | 'complete'

const PHASE: Record<Step, number> = {
  welcome: 0, installation_method: 0, detecting: 0,
  manual_connection: 1, testing: 1,
  agent_selection: 2,
  complete: 3,
}
const PHASES = ['Install', 'Connect', 'Choose agents', 'Complete']

function Copy({ text }: { text: string }) {
  const [done, setDone] = useState(false)
  return (
    <button type="button" className="dp-ghost-button dp-hpw__copy" onClick={() => {
      navigator.clipboard?.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1500) }).catch(() => {})
    }}>{done ? 'Copied' : 'Copy'}</button>
  )
}

export function HomePilotSetupWizard({ onClose, onOpenAgents }: { onClose: () => void; onOpenAgents?: () => void }) {
  const [step, setStep] = useState<Step>('welcome')
  const [apiUrl, setApiUrl] = useState('http://localhost:7860/api')
  const [browserUrl, setBrowserUrl] = useState('http://localhost:7860')
  const [apiKey, setApiKey] = useState('')
  const [allowPrivate, setAllowPrivate] = useState(true)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [detect, setDetect] = useState<{ instance: HomePilotDetectedInstance | null; ran: boolean }>({ instance: null, ran: false })
  const [test, setTest] = useState<HomePilotTestResult | null>(null)
  const [profiles, setProfiles] = useState<AgentProfile[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [note, setNote] = useState<string | null>(null)

  async function runDetect() {
    setStep('detecting'); setBusy('detect'); setNote(null)
    const r = await homepilotApi.detect()
    setBusy(null)
    const instance = r.ok ? r.data.instance : null
    setDetect({ instance, ran: true })
    if (instance) {
      setApiUrl(instance.apiUrl)
      setBrowserUrl(instance.browserUrl)
    }
  }

  async function runTest() {
    setStep('testing'); setBusy('test'); setNote(null); setTest(null)
    const r = await homepilotApi.testAddress(apiUrl.trim(), apiKey.trim() || undefined, allowPrivate)
    setBusy(null)
    if (r.ok) setTest(r.data)
    else setNote('Couldn’t reach DayPilot to test the connection.')
  }

  async function connectAndSync() {
    setBusy('connect'); setNote(null)
    const c = await homepilotApi.connect(apiUrl.trim(), apiKey.trim() || undefined, browserUrl.trim() || undefined)
    if (!c.ok || c.data.code !== 'connected') {
      setBusy(null); setNote('Connection could not be saved. Check the address and key, then test again.'); return
    }
    const connId = c.data.connection.id
    await homepilotApi.sync(connId)
    const p = await homepilotApi.listProfiles()
    setBusy(null)
    setProfiles(p.ok ? p.data.profiles : [])
    setSelected(new Set())  // new agents start disabled
    setStep('agent_selection')
  }

  async function finishSelection() {
    setBusy('enable'); setNote(null)
    for (const id of selected) await homepilotApi.setEnabled(id, true)
    setBusy(null); setStep('complete')
  }

  const progress = (
    <ol className="dp-hpw__steps" aria-label="Setup progress">
      {PHASES.map((label, i) => (
        <li key={label} className={'dp-hpw__step' + (i === PHASE[step] ? ' is-active' : i < PHASE[step] ? ' is-done' : '')}>
          <span className="dp-hpw__stepno">{i + 1}</span>{label}
        </li>
      ))}
    </ol>
  )

  return (
    <div className="dp-hpw" role="dialog" aria-modal="true" aria-label="Set up HomePilot">
      <div className="dp-hpw__panel">
        <header className="dp-hpw__head">
          <h2 className="dp-hpw__title">Set up HomePilot agents</h2>
          <button type="button" className="dp-iconbtn" aria-label="Close" onClick={onClose}>✕</button>
        </header>
        {progress}

        <div className="dp-hpw__body">
          {step === 'welcome' && (
            <div className="dp-hpw__section">
              <p>HomePilot provides the AI agents. DayPilot lets you assign work, follow progress, and approve actions. Your agents stay in HomePilot — their identity and portrait, personality, long-term memory, sessions, and tools.</p>
              <p className="dp-hpw__q"><strong>Do you already have HomePilot installed?</strong></p>
              <div className="dp-hpw__choices">
                <button type="button" className="dp-primary-button" onClick={runDetect}>Yes, connect my installation</button>
                <button type="button" className="dp-ghost-button" onClick={() => setStep('installation_method')}>No, help me install HomePilot</button>
              </div>
              <p className="dp-muted"><a href={DOCS.gettingStarted} target="_blank" rel="noreferrer">Read the official installation guide</a></p>
            </div>
          )}

          {step === 'installation_method' && (
            <div className="dp-hpw__section">
              <h3 className="dp-hpw__h3">Choose how to install HomePilot</h3>
              <div className="dp-hpw__method">
                <strong>Desktop app <span className="dp-pill dp-pill--muted">Recommended</span></strong>
                <p className="dp-muted">The easiest way — Windows, macOS, or Linux. HomePilot guides you through Docker and AI-provider setup.</p>
                <div className="dp-settings-actions">
                  <a className="dp-primary-button" href={DOCS.gettingStarted} target="_blank" rel="noreferrer">Open download instructions</a>
                  <button type="button" className="dp-ghost-button" onClick={runDetect}>I installed it — detect again</button>
                </div>
              </div>
              <div className="dp-hpw__method">
                <strong>Docker — simple container</strong>
                <pre className="dp-hpw__code">{DOCKER_RUN}<Copy text={DOCKER_RUN} /></pre>
                <button type="button" className="dp-ghost-button" onClick={runDetect}>I started HomePilot</button>
              </div>
              <div className="dp-hpw__method">
                <strong>Docker — full Compose stack</strong>
                <pre className="dp-hpw__code">{COMPOSE}<Copy text={COMPOSE} /></pre>
                <div className="dp-settings-actions">
                  <a className="dp-ghost-button" href={DOCS.github} target="_blank" rel="noreferrer">GitHub repository</a>
                  <button type="button" className="dp-ghost-button" onClick={runDetect}>I started HomePilot</button>
                </div>
              </div>
              <div className="dp-hpw__method">
                <strong>Connect another machine</strong>
                <p className="dp-muted">Use a HomePilot running on another trusted machine or server. Only connect to an installation you trust.</p>
                <button type="button" className="dp-ghost-button" onClick={() => setStep('manual_connection')}>Enter a remote address</button>
              </div>
            </div>
          )}

          {step === 'detecting' && (
            <div className="dp-hpw__section">
              <h3 className="dp-hpw__h3">{busy ? 'Looking for HomePilot…' : detect.instance ? 'HomePilot found' : 'No installation found'}</h3>
              {busy && <p className="dp-muted"><span className="dp-spinner" aria-hidden="true" /> Checking this device, Docker services, and the configured network…</p>}
              {!busy && detect.instance && (
                <>
                  <p><strong>{detect.instance.browserUrl}</strong> · {detect.instance.installationType.replace('_', ' ')}{detect.instance.version ? ` · v${detect.instance.version}` : ''}</p>
                  <div className="dp-settings-actions">
                    <button type="button" className="dp-primary-button" onClick={() => setStep('manual_connection')}>Use this installation</button>
                    <button type="button" className="dp-ghost-button" onClick={() => setStep('manual_connection')}>Use another address</button>
                  </div>
                </>
              )}
              {!busy && detect.ran && !detect.instance && (
                <>
                  <p className="dp-muted">We couldn’t find HomePilot automatically.</p>
                  <div className="dp-settings-actions">
                    <button type="button" className="dp-primary-button" onClick={() => setStep('installation_method')}>Install HomePilot</button>
                    <button type="button" className="dp-ghost-button" onClick={() => setStep('manual_connection')}>Enter address manually</button>
                    <button type="button" className="dp-ghost-button" onClick={runDetect}>Try again</button>
                  </div>
                </>
              )}
            </div>
          )}

          {step === 'manual_connection' && (
            <div className="dp-hpw__section">
              <h3 className="dp-hpw__h3">Connect DayPilot to HomePilot</h3>
              <label className="dp-settings-field"><span className="dp-settings-field__label">HomePilot API address</span></label>
              <input className="dp-provcard__input" value={apiUrl} onChange={(e) => setApiUrl(e.target.value)} placeholder="http://localhost:7860/api" aria-label="HomePilot API address" />
              <input className="dp-provcard__input" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="API key (optional)" aria-label="HomePilot API key" type="password" />
              <p className="dp-muted">Desktop / single container: <code>http://localhost:7860/api</code> · Docker Compose: <code>http://localhost:8000</code></p>
              <button type="button" className="dp-linkbtn" onClick={() => setShowAdvanced((v) => !v)}>{showAdvanced ? 'Hide advanced' : 'Advanced'}</button>
              {showAdvanced && (
                <div className="dp-provcard__advbox">
                  <label className="dp-settings-field"><span className="dp-settings-field__label">Application (browser) URL</span></label>
                  <input className="dp-provcard__input" value={browserUrl} onChange={(e) => setBrowserUrl(e.target.value)} aria-label="HomePilot application URL" />
                  <label className="dp-hpw__check"><input type="checkbox" checked={allowPrivate} onChange={(e) => setAllowPrivate(e.target.checked)} /> Allow a local / private network address</label>
                </div>
              )}
              <div className="dp-settings-actions">
                <button type="button" className="dp-primary-button" disabled={busy !== null || !apiUrl.trim()} onClick={runTest}>Test connection</button>
                <button type="button" className="dp-ghost-button" onClick={() => setStep('welcome')}>Back</button>
              </div>
            </div>
          )}

          {step === 'testing' && (
            <div className="dp-hpw__section">
              <h3 className="dp-hpw__h3">Testing the connection</h3>
              {busy && <p className="dp-muted"><span className="dp-spinner" aria-hidden="true" /> Checking HomePilot…</p>}
              {test && (
                <>
                  <ul className="dp-hpw__checks">
                    {test.checks.map((c) => (
                      <li key={c.key} className={c.ok ? 'is-ok' : 'is-bad'}><span aria-hidden="true">{c.ok ? '✓' : '✕'}</span> {c.label}</li>
                    ))}
                  </ul>
                  {test.ok ? (
                    <div className="dp-settings-actions">
                      <button type="button" className="dp-primary-button" disabled={busy !== null} onClick={connectAndSync}>{busy === 'connect' ? 'Connecting…' : 'Connect and continue'}</button>
                    </div>
                  ) : (
                    <div className="dp-settings-actions">
                      <button type="button" className="dp-ghost-button" onClick={() => setStep('manual_connection')}>{test.code === 'unauthorized' ? 'Update API key' : 'Change address'}</button>
                      <button type="button" className="dp-ghost-button" onClick={runTest}>Try again</button>
                      <a className="dp-ghost-button" href={DOCS.docs} target="_blank" rel="noreferrer">Installation help</a>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {step === 'agent_selection' && (
            <div className="dp-hpw__section">
              <h3 className="dp-hpw__h3">Choose agents for DayPilot</h3>
              <p className="dp-muted">Select which HomePilot agents appear in your workspace. New agents start disabled.</p>
              <div className="dp-settings-actions">
                <button type="button" className="dp-linkbtn" onClick={() => setSelected(new Set(profiles.map((p) => p.id)))}>Select all</button>
                <button type="button" className="dp-linkbtn" onClick={() => setSelected(new Set())}>Select none</button>
              </div>
              {profiles.length === 0 && <p className="dp-muted">No personas were found. Create or enable personas in HomePilot, then re-sync.</p>}
              <div className="dp-hpw__grid">
                {profiles.map((p) => (
                  <label key={p.id} className={'dp-hpw__agent' + (selected.has(p.id) ? ' is-sel' : '')}>
                    <input type="checkbox" checked={selected.has(p.id)} onChange={(e) => {
                      setSelected((cur) => { const n = new Set(cur); e.target.checked ? n.add(p.id) : n.delete(p.id); return n })
                    }} />
                    <span className="dp-hpw__avatar" aria-hidden="true">{p.avatarUrl ? <img src={p.avatarUrl} alt="" /> : (p.name[0] || 'A')}</span>
                    <span className="dp-hpw__agentmeta"><strong>{p.name}</strong><span className="dp-muted">{p.role}</span></span>
                  </label>
                ))}
              </div>
              <div className="dp-settings-actions">
                <button type="button" className="dp-primary-button" disabled={busy !== null} onClick={finishSelection}>{busy === 'enable' ? 'Adding…' : `Add ${selected.size} agent${selected.size === 1 ? '' : 's'}`}</button>
              </div>
            </div>
          )}

          {step === 'complete' && (
            <div className="dp-hpw__section">
              <h3 className="dp-hpw__h3">Your HomePilot agents are ready</h3>
              <ul className="dp-hpw__summary">
                <li>{selected.size} agent{selected.size === 1 ? '' : 's'} added to DayPilot</li>
                <li>Automatic synchronization is on</li>
                <li>External actions require your approval</li>
              </ul>
              <div className="dp-settings-actions">
                <button type="button" className="dp-primary-button" onClick={() => { onOpenAgents?.(); onClose() }}>Open agents</button>
                <button type="button" className="dp-ghost-button" onClick={onClose}>Finish</button>
              </div>
            </div>
          )}

          {note && <p className="dp-hpw__note" role="alert">{note}</p>}
        </div>

        <footer className="dp-hpw__foot">
          <span className="dp-hpw__lock" aria-hidden="true">🔒</span>
          <span className="dp-muted">External actions (email, calendar, coding) always require DayPilot approval. HomePilot owns identity and memory; DayPilot never copies them.</span>
        </footer>
      </div>
    </div>
  )
}
