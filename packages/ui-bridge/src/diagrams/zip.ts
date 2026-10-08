/**
 * A small, strict ZIP reader and a deterministic writer (batch B5). No dependencies.
 *
 * The reader treats every archive as hostile: it is bounded in entries and sizes, refuses ZIP64,
 * encryption, symlinks, special files, duplicate or unsafe names, overlapping or out-of-range
 * entries, and any entry whose local header disagrees with the central directory. Inflated
 * data is counted as it streams, so a lie in the headers cannot allocate more than the declared
 * and permitted size. CRC-32 is verified.
 *
 * The writer stores entries uncompressed with fixed metadata, so the same input always yields the
 * same bytes (the Python writer in Matrix Designer produces identical output).
 */

export type ZipLimits = {
  maxEntries: number
  maxEntryBytes: number
  maxTotalBytes: number
  maxRatio: number
}
export const BUNDLE_LIMITS: ZipLimits = {
  maxEntries: 200,
  maxEntryBytes: 10_000_000,
  maxTotalBytes: 60_000_000,
  maxRatio: 200,
}

export class ZipError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ZipError'
  }
}

const u16 = (b: Uint8Array, o: number) => b[o] | (b[o + 1] << 8)
const u32 = (b: Uint8Array, o: number) => (b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24)) >>> 0

let table: Uint32Array | undefined
export function crc32(data: Uint8Array): number {
  if (!table) {
    table = new Uint32Array(256)
    for (let n = 0; n < 256; n++) {
      let c = n
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
      table[n] = c >>> 0
    }
  }
  let crc = 0xffffffff
  for (let i = 0; i < data.length; i++) crc = table[(crc ^ data[i]) & 0xff] ^ (crc >>> 8)
  return (crc ^ 0xffffffff) >>> 0
}

const UNSAFE_NAME = /[\u0000-\u001f\u007f\\]/

/** Entry names must be plain relative paths: no traversal, drive letters, backslashes or controls. */
export function checkEntryName(name: string): void {
  if (!name || name.length > 200) throw new ZipError('The archive contains an entry with an invalid name.')
  // Bundle entries are always plain ASCII, which also removes any Unicode look-alike or
  // normalisation question between implementations.
  if (!/^[\x20-\x7e]+$/.test(name) || UNSAFE_NAME.test(name) || name.startsWith('/') || /^[A-Za-z]:/.test(name))
    throw new ZipError('The archive contains an unsafe entry name and was refused.')
  const parts = name.replace(/\/$/, '').split('/')
  if (parts.some((p) => p === '' || p === '.' || p === '..'))
    throw new ZipError('The archive contains an unsafe entry name and was refused.')
}

type Entry = {
  name: string
  method: number
  crc: number
  csize: number
  usize: number
  offset: number
  isDir: boolean
  nameBytes: Uint8Array
}

async function inflateRaw(data: Uint8Array, expected: number): Promise<Uint8Array> {
  if (typeof DecompressionStream === 'undefined')
    throw new ZipError('This browser cannot read compressed archive entries.')
  const stream = new Blob([data as BlobPart]).stream().pipeThrough(new DecompressionStream('deflate-raw'))
  const reader = stream.getReader()
  const out = new Uint8Array(expected)
  let total = 0
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      total += value.length
      if (total > expected) throw new ZipError('An archive entry is larger than it declares and was refused.')
      out.set(value, total - value.length)
    }
  } catch (e) {
    if (e instanceof ZipError) throw e
    throw new ZipError('An archive entry could not be decompressed.')
  } finally {
    reader.cancel().catch(() => {})
  }
  if (total !== expected) throw new ZipError('An archive entry is smaller than it declares and was refused.')
  return out
}

/** Read an archive into a name -> bytes map, or throw a ZipError saying why it was refused. */
export async function readZip(bytes: Uint8Array, limits: ZipLimits = BUNDLE_LIMITS): Promise<Map<string, Uint8Array>> {
  if (bytes.length < 22 || u32(bytes, 0) !== 0x04034b50) {
    if (bytes.length >= 22 && u32(bytes, 0) === 0x06054b50) throw new ZipError('The archive is empty.')
    throw new ZipError('This is not a valid ZIP archive.')
  }
  // The end-of-central-directory record, which must be the last thing in the file.
  let eocd = -1
  for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 22 - 65535); i--)
    if (u32(bytes, i) === 0x06054b50 && i + 22 + u16(bytes, i + 20) === bytes.length) {
      eocd = i
      break
    }
  if (eocd < 0) throw new ZipError('This is not a valid ZIP archive.')
  const disk = u16(bytes, eocd + 4),
    cdDisk = u16(bytes, eocd + 6),
    here = u16(bytes, eocd + 8),
    total = u16(bytes, eocd + 10),
    cdSize = u32(bytes, eocd + 12),
    cdOffset = u32(bytes, eocd + 16)
  if (total === 0xffff || cdSize === 0xffffffff || cdOffset === 0xffffffff)
    throw new ZipError('ZIP64 archives are not supported.')
  if (disk !== 0 || cdDisk !== 0 || here !== total) throw new ZipError('Multi-part archives are not supported.')
  if (total > limits.maxEntries) throw new ZipError(`The archive has more than ${limits.maxEntries} entries.`)
  if (cdOffset + cdSize !== eocd) throw new ZipError('The archive directory is damaged.')

  const entries: Entry[] = []
  const seen = new Set<string>()
  let p = cdOffset,
    declared = 0
  for (let i = 0; i < total; i++) {
    if (p + 46 > eocd || u32(bytes, p) !== 0x02014b50) throw new ZipError('The archive directory is damaged.')
    const madeBy = u16(bytes, p + 4),
      flags = u16(bytes, p + 8),
      method = u16(bytes, p + 10),
      crc = u32(bytes, p + 16),
      csize = u32(bytes, p + 20),
      usize = u32(bytes, p + 24),
      nameLen = u16(bytes, p + 28),
      extraLen = u16(bytes, p + 30),
      commentLen = u16(bytes, p + 32),
      diskStart = u16(bytes, p + 34),
      external = u32(bytes, p + 38),
      offset = u32(bytes, p + 42)
    const end = p + 46 + nameLen + extraLen + commentLen
    if (end > eocd) throw new ZipError('The archive directory is damaged.')
    if (csize === 0xffffffff || usize === 0xffffffff || offset === 0xffffffff)
      throw new ZipError('ZIP64 archives are not supported.')
    if (diskStart !== 0) throw new ZipError('Multi-part archives are not supported.')
    if (flags & 0x1 || flags & 0x40) throw new ZipError('Encrypted archives are not supported.')
    const nameBytes = bytes.subarray(p + 46, p + 46 + nameLen)
    let name: string
    try {
      name = new TextDecoder('utf-8', { fatal: true }).decode(nameBytes)
    } catch {
      throw new ZipError('The archive contains an entry name that is not valid text.')
    }
    checkEntryName(name)
    const key = name.toLowerCase()
    if (seen.has(key)) throw new ZipError('The archive contains duplicate entry names.')
    seen.add(key)
    // On Unix-made archives the high 16 bits are the file mode: only regular files and folders pass.
    if (madeBy >> 8 === 3) {
      const kind = (external >>> 16) & 0o170000
      if (kind && kind !== 0o100000 && kind !== 0o040000)
        throw new ZipError('The archive contains a link or special file and was refused.')
    }
    const isDir = name.endsWith('/')
    if (isDir && (usize || csize)) throw new ZipError('The archive directory is damaged.')
    if (!isDir) {
      if (method !== 0 && method !== 8) throw new ZipError('The archive uses an unsupported compression method.')
      if (usize > limits.maxEntryBytes) throw new ZipError('An archive entry is too large.')
      if (usize > 1_000_000 && usize > limits.maxRatio * Math.max(csize, 1))
        throw new ZipError('The archive looks like a compression bomb and was refused.')
      if (method === 0 && csize !== usize) throw new ZipError('The archive directory is damaged.')
      declared += usize
      if (declared > limits.maxTotalBytes) throw new ZipError('The archive expands to more than the allowed size.')
    }
    entries.push({ name, method, crc, csize, usize, offset, isDir, nameBytes: nameBytes.slice() })
    p = end
  }
  if (p !== eocd) throw new ZipError('The archive directory is damaged.')

  // Entries must sit before the directory without overlapping, and their local headers must agree.
  const spans: [number, number][] = []
  const located = new Map<Entry, number>()
  for (const e of entries) {
    if (e.isDir) continue
    if (e.offset + 30 > cdOffset || u32(bytes, e.offset) !== 0x04034b50)
      throw new ZipError('The archive is damaged or out of range.')
    const nameLen = u16(bytes, e.offset + 26),
      extraLen = u16(bytes, e.offset + 28)
    const start = e.offset + 30 + nameLen + extraLen
    const localName = bytes.subarray(e.offset + 30, e.offset + 30 + nameLen)
    if (localName.length !== e.nameBytes.length || localName.some((b, i) => b !== e.nameBytes[i]))
      throw new ZipError('The archive entry names are inconsistent and it was refused.')
    if (start + e.csize > cdOffset) throw new ZipError('The archive is damaged or out of range.')
    spans.push([e.offset, start + e.csize])
    located.set(e, start)
  }
  spans.sort((a, b) => a[0] - b[0])
  for (let i = 1; i < spans.length; i++)
    if (spans[i][0] < spans[i - 1][1]) throw new ZipError('The archive entries overlap and it was refused.')

  const out = new Map<string, Uint8Array>()
  for (const e of entries) {
    if (e.isDir) continue
    const start = located.get(e)!
    const raw = bytes.subarray(start, start + e.csize)
    const data = e.method === 0 ? raw.slice() : await inflateRaw(raw, e.usize)
    if (data.length !== e.usize) throw new ZipError('An archive entry does not match its declared size.')
    if (crc32(data) !== e.crc) throw new ZipError('An archive entry is damaged (checksum mismatch).')
    out.set(e.name, data)
  }
  return out
}

/**
 * A deterministic archive: entries stored uncompressed in the given order, 1980-01-01 timestamps,
 * regular-file mode 0644, ASCII names only. Throws for names outside the safe set.
 */
export function writeZip(entries: { name: string; data: Uint8Array }[]): Uint8Array {
  const parts: Uint8Array[] = []
  const central: Uint8Array[] = []
  let offset = 0
  const names = new Set<string>()
  for (const { name, data } of entries) {
    checkEntryName(name)
    if (!/^[\x20-\x7e]+$/.test(name) || name.endsWith('/')) throw new ZipError('Bundle entry names must be plain ASCII file names.')
    if (names.has(name.toLowerCase())) throw new ZipError('Duplicate entry name.')
    names.add(name.toLowerCase())
    if (data.length > 0xfffffffe) throw new ZipError('An entry is too large for this format.')
    const nameBytes = new TextEncoder().encode(name)
    const crc = crc32(data)
    const local = new Uint8Array(30 + nameBytes.length)
    const lv = new DataView(local.buffer)
    lv.setUint32(0, 0x04034b50, true)
    lv.setUint16(4, 20, true) // version needed
    lv.setUint16(6, 0, true) // flags
    lv.setUint16(8, 0, true) // method: stored
    lv.setUint16(10, 0, true) // time
    lv.setUint16(12, 0x0021, true) // date: 1980-01-01
    lv.setUint32(14, crc, true)
    lv.setUint32(18, data.length, true)
    lv.setUint32(22, data.length, true)
    lv.setUint16(26, nameBytes.length, true)
    local.set(nameBytes, 30)
    const head = new Uint8Array(46 + nameBytes.length)
    const hv = new DataView(head.buffer)
    hv.setUint32(0, 0x02014b50, true)
    hv.setUint16(4, 0x0314, true) // made by: Unix, 2.0
    hv.setUint16(6, 20, true)
    hv.setUint16(12, 0, true)
    hv.setUint16(14, 0x0021, true)
    hv.setUint32(16, crc, true)
    hv.setUint32(20, data.length, true)
    hv.setUint32(24, data.length, true)
    hv.setUint16(28, nameBytes.length, true)
    hv.setUint32(38, (0o100644 << 16) >>> 0, true)
    hv.setUint32(42, offset, true)
    head.set(nameBytes, 46)
    parts.push(local, data)
    central.push(head)
    offset += local.length + data.length
  }
  const cdSize = central.reduce((n, c) => n + c.length, 0)
  const end = new Uint8Array(22)
  const ev = new DataView(end.buffer)
  ev.setUint32(0, 0x06054b50, true)
  ev.setUint16(8, entries.length, true)
  ev.setUint16(10, entries.length, true)
  ev.setUint32(12, cdSize, true)
  ev.setUint32(16, offset, true)
  const all = [...parts, ...central, end]
  const out = new Uint8Array(all.reduce((n, c) => n + c.length, 0))
  let at = 0
  for (const c of all) {
    out.set(c, at)
    at += c.length
  }
  return out
}
