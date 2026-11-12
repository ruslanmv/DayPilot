/**
 * HomePilotConsent — where a DayPilot user approves (or declines) a HomePilot
 * request to read their workday, and manages existing connections.
 *
 *   #/connect/homepilot?code=ABCD-EFGH   approve a pending request
 *   #/connect/homepilot                  list and revoke connections
 *
 * The user picks the workspace — only workspaces they belong to are offered —
 * and can untick any permission. Weather and wellness are never offered: that
 * data stays in this browser. Talks only to DayPilot's own API, with the
 * session cookie and CSRF header.
 */
import React, { useCallback, useEffect, useState } from 'react'
import { apiBase } from '../env'
import { csrfToken } from '../authClient'

type Consent = {
  client: string
  accountRef: string
  requestedScopes: { scope: string; description: string }[]
  workspaces: { id: string; role: string }[]
  expiresAt: string
}
type Grant = { id: string; client: string; workspaceId: string; scopes: string[]; createdAt: string | null; lastUsedAt: string | null }

async function call<T>(path: string, init?: RequestInit): Promise<{ ok: boolean; status: number; data?: T; error?: string }> {
  try {
    const res = await fetch(`${apiBase()}${path}`, {
      ...init,
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(init?.method && init.method !== 'GET' ? { 'X-CSRF-Token': csrfToken() } : {}) },
    })
    const body = await res.json().catch(() => undefined)
    if (!res.ok) {
      const detail = body?.detail
      return { ok: false, status: res.status, error: (detail && (detail.message || detail)) || `HTTP ${res.status}` }
    }
    return { ok: true, status: res.status, data: body as T }
  } catch {
    return { ok: false, status: 0, error: 'DayPilot could not be reached.' }
  }
}

export function codeFromHash(hash: string): string {
  const query = hash.split('?')[1] || ''
  return (new URLSearchParams(query).get('code') || '').toUpperCase().slice(0, 16)
}

export function isHomePilotConsentRoute(hash: string): boolean {
  return hash.startsWith('#/connect/homepilot')
}

export function HomePilotConsent() {
  const code = codeFromHash(window.location.hash)
  const [consent, setConsent] = useState<Consent | null>(null)
  const [grants, setGrants] = useState<Grant[]>([])
  const [workspace, setWorkspace] = useState('')
  const [scopes, setScopes] = useState<string[]>([])
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const loadGrants = useCallback(async () => {
    const r = await call<{ grants: Grant[] }>('/v1/integrations/homepilot/grants')
    if (r.ok && r.data) setGrants(r.data.grants)
    else if (r.status === 401) setError('Sign in to DayPilot to manage HomePilot connections.')
  }, [])

  useEffect(() => {
    void loadGrants()
    if (!code) return
    void call<Consent>(`/v1/integrations/homepilot/consent/${encodeURIComponent(code)}`).then((r) => {
      if (r.ok && r.data) {
        setConsent(r.data)
        setWorkspace(r.data.workspaces[0]?.id || '')
        setScopes(r.data.requestedScopes.map((s) => s.scope))
      } else {
        setError(r.status === 401 ? 'Sign in to DayPilot first, then open this link again.' : String(r.error))
      }
    })
  }, [code, loadGrants])

  async function decide(approve: boolean) {
    setBusy(true)
    setError('')
    const r = await call<{ status: string }>(`/v1/integrations/homepilot/consent/${encodeURIComponent(code)}`, {
      method: 'POST', body: JSON.stringify({ approve, workspaceId: workspace, scopes }),
    })
    setBusy(false)
    if (!r.ok) { setError(String(r.error)); return }
    setConsent(null)
    setMessage(approve ? 'Connected. You can return to HomePilot.' : 'Declined. Nothing was shared.')
    void loadGrants()
  }

  async function revoke(id: string) {
    const r = await call(`/v1/integrations/homepilot/grants/${id}`, { method: 'DELETE' })
    if (r.ok) setGrants((g) => g.filter((x) => x.id !== id))
    else setError(String(r.error))
  }

  const toggle = (scope: string) =>
    setScopes((s) => (s.includes(scope) ? s.filter((x) => x !== scope) : [...s, scope]))

  return (
    <main className="mx-auto max-w-xl px-4 py-10 text-sm" style={{ color: 'var(--dp-text, inherit)' }}>
      <h1 className="text-xl font-semibold">HomePilot connections</h1>
      <p className="mt-1 opacity-70">
        HomePilot can read the parts of your workday you choose, and ask DayPilot to prepare changes that you approve here in DayPilot.
        It can never send email, change your calendar or approve anything by itself.
      </p>

      {error ? <p role="alert" className="mt-4 rounded-lg border border-red-400/40 p-3 text-red-400">{error}</p> : null}
      {message ? <p role="status" className="mt-4 rounded-lg border border-emerald-400/40 p-3">{message}</p> : null}

      {consent ? (
        <section className="mt-6 rounded-xl border border-white/15 p-4" aria-label="Connection request">
          <h2 className="text-base font-semibold">{consent.client} wants access</h2>
          <p className="mt-1 opacity-70">Request code <b>{code}</b> — check it matches the one HomePilot shows.</p>
          <label className="mt-4 block">
            <span className="block opacity-70">Workspace</span>
            <select value={workspace} onChange={(e) => setWorkspace(e.target.value)}
              className="mt-1 w-full rounded-lg border border-white/15 bg-transparent p-2">
              {consent.workspaces.map((w) => <option key={w.id} value={w.id}>{w.id} ({w.role})</option>)}
            </select>
          </label>
          <fieldset className="mt-4">
            <legend className="opacity-70">What HomePilot may do</legend>
            {consent.requestedScopes.map((s) => (
              <label key={s.scope} className="mt-2 flex items-start gap-2">
                <input type="checkbox" checked={scopes.includes(s.scope)} onChange={() => toggle(s.scope)} />
                <span>{s.description}</span>
              </label>
            ))}
            <p className="mt-2 text-xs opacity-60">Weather and wellness are not shared: that data stays in this browser.</p>
          </fieldset>
          <div className="mt-5 flex gap-2">
            <button type="button" disabled={busy || !workspace || scopes.length === 0} onClick={() => { void decide(true) }}
              className="rounded-full bg-white px-4 py-2 font-semibold text-black disabled:opacity-40">Allow</button>
            <button type="button" disabled={busy} onClick={() => { void decide(false) }}
              className="rounded-full border border-white/20 px-4 py-2">Decline</button>
          </div>
        </section>
      ) : null}

      <section className="mt-8" aria-label="Active connections">
        <h2 className="text-base font-semibold">Active connections</h2>
        {grants.length === 0 ? <p className="mt-2 opacity-60">None.</p> : null}
        {grants.map((g) => (
          <div key={g.id} className="mt-2 flex items-center justify-between gap-3 rounded-lg border border-white/10 p-3">
            <span>
              <span className="block">{g.client} · {g.workspaceId}</span>
              <span className="block text-xs opacity-60">{g.scopes.join(', ')}{g.lastUsedAt ? ` · last used ${new Date(g.lastUsedAt).toLocaleString()}` : ''}</span>
            </span>
            <button type="button" onClick={() => { void revoke(g.id) }} className="rounded-full border border-white/20 px-3 py-1">Revoke</button>
          </div>
        ))}
      </section>
      <p className="mt-8"><a href="#/" className="underline opacity-70">Back to DayPilot</a></p>
    </main>
  )
}
