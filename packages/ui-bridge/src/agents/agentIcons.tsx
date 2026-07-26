import React from 'react'

/**
 * Small inline icon set for the agents surface (directory + workspace + add).
 * Capability chips map a skill keyword to a glyph so cards read like the staff
 * directory in the product design. Everything is a 16px stroked SVG that inherits
 * `currentColor`; unknown skills fall back to a neutral dot.
 */
const S = (d: React.ReactNode) => (
  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor"
       strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>
)

const ICONS: Record<string, React.ReactNode> = {
  tasks: S(<><rect x="4" y="4" width="16" height="16" rx="3" /><path d="M8 12l3 3 5-6" /></>),
  calendar: S(<><rect x="3" y="4" width="18" height="17" rx="2" /><path d="M3 9h18M8 2v4M16 2v4" /></>),
  email: S(<><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M4 7l8 6 8-6" /></>),
  research: S(<><path d="M4 20V10M10 20V4M16 20v-8M22 20H2" /></>),
  reports: S(<><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M9 8h6M9 12h6M9 16h4" /></>),
  data: S(<><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" /></>),
  projects: S(<><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" /></>),
  docs: S(<><path d="M6 2h8l4 4v16H6z" /><path d="M14 2v4h4M9 13h6M9 17h6" /></>),
  finance: S(<><circle cx="12" cy="12" r="9" /><path d="M12 7v10M9.5 9.5c0-1 1-1.5 2.5-1.5s2.5.6 2.5 1.6c0 2.4-5 1.4-5 3.8 0 1 1 1.6 2.5 1.6s2.5-.5 2.5-1.5" /></>),
  analytics: S(<><path d="M4 19V5M20 19H4M8 17v-4M12 17v-8M16 17v-6" /></>),
  support: S(<><path d="M4 13v-1a8 8 0 0116 0v1M4 13a2 2 0 002 2h1v-4H6a2 2 0 00-2 2zM20 13a2 2 0 00-2-2h-1v4h1a2 2 0 002-2zM18 15v1a3 3 0 01-3 3h-3" /></>),
  crm: S(<><circle cx="9" cy="8" r="3" /><path d="M3 20a6 6 0 0112 0M16 6.5a3 3 0 010 5.5M21 20a5 5 0 00-4-4.9" /></>),
  feedback: S(<><path d="M4 5h16v11H8l-4 4z" /></>),
  content: S(<><path d="M4 20h4L20 8l-4-4L4 16z" /><path d="M14 6l4 4" /></>),
  strategy: S(<><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1.4" /></>),
  systems: S(<><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M8 20h8M12 16v4" /></>),
  security: S(<><path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z" /><path d="M9 12l2 2 4-4" /></>),
  hr: S(<><circle cx="9" cy="8" r="3" /><path d="M3 20a6 6 0 0112 0M17 11l2 2 3-3" /></>),
  onboarding: S(<><path d="M12 3l3 6 6 .5-4.5 4 1.4 6-5.9-3.3L6 19.5l1.4-6L3 9.5 9 9z" /></>),
  policies: S(<><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M9 8h6M9 12h6M9 16h3" /></>),
}

const ALIASES: Record<string, string> = {
  scheduling: 'calendar', schedule: 'calendar', communications: 'email', communication: 'email',
  writing: 'content', 'email drafting': 'email', 'executive support': 'tasks', it: 'systems',
  'it support': 'support', governance: 'security', compliance: 'policies', people: 'hr',
  coding: 'systems', github: 'systems', document: 'docs', 'document.generate': 'docs',
}

export function capabilityIcon(name: string): React.ReactNode {
  const key = (name || '').trim().toLowerCase()
  if (ICONS[key]) return ICONS[key]
  if (ALIASES[key] && ICONS[ALIASES[key]]) return ICONS[ALIASES[key]]
  const word = key.split(/[ ._-]/)[0]
  if (ICONS[word]) return ICONS[word]
  return S(<circle cx="12" cy="12" r="3" />)
}

/** Icons for the directory filter chips. */
export const filterIcon: Record<string, React.ReactNode> = {
  all: S(<><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></>),
  installed: S(<><circle cx="9" cy="8" r="3" /><path d="M3 20a6 6 0 0112 0M16 6.5a3 3 0 010 5.5M21 20a5 5 0 00-4-4.9" /></>),
  homepilot: S(<><path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z" /><path d="M9 12l2 2 4-4" /></>),
  imported: S(<><path d="M5 3h11l3 3v15H5z" /><path d="M12 8v7M9 12l3 3 3-3" /></>),
  favorites: S(<path d="M12 3l3 6 6 .9-4.5 4.2 1 6-5.5-3-5.5 3 1-6L3 9.9 9 9z" />),
}
