/**
 * Storyline (daypilot.storyline/v1): what a person or a model writes. It says what each slide is
 * for and what it contains, never where things go. The composer turns it into a DeckSpec.
 * Everything here is bounded; text is data and is never interpreted as markup or code.
 */
import { SpecError } from './brand.mjs'

export const SLIDE_TYPES = ['cover', 'section', 'agenda', 'statement', 'bullets', 'kpis', 'chart', 'table', 'comparison', 'timeline', 'diagram', 'decision', 'quote', 'closing']
export const MAX_SLIDES = 50
const ID = /^[A-Za-z0-9_-]{1,60}$/

const str = (v, max) => typeof v === 'string' && v.trim() && [...v].length <= max
const opt = (v, max) => v === undefined || v === null || v === '' || (typeof v === 'string' && [...v].length <= max)
const list = (v, min, max) => Array.isArray(v) && v.length >= min && v.length <= max

export function validateStoryline(s) {
  const p = []
  if (!s || typeof s !== 'object') throw new SpecError(['storyline must be an object'])
  if (s.schema_version !== 'daypilot.storyline/v1') p.push('schema_version must be daypilot.storyline/v1')
  if (!str(s.title, 200)) p.push('title: 1-200 characters')
  for (const k of ['subtitle', 'audience', 'purpose']) if (!opt(s[k], 300)) p.push(`${k}: up to 300 characters`)
  if (!list(s.slides, 1, MAX_SLIDES)) p.push(`slides: 1-${MAX_SLIDES}`)
  if (s.talk !== undefined && s.talk !== null) {
    const t = s.talk
    if (!t || typeof t !== 'object' || !Number.isFinite(t.minutes) || t.minutes < 1 || t.minutes > 120 || !Number.isInteger(t.wpm ?? 140) || (t.wpm ?? 140) < 90 || (t.wpm ?? 140) > 220)
      p.push('talk: minutes 1-120 and wpm 90-220')
  }
  const ids = new Set()
  ;(Array.isArray(s.slides) ? s.slides : []).forEach((sl, i) => {
    const w = `slide ${i + 1}`
    if (!sl || typeof sl !== 'object') return p.push(`${w}: must be an object`)
    if (!SLIDE_TYPES.includes(sl.type)) return p.push(`${w}: type must be one of ${SLIDE_TYPES.join(', ')}`)
    if (sl.id !== undefined && (!ID.test(sl.id) || ids.has(sl.id))) p.push(`${w}: id must be unique, letters/digits/_/-`)
    if (sl.id) ids.add(sl.id)
    if (!str(sl.title, 160)) p.push(`${w}: title 1-160 characters`)
    if (!opt(sl.notes, 4000)) p.push(`${w}: notes up to 4000 characters`)
    if (!opt(sl.script, 4000)) p.push(`${w}: script up to 4000 characters`)
    if (sl.seconds !== undefined && sl.seconds !== null && !(Number.isInteger(sl.seconds) && sl.seconds >= 0 && sl.seconds <= 7200)) p.push(`${w}: seconds must be a whole number 0-7200`)
    if (sl.sources !== undefined && !(list(sl.sources, 0, 20) && sl.sources.every((x) => str(x, 300)))) p.push(`${w}: sources up to 20 short references`)
    const need = (cond, msg) => cond || p.push(`${w} (${sl.type}): ${msg}`)
    switch (sl.type) {
      case 'cover':
      case 'section':
        need(opt(sl.subtitle, 240) && opt(sl.kicker, 80), 'subtitle ≤ 240, kicker ≤ 80')
        break
      case 'agenda':
        need(list(sl.items, 2, 8) && sl.items.every((x) => str(x, 90)), '2-8 items of ≤ 90 characters')
        break
      case 'statement':
        need(str(sl.statement, 220) && opt(sl.support, 400), 'statement ≤ 220, support ≤ 400')
        break
      case 'bullets':
        need(list(sl.bullets, 1, 7) && sl.bullets.every((x) => str(x, 200)), '1-7 bullets of ≤ 200 characters')
        need(opt(sl.takeaway, 200), 'takeaway ≤ 200')
        break
      case 'kpis':
        need(
          list(sl.kpis, 1, 4) && sl.kpis.every((k) => k && str(String(k.value ?? ''), 14) && str(k.label, 60) && opt(k.delta, 40)),
          '1-4 KPIs with value ≤ 14, label ≤ 60, delta ≤ 40',
        )
        need(opt(sl.footnote, 200), 'footnote ≤ 200')
        break
      case 'chart': {
        const c = sl.chart
        need(c && ['bar', 'column', 'line', 'area', 'scatter'].includes(c.type), 'chart.type bar|column|line|area|scatter')
        need(c && list(c.categories, 1, 40) && c.categories.every((x) => str(String(x), 40)), 'chart.categories 1-40 labels')
        need(
          c && list(c.series, 1, 6) && c.series.every((x) => x && str(x.name, 60) && Array.isArray(x.values) && x.values.length === (c.categories ?? []).length && x.values.every((v) => v === null || Number.isFinite(v))),
          'chart.series 1-6, each with one finite number (or null for missing) per category',
        )
        need(c && opt(c.unit, 30) && opt(c.title, 120), 'chart.unit ≤ 30, chart.title ≤ 120')
        need(sl.insights === undefined || (list(sl.insights, 0, 3) && sl.insights.every((x) => str(x, 160))), 'insights: up to 3 of ≤ 160')
        break
      }
      case 'table':
        need(list(sl.headers, 2, 8) && sl.headers.every((x) => str(x, 40)), '2-8 headers')
        need(list(sl.rows, 1, 14) && sl.rows.every((r) => Array.isArray(r) && r.length === (sl.headers ?? []).length && r.every((c) => c === null || typeof c === 'number' || opt(c, 80))), '1-14 rows, one cell per header (≤ 80 characters)')
        break
      case 'comparison':
        for (const side of ['left', 'right'])
          need(sl[side] && str(sl[side].heading, 60) && list(sl[side].points, 1, 5) && sl[side].points.every((x) => str(x, 140)), `${side}: heading and 1-5 points`)
        break
      case 'timeline':
        need(list(sl.milestones, 2, 7) && sl.milestones.every((m) => m && str(m.label, 60) && opt(m.date, 24)), '2-7 milestones with label ≤ 60, date ≤ 24')
        break
      case 'diagram':
        need(list(sl.nodes, 2, 14) && sl.nodes.every((n) => n && ID.test(n.id ?? '') && str(n.label, 50)), '2-14 nodes with id and label ≤ 50')
        need(Array.isArray(sl.edges) && sl.edges.length <= 30 && sl.edges.every((e) => e && (sl.nodes ?? []).some((n) => n.id === e.from) && (sl.nodes ?? []).some((n) => n.id === e.to) && e.from !== e.to && opt(e.label, 30)), 'edges between listed nodes, label ≤ 30')
        break
      case 'decision':
        need(str(sl.recommendation, 240), 'recommendation ≤ 240')
        need(sl.options === undefined || (list(sl.options, 0, 4) && sl.options.every((x) => str(x, 140))), 'options: up to 4')
        need(opt(sl.ask, 160), 'ask ≤ 160')
        break
      case 'quote':
        need(str(sl.quote, 300) && opt(sl.attribution, 80), 'quote ≤ 300, attribution ≤ 80')
        break
      case 'closing':
        need(sl.next_steps === undefined || (list(sl.next_steps, 0, 5) && sl.next_steps.every((x) => str(x, 120))), 'next_steps: up to 5')
        need(opt(sl.subtitle, 200), 'subtitle ≤ 200')
        break
    }
  })
  if (p.length) throw new SpecError(p)
  return s
}
