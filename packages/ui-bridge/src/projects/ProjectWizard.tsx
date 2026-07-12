import React, { useState } from 'react'

export type NewProject = {
  name: string
  goal: string
  stack: string
  repo: string
  milestone: string
}

const EMPTY: NewProject = { name: '', goal: '', stack: '', repo: '', milestone: '' }

/**
 * A small, essentials-only project wizard. Two short steps — what the project
 * is, and where the work lives — so a principal engineer can spin up a project
 * in seconds. Deeper configuration happens inside the project later.
 */
export function ProjectWizard({ open, onClose, onCreate }: {
  open: boolean
  onClose: () => void
  onCreate?: (project: NewProject) => void
}) {
  const [p, setP] = useState<NewProject>(EMPTY)
  if (!open) return null

  const set = (patch: Partial<NewProject>) => setP((prev) => ({ ...prev, ...patch }))
  const canCreate = p.name.trim().length > 0

  function create() {
    if (!canCreate) return
    onCreate?.(p)
    setP(EMPTY)
    onClose()
  }

  return (
    <div className="dp-modal-backdrop" onMouseDown={onClose}>
      <div className="dp-pw" role="dialog" aria-modal="true" aria-label="New project" onMouseDown={(e) => e.stopPropagation()}>
        <header className="dp-pw__head">
          <h3>New project</h3>
          <button className="dp-icon-button" aria-label="Close" onClick={onClose}>✕</button>
        </header>
        <div className="dp-pw__body">
          <label className="dp-onb__field">
            <span>Project name</span>
            <input value={p.name} onChange={(e) => set({ name: e.target.value })} placeholder="LLM Serving Platform" autoFocus />
          </label>
          <label className="dp-onb__field">
            <span>Goal</span>
            <input value={p.goal} onChange={(e) => set({ goal: e.target.value })} placeholder="Ship multi-tier routing with local/cloud failover" />
          </label>
          <div className="dp-pw__row">
            <label className="dp-onb__field">
              <span>Stack</span>
              <input value={p.stack} onChange={(e) => set({ stack: e.target.value })} placeholder="Python · FastAPI · React" />
            </label>
            <label className="dp-onb__field">
              <span>Repository</span>
              <input value={p.repo} onChange={(e) => set({ repo: e.target.value })} placeholder="ruslanmv/DayPilot" />
            </label>
          </div>
          <label className="dp-onb__field">
            <span>First milestone</span>
            <input value={p.milestone} onChange={(e) => set({ milestone: e.target.value })} placeholder="Routing policy draft under review" />
          </label>
        </div>
        <footer className="dp-pw__foot">
          <button className="dp-onb__back" onClick={onClose}>Cancel</button>
          <button className="dp-onb__next" onClick={create} disabled={!canCreate}>Create project</button>
        </footer>
      </div>
    </div>
  )
}
