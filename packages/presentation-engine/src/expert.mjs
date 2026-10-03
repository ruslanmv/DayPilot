/**
 * Expert mode: a reviewed JavaScript builder writes slides directly with the PptxGenJS API on top
 * of the company's branded layouts. It only ever runs inside the sandbox (bin/expert.mjs, started
 * by the server with no network, no credentials, read-only inputs and an ephemeral output folder).
 *
 *   export default async function build(deck) {
 *     const s = deck.addSlide('content')            // 'title' | 'section' | 'content' | 'quote' | 'closing'
 *     s.addText('Revenue grew 12%', { ...deck.box(0.6, 0.5, 12.1, 1), fontFace: deck.fonts.heading, fontSize: 32, bold: true, color: deck.color.foreground })
 *     s.addChart(deck.charts.bar, [{ name: 'Revenue', labels: ['Q1', 'Q2'], values: [10, 12] }], { ...deck.box(0.6, 1.8, 8, 4.8), chartColors: deck.seriesColors })
 *     s.addNotes('Speaker guidance and sources.')
 *   }
 */
import PptxGenJS from 'pptxgenjs'
import JSZip from 'jszip'
import { hex, seriesColors, tint, validateBrandKit, contrast } from './brand.mjs'
import { finish, makeMasters } from './compile.mjs'
import { M } from './compose.mjs'

const KINDS = { title: 'cover', section: 'section', content: 'bullets', quote: 'quote', closing: 'closing' }
export const MAX_EXPERT_SLIDES = 50

export async function runExpert(build, kit, assets = {}) {
  validateBrandKit(kit)
  const W = kit.slide_size.width_inches, H = kit.slide_size.height_inches
  const pal = Object.fromEntries(Object.entries(kit.palette).map(([k, v]) => [k, hex(v)]))
  const pres = new PptxGenJS()
  pres.defineLayout({ name: 'DAYPILOT', width: W, height: H })
  pres.layout = 'DAYPILOT'
  pres.theme = { headFontFace: kit.typography.slide_title.family, bodyFontFace: kit.typography.body.family }
  pres.title = 'Expert build'
  pres.author = 'DayPilot Presentations (expert)'
  const masterFor = makeMasters(pres, kit, assets, W, H, pal)
  let count = 0
  const deck = Object.freeze({
    pres,
    size: { w: W, h: H },
    margin: M,
    color: { ...pal, primaryTint: tint(pal.primary, 0.92), accentTint: tint(pal.accent, 0.88) },
    fonts: { heading: kit.typography.slide_title.family, body: kit.typography.body.family },
    sizes: Object.fromEntries(Object.entries(kit.typography).map(([k, v]) => [k, { min: v.minimum_pt, preferred: v.preferred_pt }])),
    seriesColors: seriesColors(kit),
    shapes: pres.ShapeType,
    charts: pres.ChartType,
    readable: (fg, bg) => contrast(fg, bg) >= 4.5,
    box: (x, y, w, h) => ({ x, y, w, h }),
    addSlide(kind = 'content') {
      if (!KINDS[kind]) throw new Error(`addSlide kind must be one of ${Object.keys(KINDS).join(', ')}`)
      if (++count > MAX_EXPERT_SLIDES) throw new Error(`at most ${MAX_EXPERT_SLIDES} slides`)
      return pres.addSlide({ masterName: masterFor(KINDS[kind]).name })
    },
  })
  await build(deck)
  if (!count) throw new Error('the builder added no slides')
  let buf = await pres.write({ outputType: 'nodebuffer', compression: true })
  buf = await finish(buf, kit, { slides: [] })
  return buf
}

const EMU = 914400
/** Checks that need no scene graph: geometry from the file, fonts, colours, notes, active content. */
export async function checkExpert(buf, kit, inspection) {
  const zip = await JSZip.loadAsync(buf)
  const W = kit.slide_size.width_inches, H = kit.slide_size.height_inches
  const findings = []
  const add = (severity, code, slide, message) => findings.push({ severity, code, slide, message })
  const allowed = new Set(kit.allowed_fonts ?? [])
  const brandHex = new Set(Object.values(kit.palette).map(hex))
  inspection.slides.forEach((s, i) => {
    if (!s.notes.trim()) add('warning', 'notes', `slide${i + 1}`, `Slide ${i + 1} has no speaker notes.`)
    if (!s.text.trim() && !s.charts.length && !s.tables && !s.pictures) add('hard', 'empty_slide', `slide${i + 1}`, `Slide ${i + 1} has no content.`)
  })
  for (const [i, s] of inspection.slides.entries()) {
    const xml = await zip.file(s.part).async('string')
    for (const m of xml.matchAll(/<a:off x="(-?\d+)" y="(-?\d+)"\/><a:ext cx="(\d+)" cy="(\d+)"\/>/g)) {
      const [x, y, w, h] = m.slice(1).map((v) => Number(v) / EMU)
      if (x < -0.01 || y < -0.01 || x + w > W + 0.01 || y + h > H + 0.01) add('hard', 'off_slide', `slide${i + 1}`, `Slide ${i + 1}: an object extends past the slide edge.`)
    }
    for (const m of xml.matchAll(/<a:latin typeface="([^"]+)"/g))
      if (allowed.size && !allowed.has(m[1]) && !m[1].startsWith('+')) add('hard', 'brand_font', `slide${i + 1}`, `Slide ${i + 1} uses ${m[1]}, which the brand does not allow.`)
    const off = [...new Set([...xml.matchAll(/<a:srgbClr val="([0-9A-Fa-f]{6})"/g)].map((m) => m[1].toUpperCase()))].filter((c) => !brandHex.has(c) && !['FFFFFF', '000000'].includes(c) && ![...brandHex].some((b) => [0.86, 0.88, 0.9, 0.92, 0.93, 0.94, 0.14].some((t) => tint(b, t) === c)))
    if (off.length) add('warning', 'off_palette', `slide${i + 1}`, `Slide ${i + 1} uses colours outside the brand palette: ${off.slice(0, 5).join(', ')}.`)
  }
  if (inspection.hasMacros) add('hard', 'active_content', null, 'The file contains macros.')
  if (inspection.externalLinks) add('hard', 'external_links', null, 'The file links to external resources.')
  add('warning', 'expert_limits', null, 'Expert build: text fit and overlap are checked on the rendered slides only, not measured. Review every slide.')
  const hard = findings.filter((f) => f.severity === 'hard').length
  return { schema_version: 'daypilot.quality-receipt/v1', engine: 'expert', slides_checked: inspection.slides.length, checks: ['geometry', 'fonts', 'palette', 'notes', 'active_content'], findings, hard_failures: hard, warnings: findings.length - hard, status: hard ? 'failed' : 'passed' }
}
