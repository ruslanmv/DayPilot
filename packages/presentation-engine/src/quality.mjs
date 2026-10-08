/**
 * Quality gate over what was actually produced: the compiler's scene graph (exact geometry, sizes
 * and colours it placed) and the exported file's own contents. Every slide is checked. Hard
 * findings block "review ready"; the receipt is bound to the exact PPTX bytes.
 */
import { contrast, hex, themeColors } from './brand.mjs'
import { M } from './compose.mjs'

const CONTENT = new Set(['text', 'chart', 'table', 'image', 'diagram'])
const area = (b) => Math.max(0, b.w) * Math.max(0, b.h)
function intersect(a, b) {
  const x = Math.max(a.x, b.x), y = Math.max(a.y, b.y)
  const w = Math.min(a.x + a.w, b.x + b.w) - x, h = Math.min(a.y + a.h, b.y + b.h) - y
  return w > 0 && h > 0 ? w * h : 0
}
const within = (inner, outer, slack = 0.01) => inner.x >= outer.x - slack && inner.y >= outer.y - slack && inner.x + inner.w <= outer.x + outer.w + slack && inner.y + inner.h <= outer.y + outer.h + slack

export function checkDeck({ deck, kit, scene, inspection, pptxSha256 }) {
  const findings = []
  const add = (severity, code, slide, message, element) => findings.push({ severity, code, slide, ...(element ? { element } : {}), message })
  const W = scene.slide_size.w, H = scene.slide_size.h
  const checks = []
  const ran = (name) => checks.push(name)

  ran('slide_count')
  if (inspection.slides.length !== deck.slides.length) add('hard', 'slide_count', null, `The file has ${inspection.slides.length} slides; the deck has ${deck.slides.length}.`)
  if (deck.slide_count?.exact !== undefined && deck.slide_count.exact !== inspection.slides.length) add('hard', 'slide_count', null, `Requested exactly ${deck.slide_count.exact} slides; produced ${inspection.slides.length}.`)

  ran('geometry'); ran('text_fit'); ran('contrast'); ran('logo'); ran('native_objects'); ran('notes'); ran('accessibility')
  const titles = new Map()
  scene.slides.forEach((s, i) => {
    const spec = deck.slides[i]
    const file = inspection.slides[i]
    const fixed = [...s.derived.map((d) => ({ ...d, derived: true })), ...(s.number ? [{ id: 'page_number', kind: 'text', box: s.number, derived: true }] : [])]
    const objs = [...s.objects, ...fixed]
    const diagrams = s.objects.filter((o) => o.kind === 'diagram').map((o) => o.box)
    for (const o of objs) {
      const b = o.box
      if (b.x < -0.01 || b.y < -0.01 || b.x + b.w > W + 0.01 || b.y + b.h > H + 0.01) {
        if (!o.allowOverlap && o.kind !== 'decoration') add('hard', 'off_slide', s.id, `${o.id} extends past the slide edge.`, o.id)
      } else if (!o.derived && CONTENT.has(o.kind) && (b.x < M - 0.05 || b.y < 0.3 || b.x + b.w > W - M + 0.05 || b.y + b.h > H - 0.6))
        add('warning', 'safe_area', s.id, `${o.id} is outside the ${M}-inch safe area.`, o.id)
      if (o.kind === 'text' && o.fits === false) add('hard', 'text_overflow', s.id, `Text in ${o.id} does not fit at ${o.pt} pt.`, o.id)
      if (o.kind === 'text' && o.pt !== undefined && o.minPt !== undefined && o.pt < o.minPt) add('hard', 'below_minimum', s.id, `${o.id} is ${o.pt} pt, below the ${o.minPt} pt minimum.`, o.id)
      if (o.kind === 'text' && o.verified === false) add('warning', 'fit_unverified', s.id, `${o.font} has no installed metrics; fit is estimated.`, o.id)
      if (o.kind === 'text' && o.color && o.bg) {
        const ratio = contrast(o.color, o.bg)
        const large = (o.pt ?? 0) >= 18
        const need = large ? 3 : 4.5
        if (ratio < 3) add('hard', 'contrast', s.id, `${o.id}: contrast ${ratio.toFixed(1)}:1 is unreadable.`, o.id)
        else if (ratio < need) add('warning', 'contrast', s.id, `${o.id}: contrast ${ratio.toFixed(1)}:1 is below ${need}:1.`, o.id)
      }
      if (o.kind === 'image' && o.expected_aspect && Math.abs(o.aspect / o.expected_aspect - 1) > 0.02)
        add('hard', 'distorted_image', s.id, `${o.id === 'logo' ? 'The logo' : o.id} is stretched (${o.aspect.toFixed(2)} vs ${o.expected_aspect.toFixed(2)}).`, o.id)
    }
    // incidental overlap between content objects, and between content and footer/logo/page number
    const solid = objs.filter((o) => CONTENT.has(o.kind) && !o.allowOverlap && !(o.kind !== 'diagram' && diagrams.some((d) => within(o.box, d))) && area(o.box) > 0)
    for (let a = 0; a < solid.length; a++)
      for (let b = a + 1; b < solid.length; b++) {
        const x = solid[a], y = solid[b]
        const ov = intersect(x.box, y.box)
        if (ov > 0.02 && ov > 0.03 * Math.min(area(x.box), area(y.box)))
          add(x.derived || y.derived ? 'hard' : 'hard', 'overlap', s.id, `${x.id} overlaps ${y.id}.`, x.id)
      }
    // native objects really are in the file
    for (const e of spec.elements) {
      if (e.kind === 'chart' && !file.charts.some((c) => c.series === e.series.length)) add('hard', 'not_native', s.id, `${e.id} is not a native chart with ${e.series.length} series in the file.`, e.id)
      if (e.kind === 'table' && file.tables < 1) add('hard', 'not_native', s.id, `${e.id} is not a native table in the file.`, e.id)
      if (e.kind === 'diagram' && !e.nodes.every((n) => file.names.includes(`${e.id}__node__${n.id}`))) add('hard', 'not_native', s.id, `${e.id}: not every node is an editable shape.`, e.id)
      if ((e.kind === 'chart' || e.kind === 'table' || e.kind === 'image' || e.kind === 'diagram') && !String(e.alt_text ?? '').trim()) add('hard', 'alt_text', s.id, `${e.id} has no alternative text.`, e.id)
    }
    if (!file.notes.trim()) add('warning', 'notes', s.id, 'The slide has no speaker notes.')
    const t = spec.title.trim().toLowerCase()
    if (titles.has(t)) add('warning', 'duplicate_title', s.id, `Same title as slide ${titles.get(t) + 1}; screen-reader users navigate by title.`)
    titles.set(t, i)
  })

  ran('brand')
  const theme = themeColors(kit)
  for (const [k, v] of Object.entries(theme)) if (inspection.themeColors[k] !== v) add('hard', 'brand_theme', null, `Theme colour ${k} is ${inspection.themeColors[k]}, expected ${v}.`)
  const allowed = new Set(kit.allowed_fonts ?? [])
  if (allowed.size) for (const f of inspection.fonts) if (!allowed.has(f)) add('hard', 'brand_font', null, `Font ${f} is not allowed by the brand kit.`)
  if (kit.footer?.required && kit.footer.text && scene.slides.some((s, i) => i > 0 && !s.derived.some((d) => d.id === 'footer'))) add('hard', 'footer', null, 'A required footer is missing from a slide.')
  if (inspection.hasMacros) add('hard', 'active_content', null, 'The file contains macros.')
  if (inspection.externalLinks) add('hard', 'external_links', null, 'The file links to external resources.')

  ran('evidence')
  const metrics = new Map()
  for (const src of deck.sources ?? []) for (const m of src.metrics ?? []) metrics.set(`${src.id}/${m.id}`, m)
  for (const s of deck.slides)
    for (const c of s.claims ?? []) {
      if (!c.metric_ref) continue
      const m = metrics.get(`${c.metric_ref.source_snapshot_id}/${c.metric_ref.metric_id}`)
      if (!m) add('hard', 'evidence', s.id, `Claim ${c.id} cites a missing metric.`)
      else if (typeof c.numeric_value === 'number' && c.numeric_value !== m.value) add('hard', 'evidence', s.id, `Claim ${c.id} says ${c.numeric_value}; the source says ${m.value}.`)
      else if (c.unit && m.unit && c.unit !== m.unit) add('hard', 'evidence', s.id, `Claim ${c.id} uses ${c.unit}; the source uses ${m.unit}.`)
    }

  const hard = findings.filter((f) => f.severity === 'hard').length
  return {
    schema_version: 'daypilot.quality-receipt/v1',
    pptx_sha256: pptxSha256,
    engine: scene.engine,
    slides_checked: scene.slides.length,
    checks,
    findings,
    hard_failures: hard,
    warnings: findings.length - hard,
    status: hard ? 'failed' : 'passed',
  }
}
export { hex }
