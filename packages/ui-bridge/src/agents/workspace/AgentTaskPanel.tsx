import React, { useEffect, useState } from 'react'

import { agentLifecycleLabel, homepilotApi, type AgentProfile, type AgentTaskRow } from '../../settings/homepilotClient'

/**
 * Agent task rail (Batch A5–A8, restyled to the product design). A single scroll
 * column: an "Overview" completion bar, then Active tasks / Waiting for approval
 * / Completed today, each row showing a priority pill, live status, and its
 * approval lifecycle where relevant. Read-only — work is created from the
 * conversation and executed only after you approve it. `refreshKey` re-fetches
 * after a turn.
 */
function priorityLabel(p: string): string {
  const v = (p || '').toLowerCase()
  if (v === 'high' || v === 'critical') return 'High'
  if (v === 'low') return 'Low'
  return 'Normal'
}

function timeOf(iso?: string | null): string {
  if (!iso) return ''
  try { return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) } catch { return '' }
}

function Row({ t }: { t: AgentTaskRow }) {
  const done = t.status === 'completed'
  const waiting = t.status === 'waiting_for_approval'
  const failed = t.status === 'failed' || t.status === 'cancelled'
  const life = agentLifecycleLabel(t.lifecycle)
  return (
    <article className={'dp-tr' + (done ? ' dp-tr--done' : '')}>
      <span className={'dp-tr__check' + (done ? ' is-done' : '')} aria-hidden="true">{done ? '✓' : ''}</span>
      <div className="dp-tr__body">
        <p className="dp-tr__title">{t.title}</p>
        <div className="dp-tr__meta">
          <span className={'dp-tr__prio dp-tr__prio--' + priorityLabel(t.priority).toLowerCase()}>{priorityLabel(t.priority)}</span>
          {waiting && <span className="dp-tr__state dp-tr__state--wait">Awaiting your approval</span>}
          {!waiting && !done && !failed && <span className="dp-tr__state"><span className="dp-tr__dot" aria-hidden="true" />{life || 'In progress'}</span>}
          {failed && <span className="dp-tr__state dp-tr__state--fail">{life || 'Failed'}</span>}
          {done && t.capability && <span className="dp-tr__state">Completed {timeOf(t.updatedAt) && `at ${timeOf(t.updatedAt)}`}</span>}
        </div>
      </div>
      {!done && !failed && <span className="dp-tr__pct">{Math.round(t.progress || 0)}%</span>}
    </article>
  )
}

function Section({ label, count, children }: { label: string; count: number; children: React.ReactNode }) {
  if (count === 0) return null
  return (
    <div className="dp-taskrail__section">
      <div className="dp-taskrail__section-head"><span>{label}</span><span className="dp-taskrail__section-count">{count}</span></div>
      {children}
    </div>
  )
}

export function AgentTaskPanel({ agent, refreshKey = 0 }: { agent: AgentProfile; refreshKey?: number }) {
  const [rows, setRows] = useState<AgentTaskRow[]>([])
  const [load, setLoad] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    let alive = true
    homepilotApi.getAgentTasks(agent.id).then((r) => {
      if (!alive) return
      if (r.ok) { setRows(r.data.tasks); setLoad('ready') } else setLoad('error')
    })
    return () => { alive = false }
  }, [agent.id, refreshKey])

  const active = rows.filter((t) => ['active', 'planned', 'approved', 'executing'].includes(t.status))
  const waiting = rows.filter((t) => t.status === 'waiting_for_approval')
  const completed = rows.filter((t) => ['completed', 'failed', 'cancelled'].includes(t.status))
  const overall = rows.length
    ? Math.round(rows.reduce((s, t) => s + (t.status === 'completed' ? 100 : (t.progress || 0)), 0) / rows.length)
    : 0

  return (
    <aside className="dp-taskrail" aria-label={`${agent.name}'s tasks`}>
      <header className="dp-taskrail__head">
        <h3 className="dp-taskrail__title">{agent.name}’s tasks</h3>
        <div className="dp-taskrail__overview">
          <span>Overview</span>
          <span className="dp-taskrail__pct">{overall}%</span>
        </div>
        <div className="dp-taskrail__bar" role="progressbar" aria-valuenow={overall} aria-valuemin={0} aria-valuemax={100}>
          <span style={{ width: `${overall}%` }} />
        </div>
      </header>

      {load === 'loading' && <p className="dp-taskrail__empty">Loading…</p>}
      {load === 'error' && <p className="dp-taskrail__empty">Couldn’t load tasks.</p>}
      {load === 'ready' && rows.length === 0 && (
        <p className="dp-taskrail__empty">No tasks yet. Send {agent.name} a directive to get started.</p>
      )}

      {load === 'ready' && rows.length > 0 && (
        <div className="dp-taskrail__body">
          <Section label="Active tasks" count={active.length}>{active.map((t) => <Row key={t.id} t={t} />)}</Section>
          <Section label="Waiting for approval" count={waiting.length}>{waiting.map((t) => <Row key={t.id} t={t} />)}</Section>
          <Section label="Completed" count={completed.length}>{completed.map((t) => <Row key={t.id} t={t} />)}</Section>
        </div>
      )}

      <footer className="dp-taskrail__foot">
        <span aria-hidden="true">👥</span> {agent.name} delegates to other agents to save you time.
      </footer>
    </aside>
  )
}
