import React, { FormEvent, useMemo, useState } from 'react'
import type { DayPilotAgent, DayPilotDocument, DayPilotDocumentSource, DayPilotMessage, DayPilotProject, DayPilotTask } from '@daypilot/shared-types'
import { dayHours, documentSources, initialAgents, initialDocuments, initialMessages, initialProjects, initialTasks, weekDays, weekSlots } from './spaceBridgeData'

type PortalView = 'command' | 'calendar' | 'tasks' | 'projects' | 'documents' | 'agents'
type CalendarMode = 'day' | 'week'
type DrawerItem =
  | { kind: 'task'; item: DayPilotTask }
  | { kind: 'project'; item: DayPilotProject }
  | { kind: 'agent'; item: DayPilotAgent }
  | { kind: 'document'; item: DayPilotDocument }

type SpaceBridgeShellProps = {
  compact?: boolean
}

const commandSummary = {
  now: 'Continue DayPilot UI implementation',
  next: 'Review GitPilot generated patch',
  later: 'Matrix Designer feedback + client follow-up',
  document: 'proposal_v4.docx supports the 09:00 Client Alpha review',
}

function cx(...classes: Array<string | false | undefined>) {
  return classes.filter(Boolean).join(' ')
}

function normalizeDirective(input: string) {
  return input.replace(/\s+/g, ' ').trim()
}

function taskHour(task: DayPilotTask) {
  return task.start.slice(0, 2)
}

function ownerLabel(task: DayPilotTask) {
  return task.owner === 'you' ? 'YOU' : task.owner.toUpperCase()
}

function ownerClass(owner: DayPilotTask['owner']) {
  return `dp-tag--${owner}`
}

function priorityClass(task: DayPilotTask) {
  return `dp-tag--${task.priority}`
}

function riskClass(risk?: string) {
  return risk ? `dp-tag--risk-${risk}` : 'dp-tag--medium'
}

function createHumanTask(input: string): DayPilotTask {
  const clean = normalizeDirective(input)
  const isMeeting = /meeting|meet|sync|brief|review|client/i.test(clean)
  const isGitPilot = /gitpilot|code|branch|test|patch|pr/i.test(clean)

  return {
    id: `task-${Date.now()}`,
    day: 'Thursday',
    start: isMeeting ? '13:00' : isGitPilot ? '10:00' : '12:00',
    end: isMeeting ? '14:00' : isGitPilot ? '12:00' : '13:00',
    title: clean.length > 64 ? `${clean.slice(0, 61)}...` : clean,
    priority: /critical|urgent|blocker|risk/i.test(clean) ? 'critical' : 'high',
    owner: 'you',
    executor: 'You',
    status: 'scheduled',
    source: isGitPilot ? 'GitPilot · natural command' : 'Command · natural language planning',
    confidence: 86,
    risk: /risk|blocker/i.test(clean) ? 'high' : 'medium',
    nextAction: 'Start or approve this focus block from Command when ready.',
    parallelAi: 'Scheduler checks conflicts while Project Analyst updates linked project status.',
    skipImpact: 'The requested commitment remains outside the approved day plan.',
    context: `DayPilot converted this command into a manual commitment and will synchronize calendar, tasks, projects, and AI workflows after approval. Original directive: "${clean}"`,
  }
}

function createAiTask(input: string): DayPilotTask {
  const clean = normalizeDirective(input)

  return {
    id: `task-agent-${Date.now()}`,
    day: 'Thursday',
    start: '12:00',
    end: '12:30',
    title: 'Autonomous context preparation',
    priority: 'medium',
    owner: 'ai',
    executor: 'Project Analyst',
    status: 'running',
    source: 'Ollabridge · local agent routing',
    confidence: 90,
    risk: 'low',
    nextAction: 'No manual action yet; review only if the agent requests approval.',
    parallelAi: 'Email Sentinel and Matrix Designer collect supporting context in the background.',
    skipImpact: 'DayPilot may have less evidence for the next plan adjustment.',
    context: `Background preparation for: "${clean}". Write actions remain approval-gated.`,
  }
}

function NavButton({ active, children, onClick }: { active: boolean; children: React.ReactNode; onClick: () => void }) {
  return (
    <button type="button" className={cx(active && 'is-active')} onClick={onClick}>
      {children}
    </button>
  )
}

function MorningCommandCard({ agents, projects, onFocus, onReviewAi, onAdjust }: {
  agents: DayPilotAgent[]
  projects: DayPilotProject[]
  onFocus: () => void
  onReviewAi: () => void
  onAdjust: () => void
}) {
  const runningAgents = agents.filter((agent) => agent.status === 'Running').length
  const approvals = agents.filter((agent) => agent.status === 'Needs Approval' || agent.status === 'Blocked').length
  const attentionProjects = projects.filter((project) => project.risk !== 'low').length

  return (
    <section className="dp-morning-card" aria-label="Morning command summary">
      <div className="dp-morning-copy">
        <div className="dp-eyebrow">Good morning. Here is your day.</div>
        <dl className="dp-now-next">
          <div><dt>Now</dt><dd>{commandSummary.now}</dd></div>
          <div><dt>Next</dt><dd>{commandSummary.next}</dd></div>
          <div><dt>Later</dt><dd>{commandSummary.later}</dd></div>
          <div><dt>Document</dt><dd>{commandSummary.document}</dd></div>
        </dl>
      </div>
      <div className="dp-command-metrics" aria-label="DayPilot operating signals">
        <span><strong>{runningAgents}</strong> AI running</span>
        <span><strong>{approvals}</strong> blocker needs approval</span>
        <span><strong>{projects.length}</strong> active projects</span>
        <span><strong>{attentionProjects}</strong> need attention</span>
      </div>
      <div className="dp-brief-actions">
        <button className="dp-send-button" type="button" onClick={onFocus}>Start Focus Mode</button>
        <button className="dp-ghost-button" type="button" onClick={onReviewAi}>Review AI Work</button>
        <button className="dp-ghost-button" type="button" onClick={onAdjust}>Adjust Plan</button>
      </div>
    </section>
  )
}

function ChatFeed({ messages }: { messages: DayPilotMessage[] }) {
  return (
    <div className="dp-feed" aria-label="Strategic feed">
      {messages.map((message) => (
        <article key={message.id} className={cx('dp-message', message.role === 'commander' && 'dp-message--commander')}>
          <div className="dp-message__label">{message.role === 'commander' ? 'You' : 'DayPilot'} · {message.createdAt}</div>
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
            placeholder="Continue yesterday, focus a client project, ask GitPilot, check Matrix Designer…"
            aria-label="Command DayPilot"
          />
          <button className="dp-send-button" type="submit">Send</button>
        </form>
      </div>
    </section>
  )
}

function PlanBlock({ task, selected, onSelect }: { task: DayPilotTask; selected: boolean; onSelect: () => void }) {
  return (
    <button type="button" className={cx('dp-strategy-block', selected && 'is-selected')} onClick={onSelect}>
      <div className="dp-time">{task.start}–{task.end} · {task.status.replace('_', ' ')}</div>
      <div className="dp-title">{task.title}</div>
      <div className="dp-meta-row">
        <span className={cx('dp-tag', ownerClass(task.owner))}>{ownerLabel(task)}</span>
        <span>{task.source}</span>
        <span>{task.confidence ?? 80}%</span>
      </div>
    </button>
  )
}

function TodayPlan({ tasks, selectedTaskId, onSelect }: {
  tasks: DayPilotTask[]
  selectedTaskId?: string
  onSelect: (task: DayPilotTask) => void
}) {
  const today = tasks.filter((task) => task.day === 'Thursday')

  return (
    <aside className="dp-strategy" aria-label="Today's plan">
      <div className="dp-section-head">
        <h3>Today’s Plan</h3>
        <span>Plan + execute + monitor</span>
      </div>
      <div className="dp-strategy-list">
        {today.map((task) => (
          <PlanBlock key={task.id} task={task} selected={selectedTaskId === task.id} onSelect={() => onSelect(task)} />
        ))}
      </div>
    </aside>
  )
}

function LiveContext({ projects, agents }: { projects: DayPilotProject[]; agents: DayPilotAgent[] }) {
  const approvalAgents = agents.filter((agent) => agent.status === 'Needs Approval' || agent.status === 'Blocked')
  const attentionProjects = projects.filter((project) => project.risk !== 'low')

  return (
    <aside className="dp-live" aria-label="Live context">
      <div className="dp-section-head">
        <h3>Now / Blocked</h3>
        <span>Ollabridge Live</span>
      </div>
      <div className="dp-live-list">
        <div className="dp-mini-card"><b>What should I do now?</b><span>{commandSummary.now}</span></div>
        <div className="dp-mini-card"><b>What is AI doing?</b><span>{agents.filter((agent) => agent.status === 'Running').length} workflows running in background.</span></div>
        <div className="dp-mini-card"><b>Needs approval</b><span>{approvalAgents.map((agent) => agent.name).join(', ') || 'No approvals pending.'}</span></div>
        <div className="dp-mini-card"><b>Project attention</b><span>{attentionProjects.map((project) => project.name).join(', ')}</span></div>
      </div>
    </aside>
  )
}

function DayCalendar({ tasks, onSelect }: { tasks: DayPilotTask[]; onSelect: (task: DayPilotTask) => void }) {
  return (
    <div className="dp-day-grid">
      {dayHours.map((hour) => {
        const hourTasks = tasks.filter((task) => task.start.startsWith(hour))
        return (
          <div className="dp-time-row" key={hour}>
            <div className="dp-time-label">{hour}</div>
            <div className="dp-time-cell">
              {hourTasks.length === 0 ? <div className="dp-empty">quiet buffer</div> : hourTasks.map((task) => (
                <button key={task.id} type="button" className={cx('dp-calendar-card', `dp-calendar-card--${task.owner}`)} onClick={() => onSelect(task)}>
                  <div className="dp-title">{task.title}</div>
                  <div className="dp-meta-row">
                    <span>{ownerLabel(task)}</span>
                    <span>{task.source}</span>
                    <span>{task.status.replace('_', ' ')}</span>
                    <span>{task.risk} risk</span>
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
      {weekDays.map((day) => <div key={day} className="dp-week-head"><strong>{day.slice(0, 3)}</strong><span>Active</span></div>)}
      {weekSlots.map((slot) => (
        <React.Fragment key={slot}>
          <div className="dp-week-time">{slot}</div>
          {weekDays.map((day) => (
            <div key={`${day}-${slot}`} className="dp-week-cell">
              {tasks.filter((task) => task.day === day && taskHour(task) === slot.slice(0, 2)).map((task) => (
                <button key={task.id} type="button" className={cx('dp-week-chip', `dp-week-chip--${task.owner}`)} onClick={() => onSelect(task)}>
                  {task.title}
                </button>
              ))}
            </div>
          ))}
        </React.Fragment>
      ))}
    </div>
  )
}

function CalendarCore({ tasks, onSelect }: { tasks: DayPilotTask[]; onSelect: (task: DayPilotTask) => void }) {
  const [mode, setMode] = useState<CalendarMode>('day')
  const todayTasks = useMemo(() => tasks.filter((task) => task.day === 'Thursday'), [tasks])

  return (
    <section className="dp-calendar-screen">
      <div className="dp-calendar-controls">
        <div>
          <h3>Minute-by-Minute AI Plan</h3>
          <p>Each block shows owner, source, status, and drawer actions.</p>
        </div>
        <div className="dp-calendar-toggle" role="tablist" aria-label="Calendar horizon">
          <button type="button" className={cx(mode === 'day' && 'is-active')} onClick={() => setMode('day')}>Day</button>
          <button type="button" className={cx(mode === 'week' && 'is-active')} onClick={() => setMode('week')}>Week</button>
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
        <span className={cx('dp-tag', ownerClass(task.owner))}>{ownerLabel(task)}</span>
        <span className={cx('dp-tag', priorityClass(task))}>{task.status.replace('_', ' ').toUpperCase()}</span>
        <span>{task.executor}</span>
      </div>
      <p>{task.context}</p>
    </article>
  )
}

function OperationalLedger({ tasks, onSelect }: { tasks: DayPilotTask[]; onSelect: (task: DayPilotTask) => void }) {
  const myTasks = tasks.filter((task) => task.owner === 'you' || task.owner === 'team')
  const aiTasks = tasks.filter((task) => task.owner === 'ai' || task.owner === 'system')

  return (
    <section className="dp-tasks-screen">
      <div className="dp-calendar-controls">
        <div>
          <h3>You vs AI</h3>
          <p>My Tasks are manual commitments. AI Tasks are things DayPilot is doing for you.</p>
        </div>
        <span className="dp-pill">OWNER CLARITY</span>
      </div>
      <div className="dp-ledger">
        <div className="dp-ledger-column">
          <div className="dp-ledger-head"><h3>My Tasks</h3><p>Things you must do manually.</p></div>
          <div className="dp-ledger-list">{myTasks.map((task) => <LedgerCard key={task.id} task={task} onSelect={() => onSelect(task)} />)}</div>
        </div>
        <div className="dp-ledger-column">
          <div className="dp-ledger-head"><h3>AI Tasks</h3><p>Things DayPilot is doing for you.</p></div>
          <div className="dp-ledger-list">{aiTasks.map((task) => <LedgerCard key={task.id} task={task} onSelect={() => onSelect(task)} />)}</div>
        </div>
      </div>
    </section>
  )
}

function ProjectsCore({ projects, documents, onSelect }: {
  projects: DayPilotProject[]
  documents: DayPilotDocument[]
  onSelect: (project: DayPilotProject) => void
}) {
  return (
    <section className="dp-projects-screen">
      <div className="dp-calendar-controls">
        <div>
          <h3>Projects</h3>
          <p>Continue consulting and internal work without losing yesterday’s context.</p>
        </div>
        <span className="dp-pill">CONTINUE WORK</span>
      </div>
      <div className="dp-project-grid">
        {projects.map((project) => (
          <button key={project.id} type="button" className="dp-project-card" onClick={() => onSelect(project)}>
            <div className="dp-project-top">
              <h3>{project.name}</h3>
              <span className={cx('dp-tag', riskClass(project.risk))}>{project.status}</span>
            </div>
            <div className="dp-progress"><span style={{ width: `${project.progress}%` }} /></div>
            <div className="dp-meta-row"><span>{project.progress}%</span><span>{project.aiActivity}</span><span>{project.continueAction}</span></div>
            <p>{project.nextHumanAction}</p>
            <div className="dp-project-documents">
              {documents.filter((document) => document.projectId === project.id).slice(0, 3).map((document) => <span key={document.id}>{document.name}</span>)}
            </div>
          </button>
        ))}
      </div>
    </section>
  )
}


function DocumentsCore({ sources, documents, onSelect }: {
  sources: DayPilotDocumentSource[]
  documents: DayPilotDocument[]
  onSelect: (document: DayPilotDocument) => void
}) {
  const todayDocuments = documents.filter((document) => document.status === 'Linked to Today' || document.status === 'Changed Since Last Review')
  const needsReview = documents.filter((document) => document.status === 'Needs Permission' || document.status === 'Changed Since Last Review')

  return (
    <section className="dp-documents-screen">
      <div className="dp-calendar-controls">
        <div>
          <h3>My Documents</h3>
          <p>AI-powered file command center organized by source, project, time, and relevance.</p>
        </div>
        <div className="dp-document-search" aria-label="Search documents">Search documents…</div>
      </div>
      <div className="dp-documents-layout">
        <aside className="dp-document-sources" aria-label="Document sources">
          <div className="dp-ledger-head"><h3>Sources</h3><p>Default is read + index only. No overwrite or external sharing.</p></div>
          {sources.map((source) => (
            <article key={source.id} className={cx('dp-source-card', !source.allowed && 'is-blocked')}>
              <div className="dp-title">{source.allowed ? '○' : '✕'} {source.label}</div>
              <div className="dp-meta-row"><span>{source.kind}</span><span>{source.permission}</span></div>
              <p>{source.children.join(' · ')}</p>
            </article>
          ))}
        </aside>

        <section className="dp-document-workspace" aria-label="Smart document workspace">
          <div className="dp-document-section-head"><h3>Today’s Documents</h3><span>{todayDocuments.length} linked</span></div>
          <div className="dp-document-list">
            {documents.map((document) => (
              <button key={document.id} type="button" className="dp-document-card" onClick={() => onSelect(document)}>
                <div className="dp-project-top">
                  <h3>{document.name}</h3>
                  <span className={cx('dp-tag', document.status === 'Needs Permission' ? 'dp-tag--critical' : document.status === 'Changed Since Last Review' ? 'dp-tag--high' : 'dp-tag--agent')}>{document.status}</span>
                </div>
                <div className="dp-meta-row"><span>{document.fileType}</span><span>{document.projectName}</span><span>{document.updated}</span></div>
                <p>Used in: {document.usedIn}</p>
                <p>AI status: {document.aiReadableState}</p>
                <div className="dp-document-actions"><span>Chat</span><span>Summarize</span><span>Create Tasks</span><span>Open</span></div>
              </button>
            ))}
          </div>
        </section>

        <aside className="dp-document-assistant" aria-label="Document AI assistant">
          <div className="dp-ledger-head"><h3>Document AI</h3><p>Ask about selected files, a project folder, or today’s context.</p></div>
          <div className="dp-assistant-prompts">
            <button type="button">Summarize the client contract.</button>
            <button type="button">Find the latest budget Excel for Project Alpha.</button>
            <button type="button">Compare this proposal with the previous version.</button>
            <button type="button">Which document should I review before my 14:00 meeting?</button>
          </div>
          <div className="dp-mini-card"><b>Needs review</b><span>{needsReview.map((document) => document.name).join(', ')}</span></div>
          <div className="dp-mini-card"><b>Today context</b><span>Calendar • Email • Projects • GitPilot • Matrix Designer</span></div>
        </aside>
      </div>
    </section>
  )
}

function AgentsCore({ agents, onSelect }: { agents: DayPilotAgent[]; onSelect: (agent: DayPilotAgent) => void }) {
  return (
    <section className="dp-projects-screen">
      <div className="dp-calendar-controls">
        <div>
          <h3>AI Workforce</h3>
          <p>Running, Needs Approval, or Blocked. Everything else stays in the drawer.</p>
        </div>
        <span className="dp-pill">OLLĀBRIDGE · LOCAL</span>
      </div>
      <div className="dp-agent-table">
        {agents.map((agent) => (
          <button key={agent.id} type="button" className="dp-agent-row" onClick={() => onSelect(agent)}>
            <span>{agent.name}</span>
            <span>{agent.currentWork}</span>
            <span className={cx('dp-tag', agent.status === 'Blocked' ? 'dp-tag--critical' : agent.status === 'Needs Approval' ? 'dp-tag--high' : 'dp-tag--agent')}>{agent.status}</span>
            <span>{agent.provider}</span>
          </button>
        ))}
      </div>
    </section>
  )
}

function DetailDrawer({ selected, documents, onClose }: { selected?: DrawerItem; documents: DayPilotDocument[]; onClose: () => void }) {
  const title = selected?.item && ('title' in selected.item ? selected.item.title : selected.item.name)

  return (
    <>
      <div className={cx('dp-drawer-backdrop', selected && 'is-open')} onClick={onClose} />
      <aside className={cx('dp-drawer', selected && 'is-open')} aria-hidden={!selected} aria-label="Context detail drawer">
        <div className="dp-drawer-head">
          <div><div className="dp-eyebrow">Context Drawer</div><h3>{title ?? 'No item selected'}</h3></div>
          <button type="button" className="dp-icon-button" onClick={onClose} aria-label="Close detail drawer">×</button>
        </div>

        {selected?.kind === 'task' && (
          <>
            <div className="dp-drawer-section"><h4>Why is this scheduled?</h4><p>{selected.item.context}</p></div>
            <div className="dp-drawer-section"><h4>Source / owner / status</h4><p>{selected.item.source} · {ownerLabel(selected.item)} · {selected.item.status.replace('_', ' ')}</p></div>
            <div className="dp-drawer-section"><h4>Action</h4><p>{selected.item.nextAction}</p></div>
            <div className="dp-drawer-section"><h4>AI in parallel</h4><p>{selected.item.parallelAi}</p></div>
            <div className="dp-drawer-section"><h4>If skipped</h4><p>{selected.item.skipImpact}</p></div>
          </>
        )}

        {selected?.kind === 'project' && (
          <>
            <div className="dp-drawer-section"><h4>What was done yesterday</h4><p>{selected.item.yesterday.join(' • ')}</p></div>
            <div className="dp-drawer-section"><h4>What needs to be done today</h4><p>{selected.item.today.join(' • ')}</p></div>
            <div className="dp-drawer-section"><h4>What AI is doing</h4><p>{selected.item.aiActions.join(' • ')}</p></div>
            <div className="dp-drawer-section"><h4>Files / branches / emails linked</h4><p>{selected.item.linkedSources.join(' • ')}</p></div>
            <div className="dp-drawer-section"><h4>Blocked</h4><p>{selected.item.blocked.length ? selected.item.blocked.join(' • ') : 'No blockers.'}</p></div>
            <div className="dp-drawer-section"><h4>Documents</h4><p>{documents.filter((document) => document.projectId === selected.item.id).map((document) => document.name).join(' • ') || 'No linked documents yet.'}</p></div>
            <div className="dp-drawer-section"><h4>Next recommended action</h4><p>{selected.item.nextHumanAction}</p></div>
          </>
        )}

        {selected?.kind === 'document' && (
          <>
            <div className="dp-drawer-section"><h4>Why is this file relevant today?</h4><p>{selected.item.relevance}</p></div>
            <div className="dp-drawer-section"><h4>Project / meeting</h4><p>{selected.item.projectName} · {selected.item.usedIn}</p></div>
            <div className="dp-drawer-section"><h4>What changed?</h4><p>{selected.item.changed.join(' • ')}</p></div>
            <div className="dp-drawer-section"><h4>What should I do?</h4><p>{selected.item.suggestedActions.join(' • ')}</p></div>
            <div className="dp-drawer-section"><h4>Safety</h4><p>{selected.item.aiReadableState} Original preserved: {selected.item.originalPreserved ? 'yes' : 'no'}.</p></div>
          </>
        )}

        {selected?.kind === 'agent' && (
          <>
            <div className="dp-drawer-section"><h4>Provider</h4><p>{selected.item.provider}: Live · Model: {selected.item.model} · Mode: {selected.item.mode} · Latency: {selected.item.latencyMs}ms</p></div>
            <div className="dp-drawer-section"><h4>Current work</h4><p>{selected.item.currentWork} · {selected.item.status}</p></div>
            <div className="dp-drawer-section"><h4>Detail</h4><p>{selected.item.detail}</p></div>
          </>
        )}
      </aside>
    </>
  )
}

export function SpaceBridgeShell({ compact = false }: SpaceBridgeShellProps) {
  const [view, setView] = useState<PortalView>('command')
  const [messages, setMessages] = useState<DayPilotMessage[]>(initialMessages)
  const [tasks, setTasks] = useState<DayPilotTask[]>(initialTasks)
  const [selected, setSelected] = useState<DrawerItem | undefined>()
  const selectedTaskId = selected?.kind === 'task' ? selected.item.id : undefined

  function addDirective(directive: string) {
    const humanTask = createHumanTask(directive)
    const aiTask = createAiTask(directive)
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

    setMessages((current) => [
      ...current,
      { id: `msg-user-${Date.now()}`, role: 'commander', body: directive, createdAt: timestamp },
      {
        id: `msg-ai-${Date.now()}`,
        role: 'assistant',
        createdAt: timestamp,
        body: 'Plan updated. I scheduled the work block, started AI preparation, refreshed project context, and kept approval-gated actions in the drawer.',
      },
    ])
    setTasks((current) => [humanTask, aiTask, ...current])
    setSelected({ kind: 'task', item: humanTask })
  }

  function startFocusMode() {
    const focusTask = tasks.find((task) => task.title.includes('Deep Coding')) ?? tasks[0]
    setSelected({ kind: 'task', item: focusTask })
  }

  return (
    <div className={cx('dp-shell', compact && 'dp-shell--compact')}>
      <aside className="dp-rail">
        <div className="dp-identity">
          <div className="dp-eyebrow">DayPilot Pro</div>
          <h1>Enterprise OS</h1>
          <div className="dp-status-line">● OLLABRIDGE LIVE · LOCAL MODE</div>
        </div>
        <nav className="dp-nav" aria-label="DayPilot views">
          <NavButton active={view === 'command'} onClick={() => setView('command')}>Command</NavButton>
          <NavButton active={view === 'calendar'} onClick={() => setView('calendar')}>Calendar</NavButton>
          <NavButton active={view === 'tasks'} onClick={() => setView('tasks')}>Tasks</NavButton>
          <NavButton active={view === 'projects'} onClick={() => setView('projects')}>Projects</NavButton>
          <NavButton active={view === 'documents'} onClick={() => setView('documents')}>Documents</NavButton>
          <NavButton active={view === 'agents'} onClick={() => setView('agents')}>Agents</NavButton>
        </nav>
        <div className="dp-more">More: Inbox · GitPilot · Settings</div>
      </aside>

      <main className="dp-core">
        <header className="dp-topbar">
          <div>
            <h2>{view === 'command' ? 'Daily Control Center' : view === 'calendar' ? 'Minute Plan' : view === 'tasks' ? 'You vs AI' : view === 'projects' ? 'Project Continuity' : view === 'documents' ? 'My Documents' : 'AI Workflows'}</h2>
            <p>DayPilot = Calendar + Tasks + Projects + Agents + Documents + Natural Tools.</p>
          </div>
          <span className="dp-pill">NOW · DOCUMENTS · AI RUNNING · APPROVALS</span>
        </header>

        <div className="dp-view">
          {view === 'command' && (
            <div className="dp-command-view">
              <MorningCommandCard
                agents={initialAgents}
                projects={initialProjects}
                onFocus={startFocusMode}
                onReviewAi={() => setView('agents')}
                onAdjust={() => addDirective('Adjust today around coding first, admin after lunch, and client follow-up later.')}
              />
              <div className="dp-bridge">
                <StrategicFeed messages={messages} onSubmit={addDirective} />
                <TodayPlan tasks={tasks} selectedTaskId={selectedTaskId} onSelect={(item) => setSelected({ kind: 'task', item })} />
                <LiveContext projects={initialProjects} agents={initialAgents} />
              </div>
            </div>
          )}
          {view === 'calendar' && <CalendarCore tasks={tasks} onSelect={(item) => setSelected({ kind: 'task', item })} />}
          {view === 'tasks' && <OperationalLedger tasks={tasks} onSelect={(item) => setSelected({ kind: 'task', item })} />}
          {view === 'projects' && <ProjectsCore projects={initialProjects} documents={initialDocuments} onSelect={(item) => setSelected({ kind: 'project', item })} />}
          {view === 'documents' && <DocumentsCore sources={documentSources} documents={initialDocuments} onSelect={(item) => setSelected({ kind: 'document', item })} />}
          {view === 'agents' && <AgentsCore agents={initialAgents} onSelect={(item) => setSelected({ kind: 'agent', item })} />}
        </div>
      </main>

      <DetailDrawer selected={selected} documents={initialDocuments} onClose={() => setSelected(undefined)} />
    </div>
  )
}
