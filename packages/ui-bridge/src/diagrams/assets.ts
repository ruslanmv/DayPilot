/**
 * Attachments (batch B5). Files attached to topics are identified by the SHA-256 of their bytes
 * and their type is decided from the bytes themselves, never from a file name or a claimed type.
 * SVG is refused on purpose: it can carry script.
 */
import type { Diagram, DiagramNode } from './dmind'

export const ASSET_TYPES = [
  'image/png',
  'image/jpeg',
  'image/gif',
  'image/webp',
  'application/pdf',
  'text/plain',
  'text/markdown',
] as const
export type AssetType = (typeof ASSET_TYPES)[number]
export const MAX_ASSET_BYTES = 5_000_000
export const MAX_ATTACHMENTS_PER_TOPIC = 10
export const MAX_ASSETS = 50

const EXTENSION: Record<AssetType, string> = {
  'image/png': 'png',
  'image/jpeg': 'jpg',
  'image/gif': 'gif',
  'image/webp': 'webp',
  'application/pdf': 'pdf',
  'text/plain': 'txt',
  'text/markdown': 'md',
}
export const isImage = (type: string) => type.startsWith('image/')

export type Attachment = { asset: string; name: string; type: AssetType; bytes: number }
export type AssetData = { bytes: Uint8Array; name: string; type: AssetType }
/** Keyed by `sha256:<hex>`. */
export type AssetStore = Map<string, AssetData>

const startsWith = (b: Uint8Array, magic: number[], at = 0) => magic.every((m, i) => b[at + i] === m)

/** The type of a file from its bytes, or null when it is not an allowed type. */
export function sniffType(bytes: Uint8Array, nameHint = ''): AssetType | null {
  if (startsWith(bytes, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) return 'image/png'
  if (startsWith(bytes, [0xff, 0xd8, 0xff])) return 'image/jpeg'
  if (startsWith(bytes, [0x47, 0x49, 0x46, 0x38]) && (bytes[4] === 0x37 || bytes[4] === 0x39) && bytes[5] === 0x61) return 'image/gif'
  if (startsWith(bytes, [0x52, 0x49, 0x46, 0x46]) && startsWith(bytes, [0x57, 0x45, 0x42, 0x50], 8)) return 'image/webp'
  if (startsWith(bytes, [0x25, 0x50, 0x44, 0x46, 0x2d])) return 'application/pdf'
  // Text: valid UTF-8, no NUL bytes, and not markup that could be mistaken for an image format.
  if (bytes.length && /\.(txt|md|markdown)$/i.test(nameHint) && !bytes.includes(0)) {
    try {
      const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes)
      if (/^\s*<(svg|\?xml|!doctype\s+svg)/i.test(text)) return null
      return /\.(md|markdown)$/i.test(nameHint) ? 'text/markdown' : 'text/plain'
    } catch {
      return null
    }
  }
  return null
}

export async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', bytes as BufferSource)
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

export const assetRef = (hex: string) => 'sha256:' + hex
export const isAssetRef = (v: unknown): v is string => typeof v === 'string' && /^sha256:[0-9a-f]{64}$/.test(v)
export const assetPath = (ref: string, type: AssetType) => `assets/${ref.slice(7)}.${EXTENSION[type]}`

/** A file name safe to show and to offer for download. */
export function cleanFileName(name: string): string {
  const base = name.split(/[\\/]/).pop() || 'file'
  // eslint-disable-next-line no-control-regex
  const clean = base.replace(/[\u0000-\u001f\u007f\u2028\u2029]/g, '').trim().slice(0, 120)
  return clean || 'file'
}

/** The valid attachments on a topic (unknown shapes in a hand-edited file are ignored). */
export function attachmentsOf(node: DiagramNode): Attachment[] {
  const raw = node.metadata?.attachments
  if (!Array.isArray(raw)) return []
  const out: Attachment[] = []
  for (const a of raw) {
    if (!a || typeof a !== 'object') continue
    const { asset, name, type, bytes } = a as Record<string, unknown>
    if (isAssetRef(asset) && typeof name === 'string' && ASSET_TYPES.includes(type as AssetType) && Number.isInteger(bytes) && (bytes as number) >= 0)
      out.push({ asset, name: cleanFileName(name), type: type as AssetType, bytes: bytes as number })
  }
  return out.slice(0, MAX_ATTACHMENTS_PER_TOPIC)
}

/** Every distinct attachment in the diagram, in topic order. */
export function allAttachments(d: Diagram): Attachment[] {
  const seen = new Set<string>()
  const out: Attachment[] = []
  for (const n of d.nodes)
    for (const a of attachmentsOf(n))
      if (!seen.has(a.asset)) {
        seen.add(a.asset)
        out.push(a)
      }
  return out
}

/** Attach a file to a topic: returns the new diagram and the data to keep in the asset store. */
export async function attachFile(
  d: Diagram,
  nodeId: string,
  file: { name: string; bytes: Uint8Array },
): Promise<{ diagram: Diagram; ref: string; data: AssetData } | { error: string }> {
  if (!d.nodes.some((n) => n.id === nodeId)) return { error: 'That topic no longer exists.' }
  if (!file.bytes.length) return { error: 'The file is empty.' }
  if (file.bytes.length > MAX_ASSET_BYTES) return { error: `Use a file smaller than ${MAX_ASSET_BYTES / 1_000_000} MB.` }
  const type = sniffType(file.bytes, file.name)
  if (!type) return { error: 'Attachments can be PNG, JPEG, GIF or WebP images, PDFs, or TXT and Markdown files. SVG is not allowed because it can contain scripts.' }
  const ref = assetRef(await sha256Hex(file.bytes))
  const name = cleanFileName(file.name)
  const node = d.nodes.find((n) => n.id === nodeId)!
  const existing = attachmentsOf(node)
  if (existing.some((a) => a.asset === ref)) return { error: 'That file is already attached to this topic.' }
  if (existing.length >= MAX_ATTACHMENTS_PER_TOPIC) return { error: `A topic can hold ${MAX_ATTACHMENTS_PER_TOPIC} attachments.` }
  if (!allAttachments(d).some((a) => a.asset === ref) && allAttachments(d).length >= MAX_ASSETS)
    return { error: `A diagram can hold ${MAX_ASSETS} different attachments.` }
  const entry: Attachment = { asset: ref, name, type, bytes: file.bytes.length }
  const diagram: Diagram = {
    ...d,
    nodes: d.nodes.map((n) => (n.id === nodeId ? { ...n, metadata: { ...n.metadata, attachments: [...existing, entry] } } : n)),
  }
  return { diagram, ref, data: { bytes: file.bytes, name, type } }
}

export function removeAttachment(d: Diagram, nodeId: string, ref: string): Diagram {
  return {
    ...d,
    nodes: d.nodes.map((n) => {
      if (n.id !== nodeId) return n
      const left = attachmentsOf(n).filter((a) => a.asset !== ref)
      const meta = { ...n.metadata }
      if (left.length) meta.attachments = left
      else delete meta.attachments
      const next: DiagramNode = { ...n, metadata: meta }
      if (!Object.keys(meta).length) delete next.metadata
      return next
    }),
  }
}

export function formatBytes(n: number): string {
  if (n < 1000) return `${n} B`
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)} kB`
  return `${(n / 1_000_000).toFixed(1)} MB`
}
