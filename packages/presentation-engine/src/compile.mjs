/**
 * The compiler: DeckSpec + brand kit (+ approved assets) → a native, editable .pptx and a scene
 * graph describing every object it placed. Text, charts, tables and diagrams are real PowerPoint
 * objects; nothing is a screenshot. Decoration (panels, number circles, connectors, footer, logo)
 * is derived from the layout and recorded in the scene graph with `derived: true`.
 */
import PptxGenJS from 'pptxgenjs'
import JSZip from 'jszip'
import { contrast, hex, onColor, seriesColors, themeColors, tint, validateBrandKit } from './brand.mjs'
import { M, textStyle } from './compose.mjs'
import { fit, hasMetrics, measure } from './fit.mjs'
import { validateDeck } from './deckspec.mjs'

export const ENGINE_VERSION = '0.1.0'
const DARK = new Set(['cover', 'section', 'closing'])

export async function compile(deck, kit, assets = {}) {
  validateBrandKit(kit)
  validateDeck(deck, kit)
  const W = deck.slide_size.width_inches, H = deck.slide_size.height_inches
  const pal = Object.fromEntries(Object.entries(kit.palette).map(([k, v]) => [k, hex(v)]))
  const pres = new PptxGenJS()
  pres.defineLayout({ name: 'DAYPILOT', width: W, height: H })
  pres.layout = 'DAYPILOT'
  pres.theme = { headFontFace: kit.typography.slide_title.family, bodyFontFace: kit.typography.body.family }
  pres.title = deck.title
  pres.subject = `daypilot:deck:${deck.id}`
  pres.author = 'DayPilot Presentations'
  pres.company = xmlSafe(kit.company_name ?? kit.company_id)
  const scene = { engine: ENGINE_VERSION, slide_size: { w: W, h: H }, slides: [] }

  // --- layouts: background, footer, page number and logo live on the layout, never on a slide
  const logoFor = (dark) => {
    const pref = dark ? 'dark_background' : 'light_background'
    const l = (kit.logos ?? []).find((x) => x.variant === pref && assets[x.asset_id]) ?? (kit.logos ?? []).find((x) => x.variant === 'universal' && assets[x.asset_id])
    return l ? { ...l, asset: assets[l.asset_id] } : null
  }
  const masters = new Map()
  const masterFor = (layout) => {
    const dark = DARK.has(layout)
    const bg = layout === 'section' ? pal.foreground : dark ? pal.primary : layout === 'quote' ? tint(pal.primary, 0.94) : pal.background
    const name = `DP ${layout}`
    if (masters.has(name)) return masters.get(name)
    const objects = []
    const derived = []
    const footColor = dark ? onColor(bg, kit) : readable(pal.muted, bg, kit)
    const ft = kit.typography.footnote
    if (kit.footer?.text && layout !== 'cover') {
      objects.push({ text: { text: kit.footer.text, options: { x: M, y: H - 0.55, w: W * 0.6, h: 0.32, fontFace: ft.family, fontSize: ft.minimum_pt, color: footColor, margin: 0, valign: 'middle' } } })
      derived.push({ id: 'footer', kind: 'text', box: { x: M, y: H - 0.55, w: W * 0.6, h: 0.32 }, pt: ft.minimum_pt, font: ft.family, color: footColor, bg, text: kit.footer.text })
    }
    const logo = logoFor(dark)
    if (logo) {
      const h = layout === 'cover' ? 0.62 : 0.4
      let w = h * logo.aspect_ratio
      const minW = logo.minimum_width_inches ?? 0
      const lh = w < minW ? minW / logo.aspect_ratio : h
      w = Math.max(w, minW)
      const x = layout === 'cover' ? M + 0.1 : W - M - w
      const y = layout === 'cover' ? 0.55 : H - 0.35 - lh
      // A logo made for light backgrounds never sits directly on a dark slide: it gets a white plate.
      if (dark && logo.variant !== 'dark_background') {
        const pad = Math.max(0.1, lh * (logo.clear_space_ratio ?? 0.2))
        objects.push({ rect: { x: x - pad, y: y - pad, w: w + 2 * pad, h: lh + 2 * pad, fill: { color: 'FFFFFF' }, rectRadius: 0.08 } })
        derived.push({ id: 'logo_plate', kind: 'panel', box: { x: x - pad, y: y - pad, w: w + 2 * pad, h: lh + 2 * pad }, fill: 'FFFFFF' })
      }
      objects.push({ image: { x, y, w, h: lh, data: dataUri(logo.asset), altText: `${kit.company_name ?? 'Company'} logo` } })
      derived.push({ id: 'logo', kind: 'image', box: { x, y, w, h: lh }, asset_id: logo.asset_id, aspect: w / lh, expected_aspect: logo.aspect_ratio, bg: dark && logo.variant !== 'dark_background' ? 'FFFFFF' : bg })
    }
    const showNumber = kit.footer?.show_page_number !== false && layout !== 'cover'
    const numX = logo && layout !== 'cover' ? W - M - (derived.find((d) => d.id === 'logo').box.w) - 0.9 : W - M - 0.6
    masters.set(name, { name, bg, dark, derived, numBox: showNumber ? { x: numX, y: H - 0.55, w: 0.6, h: 0.32 } : null })
    pres.defineSlideMaster({
      title: name,
      background: { color: bg },
      objects,
      ...(showNumber ? { slideNumber: { x: numX, y: H - 0.55, w: 0.6, h: 0.32, fontFace: ft.family, fontSize: ft.minimum_pt, color: footColor, align: 'right' } } : {}),
    })
    return masters.get(name)
  }

  // --- sections only when the deck has section slides
  const hasSections = deck.slides.some((s) => s.layout_id === 'section')
  let section = null
  if (hasSections && deck.slides[0].layout_id !== 'section') {
    section = 'Introduction'
    pres.addSection({ title: section })
  }
  const sourceLabel = new Map((deck.sources ?? []).map((s) => [s.id, s.label ?? s.source_id ?? s.id]))

  deck.slides.forEach((s, index) => {
    const layout = s.layout_id
    if (layout === 'section') {
      section = s.title.slice(0, 60)
      pres.addSection({ title: section })
    }
    const master = masterFor(layout)
    const slide = pres.addSlide({ masterName: master.name, ...(section ? { sectionTitle: section } : {}) })
    const objs = []
    const rec = (o) => objs.push(o)
    const box = (b) => ({ x: b.x * W, y: b.y * H, w: b.w * W, h: b.h * H })
    const els = s.elements
    const group = (el) => el.id.split('__')[1] ?? ''
    const part = (el) => el.id.split('__')[2] ?? 'text'
    const groupBox = (g) => {
      const bs = els.filter((e) => group(e) === g).map((e) => box(e.bounds))
      if (!bs.length) throw new Error(`internal: empty group ${g}`)
      const x = Math.min(...bs.map((b) => b.x)), y = Math.min(...bs.map((b) => b.y))
      return { x, y, w: Math.max(...bs.map((b) => b.x + b.w)) - x, h: Math.max(...bs.map((b) => b.y + b.h)) - y }
    }
    const panel = (id, b, fill, opts = {}) => {
      slide.addShape(pres.ShapeType.roundRect, { x: b.x, y: b.y, w: b.w, h: b.h, fill: { color: fill }, line: { color: fill, width: 0 }, rectRadius: opts.radius ?? 0.12, objectName: id })
      rec({ id, kind: 'panel', derived: true, box: b, fill })
    }
    const circle = (id, b, fill, line) => {
      slide.addShape(pres.ShapeType.ellipse, { x: b.x, y: b.y, w: b.w, h: b.h, fill: { color: fill }, line: { color: line ?? fill, width: line ? 2 : 0 }, objectName: id })
      rec({ id, kind: 'circle', derived: true, box: b, fill })
    }
    const content = { x: M, y: 1.75, w: W - 2 * M, h: H - 1.75 - 0.95 }
    const bgOf = new Map() // element id -> background colour behind it

    // --- layout decoration first, so content sits on top
    if (layout === 'cover') {
      slide.addShape(pres.ShapeType.ellipse, { x: W * 0.64, y: -H * 0.18, w: H * 1.05, h: H * 1.05, fill: { color: tint(pal.primary, 0.14) }, line: { color: tint(pal.primary, 0.14), width: 0 }, objectName: 'motif_large' })
      slide.addShape(pres.ShapeType.ellipse, { x: W * 0.83, y: H * 0.6, w: H * 0.34, h: H * 0.34, fill: { color: pal.accent }, line: { color: pal.accent, width: 0 }, objectName: 'motif_small' })
      rec({ id: 'motif', kind: 'decoration', derived: true, box: { x: W * 0.64, y: 0, w: W * 0.36, h: H }, allowOverlap: true })
    }
    if (layout === 'closing') {
      // Upper right, clear of the footer, page number and logo in the bottom corners.
      slide.addShape(pres.ShapeType.ellipse, { x: W * 0.7, y: -H * 0.32, w: H * 0.95, h: H * 0.95, fill: { color: tint(pal.primary, 0.14) }, line: { color: tint(pal.primary, 0.14), width: 0 }, objectName: 'motif_large' })
      rec({ id: 'motif', kind: 'decoration', derived: true, box: { x: W * 0.7, y: 0, w: W * 0.3, h: H * 0.63 }, allowOverlap: true })
    }
    if (layout === 'quote') {
      slide.addText('“', { x: M + 0.2, y: 0.9, w: 1.2, h: 1.4, fontFace: kit.typography.slide_title.family, fontSize: 120, color: pal.accent, bold: true, margin: 0, isTextBox: true, objectName: 'quote_mark' })
      rec({ id: 'quote_mark', kind: 'decoration', derived: true, box: { x: M + 0.2, y: 0.9, w: 1.2, h: 1.4 } })
    }
    if (layout === 'bullets' && els.some((e) => group(e) === 'takeaway')) {
      const b = groupBox('takeaway')
      const pb = { x: b.x - 0.35, y: b.y - 0.35, w: b.w + 0.7, h: b.h + 0.7 }
      panel('takeaway_panel', pb, tint(pal.accent, 0.86))
      els.filter((e) => group(e) === 'takeaway').forEach((e) => bgOf.set(e.id, tint(pal.accent, 0.86)))
    }
    if (layout === 'kpis') {
      const groups = [...new Set(els.map(group).filter((g) => g.startsWith('kpi')))]
      const tallest = Math.max(...groups.map((g) => groupBox(g).y + groupBox(g).h))
      groups.forEach((g) => {
        const b = groupBox(g)
        const tb = { x: b.x - 0.3, y: b.y - 0.3, w: b.w + 0.6, h: tallest - b.y + 0.5 }
        panel(`${g}_tile`, tb, tint(pal.primary, 0.92))
        els.filter((e) => group(e) === g).forEach((e) => bgOf.set(e.id, tint(pal.primary, 0.92)))
      })
    }
    if (layout === 'chart') {
      const ins = els.filter((e) => group(e).startsWith('insight'))
      if (ins.length) {
        const b0 = box(ins[0].bounds)
        const pb = { x: b0.x - 0.35, y: content.y, w: b0.w + 0.7, h: content.h }
        panel('insight_panel', pb, tint(pal.primary, 0.93))
        ins.forEach((e) => bgOf.set(e.id, tint(pal.primary, 0.93)))
      }
    }
    if (layout === 'comparison' && els.some((e) => group(e) === 'left') && els.some((e) => group(e) === 'right')) {
      ;['left', 'right'].forEach((g, i) => {
        const b = groupBox(g)
        const fill = tint(i ? pal.accent : pal.primary, i ? 0.88 : 0.92)
        const hh = Math.max(groupBox('left').h, groupBox('right').h)
        panel(`${g}_panel`, { x: b.x - 0.35, y: content.y, w: b.w + 0.7, h: Math.min(content.h, hh + 0.65) }, fill)
        els.filter((e) => group(e) === g).forEach((e) => bgOf.set(e.id, fill))
      })
    }
    if (layout === 'decision' && els.some((e) => group(e) === 'rec')) {
      const b = groupBox('rec')
      const askB = els.some((e) => group(e) === 'ask') ? groupBox('ask') : null
      const bottom = Math.max(b.y + b.h, askB ? askB.y + askB.h : 0)
      const pb = { x: b.x - 0.45, y: content.y, w: b.w + 0.9, h: Math.min(content.h, bottom - content.y + 0.45) }
      panel('rec_panel', pb, pal.primary)
      bgOf.set(`${s.id}__rec__rec`, pal.primary)
      if (askB) bgOf.set(`${s.id}__ask__text`, pal.primary)
    }
    if (layout === 'timeline') {
      const y = content.y + 2.2
      slide.addShape(pres.ShapeType.line, { x: content.x, y, w: content.w, h: 0, line: { color: tint(pal.primary, 0.55), width: 2.5 }, objectName: 'timeline_axis' })
      rec({ id: 'timeline_axis', kind: 'line', derived: true, box: { x: content.x, y, w: content.w, h: 0 } })
      const n = new Set(els.map(group)).size - 1
      const step = content.w / Math.max(1, n)
      for (let i = 0; i < n; i++) {
        const cx = content.x + i * step + 0.1 + 0.18
        circle(`m${i + 1}_dot`, { x: cx - 0.18, y: y - 0.18, w: 0.36, h: 0.36 }, i === 0 ? pal.accent : pal.primary)
      }
    }

    // --- content
    for (const el of els) {
      const b = box(el.bounds)
      if (el.kind === 'text') {
        const st = textStyle(kit, layout, el.role, part(el))
        const bg = bgOf.get(el.id) ?? master.bg
        let color = textColor(layout, el, part(el), bg, kit, pal)
        if (part(el) === 'number') {
          const fill = layout === 'closing' || layout === 'section' ? pal.accent : pal.primary
          circle(`${group(el)}_badge`, b, fill)
          color = onColor(fill, kit)
          const r = fit(el.text, b, { font: st.font, bold: true, maxPt: Math.min(st.maxPt, Math.floor(b.h * 72 * 0.5)), minPt: Math.min(st.minPt, Math.floor(b.h * 72 * 0.5)) })
          slide.addText(el.text, { x: b.x, y: b.y, w: b.w, h: b.h, fontFace: st.font, fontSize: r.pt, bold: true, color, align: 'center', valign: 'middle', margin: 0, isTextBox: true, objectName: el.id, fit: 'none' })
          rec({ id: el.id, kind: 'text', role: el.role, box: b, pt: r.pt, minPt: r.pt, font: st.font, color, bg: fill, fits: r.fits, verified: r.verified, text: el.text })
          continue
        }
        const r = fit(el.text, b, { font: st.font, bold: st.bold, maxPt: st.maxPt, minPt: st.minPt, indent: st.bullets ? 0.32 : 0, paraGapPt: st.paraGapPt })
        const common = { x: b.x, y: b.y, w: b.w, h: b.h, fontFace: st.font, fontSize: r.pt, color, bold: st.bold, italic: st.italic, align: st.align, valign: st.valign, margin: 0, isTextBox: true, objectName: el.id, fit: 'none' }
        if (st.bullets) {
          const lines = el.text.split('\n')
          slide.addText(
            lines.map((t, i) => ({ text: t, options: { bullet: { indent: 23 }, paraSpaceAfter: st.paraGapPt, breakLine: i < lines.length - 1 } })),
            common,
          )
        } else slide.addText(el.text, { ...common, paraSpaceAfter: st.paraGapPt })
        rec({ id: el.id, kind: 'text', role: el.role, box: b, pt: r.pt, minPt: st.minPt, font: st.font, color, bg, fits: r.fits, verified: r.verified, text: el.text, height: r.height })
      } else if (el.kind === 'chart') {
        chart(pres, slide, el, b, kit, pal)
        rec({ id: el.id, kind: 'chart', box: b, chart_type: el.chart_type, series: el.series.map((x) => ({ name: x.name, values: x.points.map((p) => p.value) })), categories: el.categories })
      } else if (el.kind === 'table') {
        const t = table(pres, slide, el, b, kit, pal)
        rec({ id: el.id, kind: 'table', box: { ...b, h: t.height }, pt: t.pt, minPt: kit.typography.data.minimum_pt, fits: t.fits, font: kit.typography.body.family, rows: el.rows.length, cols: el.headers.length })
      } else if (el.kind === 'diagram') {
        diagram(pres, slide, el, b, kit, pal, rec)
        rec({ id: el.id, kind: 'diagram', box: b, nodes: el.nodes.length, edges: el.edges.length })
      } else if (el.kind === 'image') {
        const a = assets[el.asset_id]
        if (!a) throw new Error(`image ${el.id}: asset ${el.asset_id} was not supplied`)
        const fitBox = el.fit === 'contain' ? containBox(b, a.width / a.height) : b
        slide.addImage({ data: dataUri(a), ...fitBox, altText: el.alt_text, objectName: el.id, ...(el.fit === 'crop' ? { sizing: { type: 'cover', w: b.w, h: b.h } } : {}) })
        rec({ id: el.id, kind: 'image', box: fitBox, asset_id: el.asset_id, aspect: fitBox.w / fitBox.h, expected_aspect: a.width / a.height, fit: el.fit })
      }
    }
    // --- notes: audience-facing guidance plus source references
    const refs = (s.notes.source_snapshot_ids ?? []).map((id) => sourceLabel.get(id) ?? id)
    const notes = s.notes.speaker_text + (refs.length ? `\n\nEvidence: ${refs.join('; ')}` : '') + (deck.period?.key ? `\nReporting period: ${deck.period.key}` : '')
    slide.addNotes(notes)
    scene.slides.push({ id: s.id, index, layout, background: master.bg, derived: master.derived, number: master.numBox, objects: objs, notes })
  })

  let buf = await pres.write({ outputType: 'nodebuffer', compression: true })
  buf = await finish(buf, kit, deck)
  return { pptx: buf, scene }
}

/** The wanted colour if it reaches 4.5:1 on the background, otherwise the readable fallback. */
function readable(want, bg, kit) {
  return contrast(want, bg) >= 4.5 ? want : onColor(bg, kit)
}
function xmlSafe(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
function dataUri(a) {
  return `${a.media_type};base64,${a.base64}`
}
function containBox(b, ratio) {
  if (b.w / b.h > ratio) {
    const w = b.h * ratio
    return { x: b.x + (b.w - w) / 2, y: b.y, w, h: b.h }
  }
  const h = b.w / ratio
  return { x: b.x, y: b.y + (b.h - h) / 2, w: b.w, h }
}

/** Readable colour for a text element; brand colours are used only where they pass 4.5:1. */
function textColor(layout, el, part, bg, kit, pal) {
  const pick = (want) => (contrast(want, bg) >= 4.5 ? want : onColor(bg, kit))
  if (DARK.has(layout) || bg === pal.primary) {
    if (part === 'kicker') return contrast(pal.accent, bg) >= 4.5 ? pal.accent : tint(onColor(bg, kit), 0)
    if (el.role === 'body' && part !== 'rec') return onColor(bg, kit) === 'FFFFFF' ? tint('FFFFFF', 0) : pal.foreground
    return onColor(bg, kit)
  }
  if (part === 'value') return pick(pal.primary)
  if (part === 'delta') {
    const t = el.text.trim()
    if (/^[+▲↑]/.test(t)) return pick(pal.positive)
    if (/^[-−▼↓]/.test(t)) return pick(pal.negative)
    return pick(pal.muted)
  }
  if (part === 'heading') return pick(el.id.includes('__right__') ? pal.accent : pal.primary)
  if (part === 'date' || el.role === 'footnote') return pick(pal.muted)
  if (part === 'statement') return pick(pal.primary)
  return pick(pal.foreground)
}

function chart(pres, slide, el, b, kit, pal) {
  const colors = seriesColors(kit)
  const body = kit.typography.body.family
  const labelPt = Math.max(kit.chart_style?.minimum_label_pt ?? 12, kit.typography.data.minimum_pt)
  const many = el.categories.length > 12
  const single = el.series.length === 1
  const axisColor = readable(pal.muted, 'FFFFFF', kit)
  const common = {
    x: b.x, y: b.y, w: b.w, h: b.h, objectName: el.id, altText: el.alt_text,
    chartColors: colors.slice(0, Math.max(1, el.series.length)),
    showTitle: !!el.title, title: el.title, titleFontFace: body, titleFontSize: labelPt, titleColor: pal.foreground,
    showLegend: !single, legendPos: 'b', legendFontFace: body, legendFontSize: labelPt - 2, legendColor: pal.foreground,
    catAxisLabelFontFace: body, catAxisLabelFontSize: Math.max(12, labelPt - (many ? 4 : 2)), catAxisLabelColor: axisColor,
    valAxisLabelFontFace: body, valAxisLabelFontSize: Math.max(12, labelPt - 4), valAxisLabelColor: axisColor,
    valGridLine: { color: tint(pal.muted, 0.82), size: 0.75 }, catGridLine: { style: 'none' },
    catAxisLineShow: true, valAxisLineShow: false,
    ...(el.unit ? { showValAxisTitle: true, valAxisTitle: el.unit, valAxisTitleFontFace: body, valAxisTitleFontSize: Math.max(12, labelPt - 4), valAxisTitleColor: axisColor } : {}),
    ...(el.axis_zero_baseline ? { valAxisMinVal: 0 } : {}),
  }
  const showValues = !many && single
  const decimals = el.series.some((x) => x.points.some((p) => p.value !== null && !Number.isInteger(p.value)))
  const fmt = (el.unit === '%' ? (decimals ? '0.0"%"' : '0"%"') : decimals ? '0.0' : '0')
  if (el.chart_type === 'scatter') {
    const xs = el.categories.map(Number)
    slide.addChart(pres.ChartType.scatter, [{ name: 'X', values: xs }, ...el.series.map((s) => ({ name: s.name, values: s.points.map((p) => p.value) }))], { ...common, lineSize: 0, lineDataSymbolSize: 10 })
    return
  }
  const data = el.series.map((s) => ({ name: s.name, labels: el.categories, values: s.points.map((p) => (p.value === null ? null : p.value)) }))
  const type = el.chart_type === 'line' ? pres.ChartType.line : el.chart_type === 'area' ? pres.ChartType.area : pres.ChartType.bar
  const opts = {
    ...common,
    ...(type === pres.ChartType.bar ? { barDir: el.chart_type === 'bar' ? 'bar' : 'col', barGapWidthPct: single ? 55 : 80 } : {}),
    ...(type === pres.ChartType.line ? { lineSize: 3, lineDataSymbol: 'circle', lineDataSymbolSize: 8 } : {}),
    ...(showValues ? { showValue: true, dataLabelPosition: type === pres.ChartType.bar ? 'outEnd' : 't', dataLabelFontFace: body, dataLabelFontSize: labelPt, dataLabelColor: pal.foreground } : {}),
    dataLabelFormatCode: fmt,
    ...(el.unit === '%' ? { valAxisLabelFormatCode: '0"%"' } : {}),
  }
  if (type === pres.ChartType.area) opts.dataLabelPosition = undefined
  slide.addChart(type, data, opts)
}

function table(pres, slide, el, b, kit, pal) {
  const font = kit.typography.body.family
  const minPt = kit.typography.data.minimum_pt
  const cols = el.headers.length
  const text = (c) => (c && typeof c === 'object' ? String(c.value) : String(c))
  // Column widths proportional to content (bounded), then the largest size whose wrapped cells fit 0.5 in rows.
  const longest = el.headers.map((h, i) => Math.max(measure(h, font, 14, true), ...el.rows.map((r) => measure(text(r[i]), font, 14))))
  const sum = longest.reduce((a, v) => a + Math.max(v, 0.6), 0)
  const colW = longest.map((v) => (Math.max(v, 0.6) / sum) * b.w)
  const rowH = 0.5
  let pt = Math.max(minPt, kit.typography.data.preferred_pt)
  let fits = false
  for (; pt >= minPt; pt--) {
    const ok = [el.headers, ...el.rows.map((r) => r.map(text))].every((row, ri) =>
      row.every((cell, ci) => fit(String(cell), { w: colW[ci] - 0.2, h: rowH * (ri === 0 ? 1.4 : 1) - 0.08 }, { font, bold: ri === 0, maxPt: pt, minPt: pt }).fits),
    )
    if (ok) {
      fits = true
      break
    }
  }
  pt = Math.max(pt, minPt)
  const numeric = (c) => typeof (c && typeof c === 'object' ? c.value : c) === 'number'
  const head = el.headers.map((h, i) => ({ text: h, options: { bold: true, color: onColor(pal.primary, kit), fill: { color: pal.primary }, align: el.rows.every((r) => numeric(r[i])) ? 'right' : 'left' } }))
  const rows = el.rows.map((r, ri) =>
    r.map((c) => ({ text: text(c), options: { color: pal.foreground, fill: { color: ri % 2 ? tint(pal.primary, 0.94) : 'FFFFFF' }, align: numeric(c) ? 'right' : 'left' } })),
  )
  slide.addTable([head, ...rows], { x: b.x, y: b.y, w: b.w, colW, rowH, fontFace: font, fontSize: pt, valign: 'middle', margin: [0.04, 0.1, 0.04, 0.1], border: { type: 'solid', color: tint(pal.muted, 0.75), pt: 0.75 }, objectName: el.id, autoPage: false })
  return { pt, fits, height: rowH * (el.rows.length + 1) }
}

function diagram(pres, slide, el, b, kit, pal, rec) {
  const font = kit.typography.body.family
  const nodeBox = (n) => ({ x: b.x + n.bounds.x * b.w, y: b.y + n.bounds.y * b.h, w: n.bounds.w * b.w, h: n.bounds.h * b.h })
  const boxes = new Map(el.nodes.map((n) => [n.id, nodeBox(n)]))
  const lineColor = tint(pal.primary, 0.2)
  for (const e of el.edges) {
    const a = boxes.get(e.from), z = boxes.get(e.to)
    const [p, q] = anchors(a, z)
    const x = Math.min(p.x, q.x), y = Math.min(p.y, q.y), w = Math.abs(q.x - p.x), h = Math.abs(q.y - p.y)
    slide.addShape(pres.ShapeType.line, { x, y, w: Math.max(w, 0.001), h: Math.max(h, 0.001), flipH: q.x < p.x, flipV: q.y < p.y, line: { color: lineColor, width: 1.75, endArrowType: 'triangle' }, objectName: `${el.id}__edge__${e.id}` })
    rec({ id: `${el.id}__edge__${e.id}`, kind: 'connector', derived: false, box: { x, y, w, h }, from: e.from, to: e.to, allowOverlap: true })
    if (e.label) {
      const lw = Math.min(2, measure(e.label, font, 12) + 0.2)
      const horizontal = Math.abs(q.y - p.y) < 0.01
      const lb = horizontal ? { x: (p.x + q.x) / 2 - lw / 2, y: p.y - 0.42, w: lw, h: 0.3 } : { x: (p.x + q.x) / 2 + 0.08, y: (p.y + q.y) / 2 - 0.15, w: lw, h: 0.3 }
      const labelColor = readable(pal.muted, 'FFFFFF', kit)
      slide.addText(e.label, { ...lb, fontFace: font, fontSize: 12, color: labelColor, align: 'center', valign: 'middle', margin: 0, isTextBox: true, fill: { color: 'FFFFFF' }, objectName: `${el.id}__edgelabel__${e.id}` })
      rec({ id: `${el.id}__edgelabel__${e.id}`, kind: 'text', role: 'footnote', box: lb, pt: 12, minPt: 12, font, bg: 'FFFFFF', fits: measure(e.label, font, 12) <= lw, verified: hasMetrics(font), text: e.label, allowOverlap: true, color: labelColor })
    }
  }
  const fill = tint(pal.primary, 0.9)
  for (const n of el.nodes) {
    const nb = boxes.get(n.id)
    const min = kit.typography.data.minimum_pt
    const r = fit(n.label, { w: nb.w - 0.2, h: nb.h - 0.1 }, { font, bold: true, maxPt: Math.max(min, kit.typography.body.preferred_pt), minPt: min })
    slide.addText(n.label, { shape: pres.ShapeType.roundRect, x: nb.x, y: nb.y, w: nb.w, h: nb.h, rectRadius: 0.1, fill: { color: fill }, line: { color: pal.primary, width: 1.5 }, fontFace: font, fontSize: r.pt, bold: true, color: pal.foreground, align: 'center', valign: 'middle', margin: 0.06, objectName: `${el.id}__node__${n.id}` })
    rec({ id: `${el.id}__node__${n.id}`, kind: 'text', role: 'data', box: nb, pt: r.pt, minPt: min, font, color: pal.foreground, bg: fill, fits: r.fits, verified: r.verified, text: n.label })
  }
}

/** Points on the facing sides of two boxes, so connectors meet edges rather than centres. */
function anchors(a, z) {
  const ca = { x: a.x + a.w / 2, y: a.y + a.h / 2 }, cz = { x: z.x + z.w / 2, y: z.y + z.h / 2 }
  const dx = cz.x - ca.x, dy = cz.y - ca.y
  if (Math.abs(dx) * a.h >= Math.abs(dy) * a.w)
    return dx >= 0 ? [{ x: a.x + a.w, y: ca.y }, { x: z.x, y: cz.y }] : [{ x: a.x, y: ca.y }, { x: z.x + z.w, y: cz.y }]
  return dy >= 0 ? [{ x: ca.x, y: a.y + a.h }, { x: cz.x, y: z.y }] : [{ x: ca.x, y: a.y }, { x: cz.x, y: z.y + z.h }]
}

/** Write the kit's colours into the theme and give tables alt text; refuse invalid colour values. */
async function finish(buf, kit, deck) {
  const zip = await JSZip.loadAsync(buf)
  const part = 'ppt/theme/theme1.xml'
  const colors = themeColors(kit)
  const name = xmlSafe(`${kit.company_name ?? kit.company_id} ${kit.version}`).replace(/"/g, '&quot;')
  const scheme = `<a:clrScheme name="${name}">` + Object.entries(colors).map(([k, v]) => `<a:${k}><a:srgbClr val="${v}"/></a:${k}>`).join('') + '</a:clrScheme>'
  let theme = await zip.file(part).async('string')
  theme = theme.replace(/<a:clrScheme\b[\s\S]*?<\/a:clrScheme>/, () => scheme).replace(/(<a:(?:theme|fontScheme)\b[^>]*?\bname=")[^"]*"/g, (_, h) => `${h}${name}"`)
  zip.file(part, theme)
  const alt = new Map(deck.slides.flatMap((s) => s.elements.filter((e) => e.kind === 'table' || e.kind === 'diagram').map((e) => [e.id, e.alt_text])))
  for (const file of Object.keys(zip.files).filter((f) => /^ppt\/slides\/slide\d+\.xml$/.test(f))) {
    let xml = await zip.file(file).async('string')
    xml = xml.replace(/<p:cNvPr id="(\d+)" name="([^"]*)"\/>/g, (m, id, nm) => (alt.has(nm) ? `<p:cNvPr id="${id}" name="${nm}" descr="${xmlSafe(alt.get(nm)).replace(/"/g, '&quot;')}"/>` : m))
    zip.file(file, xml)
  }
  for (const f of Object.keys(zip.files).filter((x) => x.endsWith('.xml'))) {
    const bad = (await zip.file(f).async('string')).match(/<a:srgbClr val="((?![0-9A-Fa-f]{6}")[^"]*)"/)
    if (bad) throw new Error(`internal: ${f} has an invalid colour value "${bad[1]}"`)
  }
  return zip.generateAsync({ type: 'nodebuffer', compression: 'DEFLATE' })
}
