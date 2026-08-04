import React, { useCallback, useEffect, useState } from 'react'

import { MailSetupWizard } from '../email/MailSetupWizard'
import { emailApi, mailErrorMessage, type EmailStatus } from '../email/emailClient'

/**
 * Settings → Mail (Batch 3).
 *
 * Backed by the real `/v1/email/status` — it reflects the workspace's actual
 * MailboxConnection instead of a static record. When nothing is connected it
 * opens the shared MailSetupWizard; when connected it shows the real account and
 * offers Test, Reconnect, and Disconnect. Credentials are never shown.
 */
export function MailSettingsPanel() {
  const [status, setStatus] = useState<EmailStatus | null>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [wizard, setWizard] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  const load = useCallback(() => {
    setState('loading')
    emailApi.status().then((r) => {
      if (r.ok) { setStatus(r.data); setState('ready') } else setState('error')
    })
  }, [])
  useEffect(() => { load() }, [load])

  if (state === 'loading') return <div className="dp-settings-list"><p className="dp-muted">Loading mailbox…</p></div>
  if (state === 'error') {
    return (
      <div className="dp-settings-list">
        <p className="dp-muted">Couldn’t reach the mail service.</p>
        <div className="dp-settings-actions"><button className="dp-ghost-button" type="button" onClick={load}>Retry</button></div>
      </div>
    )
  }

  // Email disabled for this deployment → explain it, never offer setup buttons
  // that call endpoints the backend has deliberately turned off (404).
  if (status && status.enabled === false) {
    return (
      <div className="dp-settings-list">
        <h3 className="dp-hp__h">Email is disabled</h3>
        <p className="dp-muted">Email is turned off for this deployment. An administrator can enable it, then you can connect a mailbox here.</p>
      </div>
    )
  }

  if (wizard || !status?.connected) {
    return (
      <div className="dp-settings-list">
        {status?.connected && <div className="dp-settings-actions"><button className="dp-ghost-button" type="button" onClick={() => setWizard(false)}>Back</button></div>}
        <MailSetupWizard
          providers={status?.providers}
          onConnected={() => { setWizard(false); load() }}
          onCancel={status?.connected ? () => setWizard(false) : undefined}
        />
      </div>
    )
  }

  const acct = status.account
  const conn = status.connection

  async function reconnect() {
    setBusy('reconnect'); setNote(null)
    const r = await emailApi.reconnect()
    setBusy(null)
    setNote(r.ok ? mailErrorMessage(r.data.code) : 'Could not reach DayPilot.')
    load()
  }
  async function disconnect() {
    setBusy('disconnect'); setNote(null)
    const r = await emailApi.disconnect()
    setBusy(null)
    if (r.ok) { setNote('Mailbox disconnected.'); load() } else setNote('Could not reach DayPilot.')
  }

  return (
    <div className="dp-settings-list">
      <div className="dp-settings-row">
        <div className="dp-settings-row__head">
          <span className={'dp-statedot ' + (conn?.status === 'connected' ? 'dp-statedot--connected' : 'dp-statedot--degraded')} aria-hidden="true" />
          <strong>{acct?.emailAddress || conn?.emailAddress || 'Mailbox'}</strong>
          <span className={'dp-tag ' + (conn?.status === 'connected' ? 'dp-tag--healthy' : 'dp-tag--degraded')}>{conn?.status ?? 'connected'}</span>
        </div>
        <p className="dp-muted">
          {acct?.provider ? `${acct.provider} · ` : ''}{conn?.imapHost ?? ''}{conn?.imapHost ? ` (IMAP ${conn.imapPort})` : ''}
        </p>
        <div className="dp-settings-kv">
          <span>Read mail</span><span className="dp-tag dp-tag--healthy">{acct?.capabilities.read ? 'allowed' : 'no'}</span>
          <span>Draft replies</span><span className="dp-tag dp-tag--healthy">{acct?.capabilities.drafts ? 'allowed' : 'no'}</span>
          <span>Send</span><span className={'dp-tag ' + (acct?.capabilities.send ? 'dp-tag--healthy' : 'dp-tag--degraded')}>{acct?.capabilities.send ? 'approval-gated' : 'off'}</span>
        </div>
        {note && <p className="dp-muted">{note}</p>}
        <div className="dp-settings-actions">
          <button className="dp-ghost-button" type="button" disabled={busy !== null} onClick={reconnect}>{busy === 'reconnect' ? 'Testing…' : 'Test connection'}</button>
          <button className="dp-ghost-button" type="button" onClick={() => setWizard(true)}>Edit settings</button>
          <button className="dp-ghost-button dp-ghost-button--danger" type="button" disabled={busy !== null} onClick={disconnect}>{busy === 'disconnect' ? 'Disconnecting…' : 'Disconnect'}</button>
        </div>
      </div>
      <p className="dp-muted">DayPilot never sends without your explicit approval, and never deletes mail. Passwords are stored encrypted server-side and never shown here.</p>
    </div>
  )
}
