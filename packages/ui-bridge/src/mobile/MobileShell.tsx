import React, { useEffect, useState } from 'react'
import type { DayPilotTodayContext } from '@daypilot/shared-types'

type MobileTab = 'today' | 'approvals' | 'projects' | 'documents'

const FALLBACK_TODAY: DayPilotTodayContext = {
  workspaceId: 'default',
  now: null,
  next: null,
  later: [],
  counts: { aiRunning: 4, approvals: 1, blockers: 1, projectsActive: 6, projectsNeedAttention: 2 },
}

const SNAPSHOT_KEY = 'daypilot.today.snapshot'

/**
 * Mobile-first phone companion: a fast daily check-in with compact
 * Now / Next / Blocked / AI Running / Approvals cards and a bottom tab bar.
 * The last Today snapshot is cached so an offline reopen still shows state;
 * approvals require a live connection (enforced by policy on the server).
 */
export function MobileShell() {
  const [tab, setTab] = useState<MobileTab>('today')
  const [today, setToday] = useState<DayPilotTodayContext>(FALLBACK_TODAY)
  const [offline, setOffline] = useState(!navigator.onLine)

  useEffect(() => {
    // Hydrate from the cached snapshot first for instant, offline-safe render.
    try {
      const cached = localStorage.getItem(SNAPSHOT_KEY)
      if (cached) setToday(JSON.parse(cached))
    } catch {
      /* ignore */
    }
    // Then refresh from the network when available.
    fetch('/v1/today')
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) {
          setToday(data)
          try {
            localStorage.setItem(SNAPSHOT_KEY, JSON.stringify(data))
          } catch {
            /* ignore */
          }
        }
      })
      .catch(() => setOffline(true))

    const on = () => setOffline(false)
    const off = () => setOffline(true)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
    }
  }, [])

  return (
    <div className="dp-mobile">
      <header className="dp-mobile__top">
        <div className="dp-eyebrow">DAYPILOT</div>
        <span className={'dp-mobile__sync' + (offline ? ' is-offline' : '')}>
          {offline ? 'Offline · last snapshot' : 'Live'}
        </span>
      </header>

      <main className="dp-mobile__body">
        {tab === 'today' && (
          <div className="dp-mobile__cards">
            <MobileCard label="NOW" value={today.now?.title ?? 'Nothing scheduled'} tone="blue" />
            <MobileCard label="NEXT" value={today.next?.title ?? '—'} tone="muted" />
            <MobileCard label="BLOCKED" value={`${today.counts.blockers}`} tone="red" hint="need resolution" />
            <MobileCard label="AI RUNNING" value={`${today.counts.aiRunning}`} tone="cyan" hint="workflows" />
            <MobileCard label="APPROVALS" value={`${today.counts.approvals}`} tone="orange" hint="need you" />
          </div>
        )}
        {tab === 'approvals' && (
          <div className="dp-mobile__cards">
            {offline ? (
              <p className="dp-muted">Approvals require a live connection. Reconnect to decide.</p>
            ) : (
              <MobileCard label="PENDING" value={`${today.counts.approvals}`} tone="orange" hint="tap to review on desktop or here" />
            )}
          </div>
        )}
        {tab === 'projects' && (
          <div className="dp-mobile__cards">
            <MobileCard label="ACTIVE" value={`${today.counts.projectsActive}`} tone="blue" />
            <MobileCard label="NEED ATTENTION" value={`${today.counts.projectsNeedAttention}`} tone="orange" />
          </div>
        )}
        {tab === 'documents' && (
          <div className="dp-mobile__cards">
            <p className="dp-muted">Document summaries appear here. Open on desktop for deep work.</p>
          </div>
        )}
      </main>

      <nav className="dp-mobile__tabs" aria-label="Mobile navigation">
        {(['today', 'approvals', 'projects', 'documents'] as MobileTab[]).map((t) => (
          <button key={t} className={'dp-mobile__tab' + (tab === t ? ' is-active' : '')} onClick={() => setTab(t)}>
            {t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </nav>
    </div>
  )
}

function MobileCard({ label, value, tone, hint }: { label: string; value: string; tone: string; hint?: string }) {
  return (
    <div className={'dp-mobile__card dp-mobile__card--' + tone}>
      <div className="dp-mobile__card-label">{label}</div>
      <div className="dp-mobile__card-value">{value}</div>
      {hint && <div className="dp-mobile__card-hint">{hint}</div>}
    </div>
  )
}
