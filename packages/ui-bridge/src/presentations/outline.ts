/**
 * Editing a storyline without JSON: each slide type exposes its content as a few plain text fields
 * (one item per line; "value | label | change" for numbers). Conversions are pure and round-trip.
 */
import type { Slide, Storyline } from './client'

export const TYPE_LABELS: Record<string, string> = {
  cover: 'Cover', section: 'Section divider', agenda: 'Agenda', statement: 'Key message', bullets: 'Points',
  kpis: 'Key numbers', chart: 'Chart', table: 'Table', comparison: 'Comparison', timeline: 'Timeline',
  diagram: 'Flow diagram', decision: 'Decision', quote: 'Quote', closing: 'Closing / next steps',
}

export type Field = { key: string; label: string; multiline?: boolean; hint?: string }

export function fieldsFor(type: string): Field[] {
  switch (type) {
    case 'cover': return [{ key: 'subtitle', label: 'Subtitle' }, { key: 'kicker', label: 'Small line above the title (e.g. the period)' }]
    case 'section': return [{ key: 'subtitle', label: 'Subtitle' }]
    case 'agenda': return [{ key: 'items', label: 'Items', multiline: true, hint: 'One per line' }]
    case 'statement': return [{ key: 'statement', label: 'Message', multiline: true }, { key: 'support', label: 'Supporting line', multiline: true }]
    case 'bullets': return [{ key: 'bullets', label: 'Points', multiline: true, hint: 'One per line' }, { key: 'takeaway', label: 'Takeaway (optional)' }]
    case 'kpis': return [{ key: 'kpis', label: 'Numbers', multiline: true, hint: 'value | label | change — one per line; “—” when unknown' }, { key: 'footnote', label: 'Footnote' }]
    case 'chart': return [{ key: 'chartType', label: 'Chart type', hint: 'column, bar, line or area' }, { key: 'unit', label: 'Unit' }, { key: 'data', label: 'Data', multiline: true, hint: 'First line: categories separated by |. Then one line per series: name | value | value … (blank = missing)' }, { key: 'insights', label: 'Insights', multiline: true, hint: 'Up to 3, one per line' }]
    case 'table': return [{ key: 'rows', label: 'Table', multiline: true, hint: 'First line: headers separated by |. Then one line per row' }]
    case 'comparison': return [{ key: 'leftHeading', label: 'Left heading' }, { key: 'leftPoints', label: 'Left points', multiline: true }, { key: 'rightHeading', label: 'Right heading' }, { key: 'rightPoints', label: 'Right points', multiline: true }]
    case 'timeline': return [{ key: 'milestones', label: 'Milestones', multiline: true, hint: 'label | date — one per line' }]
    case 'diagram': return [{ key: 'flow', label: 'Steps', multiline: true, hint: 'One step per line (connected in order), or “A -> B : label” lines' }]
    case 'decision': return [{ key: 'recommendation', label: 'Recommendation', multiline: true }, { key: 'options', label: 'Options', multiline: true, hint: 'One per line' }, { key: 'ask', label: 'What you need' }]
    case 'quote': return [{ key: 'quote', label: 'Quote', multiline: true }, { key: 'attribution', label: 'Who said it' }]
    case 'closing': return [{ key: 'subtitle', label: 'Subtitle' }, { key: 'next_steps', label: 'Next steps', multiline: true, hint: 'One per line' }]
    default: return []
  }
}

const lines = (v: string) => v.split('\n').map((x) => x.trim()).filter(Boolean)
const cells = (v: string) => v.split('|').map((x) => x.trim())
const numOrNull = (v: string) => (v === '' || v === '—' || v === '-' ? null : Number.isFinite(Number(v.replace(/,/g, ''))) ? Number(v.replace(/,/g, '')) : null)

export function readField(s: Slide, key: string): string {
  const a = (v: unknown) => (Array.isArray(v) ? v.join('\n') : '')
  switch (key) {
    case 'items': case 'bullets': case 'options': case 'next_steps': case 'insights': return a(s[key])
    case 'kpis': return ((s.kpis as { value: string; label: string; delta?: string }[]) ?? []).map((k) => [k.value, k.label, k.delta ?? ''].join(' | ').replace(/ \| $/, '')).join('\n')
    case 'chartType': return ((s.chart as { type?: string }) ?? {}).type ?? 'column'
    case 'unit': return ((s.chart as { unit?: string }) ?? {}).unit ?? ''
    case 'data': {
      const c = (s.chart ?? { categories: [], series: [] }) as { categories: string[]; series: { name: string; values: (number | null)[] }[] }
      return [c.categories.join(' | '), ...c.series.map((x) => [x.name, ...x.values.map((v) => (v === null ? '' : String(v)))].join(' | '))].join('\n')
    }
    case 'rows': return [((s.headers as string[]) ?? []).join(' | '), ...((s.rows as unknown[][]) ?? []).map((r) => r.map((c) => (c === null ? '—' : String(c))).join(' | '))].join('\n')
    case 'leftHeading': return ((s.left as { heading?: string }) ?? {}).heading ?? ''
    case 'rightHeading': return ((s.right as { heading?: string }) ?? {}).heading ?? ''
    case 'leftPoints': return a(((s.left as { points?: string[] }) ?? {}).points)
    case 'rightPoints': return a(((s.right as { points?: string[] }) ?? {}).points)
    case 'milestones': return ((s.milestones as { label: string; date?: string }[]) ?? []).map((m) => (m.date ? `${m.label} | ${m.date}` : m.label)).join('\n')
    case 'flow': {
      const nodes = (s.nodes as { id: string; label: string }[]) ?? []
      const edges = (s.edges as { from: string; to: string; label?: string }[]) ?? []
      const label = new Map(nodes.map((n) => [n.id, n.label]))
      const chain = edges.length === nodes.length - 1 && edges.every((e, i) => e.from === nodes[i].id && e.to === nodes[i + 1].id && !e.label)
      if (chain || !edges.length) return nodes.map((n) => n.label).join('\n')
      return edges.map((e) => `${label.get(e.from)} -> ${label.get(e.to)}${e.label ? ` : ${e.label}` : ''}`).join('\n')
    }
    default: return typeof s[key] === 'string' ? (s[key] as string) : ''
  }
}

export function writeField(s: Slide, key: string, v: string): Slide {
  const n: Slide = { ...s }
  switch (key) {
    case 'items': case 'bullets': case 'options': case 'next_steps': case 'insights':
      n[key] = lines(v)
      break
    case 'kpis':
      n.kpis = lines(v).map((l) => {
        const [value, label, delta] = cells(l)
        return { value: value || '—', label: label || '', ...(delta ? { delta } : {}) }
      })
      break
    case 'chartType': case 'unit': {
      const c = { ...((s.chart as object) ?? {}) } as Record<string, unknown>
      c[key === 'chartType' ? 'type' : 'unit'] = v.trim()
      n.chart = c
      break
    }
    case 'data': {
      const [head = '', ...rest] = v.split('\n').filter((l) => l.trim())
      const categories = cells(head).filter(Boolean)
      const c = { ...((s.chart as object) ?? {}) } as Record<string, unknown>
      c.categories = categories
      c.series = rest.map((l) => {
        const [name, ...vals] = cells(l)
        return { name: name || 'Series', values: categories.map((_, i) => numOrNull(vals[i] ?? '')) }
      })
      n.chart = c
      break
    }
    case 'rows': {
      const [head = '', ...rest] = v.split('\n').filter((l) => l.trim())
      n.headers = cells(head)
      n.rows = rest.map((l) => {
        const r = cells(l)
        return (n.headers as string[]).map((_, i) => (r[i] === undefined || r[i] === '' ? null : r[i]))
      })
      break
    }
    case 'leftHeading': case 'rightHeading': case 'leftPoints': case 'rightPoints': {
      const side = key.startsWith('left') ? 'left' : 'right'
      const cur = { heading: '', points: [] as string[], ...((s[side] as object) ?? {}) }
      if (key.endsWith('Heading')) cur.heading = v
      else cur.points = lines(v)
      n[side] = cur
      break
    }
    case 'milestones':
      n.milestones = lines(v).map((l) => {
        const [label, date] = cells(l)
        return { label, ...(date ? { date } : {}) }
      })
      break
    case 'flow': {
      const ls = lines(v)
      const id = (label: string) => label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40) || 'step'
      if (ls.some((l) => l.includes('->'))) {
        const nodes = new Map<string, string>()
        const edges: { from: string; to: string; label?: string }[] = []
        for (const l of ls) {
          const [pair, label] = l.split(':').map((x) => x.trim())
          const [a, b] = pair.split('->').map((x) => x.trim())
          if (!a || !b) continue
          nodes.set(id(a), a)
          nodes.set(id(b), b)
          edges.push({ from: id(a), to: id(b), ...(label ? { label } : {}) })
        }
        n.nodes = [...nodes].map(([k, label]) => ({ id: k, label }))
        n.edges = edges
      } else {
        const used = new Set<string>()
        const nodes = ls.map((label, i) => {
          let k = id(label)
          if (used.has(k)) k = `${k}-${i + 1}`
          used.add(k)
          return { id: k, label }
        })
        n.nodes = nodes
        n.edges = nodes.slice(1).map((node, i) => ({ from: nodes[i].id, to: node.id }))
      }
      break
    }
    default:
      n[key] = v
  }
  return n
}

let counter = 0
export function newSlide(type: string, existing: Slide[]): Slide {
  const ids = new Set(existing.map((s) => s.id))
  let id = `${type}-${++counter}`
  while (ids.has(id)) id = `${type}-${++counter}`
  const base = { id, type, title: TYPE_LABELS[type] ?? 'Slide' }
  switch (type) {
    case 'agenda': return { ...base, items: ['First topic', 'Second topic'] }
    case 'statement': return { ...base, statement: 'The one message for this slide.' }
    case 'bullets': return { ...base, bullets: ['First point', 'Second point'] }
    case 'kpis': return { ...base, kpis: [{ value: '—', label: 'Metric' }] }
    case 'chart': return { ...base, chart: { type: 'column', title: '', unit: '', categories: ['A', 'B', 'C'], series: [{ name: 'Series', values: [null, null, null] }] } }
    case 'table': return { ...base, headers: ['Item', 'Detail'], rows: [['—', '—']] }
    case 'comparison': return { ...base, left: { heading: 'Option A', points: ['Point'] }, right: { heading: 'Option B', points: ['Point'] } }
    case 'timeline': return { ...base, milestones: [{ label: 'Start' }, { label: 'Finish' }] }
    case 'diagram': return { ...base, nodes: [{ id: 'a', label: 'Step one' }, { id: 'b', label: 'Step two' }], edges: [{ from: 'a', to: 'b' }] }
    case 'decision': return { ...base, recommendation: 'Recommended option and why.' }
    case 'quote': return { ...base, quote: 'A memorable line.' }
    case 'closing': return { ...base, title: 'Next steps', next_steps: ['First action'] }
    default: return base
  }
}

/** Give every slide a stable id (needed for locks and per-slide regeneration). */
export function withIds(s: Storyline): Storyline {
  const used = new Set<string>()
  return {
    ...s,
    slides: s.slides.map((sl, i) => {
      let id = sl.id && /^[A-Za-z0-9_-]{1,60}$/.test(sl.id) ? sl.id : `s${i + 1}`
      while (used.has(id)) id = `${id}-${i + 1}`
      used.add(id)
      return { ...sl, id }
    }),
  }
}
