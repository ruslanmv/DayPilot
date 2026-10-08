/**
 * Links a person may follow (batch B4): http(s) only, no credentials, no whitespace or control
 * characters. Returns the normalised address, or null. javascript:, data:, file:, blob: and
 * every other scheme are refused, as are protocol-relative addresses.
 */
export function safeHref(raw: unknown): string | null {
  if (typeof raw !== 'string') return null
  const s = raw.trim()
  if (!s || s.length > 2048) return null
  for (const ch of s) {
    const c = ch.codePointAt(0)!
    if (c <= 0x20 || (c >= 0x7f && c <= 0x9f) || c === 0x2028 || c === 0x2029) return null
  }
  let url: URL
  try {
    url = new URL(s)
  } catch {
    return null
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return null
  if (url.username || url.password || !url.hostname) return null
  return url.href
}
