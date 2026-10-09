/** Resolve gateway-owned portraits through the same base as JSON API calls.
 * A bare /v1 URL would hit Vite's HTML fallback instead of its /api proxy.
 */
export function portraitUrl(avatarUrl: string | null | undefined, gatewayBase: string): string | undefined {
  if (!avatarUrl) return undefined
  if (!avatarUrl.startsWith('/v1/')) return avatarUrl
  return gatewayBase.replace(/\/$/, '') + avatarUrl
}
