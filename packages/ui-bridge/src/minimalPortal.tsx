import React, { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import type { DayPilotAgent, DayPilotDocument, DayPilotDocumentSource, DayPilotMessage, DayPilotProject, DayPilotTask } from '@daypilot/shared-types'
import { MinutePlanCalendar } from './calendar/MinutePlanCalendar'
import { isDemoMode, seedAgents, seedDocumentSources, seedDocuments, seedMessages, seedProjects, seedTasks } from './demoData'
import { askAssistant } from './assistant'
import { initTheme } from './theme'
import { SettingsMenu } from './shell/SettingsMenu'
import { SettingsPanel } from './shell/SettingsPanel'
import { CommandPalette, type PaletteAction } from './shell/CommandPalette'
import { FocusMode } from './shell/FocusMode'
import { PatchReview } from './coding/PatchReview'
import { DesignReview } from './design/DesignReview'
import { EmailWorkspace } from './email/EmailWorkspace'
import { ApprovalCenter } from './approvals/ApprovalCenter'
import { HomeWorkspace } from './home/HomeWorkspace'
import { PlanningWorkspace } from './planning/PlanningWorkspace'
import { OnboardingWizard } from './onboarding/OnboardingWizard'
import { ProjectWizard, type NewProject } from './projects/ProjectWizard'
import {
  AI_PLAN_BULLETS,
  AI_SEED,
  AI_WELCOME,
  CONTINUE_ITEMS,
  HOME_SUGGESTIONS,
  NEXT_PRIORITY,
  TODAY_PLAN,
  aiReply,
  type HomeTurn,
} from './home/homeData'
import type { SettingsSectionId } from './settings/settingsData'

type NavItem = { id: PortalView; label: string; icon: NavIconName }
const NAV_BASE: NavItem[] = [
  { id: 'home', label: 'Home', icon: 'home' },
  { id: 'planning', label: 'Planning', icon: 'planning' },
  { id: 'calendar', label: 'Calendar', icon: 'calendar' },
  { id: 'tasks', label: 'Tasks', icon: 'tasks' },
  { id: 'projects', label: 'Projects', icon: 'projects' },
  { id: 'documents', label: 'Documents', icon: 'documents' },
  { id: 'agents', label: 'Agents', icon: 'agents' },
]
// Email is an optional, feature-flagged tab (placed before Documents); DayPilot
// works without it.
const EMAIL_NAV: NavItem = { id: 'email', label: 'Email', icon: 'email' }
function navViews(emailEnabled: boolean): NavItem[] {
  if (!emailEnabled) return NAV_BASE
  const docsIndex = NAV_BASE.findIndex((n) => n.id === 'documents')
  return [...NAV_BASE.slice(0, docsIndex), EMAIL_NAV, ...NAV_BASE.slice(docsIndex)]
}

type PortalView = 'home' | 'planning' | 'calendar' | 'tasks' | 'projects' | 'documents' | 'agents' | 'email'
type DrawerItem =
  | { kind: 'task'; item: DayPilotTask }
  | { kind: 'project'; item: DayPilotProject }
  | { kind: 'agent'; item: DayPilotAgent }
  | { kind: 'document'; item: DayPilotDocument }

type SpaceBridgeShellProps = {
  compact?: boolean
  /** Optional Email tab. DayPilot works fully without it. */
  emailEnabled?: boolean
  /** Sign out of the DayPilot workspace (separate from disconnecting an AI
   *  provider). Provided by the auth gate; when absent, Sign out opens the
   *  profile settings (local-first default). */
  onSignOut?: () => void
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

type NavIconName = 'home' | 'planning' | 'calendar' | 'tasks' | 'projects' | 'email' | 'documents' | 'agents' | 'settings'

function NavIcon({ name }: { name: NavIconName }) {
  const p: Record<NavIconName, React.ReactNode> = {
    home: <path d="M3 10.5 12 3l9 7.5M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5" />,
    planning: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3.5 2" /></>,
    calendar: <><rect x="3.5" y="4.5" width="17" height="16" rx="2" /><path d="M3.5 9h17M8 3v3M16 3v3" /></>,
    tasks: <><circle cx="12" cy="12" r="9" /><path d="m8.5 12 2.4 2.4L16 9.5" /></>,
    projects: <><rect x="3.5" y="4.5" width="17" height="15" rx="2" /><path d="M3.5 9.5h17M9 4.5v15" /></>,
    email: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m4 6.5 8 6 8-6" /></>,
    documents: <><path d="M6 3h7l5 5v11a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" /><path d="M13 3v5h5M8.5 13h7M8.5 16.5h7" /></>,
    agents: <><circle cx="12" cy="8" r="3.2" /><path d="M5 20c0-3.5 3.1-5.5 7-5.5s7 2 7 5.5" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 13.5a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2v.1a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-2.9-1.2l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0-1.2-2.9H4a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.2-2.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 2.9-1.2V4a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 2.9 1.2l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9Z" /></>,
  }
  return (
    <svg className="dp-nav__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {p[name]}
    </svg>
  )
}

function NavButton({ active, icon, children, onClick }: { active: boolean; icon?: NavIconName; children: React.ReactNode; onClick: () => void }) {
  return (
    <button type="button" className={cx(active && 'is-active')} onClick={onClick}>
      {icon && <NavIcon name={icon} />}
      <span className="dp-nav__label">{children}</span>
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

/** Minute Plan calendar — professional Day + Week timetable with an
 *  Outlook-style live current-time indicator (see calendar/MinutePlanCalendar). */
function CalendarCore({ tasks, onSelect }: { tasks: DayPilotTask[]; onSelect: (task: DayPilotTask) => void }) {
  return <MinutePlanCalendar tasks={tasks} onSelect={onSelect} />
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

function newProjectFrom(np: NewProject): DayPilotProject {
  return {
    id: `proj-${Date.now()}`,
    name: np.name,
    progress: 0,
    status: 'Active',
    aiActivity: 'Ready to start',
    nextHumanAction: np.milestone || np.goal || 'Define the first milestone',
    continueAction: np.goal || 'Kick off the first milestone',
    risk: 'low',
    aiActions: [],
    designerInput: [],
    recentSignals: np.stack ? [`Stack: ${np.stack}`] : [],
    linkedSources: np.repo ? [np.repo] : [],
    yesterday: [],
    today: np.goal ? [np.goal] : [],
    blocked: [],
  }
}

function ProjectsCore({ projects, documents, onSelect, onNew }: {
  projects: DayPilotProject[]
  documents: DayPilotDocument[]
  onSelect: (project: DayPilotProject) => void
  onNew?: () => void
}) {
  return (
    <section className="dp-projects-screen">
      <div className="dp-calendar-controls">
        <div>
          <h3>Projects</h3>
          <p>Continue consulting and internal work without losing yesterday’s context.</p>
        </div>
        {onNew && <button type="button" className="dp-ghost-button" onClick={onNew}>+ New project</button>}
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

export function SpaceBridgeShell({ compact = false, emailEnabled = false, onSignOut }: SpaceBridgeShellProps) {
  const isMobile = useIsMobile()
  // Apply the persisted theme (dark by default) so the shell is consistent even
  // when the host app didn't call initTheme() itself.
  useEffect(() => { initTheme() }, [])
  const NAV_VIEWS = navViews(emailEnabled)
  const [view, setView] = useState<PortalView>('home')
  const [messages, setMessages] = useState<DayPilotMessage[]>(seedMessages)
  const [tasks, setTasks] = useState<DayPilotTask[]>(seedTasks)
  const [projects, setProjects] = useState<DayPilotProject[]>(seedProjects)
  const documents = useMemo(seedDocuments, [])
  const documentSources = useMemo(seedDocumentSources, [])
  const agents = useMemo(seedAgents, [])
  const [projectWizardOpen, setProjectWizardOpen] = useState(false)
  const [selected, setSelected] = useState<DrawerItem | undefined>()
  const [settingsSection, setSettingsSection] = useState<SettingsSectionId | undefined>()
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [focusTask, setFocusTask] = useState<DayPilotTask | undefined>()
  const [patchReviewOpen, setPatchReviewOpen] = useState(false)
  const [designOpen, setDesignOpen] = useState(false)
  const [approvalsOpen, setApprovalsOpen] = useState(false)
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
    const target = tasks.find((task) => task.title.includes('Deep Coding')) ?? tasks[0]
    if (target) setFocusTask(target)
  }

  function exitFocus(outcome: 'done' | 'blocked' | 'hand_to_ai' | 'cancel') {
    if (focusTask && outcome !== 'cancel') {
      const nextStatus = outcome === 'done' ? 'done' : outcome === 'blocked' ? 'blocked' : 'running'
      setTasks((current) =>
        current.map((t) => (t.id === focusTask.id ? { ...t, status: nextStatus } : t)),
      )
    }
    setFocusTask(undefined)
  }

  const paletteActions: PaletteAction[] = useMemo(() => {
    const navActions: PaletteAction[] = NAV_VIEWS.map((nav, index) => ({
      id: `nav-${nav.id}`,
      label: `Go to ${nav.label}`,
      hint: `⌘${index + 1}`,
      keywords: 'navigate view',
      run: () => setView(nav.id),
    }))
    return [
      ...navActions,
      { id: 'new-project', label: 'New project', hint: 'create', keywords: 'add project create new', run: () => setProjectWizardOpen(true) },
      { id: 'focus', label: 'Start Focus Mode', hint: 'F', keywords: 'focus deep work', run: startFocusMode },
      { id: 'review-ai', label: 'Review AI Work', keywords: 'agents approvals', run: () => setView('agents') },
      { id: 'approvals', label: 'Approval Center', hint: 'approvals', keywords: 'approve reject sensitive actions queue', run: () => setApprovalsOpen(true) },
      { id: 'patch-review', label: 'Review AI Patches · GitPilot', hint: 'coding', keywords: 'gitpilot diff patch code', run: () => setPatchReviewOpen(true) },
      { id: 'matrix-designer', label: 'Matrix Designer · Batch Roadmap', hint: 'design', keywords: 'design bundle review planner batches', run: () => setDesignOpen(true) },
      { id: 'settings', label: 'Open Settings', hint: '⌘,', keywords: 'preferences', run: () => setSettingsSection('profile') },
      { id: 'providers', label: 'AI Providers · Ollabridge', keywords: 'model health routing', run: () => setSettingsSection('providers') },
      { id: 'integrations', label: 'Integrations · GitPilot · Matrix Designer', keywords: 'connect', run: () => setSettingsSection('integrations') },
    ]
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tasks])

  // Global keyboard shortcuts: ⌘K palette, ⌘, settings, F focus, ⌘1–6 nav.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const meta = event.metaKey || event.ctrlKey
      const target = event.target as HTMLElement | null
      const typing = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')
      if (meta && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setPaletteOpen((open) => !open)
        return
      }
      if (meta && event.key === ',') {
        event.preventDefault()
        setSettingsSection('profile')
        return
      }
      if (meta && /^[1-6]$/.test(event.key)) {
        event.preventDefault()
        setView(NAV_VIEWS[Number(event.key) - 1].id)
        return
      }
      if (!meta && !typing && event.key.toLowerCase() === 'f') {
        startFocusMode()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tasks])

  // Phones get a dedicated ChatGPT-style shell (hamburger drawer, single-page
  // views, full-screen AI) rather than a squeezed desktop layout.
  if (isMobile) return <MobilePortal emailEnabled={emailEnabled} />

  return (
    <div className={cx('dp-shell', compact && 'dp-shell--compact')}>
      <aside className="dp-rail">
        <div className="dp-brand">
          <svg className="dp-brand__mark" viewBox="0 0 32 32" fill="none" aria-hidden="true">
            <path d="M16 3.5 28.5 28 16 22.2 3.5 28Z" fill="currentColor" opacity="0.5" />
            <path d="M16 3.5 28.5 28 16 22.2Z" fill="currentColor" />
          </svg>
          <span className="dp-brand__word">DayPilot</span>
          {isDemoMode() && <span className="dp-demo-badge" title="Showing sample data. Set VITE_DAYPILOT_DEMO_MODE=false for a clean, real-data workspace.">Demo mode</span>}
        </div>
        <nav className="dp-nav" aria-label="DayPilot views">
          {NAV_VIEWS.map((nav) => (
            <NavButton key={nav.id} active={view === nav.id} icon={nav.icon} onClick={() => setView(nav.id)}>
              {nav.label}
            </NavButton>
          ))}
        </nav>
        <div className="dp-rail-spacer" />
        <nav className="dp-nav dp-nav--secondary" aria-label="Settings">
          <NavButton active={false} icon="settings" onClick={() => setSettingsSection('profile')}>Settings</NavButton>
        </nav>
        <SettingsMenu
          workspaceName="Product Lead"
          onOpenSection={(section) => setSettingsSection(section)}
          onSignOut={() => (onSignOut ? onSignOut() : setSettingsSection('profile'))}
        />
      </aside>

      <main className="dp-core">
        {view === 'home' ? (
          <HomeWorkspace
            onStartFocus={startFocusMode}
            onNavigate={(target) => setView(target)}
            onOpenPalette={() => setPaletteOpen(true)}
            onOpenProjectWizard={() => setProjectWizardOpen(true)}
            onOpenApprovals={() => setApprovalsOpen(true)}
          />
        ) : (
          <>
            <header className="dp-topbar">
              <div>
                <h2>{view === 'planning' ? 'Day Planner' : view === 'calendar' ? 'Minute Plan' : view === 'tasks' ? 'You vs AI' : view === 'projects' ? 'Project Continuity' : view === 'documents' ? 'My Documents' : view === 'email' ? 'Email' : 'AI Workflows'}</h2>
                <p>DayPilot = Calendar + Tasks + Projects + Agents + Documents + Natural Tools.</p>
              </div>
              <span className="dp-pill">NOW · DOCUMENTS · AI RUNNING · APPROVALS</span>
            </header>

            <div className="dp-view">
              {view === 'planning' && <PlanningWorkspace onStartFocus={startFocusMode} />}
              {view === 'calendar' && <CalendarCore tasks={tasks} onSelect={(item) => setSelected({ kind: 'task', item })} />}
              {view === 'tasks' && <OperationalLedger tasks={tasks} onSelect={(item) => setSelected({ kind: 'task', item })} />}
              {view === 'projects' && <ProjectsCore projects={projects} documents={documents} onSelect={(item) => setSelected({ kind: 'project', item })} onNew={() => setProjectWizardOpen(true)} />}
              {view === 'documents' && <DocumentsCore sources={documentSources} documents={documents} onSelect={(item) => setSelected({ kind: 'document', item })} />}
              {view === 'agents' && <AgentsCore agents={agents} onSelect={(item) => setSelected({ kind: 'agent', item })} />}
              {view === 'email' && <EmailWorkspace />}
            </div>
          </>
        )}
      </main>

      <DetailDrawer selected={selected} documents={documents} onClose={() => setSelected(undefined)} />

      <CommandPalette open={paletteOpen} actions={paletteActions} onClose={() => setPaletteOpen(false)} />
      {settingsSection && (
        <SettingsPanel section={settingsSection} onClose={() => setSettingsSection(undefined)} />
      )}
      {focusTask && <FocusMode task={focusTask} onExit={exitFocus} />}
      {patchReviewOpen && <PatchReview onClose={() => setPatchReviewOpen(false)} />}
      {designOpen && <DesignReview onClose={() => setDesignOpen(false)} />}
      {approvalsOpen && <ApprovalCenter onClose={() => setApprovalsOpen(false)} />}
      <ProjectWizard
        open={projectWizardOpen}
        onClose={() => setProjectWizardOpen(false)}
        onCreate={(np) => { const p = newProjectFrom(np); setProjects((cur) => [p, ...cur]); setView('projects'); setSelected({ kind: 'project', item: p }) }}
      />
      <OnboardingWizard />
    </div>
  )
}

/* ============================================================
   Mobile shell — a ChatGPT-style phone experience: a fixed top
   app bar (hamburger · title · sparkle), an off-canvas navigation
   drawer, single-page vertical views, and a full-screen AI chat.
   ============================================================ */

function useIsMobile(breakpoint = 767): boolean {
  const query = `(max-width: ${breakpoint}px)`
  const [matches, setMatches] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(query).matches,
  )
  useEffect(() => {
    if (typeof window === 'undefined') return
    const mq = window.matchMedia(query)
    const onChange = () => setMatches(mq.matches)
    onChange()
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [query])
  return matches
}

const MOBILE_TITLES: Record<PortalView, string> = {
  home: 'Home',
  planning: 'Planning',
  calendar: 'Calendar',
  tasks: 'Tasks',
  projects: 'Projects',
  email: 'Email',
  documents: 'Documents',
  agents: 'Agents',
}

const RECENT_AI = isDemoMode() ? ['Email workspace status', 'Prepare Client Alpha meeting', "Today's plan"] : []

function MobilePortal({ emailEnabled }: { emailEnabled: boolean }) {
  const NAV = navViews(emailEnabled)
  const [view, setView] = useState<PortalView>('home')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [aiOpen, setAiOpen] = useState(false)
  const [aiSeed, setAiSeed] = useState<string | undefined>()
  const [tasks] = useState<DayPilotTask[]>(seedTasks)
  const [projects, setProjects] = useState<DayPilotProject[]>(seedProjects)
  const documents = useMemo(seedDocuments, [])
  const documentSources = useMemo(seedDocumentSources, [])
  const agents = useMemo(seedAgents, [])
  const [projectWizardOpen, setProjectWizardOpen] = useState(false)
  const [selected, setSelected] = useState<DrawerItem | undefined>()
  const [settingsSection, setSettingsSection] = useState<SettingsSectionId | undefined>()
  const [focusTask, setFocusTask] = useState<DayPilotTask | undefined>()

  // Escape closes the top-most overlay.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== 'Escape') return
      if (aiOpen) setAiOpen(false)
      else if (drawerOpen) setDrawerOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [aiOpen, drawerOpen])

  // Lock body scroll while the drawer or AI is open.
  useEffect(() => {
    const locked = drawerOpen || aiOpen
    const prev = document.body.style.overflow
    if (locked) document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [drawerOpen, aiOpen])

  function go(target: PortalView) {
    setView(target)
    setDrawerOpen(false)
  }
  function openAi(seed?: string) {
    setAiSeed(seed)
    setAiOpen(true)
    setDrawerOpen(false)
  }
  function startFocus() {
    const target = tasks.find((t) => t.title.includes('Deep Coding')) ?? tasks[0]
    if (target) setFocusTask(target)
  }

  return (
    <div className="dp-m">
      <header className="dp-m__bar">
        <button className="dp-m__iconbtn" aria-label="Open menu" onClick={() => setDrawerOpen(true)}>
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <path d="M4 7h16M4 12h16M4 17h16" />
          </svg>
        </button>
        <h1 className="dp-m__title">{MOBILE_TITLES[view]}</h1>
        <button className="dp-m__spark" aria-label="Open AI Assistant" onClick={() => openAi()}>
          <span aria-hidden="true">✦</span>
        </button>
      </header>

      <main className="dp-m__main">
        {view === 'home' && <MobileHome onStartFocus={startFocus} onNavigate={go} onAsk={openAi} />}
        {view === 'planning' && <PlanningWorkspace onStartFocus={startFocus} />}
        {view === 'calendar' && <CalendarCore tasks={tasks} onSelect={(item) => setSelected({ kind: 'task', item })} />}
        {view === 'tasks' && <OperationalLedger tasks={tasks} onSelect={(item) => setSelected({ kind: 'task', item })} />}
        {view === 'projects' && <ProjectsCore projects={projects} documents={documents} onSelect={(item) => setSelected({ kind: 'project', item })} onNew={() => setProjectWizardOpen(true)} />}
        {view === 'documents' && <DocumentsCore sources={documentSources} documents={documents} onSelect={(item) => setSelected({ kind: 'document', item })} />}
        {view === 'agents' && <AgentsCore agents={agents} onSelect={(item) => setSelected({ kind: 'agent', item })} />}
        {view === 'email' && <EmailWorkspace />}
      </main>

      {/* Off-canvas navigation drawer */}
      {drawerOpen && (
        <>
          <div className="dp-m__scrim" onClick={() => setDrawerOpen(false)} aria-hidden="true" />
          <nav className="dp-m__drawer" aria-label="Navigation">
            <div className="dp-m__drawer-brand">
              <svg className="dp-brand__mark" viewBox="0 0 32 32" fill="none" aria-hidden="true">
                <path d="M16 3.5 28.5 28 16 22.2 3.5 28Z" fill="currentColor" opacity="0.5" />
                <path d="M16 3.5 28.5 28 16 22.2Z" fill="currentColor" />
              </svg>
              <span className="dp-brand__word">DayPilot</span>
            </div>
            <div className="dp-m__drawer-nav">
              {NAV.map((nav) => (
                <button key={nav.id} className={'dp-m__navitem' + (view === nav.id ? ' is-active' : '')} onClick={() => go(nav.id)}>
                  <NavIcon name={nav.icon} />
                  <span>{nav.label}</span>
                </button>
              ))}
            </div>
            <div className="dp-m__drawer-section">Recent AI conversations</div>
            <div className="dp-m__drawer-nav">
              {RECENT_AI.length === 0 && <p className="dp-m__recent-empty">No conversations yet. Ask the assistant anything to get started.</p>}
              {RECENT_AI.map((c) => (
                <button key={c} className="dp-m__recent" onClick={() => openAi(c)}>
                  <span className="dp-m__recent-spark" aria-hidden="true">✦</span>
                  <span className="dp-m__recent-text">{c}</span>
                </button>
              ))}
            </div>
            <div className="dp-m__drawer-foot">
              <button className="dp-m__navitem" onClick={() => { setProjectWizardOpen(true); setDrawerOpen(false) }}>
                <NavIcon name="projects" />
                <span>New project</span>
              </button>
              <button className="dp-m__navitem" onClick={() => { setSettingsSection('profile'); setDrawerOpen(false) }}>
                <NavIcon name="settings" />
                <span>Settings</span>
              </button>
              <button className="dp-m__profile" onClick={() => { setSettingsSection('profile'); setDrawerOpen(false) }}>
                <span className="dp-m__avatar" aria-hidden="true">RM</span>
                <span className="dp-m__profile-text">
                  <span className="dp-m__profile-name">Ruslan M.</span>
                  <span className="dp-m__profile-role">Product Lead</span>
                </span>
              </button>
            </div>
          </nav>
        </>
      )}

      {/* Full-screen AI conversation */}
      {aiOpen && <MobileAI seed={aiSeed} onClose={() => setAiOpen(false)} onNavigate={go} />}

      <DetailDrawer selected={selected} documents={documents} onClose={() => setSelected(undefined)} />
      {settingsSection && <SettingsPanel section={settingsSection} onClose={() => setSettingsSection(undefined)} />}
      {focusTask && <FocusMode task={focusTask} onExit={() => setFocusTask(undefined)} />}
      <ProjectWizard
        open={projectWizardOpen}
        onClose={() => setProjectWizardOpen(false)}
        onCreate={(np) => { const p = newProjectFrom(np); setProjects((cur) => [p, ...cur]); go('projects'); setSelected({ kind: 'project', item: p }) }}
      />
      <OnboardingWizard />
    </div>
  )
}

function MobileHome({ onStartFocus, onNavigate, onAsk }: {
  onStartFocus: () => void
  onNavigate: (view: PortalView) => void
  onAsk: (seed?: string) => void
}) {
  return (
    <div className="dp-m__page">
      <section className="dp-m__ready">
        <h2 className="dp-m__ready-title"><span className="dp-m__ready-icon" aria-hidden="true">☼</span> {NEXT_PRIORITY ? 'Your day is ready' : 'Ready when you are'}</h2>
        <p className="dp-m__ready-sub">{NEXT_PRIORITY ? 'Focus on your top priority and keep the momentum.' : 'No plan yet for today. Ask the assistant to generate one.'}</p>
      </section>

      {NEXT_PRIORITY && (
        <section className="dp-m__card">
          <div className="dp-m__label">Next priority</div>
          <div className="dp-m__np">
            <span className="dp-m__np-icon" aria-hidden="true">🖥</span>
            <div className="dp-m__np-body">
              <div className="dp-m__np-title">{NEXT_PRIORITY.title}</div>
              <div className="dp-m__np-meta"><span>🗓 {NEXT_PRIORITY.time}</span><span className="dp-m__dot">·</span><span className="dp-chip">{NEXT_PRIORITY.project}</span></div>
            </div>
          </div>
          <p className="dp-m__np-support">{NEXT_PRIORITY.support}</p>
          <button className="dp-m__cta" onClick={onStartFocus}>▶ Start focus</button>
          <button className="dp-m__ghostlink" onClick={() => onNavigate('projects')}>View project ↗</button>
        </section>
      )}

      <section className="dp-m__card">
        <h3 className="dp-m__card-title"><span aria-hidden="true">🗓</span> Today's plan</h3>
        {TODAY_PLAN.length > 0 ? (
          <ul className="dp-m__agenda">
            {TODAY_PLAN.map((item) => (
              <li key={item.time} className="dp-m__agenda-row" onClick={() => onNavigate('planning')}>
                <span className="dp-m__agenda-dot" aria-hidden="true" />
                <span className="dp-m__agenda-time">{item.time}</span>
                <span className="dp-m__agenda-title">{item.title}</span>
                <span className="dp-m__agenda-tag">{item.tag}</span>
                <span className="dp-m__agenda-chev" aria-hidden="true">›</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="dp-m__card-empty">No blocks scheduled yet. Ask the assistant to generate a plan.</p>
        )}
        <button className="dp-m__more" onClick={() => onNavigate('planning')}>Open planner →</button>
      </section>

      <section className="dp-m__card">
        <h3 className="dp-m__card-title"><span aria-hidden="true">⟳</span> Continue from yesterday</h3>
        <div className="dp-m__continue">
          {CONTINUE_ITEMS.length === 0 && <p className="dp-m__card-empty">Nothing carried over yet.</p>}
          {CONTINUE_ITEMS.map((c) => (
            <button key={c.id} className="dp-m__cont" onClick={() => onNavigate('projects')}>
              <span className={'dp-m__cont-icon dp-continue__icon--' + c.accent} aria-hidden="true">{c.icon}</span>
              <span className="dp-m__cont-body">
                <span className="dp-m__cont-name">{c.name}</span>
                <span className="dp-m__cont-status">{c.status}</span>
                <span className="dp-m__cont-bar"><span className={'dp-continue__fill dp-continue__fill--' + c.accent} style={{ width: `${c.progress}%` }} /></span>
                <span className="dp-m__cont-next">Next: {c.next}</span>
              </span>
              <span className="dp-m__cont-pct">{c.progress}%</span>
            </button>
          ))}
        </div>
        <button className="dp-m__more" onClick={() => onNavigate('projects')}>View all projects →</button>
      </section>

      <section className="dp-m__askrow">
        <button className="dp-m__ask" onClick={() => onAsk()}>
          <span className="dp-m__ask-spark" aria-hidden="true">✦</span> Ask the AI Assistant
        </button>
      </section>
    </div>
  )
}

function MobileAI({ seed, onClose, onNavigate }: {
  seed?: string
  onClose: () => void
  onNavigate: (view: PortalView) => void
}) {
  const [turns, setTurns] = useState<HomeTurn[]>(AI_SEED)
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const [atBottom, setAtBottom] = useState(true)
  const logRef = useRef<HTMLDivElement>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)
  const seededRef = useRef(false)

  const scrollToBottom = () => {
    const el = logRef.current
    if (el) el.scrollTop = el.scrollHeight
  }

  // Auto-scroll to the latest message only when the user is already at the
  // bottom — never yank them away while reading older messages.
  useEffect(() => {
    if (atBottom) scrollToBottom()
  }, [turns, thinking, atBottom])

  const send = React.useCallback((text: string) => {
    const q = text.trim()
    if (!q) return
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    const rtime = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    setTurns((t) => [...t, { role: 'user', body: q, time }])
    setInput('')
    setAtBottom(true)
    setThinking(true)
    if (taRef.current) taRef.current.style.height = 'auto'
    if (isDemoMode()) {
      window.setTimeout(() => {
        setTurns((t) => [...t, { role: 'assistant', body: aiReply(q), time: rtime() }])
        setThinking(false)
      }, 400)
      return
    }
    askAssistant(q)
      .then((reply) => {
        setTurns((t) => [...t, { role: 'assistant', body: reply.text, time: rtime() }])
        if (reply.action?.kind === 'navigate') onNavigate(reply.action.target)
      })
      .catch(() => setTurns((t) => [...t, { role: 'assistant', body: "I couldn't reach the backend just now. Please try again.", time: rtime() }]))
      .finally(() => setThinking(false))
  }, [onNavigate])

  // Seed the composer from a tapped "recent conversation" suggestion.
  useEffect(() => {
    if (seed && !seededRef.current) {
      seededRef.current = true
      send(seed)
    }
  }, [seed, send])

  function onScroll() {
    const el = logRef.current
    if (!el) return
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 48)
  }

  function grow() {
    const ta = taRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 140) + 'px'
  }

  return (
    <div className="dp-m__ai" role="dialog" aria-label="AI Assistant">
      <header className="dp-m__bar">
        <button className="dp-m__iconbtn" aria-label="Back" onClick={onClose}>
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="m15 5-7 7 7 7" />
          </svg>
        </button>
        <h1 className="dp-m__title"><span className="dp-m__title-spark" aria-hidden="true">✦</span> AI Assistant</h1>
        <button className="dp-m__iconbtn" aria-label="More">⋯</button>
      </header>

      <div className="dp-m__ailog" ref={logRef} onScroll={onScroll}>
        <div className="dp-home-ai__turn dp-home-ai__turn--assistant">
          <div className="dp-home-ai__bubble">
            <p style={{ whiteSpace: 'pre-line', margin: 0 }}>{AI_WELCOME}</p>
            {AI_PLAN_BULLETS.length > 0 && <ul className="dp-home-ai__plan">{AI_PLAN_BULLETS.map((b) => <li key={b}>{b}</li>)}</ul>}
          </div>
        </div>
        {turns.map((t, i) => (
          <div key={i} className={'dp-home-ai__turn dp-home-ai__turn--' + t.role}>
            <div className="dp-home-ai__bubble">
              <p style={{ margin: 0 }}>{t.body}</p>
              {t.action && <button className="dp-home-ai__inline" onClick={() => { onNavigate(t.action!.target as PortalView); onClose() }}>↗ {t.action.label}</button>}
              {t.time && <span className="dp-home-ai__time">{t.time}</span>}
            </div>
          </div>
        ))}
        {thinking && <div className="dp-home-ai__turn dp-home-ai__turn--assistant"><div className="dp-home-ai__bubble dp-home-ai__bubble--loading">Thinking…</div></div>}
      </div>

      {!atBottom && (
        <button className="dp-m__jump" onClick={() => { setAtBottom(true); scrollToBottom() }} aria-label="Jump to latest">
          ↓ Latest
        </button>
      )}

      <div className="dp-m__aifoot-wrap">
        <div className="dp-m__chips">
          {HOME_SUGGESTIONS.map((s) => (
            <button key={s.label} className="dp-m__chip" onClick={() => send(s.label)}>
              <span aria-hidden="true">{s.icon}</span> {s.label}
            </button>
          ))}
        </div>
        <form className="dp-m__composer" onSubmit={(e) => { e.preventDefault(); send(input) }}>
          <button type="button" className="dp-m__attach" aria-label="Attach">+</button>
          <textarea
            ref={taRef}
            className="dp-m__ta"
            value={input}
            rows={1}
            onChange={(e) => { setInput(e.target.value); grow() }}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) } }}
            placeholder="Ask anything or give an instruction…"
            aria-label="Ask anything or give an instruction"
          />
          <button type="submit" className="dp-m__sendbtn" aria-label="Send" disabled={!input.trim()}>➤</button>
        </form>
        <div className="dp-m__aidisc">AI responses may be incorrect.</div>
      </div>
    </div>
  )
}
