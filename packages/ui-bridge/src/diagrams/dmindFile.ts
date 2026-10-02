/**
 * The `.dmind` file (batch B1): UTF-8 JSON in the dmind/v1 schema.
 *
 * Opening a file always yields a new draft; nothing here touches saved diagrams. Anything this
 * version does not use is kept and reported, never dropped. The ZIP bundle form (B5) is detected
 * from the first bytes so a future reader and this one agree on which form a file is.
 */
import { fromBundle, validateDiagram, type Diagram } from './dmind'

export const DMIND_EXTENSION = '.dmind'
export const DMIND_MIME = 'application/vnd.dmind+json'
export const MAX_FILE_BYTES = 2_000_000
export const MAX_TEXT_CHARS = 100_000

export type FileForm = 'json' | 'zip' | 'unknown'
export type UnknownReport = {
  topLevel: string[]
  nodeKeys: string[]
  edgeKeys: string[]
  metadataKeys: string[]
  total: number
}
export type ImportResult =
  | { kind: 'diagram'; diagram: Diagram; via: 'dmind' | 'bundle'; report: UnknownReport }
  | { kind: 'text'; text: string; name: string }

const KNOWN = {
  topLevel: ['schema_version', 'id', 'title', 'kind', 'nodes', 'edges', 'metadata'],
  node: ['id', 'label', 'notes', 'collapsed', 'position', 'metadata'],
  edge: ['id', 'source', 'target', 'kind', 'label'],
}

/** `.dmind` for a title; characters outside letters, digits, dot, dash and underscore become `-`. */
export function dmindFileName(title: string): string {
  const stem =
    title
      .trim()
      .slice(0, 80)
      .replace(/[^\p{L}\p{N}._-]+/gu, '-')
      .replace(/^[-.]+|[-.]+$/g, '') || 'diagram'
  return stem + DMIND_EXTENSION
}

/** Portable, readable and diff-friendly: two-space JSON with a trailing newline. */
export function serializeDmind(d: Diagram): string {
  return JSON.stringify(validateDiagram(d), null, 2) + '\n'
}

export function detectForm(bytes: Uint8Array): FileForm {
  let i = 0
  if (bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) i = 3 // UTF-8 byte order mark
  while (i < bytes.length && (bytes[i] === 0x20 || bytes[i] === 0x09 || bytes[i] === 0x0a || bytes[i] === 0x0d)) i++
  if (bytes[i] === 0x7b) return 'json' // {
  if (bytes[0] === 0x50 && bytes[1] === 0x4b) return 'zip' // PK
  return 'unknown'
}

/** Fields this version does not use: kept on save and export, listed for the person. */
export function unknownFields(d: Diagram): UnknownReport {
  const diff = (obj: object, known: string[]) => Object.keys(obj).filter((k) => !known.includes(k))
  const topLevel = diff(d, KNOWN.topLevel)
  const nodeKeys = new Set<string>()
  const edgeKeys = new Set<string>()
  d.nodes.forEach((n) => diff(n, KNOWN.node).forEach((k) => nodeKeys.add(k)))
  d.edges.forEach((e) => diff(e, KNOWN.edge).forEach((k) => edgeKeys.add(k)))
  const metadataKeys = Object.keys(d.metadata || {}).filter(
    (k) => !['generator', 'ai_assisted', 'design_bundle', 'validation_status', 'sources', 'layout', 'tags', 'project_id'].includes(k),
  )
  return {
    topLevel,
    nodeKeys: [...nodeKeys],
    edgeKeys: [...edgeKeys],
    metadataKeys,
    total: topLevel.length + nodeKeys.size + edgeKeys.size + metadataKeys.length,
  }
}

export function describeUnknown(report: UnknownReport): string {
  if (!report.total) return ''
  const parts = [
    report.topLevel.length && `document: ${report.topLevel.join(', ')}`,
    report.nodeKeys.length && `topics: ${report.nodeKeys.join(', ')}`,
    report.edgeKeys.length && `links: ${report.edgeKeys.join(', ')}`,
    report.metadataKeys.length && `metadata: ${report.metadataKeys.join(', ')}`,
  ].filter(Boolean)
  return `Kept ${report.total} field(s) this version does not use (${parts.join('; ')}). They are preserved when you save or export.`
}

function decode(bytes: Uint8Array): string {
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes).replace(/^﻿/, '')
  } catch {
    throw new Error('This file is not valid UTF-8 text.')
  }
}

/** Parse the JSON form of a dmind file or a Matrix Design Bundle. */
export function parseDmindText(text: string): ImportResult {
  let value: unknown
  try {
    value = JSON.parse(text)
  } catch (e) {
    throw new Error('This file is not valid JSON: ' + (e instanceof Error ? e.message : 'parse error'))
  }
  const schema = (value as { schema_version?: unknown } | null)?.schema_version
  if (schema === 'matrix.designer.bundle/v1') {
    const diagram = fromBundle(value)
    return { kind: 'diagram', diagram, via: 'bundle', report: unknownFields(diagram) }
  }
  if (typeof schema === 'string' && schema.startsWith('dmind/') && schema !== 'dmind/v1')
    throw new Error(`This file uses ${schema}; this version reads dmind/v1. Update DayPilot to open it.`)
  const diagram = validateDiagram(value)
  return { kind: 'diagram', diagram, via: 'dmind', report: unknownFields(diagram) }
}

/**
 * Read any file a person may bring: dmind JSON, a Matrix bundle or an outline in TXT/Markdown.
 * Bounded before parsing, with errors that say what to do next.
 */
export function importFile(name: string, bytes: Uint8Array): ImportResult {
  if (bytes.length > MAX_FILE_BYTES) throw new Error('Use a file smaller than 2 MB.')
  const lower = name.toLowerCase()
  const form = detectForm(bytes)
  if (form === 'zip') throw new Error('The .dmind bundle form (ZIP) is not supported by this reader.')
  if (/\.(txt|md|markdown)$/.test(lower)) {
    const text = decode(bytes)
    if (text.length > MAX_TEXT_CHARS) throw new Error('Text source exceeds 100000 characters.')
    return { kind: 'text', text, name }
  }
  if (/\.(dmind|json)$/.test(lower)) {
    if (form !== 'json') throw new Error('This file is not a dmind document: it should be JSON starting with "{".')
    return parseDmindText(decode(bytes))
  }
  throw new Error(
    'Supported attachments: .dmind, JSON (dmind or Matrix Design Bundle), TXT and Markdown.',
  )
}
