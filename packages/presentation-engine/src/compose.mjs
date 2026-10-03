/**
 * The composer: storyline + brand kit → a positioned DeckSpec (daypilot.deck-spec/v1).
 *
 * It owns layout decisions so that neither a person nor a model has to: curated layouts with
 * shared anchors, a 0.6-inch safe margin, role-based type sizes that shrink only down to the
 * kit's minimums, and a finding (never a silent cut) when content does not fit. Element ids are
 * `<slide>__<group>__<part>` so the compiler can draw the right panels, numbers and connectors.
 */
import { SpecError, validateBrandKit } from './brand.mjs'
import { digest } from './canonical.mjs'
import { fit } from './fit.mjs'
import { validateStoryline } from './storyline.mjs'

export const M = 0.6 // safe margin, inches
const GAP = 0.3

/** How each role is set on each layout: one place, shared with the compiler. */
export function textStyle(kit, layout, role, part) {
  const t = kit.typography[role] ?? kit.typography.body
  const s = { role, font: t.family, minPt: t.minimum_pt, maxPt: t.preferred_pt, bold: false, bullets: false, numbered: false, paraGapPt: 0, align: 'left', valign: 'top', italic: false }
  if (role === 'deck_title' || role === 'slide_title') s.bold = true
  if (role === 'data') s.bold = true
  if (part === 'kicker') Object.assign(s, { maxPt: Math.max(t.minimum_pt, 16), bold: true })
  if (part === 'value') Object.assign(s, { maxPt: Math.max(t.preferred_pt, 60), valign: 'bottom' })
  if (part === 'delta') Object.assign(s, { minPt: Math.max(t.minimum_pt, 12), maxPt: Math.max(t.preferred_pt, 16), bold: true })
  if (part === 'statement') Object.assign(s, { maxPt: Math.max(t.preferred_pt, 36), bold: true })
  if (part === 'quote') Object.assign(s, { maxPt: Math.max(t.preferred_pt, 30), italic: true })
  if (part === 'heading') Object.assign(s, { maxPt: Math.max(t.preferred_pt, 22), bold: true })
  if (part === 'rec') Object.assign(s, { maxPt: Math.max(t.preferred_pt, 26), bold: true })
  if (part === 'number') Object.assign(s, { align: 'center', valign: 'middle', bold: true })
  if (part === 'bullets') Object.assign(s, { bullets: true, paraGapPt: Math.round(t.preferred_pt * 0.55) })
  if (part === 'insight' || part === 'takeaway') Object.assign(s, { paraGapPt: 6 })
  if (layout === 'section' && role === 'deck_title') s.valign = 'bottom'
  return s
}

const bulletIndent = (s) => (s.bullets ? 0.32 : 0)

function nb(b, W, H) {
  const r = (v) => Math.round(v * 10000) / 10000
  return { x: r(b.x / W), y: r(b.y / H), w: r(b.w / W), h: r(b.h / H) }
}

/** Layered (left-to-right) placement for a small directed graph, inside a unit box. */
export function layeredLayout(nodes, edges) {
  const ids = nodes.map((n) => n.id)
  const out = new Map(ids.map((i) => [i, []]))
  const indeg = new Map(ids.map((i) => [i, 0]))
  for (const e of edges) {
    out.get(e.from).push(e.to)
    indeg.set(e.to, indeg.get(e.to) + 1)
  }
  // Longest-path layering on an acyclic version of the graph (back edges ignored for layering).
  const layer = new Map()
  const state = new Map()
  const order = []
  const visit = (start) => {
    const stack = [[start, 0]]
    while (stack.length) {
      const top = stack[stack.length - 1]
      const [v, i] = top
      if (i === 0) state.set(v, 1)
      const next = out.get(v)
      if (i < next.length) {
        top[1]++
        const w = next[i]
        if (!state.has(w)) stack.push([w, 0])
      } else {
        state.set(v, 2)
        order.push(v)
        stack.pop()
      }
    }
  }
  ids.filter((i) => indeg.get(i) === 0).forEach((i) => !state.has(i) && visit(i))
  ids.forEach((i) => !state.has(i) && visit(i))
  order.reverse()
  const pos = new Map(order.map((v, k) => [v, k]))
  for (const v of order) {
    let l = 0
    for (const e of edges) if (e.to === v && pos.get(e.from) < pos.get(v)) l = Math.max(l, (layer.get(e.from) ?? 0) + 1)
    layer.set(v, l)
  }
  const cols = Math.max(...layer.values()) + 1
  const byCol = Array.from({ length: cols }, () => [])
  ids.forEach((i) => byCol[layer.get(i)].push(i))
  const rows = Math.max(...byCol.map((c) => c.length))
  const cw = 1 / cols, rh = 1 / rows
  const w = Math.min(0.24, cw * 0.62), h = Math.min(0.24, rh * 0.6)
  const place = new Map()
  byCol.forEach((col, c) =>
    col.forEach((id, r) => {
      const offset = (rows - col.length) / 2
      place.set(id, { x: c * cw + (cw - w) / 2, y: (r + offset) * rh + (rh - h) / 2, w, h })
    }),
  )
  return { place, cols, rows }
}

export function compose(storyline, kit, opts = {}) {
  validateBrandKit(kit)
  validateStoryline(storyline)
  const W = kit.slide_size.width_inches, H = kit.slide_size.height_inches
  const findings = []
  const deckId = opts.deckId ?? 'deck'
  const slides = []
  const content = { x: M, y: 1.75, w: W - 2 * M, h: H - 1.75 - 0.95 }
  const titleBox = { x: M, y: 0.5, w: W - 2 * M, h: 1.05 }

  storyline.slides.forEach((sl, index) => {
    const sid = sl.id ?? `s${index + 1}`
    const layout = sl.type
    const els = []
    const text = (group, part, role, value, box0, extra = {}) => {
      let box = box0
      const id = `${sid}__${group}__${part}`
      const style = textStyle(kit, layout, role, part)
      const r = fit(value, box, { font: style.font, bold: style.bold, maxPt: style.maxPt, minPt: style.minPt, indent: bulletIndent(style), paraGapPt: style.paraGapPt })
      if (!r.fits) findings.push({ severity: 'hard', code: 'text_overflow', slide: sid, element: id, message: `“${String(value).slice(0, 40)}…” does not fit at the ${style.minPt} pt minimum; shorten it or split the slide.` })
      if (extra.shrink && r.fits) box = { ...box, h: Math.min(box.h, Math.max(extra.minH ?? 0, r.height + 0.2)) }
      if (!r.verified) findings.push({ severity: 'warning', code: 'fit_unverified', slide: sid, element: id, message: `Font ${style.font} has no metrics here; fit is estimated.` })
      els.push({ id, kind: 'text', bounds: nb(box, W, H), content_locked: false, layout_locked: false, role, text: String(value), claim_ids: extra.claim_ids ?? [] })
    }
    const title = (role = 'slide_title') => text('title', 'text', role, sl.title, titleBox)

    switch (layout) {
      case 'cover': {
        if (sl.kicker) text('kicker', 'kicker', 'footnote', sl.kicker, { x: M + 0.1, y: 1.9, w: W * 0.62, h: 0.45 })
        text('title', 'text', 'deck_title', sl.title, { x: M + 0.1, y: 2.4, w: W * 0.66, h: 2.0 })
        if (sl.subtitle) text('subtitle', 'text', 'body', sl.subtitle, { x: M + 0.1, y: 4.55, w: W * 0.6, h: 1.0 })
        break
      }
      case 'section': {
        text('num', 'number', 'data', sl.kicker || String(slides.filter((s) => s.layout_id === 'section').length + 1).padStart(2, '0'), { x: M + 0.1, y: 2.05, w: 1.3, h: 1.3 })
        text('title', 'text', 'deck_title', sl.title, { x: M + 0.1, y: 3.55, w: W * 0.7, h: 1.6 })
        if (sl.subtitle) text('subtitle', 'text', 'body', sl.subtitle, { x: M + 0.1, y: 5.25, w: W * 0.6, h: 0.9 })
        break
      }
      case 'agenda': {
        title()
        const n = sl.items.length, cols = n > 6 ? 2 : 1, per = Math.ceil(n / cols)
        const colW = (content.w - (cols - 1) * 0.6) / cols, rowH = Math.min(1.0, content.h / per)
        sl.items.forEach((item, i) => {
          const c = Math.floor(i / per), r = i % per
          const x = content.x + c * (colW + 0.6), y = content.y + r * rowH
          text(`item${i + 1}`, 'number', 'data', String(i + 1), { x, y: y + 0.08, w: 0.62, h: 0.62 })
          text(`item${i + 1}`, 'text', 'body', item, { x: x + 0.95, y: y + 0.08, w: colW - 0.95, h: 0.62 })
        })
        break
      }
      case 'statement': {
        title()
        text('statement', 'statement', 'slide_title', sl.statement, { x: content.x, y: content.y + 0.2, w: content.w * 0.82, h: 2.4 })
        if (sl.support) text('support', 'text', 'body', sl.support, { x: content.x, y: content.y + 2.8, w: content.w * 0.7, h: content.h - 2.8 })
        break
      }
      case 'bullets': {
        title()
        const side = sl.takeaway ? 3.9 : 0
        text('body', 'bullets', 'body', sl.bullets.join('\n'), { x: content.x, y: content.y, w: content.w - (side ? side + 0.5 : 0), h: content.h })
        if (sl.takeaway) text('takeaway', 'takeaway', 'body', sl.takeaway, { x: W - M - side + 0.35, y: content.y + 0.35, w: side - 0.7, h: content.h - 0.7 }, { shrink: true, minH: 1.4 })
        break
      }
      case 'kpis': {
        title()
        const n = sl.kpis.length, tileW = (content.w - (n - 1) * GAP) / n, tileY = content.y + 0.35, tileH = Math.min(3.6, content.h - (sl.footnote ? 1.0 : 0.4))
        sl.kpis.forEach((k, i) => {
          const x = content.x + i * (tileW + GAP)
          const claim = k.metric_ref ? [`${sid}_claim${i + 1}`] : []
          text(`kpi${i + 1}`, 'value', 'data', String(k.value), { x: x + 0.35, y: tileY + 0.3, w: tileW - 0.7, h: tileH * 0.42 }, { claim_ids: claim })
          text(`kpi${i + 1}`, 'label', 'body', k.label, { x: x + 0.35, y: tileY + 0.3 + tileH * 0.45, w: tileW - 0.7, h: tileH * 0.24 })
          if (k.delta) text(`kpi${i + 1}`, 'delta', 'body', k.delta, { x: x + 0.35, y: tileY + 0.3 + tileH * 0.72, w: tileW - 0.7, h: tileH * 0.18 })
        })
        if (sl.footnote) text('footnote', 'text', 'footnote', sl.footnote, { x: content.x, y: tileY + tileH + 0.25, w: content.w, h: 0.45 })
        break
      }
      case 'chart': {
        title()
        const ins = sl.insights ?? []
        const side = ins.length ? 3.9 : 0
        const c = sl.chart
        els.push({
          id: `${sid}__chart__main`, kind: 'chart', bounds: nb({ x: content.x, y: content.y, w: content.w - (side ? side + 0.4 : 0), h: content.h }, W, H),
          content_locked: false, layout_locked: false, chart_type: c.type, title: c.title ?? '', unit: c.unit ?? '',
          categories: c.categories.map(String),
          series: c.series.map((s) => ({ name: s.name, points: s.values.map((v, k) => ({ value: v, ...(s.metric_refs?.[k] ? { metric_ref: s.metric_refs[k] } : {}) })) })),
          alt_text: chartAlt(c), axis_zero_baseline: c.zero_baseline !== false,
        })
        ins.forEach((t, i) => text(`insight${i + 1}`, 'insight', 'body', t, { x: W - M - side + 0.35, y: content.y + 0.35 + i * ((content.h - 0.7) / 3), w: side - 0.7, h: (content.h - 0.7) / 3 - 0.15 }))
        break
      }
      case 'table': {
        title()
        const rowH = 0.5
        const needed = (sl.rows.length + 1) * rowH
        if (needed > content.h) findings.push({ severity: 'hard', code: 'table_overflow', slide: sid, element: `${sid}__table__main`, message: `${sl.rows.length} rows need ${needed.toFixed(1)} in; split the table across slides.` })
        els.push({
          id: `${sid}__table__main`, kind: 'table', bounds: nb({ x: content.x, y: content.y, w: content.w, h: Math.min(content.h, needed) }, W, H),
          content_locked: false, layout_locked: false, headers: sl.headers.map(String),
          rows: sl.rows.map((r, ri) => r.map((v, ci) => ({ value: v === null ? '—' : v, ...(sl.metric_refs?.[ri]?.[ci] ? { metric_ref: sl.metric_refs[ri][ci] } : {}) }))),
          alt_text: `Table with ${sl.rows.length} rows: ${sl.headers.join(', ')}.`,
        })
        break
      }
      case 'comparison': {
        title()
        const colW = (content.w - 0.5) / 2
        ;['left', 'right'].forEach((side, i) => {
          const x = content.x + i * (colW + 0.5)
          text(side, 'heading', 'body', sl[side].heading, { x: x + 0.35, y: content.y + 0.3, w: colW - 0.7, h: 0.6 })
          text(side, 'bullets', 'body', sl[side].points.join('\n'), { x: x + 0.35, y: content.y + 1.05, w: colW - 0.7, h: content.h - 1.35 }, { shrink: true, minH: 1.6 })
        })
        break
      }
      case 'timeline': {
        title()
        const n = sl.milestones.length, step = content.w / n
        sl.milestones.forEach((m, i) => {
          const x = content.x + i * step
          const up = i % 2 === 0
          const axis = content.y + 2.2
          if (m.date) text(`m${i + 1}`, 'date', 'footnote', m.date, { x: x + 0.1, y: up ? axis - 1.55 : axis + 0.45, w: step - 0.2, h: 0.4 })
          text(`m${i + 1}`, 'text', 'body', m.label, { x: x + 0.1, y: up ? axis - 1.15 : axis + 0.85, w: Math.min(2 * step - 0.4, 3.2, content.x + content.w - x - 0.1), h: 0.85 })
        })
        break
      }
      case 'diagram': {
        title()
        const { place } = layeredLayout(sl.nodes, sl.edges)
        els.push({
          id: `${sid}__diagram__main`, kind: 'diagram', bounds: nb(content, W, H), content_locked: false, layout_locked: false,
          source_snapshot_id: sl.source_snapshot_id ?? 'storyline',
          nodes: sl.nodes.map((n) => ({ id: n.id, label: n.label, bounds: roundBox(place.get(n.id)) })),
          edges: sl.edges.map((e, i) => ({ id: `e${i + 1}`, from: e.from, to: e.to, ...(e.label ? { label: e.label } : {}) })),
          alt_text: diagramAlt(sl),
        })
        break
      }
      case 'decision': {
        title()
        const leftW = content.w * 0.52
        text('rec', 'rec', 'body', sl.recommendation, { x: content.x + 0.45, y: content.y + 0.45, w: leftW - 0.9, h: content.h - 0.9 - (sl.ask ? 0.9 : 0) }, { shrink: true, minH: 1.2 })
        const recBottom = els[els.length - 1].bounds.y * H + els[els.length - 1].bounds.h * H
        if (sl.ask) text('ask', 'text', 'body', sl.ask, { x: content.x + 0.45, y: recBottom + 0.35, w: leftW - 0.9, h: 0.8 }, { shrink: true })
        if (sl.options?.length) text('options', 'bullets', 'body', sl.options.join('\n'), { x: content.x + leftW + 0.5, y: content.y + 0.2, w: content.w - leftW - 0.5, h: content.h - 0.2 })
        break
      }
      case 'quote': {
        text('quote', 'quote', 'body', sl.quote, { x: M + 1.2, y: 2.0, w: W - 2 * M - 2.4, h: 3.0 })
        if (sl.attribution) text('attribution', 'text', 'footnote', '— ' + sl.attribution, { x: M + 1.2, y: 5.15, w: W - 2 * M - 2.4, h: 0.5 })
        if (sl.title) els.push(...[]) // the title stays as the slide's accessible name (notes and outline)
        break
      }
      case 'closing': {
        text('title', 'text', 'deck_title', sl.title, { x: M + 0.1, y: 1.3, w: W * 0.8, h: 1.4 })
        if (sl.subtitle) text('subtitle', 'text', 'body', sl.subtitle, { x: M + 0.1, y: 2.75, w: W * 0.7, h: 0.8 })
        ;(sl.next_steps ?? []).forEach((st, i) => {
          const y = 3.75 + i * 0.68
          text(`step${i + 1}`, 'number', 'data', String(i + 1), { x: M + 0.1, y: y + 0.02, w: 0.52, h: 0.52 })
          text(`step${i + 1}`, 'text', 'body', st, { x: M + 0.85, y: y + 0.04, w: W * 0.6, h: 0.5 })
        })
        break
      }
    }
    const refs = collectRefs(sl)
    slides.push({
      id: sid,
      layout_id: layout,
      purpose: sl.purpose ?? defaultPurpose(sl),
      title: sl.title,
      notes: { speaker_text: speakerNotes(sl), source_snapshot_ids: [...new Set(refs.map((r) => r.source_snapshot_id))] },
      claims: claimsFor(sid, sl),
      elements: els,
    })
  })

  const deck = {
    schema_version: 'daypilot.deck-spec/v1',
    fixture_only: !!opts.fixtureOnly,
    id: deckId,
    workspace_id: opts.workspaceId ?? 'local',
    company_id: kit.company_id,
    title: storyline.title,
    language: storyline.language ?? 'en',
    purpose: storyline.purpose ?? storyline.title,
    audience: storyline.audience ?? 'Internal',
    brand_ref: { id: kit.id, version: kit.version, sha256: digest(kit) },
    template_ref: opts.templateRef ?? { id: `${kit.id}_curated`, version: 1, sha256: digest({ curated: kit.id }) },
    slide_size: { width_inches: W, height_inches: H },
    slide_count: { exact: slides.length },
    period: storyline.period ?? null,
    sources: storyline.sources ?? [],
    slides,
  }
  if (deck.period === null) delete deck.period
  return { deck, findings }
}

const roundBox = (b) => Object.fromEntries(Object.entries(b).map(([k, v]) => [k, Math.round(v * 10000) / 10000]))

function chartAlt(c) {
  const parts = c.series.map((s) => `${s.name}: ${s.values.map((v, i) => `${c.categories[i]} ${v === null ? 'no data' : v}`).join(', ')}`)
  return `${c.title || 'Chart'}${c.unit ? ` (${c.unit})` : ''}. ${parts.join('; ')}`.slice(0, 1000)
}
function diagramAlt(sl) {
  const label = new Map(sl.nodes.map((n) => [n.id, n.label]))
  return (`${sl.title}: ` + (sl.edges.length ? sl.edges.map((e) => `${label.get(e.from)} → ${label.get(e.to)}${e.label ? ` (${e.label})` : ''}`).join('; ') : sl.nodes.map((n) => n.label).join(', '))).slice(0, 1000)
}
function defaultPurpose(sl) {
  return { cover: 'Open the presentation', section: 'Introduce a section', agenda: 'Set expectations', closing: 'Close with next steps' }[sl.type] ?? `Explain: ${sl.title}`.slice(0, 200)
}
function collectRefs(sl) {
  const refs = []
  for (const k of sl.kpis ?? []) if (k.metric_ref) refs.push(k.metric_ref)
  for (const s of sl.chart?.series ?? []) for (const r of s.metric_refs ?? []) if (r) refs.push(r)
  for (const row of sl.metric_refs ?? []) for (const r of row ?? []) if (r) refs.push(r)
  return refs
}
function claimsFor(sid, sl) {
  return (sl.kpis ?? []).flatMap((k, i) =>
    k.metric_ref
      ? [{ id: `${sid}_claim${i + 1}`, classification: 'observed', text: `${k.label}: ${k.value}`.slice(0, 500), metric_ref: k.metric_ref, ...(typeof k.numeric_value === 'number' ? { numeric_value: k.numeric_value } : {}), ...(k.unit ? { unit: k.unit } : {}) }]
      : [],
  )
}
function speakerNotes(sl) {
  const base = notesBody(sl)
  return sl.sources?.length ? `${base}\n\nSources: ${sl.sources.join('; ')}`.slice(0, 4000) : base
}
function notesBody(sl) {
  if (sl.notes && sl.notes.trim()) return sl.notes.trim()
  switch (sl.type) {
    case 'chart': return `Walk through ${sl.chart.title || 'the chart'}. ${chartAlt(sl.chart)}`.slice(0, 4000)
    case 'kpis': return sl.kpis.map((k) => `${k.label}: ${k.value}${k.delta ? ` (${k.delta})` : ''}`).join('. ')
    case 'bullets': return sl.takeaway ? `Key point: ${sl.takeaway}` : `Cover: ${sl.bullets.join('; ')}`.slice(0, 4000)
    case 'decision': return `Recommendation: ${sl.recommendation}${sl.ask ? ` Ask: ${sl.ask}` : ''}`
    default: return sl.subtitle || sl.statement || sl.title
  }
}
export { SpecError }
