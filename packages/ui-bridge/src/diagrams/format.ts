/** Small display helpers (kept pure so they are tested). */
export function relativeTime(then: number | string | null | undefined, now = Date.now()): string {
  if (then === null || then === undefined) return ''
  const t = typeof then === 'string' ? Date.parse(then) : then
  if (!Number.isFinite(t)) return ''
  const s = Math.max(0, Math.round((now - t) / 1000))
  if (s < 45) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  if (s < 86400 * 14) return `${Math.round(s / 86400)} d ago`
  return new Date(t).toISOString().slice(0, 10)
}
