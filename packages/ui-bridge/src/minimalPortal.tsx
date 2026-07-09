import React, { FormEvent, useMemo, useState } from 'react'
import type { DayPilotMessage, DayPilotTask } from '@daypilot/shared-types'
import { dayHours, initialMessages, initialTasks, weekDays, weekSlots } from './spaceBridgeData'

type PortalView = 'bridge' | 'calendar' | 'tasks'
type CalendarMode = 'day' | 'week'

type SpaceBridgeShellProps = {
  compact?: boolean
}

function cx(...classes: Array<string | false | undefined>) {
  return classes.filter(Boolean).join(' ')
}

function taskHour(task: DayPilotTask) {
  return task.start.slice(0, 2)
}

function priorityClass(task: DayPilotTask) {
  return `dp-tag--${task.priority}`
}

function ownerClass(task: DayPilotTask) {
  return task.owner === 'commander' ? 'dp-tag--commander' : 'dp-tag--agent'
}

function normalizeDirective(input: string) {
  return input.replace(/\s+/g, ' ').trim()
}

function createCommanderTask(input: string): DayPilotTask {
  const clean = normalizeDirective(input)
  const hasEvening = /18|6\s*pm|evening/i.test(clean)
  const hasMeeting = /meeting|meet|sync|brief/i.test(clean)
  return {
    id: `task-${Date.now()}`,
    day: 'Thursday',
    start: hasEvening ? '18:00' : hasMeeting ? '16:00' : '12:00',
    end: hasEvening ? '19:00' : hasMeeting ? '16:45' : '13:00',
    title: clean.length > 64 ? `${clean.slice(0, 61)}...` : clean,
    priority: /critical|urgent|blocker/i.test(clean) ? 'critical' : 'high',
    owner: 'commander',
    executor: 'Commander',
    status: hasEvening ? 'scheduled' : 'active',
    source: 'Strategic Feed directive',
    context: `Manual assignment created from the command feed. DayPilot protected the time block and will keep autonomous agent work out of the same focus window. Original directive: "${clean}"`,
  }
}

function createAgentFollowup(input: string): DayPilotTask {
  const clean = normalizeDirective(input)
  return {
    id: `task-agent-${Date.now()}`,
    day: 'Thursday',
    start: '12:00',
    end: '12:30',
    title: 'Autonomous context preparation',
    priority: 'medium',
    owner: 'agent',
    executor: 'Sec-Core',
    status: 'scheduled',
    source: 'Matrix RAG · local HomePilot cluster',
    context: `Background preparation created by the directive. Sec-Core will gather emails, local notes, and repository context related to: "${clean}". Write actions remain approval-gated.`,
  }
}

function NavButton({ active, children, onClick }: { active: boolean; children: React.ReactNode; onClick: () => void }) {
  return (
    <button type="button" className={cx(active && 'is-active')} onClick={onClick}>
      {children}
    </button>
  )
}

function StrategyBlock({ task, selected, onSelect }: { task: DayPilotTask; selected: boolean; onSelect: () => void }) {
  return (
    <button type="button" className={cx('dp-strategy-block', selected && 'is-selected')} onClick={onSelect}>
      <div className="dp-time">{task.start}–{task.end} · {task.day}</div>
      <div className="dp-title">{task.title}</div>
      <div className="dp-meta-row">
        <span className={cx('dp-tag', ownerClass(task))}>{task.owner === 'commander' ? 'COMMANDER' : '.HPERSONA'}</span>
        <span className={cx('dp-tag', priorityClass(task))}>{task.priority.toUpperCase()}</span>
        <span>{task.executor}</span>
      </div>
    </button>
  )
}

function ChatFeed({ messages }: { messages: DayPilotMessage[] }) {
  return (
    <div className="dp-feed" aria-label="Strategy orchestration feed">
      {messages.map((message) => (
        <article key={message.id} className={cx('dp-message', message.role === 'commander' && 'dp-message--commander')}>
          <div className="dp-message__label">{message.role === 'commander' ? 'Commander' : 'DayPilot'} · {message.createdAt}</div>
          <div className="dp-bubble">{message.body}</div>
        </article>
      ))}
    </div>
  )
}

function StrategicFeed({ messages, onSubmit }: { messages: DayPilotMessage[]; onSubmit: (directive: string) => void }) {
  const [directive, setDirective] = useState('')

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const clean = normalizeDirective(directive)
    if (!clean) return
    onSubmit(clean)
    setDirective('')
  }

  return (
    <section className="dp-chat">
      <ChatFeed messages={messages} />
      <div className="dp-command-bar">
        <form className="dp-command-form" onSubmit={handleSubmit}>
          <span className="dp-muted" aria-hidden="true">⌘</span>
          <input
            value={directive}
            onChange={(event) => setDirective(event.target.value)}
            placeholder="Ask DayPilot to schedule, rebalance, summarize, or delegate…"
            aria-label="Command DayPilot"
          />
          <button className="dp-send-button" type="submit">Send</button>
        </form>
      </div>
    </section>
  )
}

function StrategyBlocks({ tasks, selectedTaskId, onSelect }: { tasks: DayPilotTask[]; selectedTaskId?: string; onSelect: (task: DayPilotTask) => void }) {
  const today = tasks.filter((task) => task.day === 'Monday' || task.day === 'Thursday')
  return (
    <aside className="dp-strategy" aria-label="Clickable strategy blocks">
      <div className="dp-section-head">
        <h3>Today's Strategy</h3>
        <span>{today.length} blocks</span>
      </div>
      <div className="dp-strategy-list">
        {today.map((task) => (
          <StrategyBlock key={task.id} task={task} selected={selectedTaskId === task.id} onSelect={() => onSelect(task)} />
        ))}
      </div>
    </aside>
  )
}

function DayCalendar({ tasks, onSelect }: { tasks: DayPilotTask[]; onSelect: (task: DayPilotTask) => void }) {
  return (
    <div className="dp-day-grid">
      {dayHours.map((hour) => {
        const hourTasks = tasks.filter((task) => taskHour(task) === hour.slice(0, 2))
        return (
          <div className="dp-time-row" key={hour}>
            <div className="dp-time-label">{hour}</div>
            <div className="dp-time-cell">
              {hourTasks.length === 0 ? <div className="dp-empty">quiet buffer</div> : hourTasks.map((task) => (
                <button
                  key={task.id}
                  type="button"
                  className={cx('dp-calendar-card', task.owner === 'commander' ? 'dp-calendar-card--commander' : 'dp-calendar-card--agent')}
                  onClick={() => onSelect(task)}
                >
                  <div className="dp-title">{task.title}</div>
                  <div className="dp-meta-row">
                    <span>{task.start}–{task.end}</span>
                    <span>·</span>
                    <span>{task.executor}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function WeekCalendar({ tasks, onSelect }: { tasks: DayPilotTask[]; onSelect: (task: DayPilotTask) => void }) {
  return (
    <div className="dp-week-grid" aria-label="Week horizon calendar matrix">
      <div className="dp-week-head" />
      {weekDays.map((day) => (
        <div key={day} className="dp-week-head"><strong>{day.slice(0, 3)}</strong><span>Active</span></div>
      ))}
      {weekSlots.map((slot) => (
        <React.Fragment key={slot}>
          <div className="dp-week-time">{slot}</div>
          {weekDays.map((day) => {
            const slotTasks = tasks.filter((task) => task.day === day && taskHour(task) === slot.slice(0, 2))
            return (
              <div key={`${day}-${slot}`} className="dp-week-cell">
                {slotTasks.map((task) => (
                  <button
                    key={task.id}
                    type="button"
                    className={cx('dp-week-chip', task.owner === 'commander' ? 'dp-week-chip--commander' : 'dp-week-chip--agent')}
                    onClick={() => onSelect(task)}
                  >
                    {task.title}
                  </button>
                ))}
              </div>
            )
          })}
        </React.Fragment>
      ))}
    </div>
  )
}

function CalendarCore({ tasks, onSelect }: { tasks: DayPilotTask[]; onSelect: (task: DayPilotTask) => void }) {
  const [mode, setMode] = useState<CalendarMode>('day')
  const todayTasks = useMemo(() => tasks.filter((task) => task.day === 'Monday' || task.day === 'Thursday'), [tasks])
  return (
    <section className="dp-calendar-screen">
      <div className="dp-calendar-controls">
        <div>
          <h3>Temporal Matrix Distribution</h3>
          <p>AI-arranged workday with protected buffers and meeting preparation blocks.</p>
        </div>
        <div className="dp-calendar-toggle" role="tablist" aria-label="Calendar horizon">
          <button type="button" className={cx(mode === 'day' && 'is-active')} onClick={() => setMode('day')}>Day Horizon</button>
          <button type="button" className={cx(mode === 'week' && 'is-active')} onClick={() => setMode('week')}>Week Horizon</button>
        </div>
      </div>
      <div className="dp-calendar-area">
        {mode === 'day' ? <DayCalendar tasks={todayTasks} onSelect={onSelect} /> : <WeekCalendar tasks={tasks} onSelect={onSelect} />}
      </div>
    </section>
  )
}

function LedgerCard({ task, onSelect }: { task: DayPilotTask; onSelect: () => void }) {
  return (
    <article className="dp-ledger-card" onClick={onSelect} role="button" tabIndex={0} onKeyDown={(event) => event.key === 'Enter' && onSelect()}>
      <div className="dp-title">{task.title}</div>
      <div className="dp-meta-row">
        <span className={cx('dp-tag', ownerClass(task))}>{task.status.toUpperCase()}</span>
        <span>{task.start}–{task.end}</span>
        <span>{task.executor}</span>
      </div>
      <p>{task.context}</p>
    </article>
  )
}

function OperationalLedger({ tasks, onSelect }: { tasks: DayPilotTask[]; onSelect: (task: DayPilotTask) => void }) {
  const commanderTasks = tasks.filter((task) => task.owner === 'commander')
  const agentTasks = tasks.filter((task) => task.owner === 'agent')
  return (
    <section className="dp-tasks-screen">
      <div className="dp-calendar-controls">
        <div>
          <h3>Operational Ledger</h3>
          <p>Manual focus blocks stay separate from autonomous .hpersona processes.</p>
        </div>
        <span className="dp-pill">REALTIME STATE MATRIX</span>
      </div>
      <div className="dp-ledger">
        <div className="dp-ledger-column">
          <div className="dp-ledger-head">
            <h3>Commander Assignments</h3>
            <p>Deep manual work, structural decisions, meeting prep.</p>
          </div>
          <div className="dp-ledger-list">
            {commanderTasks.map((task) => <LedgerCard key={task.id} task={task} onSelect={() => onSelect(task)} />)}
          </div>
        </div>
        <div className="dp-ledger-column">
          <div className="dp-ledger-head">
            <h3>Autonomous Agents (.H)</h3>
            <p>Background scanning, RAG merges, PR checks, read-only preparation.</p>
          </div>
          <div className="dp-ledger-list">
            {agentTasks.map((task) => <LedgerCard key={task.id} task={task} onSelect={() => onSelect(task)} />)}
          </div>
        </div>
      </div>
    </section>
  )
}

function DetailDrawer({ task, onClose }: { task?: DayPilotTask; onClose: () => void }) {
  return (
    <>
      <div className={cx('dp-drawer-backdrop', task && 'is-open')} onClick={onClose} />
      <aside className={cx('dp-drawer', task && 'is-open')} aria-hidden={!task} aria-label="Context detail drawer">
        <div className="dp-drawer-head">
          <div>
            <div className="dp-eyebrow">Context Telemetry</div>
            <h3>{task?.title ?? 'No task selected'}</h3>
          </div>
          <button type="button" className="dp-icon-button" onClick={onClose} aria-label="Close detail drawer">×</button>
        </div>
        {task && (
          <>
            <div className="dp-drawer-section">
              <h4>Target execution frame</h4>
              <p>{task.day} · {task.start}–{task.end} · {task.executor}</p>
            </div>
            <div className="dp-drawer-section">
              <h4>State</h4>
              <p>{task.status.toUpperCase()} · {task.priority.toUpperCase()} · {task.owner === 'commander' ? 'Commander manual focus' : 'Autonomous .hpersona process'}</p>
            </div>
            <div className="dp-drawer-section">
              <h4>Source</h4>
              <p>{task.source ?? 'Local DayPilot state'}</p>
            </div>
            <div className="dp-drawer-section">
              <h4>Vector context elements</h4>
              <p>{task.context}</p>
            </div>
          </>
        )}
      </aside>
    </>
  )
}

export function SpaceBridgeShell({ compact = false }: SpaceBridgeShellProps) {
  const [view, setView] = useState<PortalView>('bridge')
  const [messages, setMessages] = useState<DayPilotMessage[]>(initialMessages)
  const [tasks, setTasks] = useState<DayPilotTask[]>(initialTasks)
  const [selectedTask, setSelectedTask] = useState<DayPilotTask | undefined>()

  function addDirective(directive: string) {
    const commanderTask = createCommanderTask(directive)
    const agentTask = createAgentFollowup(directive)
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

    setMessages((current) => [
      ...current,
      { id: `msg-user-${Date.now()}`, role: 'commander', body: directive, createdAt: timestamp },
      {
        id: `msg-ai-${Date.now()}`,
        role: 'assistant',
        createdAt: timestamp,
        body:
          'Directive processed. I updated the strategy blocks, protected the calendar allocation, and separated Commander work from autonomous .hpersona preparation in the operational ledger.',
      },
    ])
    setTasks((current) => [commanderTask, agentTask, ...current])
    setSelectedTask(commanderTask)
  }

  return (
    <div className={cx('dp-shell', compact && 'dp-shell--compact')}>
      <aside className="dp-rail">
        <div className="dp-identity">
          <div className="dp-eyebrow">DayPilot</div>
          <h1>Command Bridge</h1>
          <div className="dp-status-line">● LOCAL SYNC · HOMEPILOT READY</div>
        </div>
        <nav className="dp-nav" aria-label="DayPilot views">
          <NavButton active={view === 'bridge'} onClick={() => setView('bridge')}>Command Bridge</NavButton>
          <NavButton active={view === 'calendar'} onClick={() => setView('calendar')}>Calendar Core</NavButton>
          <NavButton active={view === 'tasks'} onClick={() => setView('tasks')}>Task Ledger</NavButton>
        </nav>
      </aside>
      <main className="dp-core">
        <header className="dp-topbar">
          <div>
            <h2>{view === 'bridge' ? 'Strategic Feed' : view === 'calendar' ? 'Temporal Matrix' : 'Operational Ledger'}</h2>
            <p>Premium minimalist portal for AI-organized workdays, meetings, tasks, and background agents.</p>
          </div>
          <span className="dp-pill">OBSIDIAN · APPLE BLUE · CONTEXT DRAWER</span>
        </header>
        <div className="dp-view">
          {view === 'bridge' && (
            <div className="dp-bridge">
              <StrategicFeed messages={messages} onSubmit={addDirective} />
              <StrategyBlocks tasks={tasks} selectedTaskId={selectedTask?.id} onSelect={setSelectedTask} />
            </div>
          )}
          {view === 'calendar' && <CalendarCore tasks={tasks} onSelect={setSelectedTask} />}
          {view === 'tasks' && <OperationalLedger tasks={tasks} onSelect={setSelectedTask} />}
        </div>
      </main>
      <DetailDrawer task={selectedTask} onClose={() => setSelectedTask(undefined)} />
    </div>
  )
}
