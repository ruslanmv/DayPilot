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
  // Reference `import.meta.env` as a single, contiguous expression so Vite
  // statically inlines the VITE_* values at build time. Reading it indirectly
  // (e.g. `const m = import.meta; m.env`) defeats that replacement and yields
  // `undefined` in a production bundle, which would silently disable demo mode
  // and the configured API base.
  try {
    // @ts-ignore - Vite injects `import.meta.env` in the browser build.
    const env = import.meta.env as ViteEnv | undefined
    if (env) return env
  } catch {
    /* not a Vite/ESM runtime (tests, SSR) */
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
