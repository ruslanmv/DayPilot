/**
 * Dev-time generator for src/metrics/fonts.json: advance widths (per 1000 em) of the fonts the
 * render worker ships, read straight from their TrueType files. Metric-compatible pairs share
 * widths with the Office fonts named in decks (Liberation Sans = Arial, Carlito = Calibri, ...).
 * Run: node src/metrics/gen-metrics.mjs (needs the fonts installed; see implementation-plan.md).
 */
import fs from 'node:fs'

const FONTS = {
  Arial: 'liberation/LiberationSans', 'Times New Roman': 'liberation/LiberationSerif', 'Courier New': 'liberation/LiberationMono',
  Calibri: 'crosextra/Carlito', Cambria: 'crosextra/Caladea',
}
const RANGES = [[0x20, 0x7e], [0xa0, 0x17f], [0x2010, 0x2027], [0x2030, 0x203a], [0x20ac, 0x20ac], [0x2122, 0x2122], [0x2190, 0x2193], [0x2212, 0x2212]]

function table(buf, tag) {
  const n = buf.readUInt16BE(4)
  for (let i = 0; i < n; i++) {
    const p = 12 + i * 16
    if (buf.toString('latin1', p, p + 4) === tag) return buf.readUInt32BE(p + 8)
  }
  throw new Error('no table ' + tag)
}
function cmap4(buf) {
  const base = table(buf, 'cmap')
  const n = buf.readUInt16BE(base + 2)
  for (let i = 0; i < n; i++) {
    const pid = buf.readUInt16BE(base + 4 + i * 8), eid = buf.readUInt16BE(base + 6 + i * 8)
    const off = base + buf.readUInt32BE(base + 8 + i * 8)
    if (pid === 3 && eid === 1 && buf.readUInt16BE(off) === 4) {
      const segX2 = buf.readUInt16BE(off + 6)
      const ends = off + 14, starts = ends + segX2 + 2, deltas = starts + segX2, ranges = deltas + segX2
      return (cp) => {
        for (let s = 0; s < segX2 / 2; s++) {
          const end = buf.readUInt16BE(ends + s * 2)
          if (cp > end) continue
          const start = buf.readUInt16BE(starts + s * 2)
          if (cp < start) return 0
          const delta = buf.readInt16BE(deltas + s * 2), ro = buf.readUInt16BE(ranges + s * 2)
          if (!ro) return (cp + delta) & 0xffff
          const g = buf.readUInt16BE(ranges + s * 2 + ro + (cp - start) * 2)
          return g ? (g + delta) & 0xffff : 0
        }
        return 0
      }
    }
  }
  throw new Error('no cmap 3/1 format 4')
}
function widths(file) {
  const buf = fs.readFileSync(file)
  const upem = buf.readUInt16BE(table(buf, 'head') + 18)
  const nh = buf.readUInt16BE(table(buf, 'hhea') + 34)
  const hmtx = table(buf, 'hmtx')
  const glyph = cmap4(buf)
  const adv = (g) => buf.readUInt16BE(hmtx + Math.min(g, nh - 1) * 4)
  const out = {}
  for (const [a, b] of RANGES)
    for (let cp = a; cp <= b; cp++) {
      const g = glyph(cp)
      if (g) out[cp] = Math.round((adv(g) * 1000) / upem)
    }
  return out
}
const result = {}
for (const [name, path] of Object.entries(FONTS))
  result[name] = {
    regular: widths(`/usr/share/fonts/truetype/${path}-Regular.ttf`),
    bold: widths(`/usr/share/fonts/truetype/${path}-Bold.ttf`),
  }
fs.writeFileSync(new URL('./fonts.json', import.meta.url), JSON.stringify(result))
console.log(Object.keys(result).map((k) => `${k}: ${Object.keys(result[k].regular).length} glyphs`).join('\n'))
