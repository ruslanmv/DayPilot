/**
 * Conservative email HTML sanitizer.
 *
 * Email bodies are **untrusted input**. Provider HTML is never injected raw into
 * the app DOM: we parse it in an inert document, keep only a safe tag/attribute
 * allowlist, drop scripts/styles/iframes/objects and all inline event handlers,
 * neutralize `javascript:`/`data:` URLs, and (by default) block remote tracking
 * images by stripping their `src` and flagging that images were blocked. CSS is
 * not allowed through, so email styles cannot escape the content container.
 *
 * This is a defense-in-depth layer; a production deployment should still render
 * inside a sandboxed iframe with a strict CSP. When no DOM is available (SSR /
 * tests) we fall back to a plain-text projection.
 */

const ALLOWED_TAGS = new Set([
  'a', 'p', 'br', 'div', 'span', 'b', 'strong', 'i', 'em', 'u', 's', 'blockquote',
  'ul', 'ol', 'li', 'pre', 'code', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr',
  'table', 'thead', 'tbody', 'tr', 'td', 'th', 'img',
])
const ALLOWED_ATTRS = new Set(['href', 'title', 'alt', 'colspan', 'rowspan'])
const URL_ATTRS = new Set(['href', 'src'])

export type SanitizeOptions = { allowRemoteImages?: boolean }
export type SanitizeResult = { html: string; blockedImages: number; hasHtml: boolean }

function safeUrl(value: string): string | null {
  const v = value.trim()
  // Allow http(s), mailto, and relative/anchor links only.
  if (/^(https?:|mailto:)/i.test(v)) return v
  if (/^(\/|#)/.test(v)) return v
  if (/^[a-z][a-z0-9+.-]*:/i.test(v)) return null // any other scheme (javascript:, data:, vbscript:…)
  return v
}

export function sanitizeEmailHtml(input: string, opts: SanitizeOptions = {}): SanitizeResult {
  if (!input) return { html: '', blockedImages: 0, hasHtml: false }
  if (typeof document === 'undefined' || typeof DOMParser === 'undefined') {
    // No DOM — return an escaped plain-text projection.
    const text = input.replace(/<[^>]*>/g, ' ').replace(/&nbsp;/g, ' ')
    return { html: escapeText(text), blockedImages: 0, hasHtml: false }
  }

  const doc = new DOMParser().parseFromString(input, 'text/html')
  let blockedImages = 0

  const walk = (node: Node) => {
    const children = Array.from(node.childNodes)
    for (const child of children) {
      if (child.nodeType === 8) { child.parentNode?.removeChild(child); continue } // comments
      if (child.nodeType !== 1) continue
      const el = child as Element
      const tag = el.tagName.toLowerCase()
      if (!ALLOWED_TAGS.has(tag)) {
        // Drop the element but keep its text so content isn't lost.
        const text = el.textContent || ''
        if (text.trim()) el.replaceWith(doc.createTextNode(text))
        else el.remove()
        continue
      }
      // Strip every attribute not on the allowlist (kills on* handlers, style…).
      for (const attr of Array.from(el.attributes)) {
        const name = attr.name.toLowerCase()
        if (!ALLOWED_ATTRS.has(name)) { el.removeAttribute(attr.name); continue }
        if (URL_ATTRS.has(name)) {
          const cleaned = safeUrl(attr.value)
          if (cleaned === null) el.removeAttribute(attr.name)
          else el.setAttribute(attr.name, cleaned)
        }
      }
      if (tag === 'a') {
        el.setAttribute('rel', 'noopener noreferrer nofollow')
        el.setAttribute('target', '_blank')
      }
      if (tag === 'img' && !opts.allowRemoteImages) {
        const src = el.getAttribute('src') || ''
        if (/^https?:/i.test(src)) { el.removeAttribute('src'); blockedImages += 1 }
      }
      walk(el)
    }
  }
  walk(doc.body)
  return { html: doc.body.innerHTML, blockedImages, hasHtml: true }
}

function escapeText(text: string): string {
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>')
}

/** Render plain-text email safely as escaped HTML with line breaks. */
export function textToSafeHtml(text: string): string {
  return escapeText(text || '')
}
