/**
 * Runtime environment for the DayPilot web shell.
 *
 * The product ships in a *clean, real-data* state by default: no fabricated
 * tasks, projects, documents, or assistant chatter. Demo/sample content is
 * strictly opt-in via `VITE_DAYPILOT_DEMO_MODE=true`, and when it is on the UI
 * shows a visible "Demo mode" badge so nobody mistakes sample data for real
 * data. This mirrors how a production app behaves on first run.
 */

type ViteEnv = Record<string, string | boolean | undefined>

function readEnv(): ViteEnv {
  // `import.meta.env` is defined by Vite in the browser build. Guard so the
  // module is also importable outside Vite (tests, SSR) without throwing.
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const meta = import.meta as any
    if (meta && meta.env) return meta.env as ViteEnv
  } catch {
    /* not a module-env runtime */
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const g = globalThis as any
  if (g && g.process && g.process.env) return g.process.env as ViteEnv
  return {}
}

/** True only when demo/sample data was explicitly requested. Defaults to false
 *  so the shell starts empty and connected to real data. */
export function isDemoMode(): boolean {
  return String(readEnv().VITE_DAYPILOT_DEMO_MODE ?? '').toLowerCase() === 'true'
}

/** Base URL of the DayPilot API gateway. Defaults to a same-origin `/api`
 *  reverse-proxy path; override with `VITE_DAYPILOT_API_BASE`. */
export function apiBase(): string {
  const raw = String(readEnv().VITE_DAYPILOT_API_BASE ?? '').trim()
  const base = raw || '/api'
  return base.endsWith('/') ? base.slice(0, -1) : base
}

/** Workspace the shell operates on (single-tenant default for local dev). */
export function workspaceId(): string {
  return String(readEnv().VITE_DAYPILOT_WORKSPACE_ID ?? '').trim() || 'default'
}
