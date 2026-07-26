import React from 'react'

import type { AgentFileRef } from './types'

/**
 * Files tab (Batch A4). Documents the agent referenced or produced. Read-only in
 * A4 — the RAG + document links are wired in a later batch. HomePilot owns the
 * files; DayPilot only lists safe references.
 */
export function AgentFilesPanel({ agentName, files }: { agentName: string; files: AgentFileRef[] }) {
  if (files.length === 0) {
    return (
      <div className="dp-agentws__empty">
        <p><b>No files yet.</b></p>
        <p>Documents {agentName} works with — sources you share and drafts they produce — are listed here.</p>
      </div>
    )
  }
  return (
    <ul className="dp-agentws__files" aria-label={`${agentName} files`}>
      {files.map((f) => (
        <li key={f.id} className="dp-agentws__file">
          <span className="dp-agentws__file-name">{f.name}</span>
          {f.meta && <span className="dp-agentws__file-meta">{f.meta}</span>}
        </li>
      ))}
    </ul>
  )
}
