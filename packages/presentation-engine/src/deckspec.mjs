/**
 * Semantic validation of a DeckSpec (daypilot.deck-spec/v1) beyond what JSON Schema can express:
 * unique stable ids, normalized bounds inside the slide, exact slide count, chart/table/diagram
 * integrity and metric references that resolve to a source snapshot.
 */
import { SpecError } from './brand.mjs'

const ID = /^[A-Za-z0-9_-]{1,120}$/
const KINDS = ['text', 'chart', 'table', 'diagram', 'image']
const ROLES = ['deck_title', 'slide_title', 'body', 'data', 'footnote']

function inside(b) {
  return b && [b.x, b.y, b.w, b.h].every((v) => Number.isFinite(v)) && b.x >= 0 && b.y >= 0 && b.w > 0 && b.h > 0 && b.x + b.w <= 1.0001 && b.y + b.h <= 1.0001
}

export function validateDeck(deck, kit) {
  const p = []
  if (!deck || typeof deck !== 'object') throw new SpecError(['deck must be an object'])
  if (deck.schema_version !== 'daypilot.deck-spec/v1') p.push('schema_version must be daypilot.deck-spec/v1')
  if (typeof deck.title !== 'string' || !deck.title.trim() || deck.title.length > 200) p.push('title: 1-200 characters')
  if (kit && (deck.slide_size?.width_inches !== kit.slide_size.width_inches || deck.slide_size?.height_inches !== kit.slide_size.height_inches))
    p.push('slide_size must equal the brand kit slide size')
  if (kit && deck.company_id !== kit.company_id) p.push('deck and brand kit belong to different companies')
  const slides = Array.isArray(deck.slides) ? deck.slides : []
  if (!slides.length || slides.length > 50) p.push('slides: 1-50')
  const count = deck.slide_count ?? {}
  if (count.exact !== undefined && count.exact !== slides.length) p.push(`slide_count.exact is ${count.exact} but the deck has ${slides.length} slides`)
  if (count.minimum !== undefined && slides.length < count.minimum) p.push(`fewer than ${count.minimum} slides`)
  if (count.maximum !== undefined && slides.length > count.maximum) p.push(`more than ${count.maximum} slides`)
  const metrics = new Map()
  for (const s of deck.sources ?? []) for (const m of s.metrics ?? []) metrics.set(`${s.id}/${m.id}`, m)
  const resolves = (ref) => !ref || metrics.has(`${ref.source_snapshot_id}/${ref.metric_id}`)
  const ids = new Set()
  const seen = (id, w) => {
    if (!ID.test(id ?? '')) p.push(`${w}: invalid id`)
    else if (ids.has(id)) p.push(`${w}: duplicate id ${id}`)
    ids.add(id)
  }
  slides.forEach((s, i) => {
    const w = `slide ${i + 1}`
    seen(s.id, w)
    if (typeof s.layout_id !== 'string' || !s.layout_id) p.push(`${w}: layout_id required`)
    if (typeof s.title !== 'string' || !s.title.trim()) p.push(`${w}: title required (it is the slide's accessible name)`)
    if (typeof s.notes?.speaker_text !== 'string') p.push(`${w}: notes.speaker_text required`)
    if ((s.elements ?? []).length > 100) p.push(`${w}: more than 100 elements`)
    for (const c of s.claims ?? []) if (!resolves(c.metric_ref)) p.push(`${w}: claim ${c.id} cites a metric that is not in the sources`)
    for (const e of s.elements ?? []) {
      const ew = `${w} ${e.id}`
      seen(e.id, ew)
      if (!KINDS.includes(e.kind)) p.push(`${ew}: unknown kind`)
      if (!inside(e.bounds)) p.push(`${ew}: bounds must be inside the slide`)
      if (e.kind === 'text') {
        if (!ROLES.includes(e.role)) p.push(`${ew}: unknown role`)
        if (typeof e.text !== 'string' || e.text.length > 8000) p.push(`${ew}: text required (≤ 8000)`)
      }
      if (e.kind === 'chart') {
        if (!['bar', 'column', 'line', 'area', 'scatter'].includes(e.chart_type)) p.push(`${ew}: unsupported chart type`)
        if (!Array.isArray(e.categories) || !e.categories.length) p.push(`${ew}: categories required`)
        if (!Array.isArray(e.series) || !e.series.length || e.series.length > 12) p.push(`${ew}: 1-12 series`)
        for (const se of e.series ?? []) {
          if ((se.points ?? []).length !== (e.categories ?? []).length) p.push(`${ew}: series ${se.name} needs one point per category`)
          for (const pt of se.points ?? []) {
            if (!(pt.value === null || Number.isFinite(pt.value))) p.push(`${ew}: chart values must be numbers (null for missing)`)
            if (!resolves(pt.metric_ref)) p.push(`${ew}: a point cites a metric that is not in the sources`)
            const m = pt.metric_ref && metrics.get(`${pt.metric_ref.source_snapshot_id}/${pt.metric_ref.metric_id}`)
            if (m && m.value !== pt.value) p.push(`${ew}: a point shows ${pt.value} but its source says ${m.value}`)
          }
        }
        if (typeof e.alt_text !== 'string' || !e.alt_text.trim()) p.push(`${ew}: alt_text required`)
        if (e.chart_type === 'scatter' && !(e.categories ?? []).every((c) => Number.isFinite(Number(c)))) p.push(`${ew}: scatter categories must be numbers`)
      }
      if (e.kind === 'table') {
        if (!Array.isArray(e.headers) || e.headers.length < 1 || e.headers.length > 15) p.push(`${ew}: 1-15 headers`)
        for (const r of e.rows ?? []) {
          if (!Array.isArray(r) || r.length !== e.headers.length) p.push(`${ew}: every row needs one cell per header`)
          for (const c of r ?? []) {
            if (!resolves(c?.metric_ref)) p.push(`${ew}: a cell cites a metric that is not in the sources`)
            const m = c?.metric_ref && metrics.get(`${c.metric_ref.source_snapshot_id}/${c.metric_ref.metric_id}`)
            if (m && m.value !== c.value) p.push(`${ew}: a cell shows ${c.value} but its source says ${m.value}`)
          }
        }
      }
      if (e.kind === 'diagram') {
        const nodes = new Set()
        for (const n of e.nodes ?? []) {
          if (!ID.test(n.id ?? '') || nodes.has(n.id)) p.push(`${ew}: node ids must be unique`)
          nodes.add(n.id)
          if (!inside(n.bounds)) p.push(`${ew}: node ${n.id} must be inside the diagram`)
          if (typeof n.label !== 'string' || !n.label.trim()) p.push(`${ew}: node ${n.id} needs a label`)
        }
        for (const ed of e.edges ?? []) if (!nodes.has(ed.from) || !nodes.has(ed.to)) p.push(`${ew}: edge ${ed.id} must connect listed nodes`)
        if ((e.nodes ?? []).length > 24) p.push(`${ew}: more than 24 nodes is not readable on one slide; split it`)
      }
      if (e.kind === 'image' && (typeof e.alt_text !== 'string' || !['contain', 'crop'].includes(e.fit))) p.push(`${ew}: image needs alt_text and fit`)
    }
  })
  if (p.length) throw new SpecError(p.slice(0, 40))
  return deck
}
