/**
 * Resilient saves (batch B2): retry only what can succeed on retry, and never turn a lost
 * response into a false conflict.
 */
export type Attempt<T> = { ok: true; data: T } | { ok: false; error: string; status?: number }

/** Network failures, timeouts, throttling and server faults are worth retrying; 4xx never. */
export function retryable<T>(r: Attempt<T>): boolean {
  if (r.ok) return false
  const s = r.status
  return s === undefined || s === 408 || s === 429 || (s >= 500 && s !== 501)
}

export type RetryOptions = {
  attempts?: number
  baseMs?: number
  sleep?: (ms: number) => Promise<void>
  random?: () => number
  onRetry?: (next: number, delayMs: number) => void
}

export async function withRetry<T>(
  fn: () => Promise<Attempt<T>>,
  { attempts = 4, baseMs = 600, sleep = (ms) => new Promise((r) => setTimeout(r, ms)), random = Math.random, onRetry }: RetryOptions = {},
): Promise<Attempt<T>> {
  let last = await fn()
  for (let n = 1; n < attempts && retryable(last); n++) {
    const delay = Math.round(baseMs * 2 ** (n - 1) * (0.5 + random() / 2))
    onRetry?.(n + 1, delay)
    await sleep(delay)
    last = await fn()
  }
  return last
}

const stable = (v: unknown): string =>
  JSON.stringify(v, (_k, x) =>
    x && typeof x === 'object' && !Array.isArray(x)
      ? Object.fromEntries(Object.entries(x as Record<string, unknown>).sort(([a], [b]) => (a < b ? -1 : 1)))
      : x,
  )
/** True when the server already holds exactly what we tried to save (a response was lost). */
export const sameContent = (a: unknown, b: unknown) => stable(a) === stable(b)

/** Tags exactly as the server normalises them, so saved and local documents compare equal. */
export function normalizeTags(tags: string[]): string[] {
  const out: string[] = []
  for (const t of tags) {
    const v = t.split(/\s+/).filter(Boolean).join(' ').toLowerCase().replace(/\|/g, '')
    if (v && v.length <= 40 && !out.includes(v)) out.push(v)
  }
  return out.slice(0, 20)
}
