import React, { useEffect, useMemo, useState } from 'react'
import type { DayPilotCoderOption, DayPilotCodingMode } from '@daypilot/shared-types'
import { codingApi, type CoderCatalog, type ExecutorOption } from './codingClient'

type StartCodingRunProps = {
  /** The project this run belongs to; its repository is inherited. */
  projectId?: string | null
  projectRepository?: string
  /** Prefills the instruction — a design batch, a task, or nothing. */
  initialTask?: string
  taskId?: string | null
  onStarted: (runId: string) => void
  onClose: () => void
}

const MODES: Array<{ id: DayPilotCodingMode; label: string; hint: string }> = [
  { id: 'ask', label: 'Ask', hint: 'Writes only after you approve. The safe default.' },
  { id: 'plan', label: 'Plan', hint: 'Read-only: produces a plan and a diff, changes nothing.' },
  { id: 'auto', label: 'Auto', hint: 'Runs without stopping. Still approval-gated before any write.' },
]

/**
 * Start a coding run: what to build, where, and who writes it.
 *
 * The three choices are separate on purpose. The repository is the project's and
 * is inherited rather than retyped. The *executor* owns the governed pipeline —
 * the throwaway checkout, the path policy, the sandbox, the risk score. The
 * *coder* is only the author of the diff, so switching to Claude Code or Codex
 * changes who writes it and nothing about how it is governed.
 *
 * Coders come from the executor, which probes its own host, so an agent whose
 * CLI or credential is missing appears disabled with the reason rather than
 * failing once the run is already under way.
 */
export function StartCodingRun({
  projectId,
  projectRepository = '',
  initialTask = '',
  taskId = null,
  onStarted,
  onClose,
}: StartCodingRunProps) {
  const [task, setTask] = useState(initialTask)
  const [repo, setRepo] = useState('')
  const [mode, setMode] = useState<DayPilotCodingMode>('ask')
  const [executor, setExecutor] = useState('')
  const [coder, setCoder] = useState('')
  const [executors, setExecutors] = useState<ExecutorOption[]>([])
  const [catalog, setCatalog] = useState<CoderCatalog>({ coders: [], reachable: true, detail: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const effectiveRepo = repo.trim() || projectRepository
  const canStart = Boolean(task.trim()) && Boolean(effectiveRepo) && !busy

  useEffect(() => {
    let live = true
    codingApi.executors().then((items) => {
      if (!live) return
      setExecutors(items)
      const preferred = items.find((e) => e.default && e.enabled) || items.find((e) => e.enabled)
      setExecutor((current) => current || preferred?.executor || '')
    })
    return () => {
      live = false
    }
  }, [])

  useEffect(() => {
    let live = true
    codingApi.coders(executor || undefined, projectId).then((next) => {
      if (live) setCatalog(next)
    })
    return () => {
      live = false
    }
  }, [executor, projectId])

  // The deployment's own default is the resting choice: picking a coder is an
  // override, never a requirement.
  const defaultCoder = useMemo(
    () => catalog.coders.find((c) => c.default)?.id || '',
    [catalog.coders],
  )

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  async function start() {
    setBusy(true)
    setError('')
    const result = await codingApi.start({
      task: task.trim(),
      repo: repo.trim(),
      mode,
      executor: executor || undefined,
      coder: coder ? { provider: coder, model: '' } : undefined,
      projectId,
      taskId,
    })
    setBusy(false)
    if (!result.ok) {
      setError(result.error)
      return
    }
    onStarted(result.run.id)
  }

  return (
    <div className="dp-modal-backdrop" onMouseDown={onClose}>
      <div
        className="dp-pw dp-start-run"
        role="dialog"
        aria-modal="true"
        aria-label="Start a coding run"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="dp-pw__head">
          <h3>Start a coding run</h3>
          <button className="dp-icon-button" aria-label="Close" onClick={onClose}>✕</button>
        </header>

        <div className="dp-pw__body">
          <label className="dp-onb__field">
            <span>What should be built?</span>
            <textarea
              value={task}
              onChange={(e) => setTask(e.target.value)}
              rows={3}
              placeholder="Add a /health endpoint with a smoke test"
              autoFocus
            />
          </label>

          <label className="dp-onb__field">
            <span>Repository</span>
            <input
              value={repo}
              onChange={(e) => setRepo(e.target.value)}
              placeholder={projectRepository || 'https://github.com/owner/repo'}
            />
            {projectRepository && !repo.trim() ? (
              <small className="dp-onb__hint">
                Using this project’s repository: {projectRepository}
              </small>
            ) : null}
            {!projectRepository && !repo.trim() ? (
              <small className="dp-onb__hint">
                This project has no repository yet — add one here and the run will use it.
              </small>
            ) : null}
          </label>

          <fieldset className="dp-onb__field">
            <legend>Mode</legend>
            <div className="dp-start-run__modes" role="radiogroup" aria-label="Mode">
              {MODES.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  role="radio"
                  aria-checked={mode === m.id}
                  className={'dp-start-run__mode' + (mode === m.id ? ' is-active' : '')}
                  onClick={() => setMode(m.id)}
                  title={m.hint}
                >
                  {m.label}
                </button>
              ))}
            </div>
            <small className="dp-onb__hint">{MODES.find((m) => m.id === mode)?.hint}</small>
          </fieldset>

          <div className="dp-pw__row">
            <label className="dp-onb__field">
              <span>Executor</span>
              <select value={executor} onChange={(e) => setExecutor(e.target.value)}>
                {executors.map((e) => (
                  <option key={e.executor} value={e.executor} disabled={!e.enabled}>
                    {e.executor}
                    {e.default ? ' (default)' : ''}
                    {e.enabled ? '' : ' — not enabled'}
                  </option>
                ))}
              </select>
              <small className="dp-onb__hint">Owns the workspace, guardrails, and review.</small>
            </label>

            <label className="dp-onb__field">
              <span>AI coder</span>
              <select
                value={coder}
                onChange={(e) => setCoder(e.target.value)}
                disabled={!catalog.reachable || catalog.coders.length === 0}
              >
                <option value="">
                  {defaultCoder ? `Deployment default (${defaultCoder})` : 'Deployment default'}
                </option>
                {catalog.coders.map((c: DayPilotCoderOption) => (
                  <option key={c.id} value={c.id} disabled={!c.available} title={c.reason}>
                    {c.label}
                    {c.available ? '' : ` — ${c.reason}`}
                  </option>
                ))}
              </select>
              <small className="dp-onb__hint">
                {!catalog.reachable
                  ? catalog.detail || 'The executor could not be reached.'
                  : 'Only who writes the patch changes. Every guardrail stays the same.'}
              </small>
            </label>
          </div>

          {error ? (
            <p className="dp-start-run__error" role="alert">
              {error}
            </p>
          ) : null}
        </div>

        <footer className="dp-pw__foot">
          <button className="dp-onb__back" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="dp-onb__next" onClick={start} disabled={!canStart}>
            {busy ? 'Starting…' : mode === 'plan' ? 'Plan it' : 'Start run'}
          </button>
        </footer>
      </div>
    </div>
  )
}
