import React, { useMemo, useState } from 'react'
import { diagramsApi } from './diagramsClient'
import type { Diagram } from './dmind'
import { GanttView } from './GanttView'
import { PRIORITIES, STATUSES, ScheduleError, exportable, gantt, makeTasks, progress, readTask, schedule, setTask, type Priority, type TaskStatus } from './tasks'

const today = () => new Date().toISOString().slice(0, 10)

/**
 * Tasks (batch C4): turn the map into a work breakdown, schedule it, see it as a Gantt chart and send
 * the open tasks to the DayPilot task list. Every step is an ordinary, undoable edit of the map.
 */
export function TasksPanel({
  diagram,
  selected,
  savedId,
  onChange,
  onMessage,
}: {
  diagram: Diagram
  selected: string
  savedId?: string
  onChange: (next: Diagram) => void
  onMessage: (text: string) => void
}) {
  const [start, setStart] = useState(today())
  const [showGantt, setShowGantt] = useState(false)
  const [busy, setBusy] = useState(false)
  const stats = useMemo(() => progress(diagram), [diagram])
  const chart = useMemo(() => gantt(diagram), [diagram])
  const node = diagram.nodes.find((n) => n.id === selected)
  const task = node ? readTask(node) : null
  const attempt = (fn: () => Diagram, ok?: (next: Diagram) => string) => {
    try {
      const next = fn()
      onChange(next)
      if (ok) onMessage(ok(next))
    } catch (e) {
      onMessage(e instanceof ScheduleError || e instanceof Error ? e.message : 'That did not work.')
    }
  }

  async function send() {
    const items = exportable(diagram)
    if (!savedId) return onMessage('Save the diagram first, then send its tasks.')
    if (!items.length) return onMessage('There are no open tasks to send.')
    if (!window.confirm(`Add ${items.length} open task(s) to your DayPilot task list? Tasks already sent are skipped.`)) return
    setBusy(true)
    const r = await diagramsApi.pushTasks(savedId, items)
    setBusy(false)
    onMessage(r.ok ? `Added ${r.data.created} task(s) to your task list${r.data.skipped ? `; ${r.data.skipped} were already there` : ''}.` : r.error)
  }

  return (
    <details className="dmind-tasks">
      <summary>
        Tasks and timeline{stats.total ? ` · ${stats.done}/${stats.total} done` : ''}
      </summary>
      <div className="dmind-tasks-body">
        <p>
          Turn the map into a plan: leaf topics become tasks, phases run one after another, and dependency links make a task wait.
        </p>
        <div className="dmind-tasks-row">
          <button onClick={() => attempt(() => makeTasks(diagram).diagram, () => 'Leaf topics are now tasks. Set dates with Schedule.')}>Make tasks from leaf topics</button>
          <label>
            Start date
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          </label>
          <button disabled={!stats.total} onClick={() => attempt(() => schedule(diagram, start), () => 'Scheduled. Open the timeline to see it.')}>
            Schedule
          </button>
          <button aria-pressed={showGantt} disabled={!stats.total} onClick={() => setShowGantt(!showGantt)}>
            {showGantt ? 'Hide timeline' : 'Show timeline'}
          </button>
          <button disabled={busy || !stats.total} onClick={() => void send()}>
            Send open tasks to Tasks
          </button>
        </div>
        {stats.total > 0 && (
          <progress aria-label="Tasks done" max={100} value={stats.percent}>
            {stats.percent}%
          </progress>
        )}
        {node && (
          <fieldset className="dmind-task-edit">
            <legend>Selected topic: {node.label}</legend>
            {task ? (
              <>
                <label>
                  Status
                  <select value={task.status} onChange={(e) => attempt(() => setTask(diagram, node.id, { ...task, status: e.target.value as TaskStatus }))}>
                    {STATUSES.map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Starts
                  <input type="date" value={task.start ?? ''} onChange={(e) => attempt(() => setTask(diagram, node.id, { ...task, start: e.target.value || undefined }))} />
                </label>
                <label>
                  Days
                  <input type="number" min={1} max={3650} value={task.days ?? ''} onChange={(e) => attempt(() => setTask(diagram, node.id, { ...task, days: e.target.value ? Number(e.target.value) : undefined }))} />
                </label>
                <label>
                  Owner
                  <input maxLength={80} value={task.owner ?? ''} onChange={(e) => attempt(() => setTask(diagram, node.id, { ...task, owner: e.target.value || undefined }))} />
                </label>
                <label>
                  Priority
                  <select value={task.priority ?? 'medium'} onChange={(e) => attempt(() => setTask(diagram, node.id, { ...task, priority: e.target.value as Priority }))}>
                    {PRIORITIES.map((p) => (
                      <option key={p}>{p}</option>
                    ))}
                  </select>
                </label>
                <button onClick={() => attempt(() => setTask(diagram, node.id, null))}>Not a task</button>
              </>
            ) : (
              <button onClick={() => attempt(() => setTask(diagram, node.id, { status: 'todo', days: 2 }))}>Make this a task</button>
            )}
          </fieldset>
        )}
        {showGantt && <GanttView data={chart} />}
      </div>
    </details>
  )
}
