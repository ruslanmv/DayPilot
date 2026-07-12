/**
 * HomePilot Family state language.
 *
 * A single vocabulary for the states that recur across Command, Agents,
 * Documents, and Approvals. Every surface renders these the same way — same
 * color, same icon, same words — so the user learns the language once.
 */
import { color } from './tokens'

export type FamilyState =
  | 'local-first'
  | 'approval-gated'
  | 'ai-running'
  | 'blocked'
  | 'safe'
  | 'needs-attention'

export type StateStyle = {
  /** Canonical CSS variable driving this state's color. */
  cssVar: string
  /** Resolved hex/rgba for non-CSS surfaces. */
  color: string
  /** Monochrome glyph (emoji placeholder; swap for the icon set in the app). */
  icon: string
  /** Human label used in pills and tooltips. */
  label: string
  /** One-line meaning for tooltips and the brand guide. */
  meaning: string
}

export const STATE_LANGUAGE: Record<FamilyState, StateStyle> = {
  'local-first': {
    cssVar: '--hp-state-local-first',
    color: color.accentGreen,
    icon: '🔒',
    label: 'Local-first',
    meaning: 'Runs and stays on this device unless cloud sync is explicitly enabled.',
  },
  'approval-gated': {
    cssVar: '--hp-state-approval-gated',
    color: color.accentOrange,
    icon: '✋',
    label: 'Needs approval',
    meaning: 'A sensitive action is queued and will not execute until you approve it.',
  },
  'ai-running': {
    cssVar: '--hp-state-ai-running',
    color: color.accentCyan,
    icon: '◐',
    label: 'AI running',
    meaning: 'An agent is actively working this item in the background.',
  },
  blocked: {
    cssVar: '--hp-state-blocked',
    color: color.accentRed,
    icon: '⛔',
    label: 'Blocked',
    meaning: 'Cannot proceed until a dependency, decision, or error is resolved.',
  },
  safe: {
    cssVar: '--hp-state-safe',
    color: color.accentGreen,
    icon: '✓',
    label: 'Safe',
    meaning: 'Completed or verified with no outstanding risk.',
  },
  'needs-attention': {
    cssVar: '--hp-state-needs-attention',
    color: color.accentOrange,
    icon: '⚠',
    label: 'Needs attention',
    meaning: 'At risk or drifting; review recommended but not yet blocking.',
  },
}

export const FAMILY_STATES = Object.keys(STATE_LANGUAGE) as FamilyState[]
