import React from 'react'
import type { DiagramSummary } from './diagramsClient'
import type { DiagramKind } from './dmind'
import { relativeTime } from './format'
import { TEMPLATES, type Template } from './templates'

const KINDS: Array<{
  id: DiagramKind
  title: string
  text: string
  tone: 'map' | 'flow' | 'system'
}> = [
  {
    id: 'mindmap',
    title: 'Mind map',
    text: 'A topic in the center, with branches for ideas.',
    tone: 'map',
  },
  {
    id: 'flowchart',
    title: 'Flowchart',
    text: 'Steps in order, including decisions.',
    tone: 'flow',
  },
  {
    id: 'system',
    title: 'System',
    text: 'Parts of a system and how they depend on each other.',
    tone: 'system',
  },
]

const FEATURED = ['project-plan', 'decision', 'meeting-notes', 'user-journey', 'approval-flow', 'system-design']

function KindMark({ tone }: { tone: 'map' | 'flow' | 'system' }) {
  if (tone === 'flow') {
    return (
      <svg viewBox="0 0 72 36" width="72" height="36" aria-hidden="true">
        <rect x="1" y="8" width="16" height="20" rx="4" />
        <rect x="28" y="8" width="16" height="20" rx="4" />
        <rect x="55" y="8" width="16" height="20" rx="4" />
        <path d="M17 18h11M44 18h11" />
      </svg>
    )
  }
  if (tone === 'system') {
    return (
      <svg viewBox="0 0 72 36" width="72" height="36" aria-hidden="true">
        <rect x="26" y="1" width="20" height="14" rx="3" />
        <rect x="2" y="21" width="20" height="14" rx="3" />
        <rect x="50" y="21" width="20" height="14" rx="3" />
        <path d="M32 15v6M40 15l14 6M28 15L16 21" />
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 72 36" width="72" height="36" aria-hidden="true">
      <rect x="26" y="10" width="20" height="16" rx="4" />
      <path d="M26 18H12M46 18h14M36 10V4M36 26v6" />
      <circle cx="8" cy="18" r="3" />
      <circle cx="64" cy="18" r="3" />
      <circle cx="36" cy="3" r="2.5" />
      <circle cx="36" cy="33" r="2.5" />
    </svg>
  )
}

/**
 * The idle center of dmind: pick a diagram type or a template. Both open the
 * existing wizard with the outline already chosen, so the person only edits
 * and presses Next.
 */
export function DiagramLanding({
  recent,
  onOpen,
  onCreate,
  onTemplate,
}: {
  recent: DiagramSummary[]
  onOpen: (id: string) => void
  onCreate: (kind: DiagramKind) => void
  onTemplate: (template: Template) => void
}) {
  const featured = FEATURED.map((id) => TEMPLATES.find((t) => t.id === id)).filter((t): t is Template => !!t)
  return (
    <div className="dmind-land">
      <p className="dmind-land-lead">
        Pick a type or a template. You edit a short outline, then DayPilot draws the diagram on this device.
      </p>

      {recent.length > 0 && (
        <section className="dmind-land-block" aria-label="Recent diagrams">
          <h3>Continue</h3>
          <div className="dmind-recent">
            {recent.map((item) => (
              <button key={item.id} type="button" className="dmind-recent-item" onClick={() => onOpen(item.id)}>
                <strong>{item.title}</strong>
                <small>
                  Revision {item.revision}
                  {item.updatedAt ? ` · ${relativeTime(item.updatedAt)}` : ''}
                </small>
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="dmind-land-block" aria-label="Diagram types">
        <h3>Start a diagram</h3>
        <div className="dmind-kinds">
          {KINDS.map((kind) => (
            <button
              key={kind.id}
              type="button"
              className={`dmind-kind dmind-kind--${kind.tone}`}
              onClick={() => onCreate(kind.id)}
            >
              <KindMark tone={kind.tone} />
              <strong>{kind.title}</strong>
              <span>{kind.text}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="dmind-land-block" aria-label="Templates">
        <h3>Or start from a template</h3>
        <div className="dmind-templates">
          {featured.map((template) => (
            <button key={template.id} type="button" className="dmind-template" onClick={() => onTemplate(template)}>
              <strong>{template.name}</strong>
              <small>{template.blurb}</small>
            </button>
          ))}
        </div>
      </section>
    </div>
  )
}
