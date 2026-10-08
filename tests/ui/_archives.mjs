/**
 * Archive builders for the bundle tests. `craft` writes a ZIP byte by byte so one field at a time can
 * be falsified; `hostileArchives` lists archives every reader must refuse. The same archives are
 * written to packages/dmind-contract/archive-cases.json (see gen-archive-corpus.mjs) so the Python
 * reader in Matrix Designer is held to exactly the same cases.
 */
import zlib from 'node:zlib'

export function archiveTools(m) {
  const crc32 = m.zip.crc32
  /** Build an archive byte by byte so individual fields can be falsified. */
  function craft(entries, { comment = 0, tail = 0, cdOffsetDelta = 0, total } = {}) {
    const parts = [],
      central = []
    let offset = 0
    for (const e of entries) {
      const nameBytes = Buffer.isBuffer(e.name) ? e.name : Buffer.from(e.name)
      const data = Buffer.from(e.data ?? '')
      const method = e.method ?? 0
      const body = method === 8 && e.deflate !== false ? zlib.deflateRawSync(data) : data
      const crc = e.crc ?? crc32(data)
      const csize = e.csize ?? body.length,
        usize = e.usize ?? data.length
      const localName = e.localName ? Buffer.from(e.localName) : nameBytes
      const at = e.offset ?? offset
      const l = Buffer.alloc(30)
      l.writeUInt32LE(0x04034b50, 0)
      l.writeUInt16LE(20, 4)
      l.writeUInt16LE(e.flags ?? 0, 6)
      l.writeUInt16LE(method, 8)
      l.writeUInt16LE(0x21, 12)
      l.writeUInt32LE(crc, 14)
      l.writeUInt32LE(csize >>> 0, 18)
      l.writeUInt32LE(usize >>> 0, 22)
      l.writeUInt16LE(localName.length, 26)
      parts.push(l, localName, body)
      const c = Buffer.alloc(46)
      c.writeUInt32LE(0x02014b50, 0)
      c.writeUInt16LE(e.madeBy ?? 0x0314, 4)
      c.writeUInt16LE(20, 6)
      c.writeUInt16LE(e.flags ?? 0, 8)
      c.writeUInt16LE(method, 10)
      c.writeUInt16LE(0x21, 14)
      c.writeUInt32LE(crc, 16)
      c.writeUInt32LE(csize >>> 0, 20)
      c.writeUInt32LE(usize >>> 0, 24)
      c.writeUInt16LE(nameBytes.length, 28)
      c.writeUInt16LE(e.diskStart ?? 0, 34)
      c.writeUInt32LE(e.external ?? (0o100644 << 16) >>> 0, 38)
      c.writeUInt32LE(at >>> 0, 42)
      central.push(c, nameBytes)
      offset += 30 + localName.length + body.length
    }
    const cd = Buffer.concat(central)
    const end = Buffer.alloc(22)
    end.writeUInt32LE(0x06054b50, 0)
    end.writeUInt16LE(total ?? entries.length, 8)
    end.writeUInt16LE(total ?? entries.length, 10)
    end.writeUInt32LE(cd.length, 12)
    end.writeUInt32LE(offset + cdOffsetDelta, 16)
    end.writeUInt16LE(comment, 20)
    return new Uint8Array(Buffer.concat([...parts, cd, end, Buffer.alloc(tail, 0x41)]))
  }

  const good = craft([
    { name: 'a.txt', data: 'hello' },
    { name: 'dir/', data: '' },
    { name: 'dir/b.txt', data: 'world', method: 8 },
  ])

  /** [label, archive, message pattern, optional limits override] */
  const hostile = []
  const add = (label, archive, pattern, limits) => hostile.push([label, archive, pattern, limits])
  for (const [label, name] of [
    ['parent traversal', '../evil'],
    ['nested traversal', 'a/../../evil'],
    ['absolute path', '/etc/passwd'],
    ['drive letter', 'C:/x'],
    ['backslash', 'a\\b'],
    ['dot segment', './x'],
    ['empty segment', 'a//b'],
    ['control character', 'a\u0001b'],
    ['name too long', 'n'.repeat(201)],
  ])
    add(label, craft([{ name, data: 'x' }]), /unsafe entry name|invalid name/)
  add('invalid UTF-8 name', craft([{ name: Buffer.from([0x61, 0xff, 0xfe]), data: 'x' }]), /not valid text/)
  add('duplicate names', craft([{ name: 'a', data: '1' }, { name: 'a', data: '2' }]), /duplicate/)
  add('duplicate names differing by case', craft([{ name: 'a.txt', data: '1' }, { name: 'A.TXT', data: '2' }]), /duplicate/)
  add('symlink', craft([{ name: 'link', data: '/etc/passwd', external: (0o120777 << 16) >>> 0 }]), /link or special/)
  add('device file', craft([{ name: 'dev', data: '', external: (0o020644 << 16) >>> 0 }]), /link or special/)
  add('encrypted', craft([{ name: 'a', data: 'x', flags: 1 }]), /Encrypted/)
  add('strong encryption', craft([{ name: 'a', data: 'x', flags: 0x40 }]), /Encrypted/)
  add('unsupported method', craft([{ name: 'a', data: 'x', method: 12 }]), /unsupported compression/)
  add('zip64 sizes', craft([{ name: 'a', data: 'x', csize: 0xffffffff, usize: 0xffffffff }]), /ZIP64/)
  add('multi-part', craft([{ name: 'a', data: 'x', diskStart: 1 }]), /Multi-part/)
  add('directory with data', craft([{ name: 'd/', data: 'x' }]), /directory is damaged/)
  add('stored size mismatch', craft([{ name: 'a', data: 'hello', usize: 3 }]), /damaged/)
  add('inflates larger than declared', craft([{ name: 'a', data: 'x'.repeat(5000), method: 8, usize: 10 }]), /larger than it declares/)
  add('inflates smaller than declared', craft([{ name: 'a', data: 'xx', method: 8, usize: 100 }]), /smaller than it declares/)
  add('bad checksum', craft([{ name: 'a', data: 'hello', crc: 1234 }]), /checksum/)
  add('corrupt deflate stream', craft([{ name: 'a', data: Buffer.from([0xff, 0xff, 0xff, 0xff]), method: 8, deflate: false, usize: 40 }]), /could not be decompressed|smaller than|larger than/)
  add('compression bomb (ratio)', craft([{ name: 'a', data: Buffer.alloc(9_000_000), method: 8 }]), /compression bomb/)
  add('entry over the size limit', craft([{ name: 'a', data: 'x', method: 8, usize: 11_000_000, csize: 10 }]), /too large/)
  add('total over the limit', craft(Array.from({ length: 7 }, (_, i) => ({ name: 'f' + i, data: 'x', usize: 9_000_000, csize: 9_000_000, method: 0, crc: 0 }))), /allowed size|damaged/)
  add('too many entries', craft(Array.from({ length: 201 }, (_, i) => ({ name: 'f' + i, data: '' }))), /more than 200 entries/)
  add('local name differs from the directory', craft([{ name: 'safe.txt', data: 'x', localName: 'other.txt' }]), /inconsistent/)
  add('entry data runs into the next entry', craft([{ name: 'a', data: 'xx', csize: 10, usize: 10 }, { name: 'b', data: 'yy' }]), /overlap/)
  add('offset beyond the directory', craft([{ name: 'a', data: 'x', offset: 5000 }]), /damaged or out of range/)
  add('directory offset wrong', craft([{ name: 'a', data: 'x' }], { cdOffsetDelta: 3 }), /directory is damaged/)
  add('entry count wrong', craft([{ name: 'a', data: 'x' }], { total: 2 }), /directory is damaged/)
  add('trailing bytes after the end record', craft([{ name: 'a', data: 'x' }], { tail: 7 }), /not a valid ZIP/)
  add('truncated', good.slice(0, good.length - 10), /not a valid ZIP/)
  add('too short', new Uint8Array(10), /not a valid ZIP/)
  add('not a zip', new TextEncoder().encode('this is plainly not an archive at all, just text'), /not a valid ZIP/)
  add('empty archive', Uint8Array.from([0x50, 0x4b, 5, 6, ...new Array(18).fill(0)]), /empty/)

  return { craft, good, hostile }
}

import crypto from 'node:crypto'
export const PNG = Uint8Array.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 13, 73, 72, 68, 82, 0, 0, 0, 1, 0, 0, 0, 1, 8, 6, 0, 0, 0, 31, 21, 196, 137])
export const PDF = new TextEncoder().encode('%PDF-1.4\n%fake body\n')
export const sha256 = (b) => crypto.createHash('sha256').update(b).digest('hex')

/** A real bundle (one PNG, one PDF) and the tampered variants every reader must refuse. */
export async function bundleTools(m) {
  const { assets: A, bundle: Bn, dmind, zip: z } = m
  const bytes = (s) => new TextEncoder().encode(s)
  const base = dmind.fromOutline('Spec', 'Design\nBuild', 'mindmap')
  const a1 = await A.attachFile(base, 'n1', { name: 'sketch.png', bytes: PNG })
  const a2 = await A.attachFile(a1.diagram, 'n2', { name: 'brief.pdf', bytes: PDF })
  const store = new Map([
    [a1.ref, a1.data],
    [a2.ref, a2.data],
  ])
  const doc = a2.diagram
  const packed = await Bn.packBundle(doc, store)
  const files = await z.readZip(packed)
  const pngPath = `assets/${sha256(PNG)}.png`
  const pdfPath = `assets/${sha256(PDF)}.pdf`

  /** Re-pack the genuine bundle after `mutate(files, manifest)` changed it. */
  const tamper = (mutate) => {
    const f = new Map(files)
    const mf = JSON.parse(new TextDecoder().decode(f.get('manifest.json')))
    const out = mutate(f, mf) ?? { f, mf }
    return z.writeZip([
      { name: 'manifest.json', data: bytes(JSON.stringify(out.mf, null, 2) + '\n') },
      ...[...out.f].filter(([n]) => n !== 'manifest.json').map(([name, data]) => ({ name, data })),
    ])
  }
  const setDocument = (f, mf, text) => {
    const data = bytes(text)
    f.set('document.json', data)
    mf.document = { bytes: data.length, path: 'document.json', sha256: sha256(data) }
  }
  const pngEntry = (mf) => mf.assets.find((a) => a.type === 'image/png')
  /** [label, archive bytes, message pattern] */
  const cases = [
    ['wrong document hash', tamper((f, mf) => { mf.document.sha256 = '0'.repeat(64) }), /document does not match its manifest/],
    ['wrong document size', tamper((f, mf) => { mf.document.bytes += 1 }), /document does not match its manifest/],
    ['edited document', tamper((f) => { f.set('document.json', bytes(new TextDecoder().decode(f.get('document.json')).replace('Spec', 'Spoof'))) }), /document does not match its manifest/],
    ['wrong asset hash', tamper((f, mf) => { const a = pngEntry(mf); a.sha256 = '0'.repeat(64); a.path = `assets/${'0'.repeat(64)}.png` }), /missing an attachment|does not match/],
    ['edited asset bytes', tamper((f) => { f.set(pngPath, Uint8Array.from([...PNG.slice(0, -1), 1])) }), /does not match its recorded hash/],
    ['asset claims another type', tamper((f, mf) => { pngEntry(mf).type = 'application/pdf' }), /unexpected attachment path|not the type it claims/],
    ['disallowed type', tamper((f, mf) => { pngEntry(mf).type = 'image/svg+xml' }), /type that is not allowed/],
    ['path outside assets', tamper((f, mf) => { pngEntry(mf).path = '../evil.png' }), /unexpected attachment path/],
    ['size mismatch', tamper((f, mf) => { pngEntry(mf).bytes += 1 }), /does not match its manifest|recorded hash/],
    ['listed asset missing', tamper((f) => { f.delete(pngPath) }), /missing an attachment/],
    ['unlisted file', tamper((f) => { f.set('assets/extra.txt', bytes('hi')) }), /unlisted file/],
    ['script file', tamper((f) => { f.set('evil.html', bytes('<script>')) }), /unlisted file/],
    ['missing manifest', z.writeZip([{ name: 'document.json', data: files.get('document.json') }]), /not a dmind bundle/],
    ['missing document', tamper((f) => { f.delete('document.json') }), /not a dmind bundle/],
    ['unsupported format', tamper((f, mf) => { mf.format = 'dmind-bundle/v9' }), /unsupported format/],
    ['manifest not an object', tamper((f) => ({ f, mf: [] })), /unsupported format/],
    ['too many assets', tamper((f, mf) => { mf.assets = Array.from({ length: 51 }, () => mf.assets[0]) }), /can hold 50/],
    ['invalid asset entry', tamper((f, mf) => { mf.assets[0] = { path: 5 } }), /invalid attachment/],
    ['document that fails the contract', tamper((f, mf) => setDocument(f, mf, JSON.stringify({ schema_version: 'dmind/v1' }))), /./],
    ['document not JSON', tamper((f, mf) => setDocument(f, mf, '{nope')), /not valid JSON/],
    ['manifest not JSON', z.writeZip([{ name: 'manifest.json', data: bytes('{') }, { name: 'document.json', data: bytes('{}') }]), /manifest is not valid/],
  ]
  void pdfPath
  return { doc, store, packed, files, cases, a1, a2 }
}
