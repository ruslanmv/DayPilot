/** Canonical JSON digest shared with Python: json.dumps(v, sort_keys=True, separators=(',', ':')) (ASCII-escaped). */
import { createHash } from 'node:crypto'

function enc(v) {
  if (v === null) return 'null'
  if (typeof v === 'boolean') return v ? 'true' : 'false'
  if (typeof v === 'number') {
    if (!Number.isFinite(v)) throw new Error('non-finite number')
    return Number.isInteger(v) ? String(v) : String(v)
  }
  if (typeof v === 'string')
    return '"' + v.replace(/[\\"\u0000-\u001f\u007f-￿]/g, (c) => {
      if (c === '"') return '\\"'
      if (c === '\\') return '\\\\'
      const m = { '\n': '\\n', '\r': '\\r', '\t': '\\t', '\b': '\\b', '\f': '\\f' }[c]
      if (m) return m
      return '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0')
    }) + '"'
  if (Array.isArray(v)) return '[' + v.map(enc).join(',') + ']'
  return '{' + Object.keys(v).sort().map((k) => enc(k) + ':' + enc(v[k])).join(',') + '}'
}
export const canonical = enc
export const digest = (v) => createHash('sha256').update(enc(v), 'utf8').digest('hex')
export const sha256 = (buf) => createHash('sha256').update(buf).digest('hex')
