/** presentation-engine checks. Run: node test/engine.test.mjs */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import * as E from '../src/index.mjs'
import { SAMPLE_KITS, weeklySample } from '../src/samples.mjs'
import { solidPng } from './png.mjs'

let checks = 0
const ok = async (name, fn) => {
  try {
    await fn()
    checks++
  } catch (e) {
    console.error('FAIL', name)
    throw e
  }
}
const build = async (story, kit, assets = {}) => {
  const { deck, findings } = E.compose(story, kit, { deckId: 'd1' })
  const { pptx, scene } = await E.compile(deck, kit, assets)
  const inspection = await E.inspect(pptx)
  return { deck, findings, pptx, scene, inspection, receipt: E.checkDeck({ deck, kit, scene, inspection, pptxSha256: E.sha256(pptx) }) }
}

await ok('both sample companies: every layout composes, compiles and passes the gate', async () => {
  for (const make of Object.values(SAMPLE_KITS)) {
    const kit = make()
    const r = await build(weeklySample(), kit)
    assert.deepEqual(r.findings, [])
    assert.equal(r.receipt.status, 'passed', JSON.stringify(r.receipt.findings))
    assert.equal(r.receipt.hard_failures, 0)
    assert.equal(r.inspection.slides.length, 12)
    assert.equal(r.inspection.slides.filter((s) => s.charts.length).length, 2)
    assert.equal(r.inspection.slides.reduce((a, s) => a + s.tables, 0), 1)
    assert.ok(r.inspection.slides.every((s) => s.notes.trim().length > 0))
    assert.deepEqual(r.inspection.themeColors, E.themeColors(kit))
    assert.ok(r.inspection.fonts.every((f) => kit.allowed_fonts.includes(f)))
  }
})

await ok('native objects: chart series, table, editable diagram nodes, alt text and stable object names', async () => {
  const r = await build(weeklySample(), SAMPLE_KITS.northwind())
  const chart = r.inspection.slides[3]
  assert.equal(chart.charts[0].series, 1)
  assert.ok(chart.names.includes('throughput__chart__main'))
  const flow = r.inspection.slides[8]
  for (const n of ['plan', 'build', 'review', 'release', 'monitor']) assert.ok(flow.names.includes(`flow__diagram__main__node__${n}`))
  assert.ok(r.inspection.slides[6].altTexts >= 1, 'the table carries alt text')
  assert.ok(chart.altTexts >= 1, 'the chart carries alt text')
  assert.equal(r.inspection.hasMacros, false)
  assert.equal(r.inspection.externalLinks, 0)
})

await ok('the PR 19 fixture deck compiles unchanged and passes', async () => {
  const ex = new URL('../../../docs/presentations/examples/', import.meta.url)
  const kit = JSON.parse(fs.readFileSync(new URL('brand-kit.example.json', ex)))
  const deck = JSON.parse(fs.readFileSync(new URL('deck-spec.example.json', ex)))
  const { pptx, scene } = await E.compile(deck, kit, {})
  const inspection = await E.inspect(pptx)
  const r = E.checkDeck({ deck, kit, scene, inspection, pptxSha256: E.sha256(pptx) })
  assert.equal(r.hard_failures, 0, JSON.stringify(r.findings))
  assert.equal(inspection.slides.length, 6)
})

await ok('semantic output is deterministic', async () => {
  const kit = SAMPLE_KITS.verdant()
  const a = E.compose(weeklySample(), kit, { deckId: 'd' }).deck
  const b = E.compose(weeklySample(), kit, { deckId: 'd' }).deck
  assert.equal(E.digest(a), E.digest(b))
  // pptxgenjs numbers chart parts with a process-wide counter, so part names are not compared
  const strip = (i) => ({ ...i, slides: i.slides.map((s) => ({ ...s, charts: s.charts.map(({ part, ...c }) => c) })) })
  const ia = strip(await E.inspect((await E.compile(a, kit)).pptx))
  const ib = strip(await E.inspect((await E.compile(b, kit)).pptx))
  assert.deepEqual(ia, ib)
})

await ok('text that cannot fit is a finding, never a silent cut or a size below the minimum', async () => {
  const story = { schema_version: 'daypilot.storyline/v1', title: 'T', slides: [{ type: 'bullets', title: 'Too much', takeaway: 'Narrow column', bullets: Array(7).fill('This bullet is long enough to wrap onto several lines at the minimum size, and there are seven of them, which is too many for one slide by design. '.slice(0, 199)) }] }
  const base = SAMPLE_KITS.northwind()
  const kit = { ...base, typography: { ...base.typography, body: { ...base.typography.body, minimum_pt: 22, preferred_pt: 24 } } }
  const { findings } = E.compose(story, kit)
  assert.ok(findings.some((f) => f.code === 'text_overflow'))
  const r = await build(story, kit)
  assert.equal(r.receipt.status, 'failed')
  assert.ok(r.receipt.findings.some((f) => f.code === 'text_overflow'))
  assert.ok(r.scene.slides[0].objects.filter((o) => o.kind === 'text').every((o) => o.pt >= o.minPt))
})

await ok('hostile text is escaped data in every part of the file', async () => {
  const evil = '<script>&"\'</a:t><p:sp>'
  const kit = { ...SAMPLE_KITS.northwind(), company_name: 'Harrow & Sons <x>', footer: { text: 'A & B <c>', required: true, show_page_number: true } }
  const story = { schema_version: 'daypilot.storyline/v1', title: evil, slides: [
    { type: 'cover', title: evil, subtitle: evil, kicker: '&&' },
    { type: 'table', title: 'T & <x>', headers: ['A<b>', 'B&'], rows: [[evil, 3]] },
    { type: 'diagram', title: 'D', nodes: [{ id: 'a', label: evil }, { id: 'b', label: '&' }], edges: [{ from: 'a', to: 'b', label: '<&>' }] },
    { type: 'chart', title: 'C', chart: { type: 'bar', title: evil, unit: '&', categories: ['<a>', 'b&'], series: [{ name: evil.slice(0, 50), values: [1, 2] }] } },
  ] }
  const r = await build(story, kit)
  const text = r.inspection.slides.map((s) => s.text).join(' ')
  assert.ok(text.includes(evil), 'text survives as text')
  assert.equal(r.receipt.hard_failures, 0, JSON.stringify(r.receipt.findings))
})

await ok('logos keep their proportions; a stretched logo is a hard failure', async () => {
  const png = solidPng(300, 100, [11, 60, 93])
  const kit = { ...SAMPLE_KITS.northwind(), logos: [{ asset_id: 'logo1', sha256: E.sha256(png), variant: 'universal', aspect_ratio: 3, minimum_width_inches: 1.2, clear_space_ratio: 0.2, rights: 'company_original' }] }
  const assets = { logo1: { media_type: 'image/png', base64: png.toString('base64'), width: 300, height: 100 } }
  const r = await build(weeklySample(), kit, assets)
  assert.equal(r.receipt.hard_failures, 0, JSON.stringify(r.receipt.findings))
  assert.ok(r.inspection.slides.every((s) => s.pictures >= 0))
  const logo = r.scene.slides[1].derived.find((d) => d.id === 'logo')
  assert.ok(Math.abs(logo.aspect - 3) < 0.01 && logo.box.w >= 1.2 - 1e-9)
  const bad = { ...kit, logos: [{ ...kit.logos[0], aspect_ratio: 2 }] }
  const r2 = await build(weeklySample(), bad, assets)
  assert.equal(r2.receipt.hard_failures, 0, 'the declared ratio drives placement, so it is consistent with itself')
  r2.scene.slides[1].derived.find((d) => d.id === 'logo').expected_aspect = 3
  const again = E.checkDeck({ deck: r2.deck, kit: bad, scene: r2.scene, inspection: r2.inspection, pptxSha256: 'x' })
  assert.ok(again.findings.some((f) => f.code === 'distorted_image'))
})

await ok('validation refuses bad kits, storylines and decks with readable problems', async () => {
  const kit = SAMPLE_KITS.northwind()
  const bad = [
    { ...kit, palette: { ...kit.palette, primary: 'blue' } },
    { ...kit, typography: { ...kit.typography, body: { family: 'Calibri', minimum_pt: 8, preferred_pt: 20 } } },
    { ...kit, typography: { ...kit.typography, body: { family: 'Comic Sans', minimum_pt: 16, preferred_pt: 20 } } },
    { ...kit, slide_size: { width_inches: 100, height_inches: 7.5 } },
    { ...kit, schema_version: 'x' },
  ]
  for (const k of bad) assert.throws(() => E.validateBrandKit(k), E.SpecError)
  const story = weeklySample()
  const broken = [
    { ...story, slides: [] }, { ...story, slides: [{ type: 'nope', title: 'x' }] },
    { ...story, slides: [{ type: 'chart', title: 'x', chart: { type: 'pie', categories: ['a'], series: [{ name: 's', values: [1] }] } }] },
    { ...story, slides: [{ type: 'chart', title: 'x', chart: { type: 'bar', categories: ['a', 'b'], series: [{ name: 's', values: [1] }] } }] },
    { ...story, slides: [{ type: 'chart', title: 'x', chart: { type: 'bar', categories: ['a'], series: [{ name: 's', values: [Infinity] }] } }] },
    { ...story, slides: [{ type: 'diagram', title: 'x', nodes: [{ id: 'a', label: 'A' }, { id: 'b', label: 'B' }], edges: [{ from: 'a', to: 'z' }] }] },
    { ...story, slides: [{ type: 'table', title: 'x', headers: ['a', 'b'], rows: [['1']] }] },
    { ...story, slides: Array(51).fill({ type: 'statement', title: 'x', statement: 'y' }) },
    { ...story, slides: [{ id: 'dup', type: 'statement', title: 'x', statement: 'y' }, { id: 'dup', type: 'statement', title: 'x', statement: 'y' }] },
  ]
  for (const s of broken) assert.throws(() => E.validateStoryline(s), E.SpecError)
  const { deck } = E.compose(weeklySample(), kit)
  const tamper = (fn) => { const d = structuredClone(deck); fn(d); assert.throws(() => E.validateDeck(d, kit), E.SpecError) }
  tamper((d) => { d.slide_count.exact = 3 })
  tamper((d) => { d.slides[1].elements[0].bounds.x = 0.95 })
  tamper((d) => { d.slides[1].id = d.slides[0].id })
  tamper((d) => { d.company_id = 'other' })
  tamper((d) => { d.slides[2].claims[0].metric_ref.metric_id = 'ghost' })
  tamper((d) => { d.sources[0].metrics[0].value = 26; d.slides[3].elements[1].series[0].points[0].metric_ref = { source_snapshot_id: 'metrics', metric_id: 'accepted' } })
})

await ok('evidence: a claim that disagrees with its source fails the gate', async () => {
  const story = weeklySample()
  story.slides[2].kpis[0].numeric_value = 26
  const r = await build(story, SAMPLE_KITS.northwind())
  assert.ok(r.receipt.findings.some((f) => f.code === 'evidence'))
  assert.equal(r.receipt.status, 'failed')
})

await ok('missing chart values stay missing and decimals are labelled as decimals', async () => {
  const story = { schema_version: 'daypilot.storyline/v1', title: 'T', slides: [{ type: 'chart', title: 'Gaps', chart: { type: 'line', unit: 'days', categories: ['a', 'b', 'c'], series: [{ name: 's', values: [1.5, null, 2.25] }] } }] }
  const r = await build(story, SAMPLE_KITS.verdant())
  assert.equal(r.receipt.hard_failures, 0)
  assert.equal(r.deck.slides[0].elements[1].series[0].points[1].value, null)
})

await ok('low-contrast brand colours are flagged before activation and avoided on slides', async () => {
  const kit = { ...SAMPLE_KITS.verdant(), palette: { ...SAMPLE_KITS.verdant().palette, primary: '#FFE066', muted: '#BBBBBB' } }
  const w = E.brandWarnings(E.validateBrandKit(kit))
  assert.ok(w.some((x) => x.includes('Muted text contrast')))
  const r = await build(weeklySample(), kit)
  assert.equal(r.receipt.findings.filter((f) => f.code === 'contrast' && f.severity === 'hard').length, 0)
})

await ok('layered diagram layout is bounded and handles cycles', async () => {
  const nodes = Array.from({ length: 6 }, (_, i) => ({ id: 'n' + i }))
  const { place } = E.layeredLayout(nodes, [{ from: 'n0', to: 'n1' }, { from: 'n1', to: 'n2' }, { from: 'n2', to: 'n0' }, { from: 'n3', to: 'n4' }])
  for (const b of place.values()) assert.ok(b.x >= 0 && b.y >= 0 && b.x + b.w <= 1 && b.y + b.h <= 1)
})

await ok('fit uses real metrics: wider text needs smaller type or more lines', async () => {
  assert.ok(E.measure('WWWW', 'Arial', 20) > E.measure('iiii', 'Arial', 20) * 3)
  const r = E.fit('A short title', { w: 10, h: 1 }, { font: 'Calibri', maxPt: 36, minPt: 24 })
  assert.equal(r.pt, 36)
  assert.equal(E.fit('x', { w: 1, h: 1 }, { font: 'Nonexistent', maxPt: 20, minPt: 12 }).verified, false)
})

await ok('line charts of values far from zero get a fitted axis; bars and columns keep zero', async () => {
  const kit = Object.values(SAMPLE_KITS)[0]()
  const story = (type, values) => ({ schema_version: 'daypilot.storyline/v1', title: 'T', slides: [{ id: 'c', type: 'chart', title: 'Forecasts', chart: { type, categories: ['2016', '2022', '2023', '2024'], series: [{ name: 'Year', values }] } }] })
  const line = E.compose(story('line', [2061, 2059, 2047, 2042]), kit, { deckId: 'd' }).deck.slides[0].elements.find((e) => e.kind === 'chart')
  assert.equal(line.axis_zero_baseline, false)
  assert.ok(line.axis_min <= 2042 && line.axis_min >= 2000 && line.axis_max >= 2061 && line.axis_max <= 2100, JSON.stringify(line))
  const col = E.compose(story('column', [2061, 2059, 2047, 2042]), kit, { deckId: 'd' }).deck.slides[0].elements.find((e) => e.kind === 'chart')
  assert.equal(col.axis_zero_baseline, true)
  assert.equal(col.axis_min, undefined)
  const near = E.compose(story('line', [3, 9, 4, 12]), kit, { deckId: 'd' }).deck.slides[0].elements.find((e) => e.kind === 'chart')
  assert.equal(near.axis_zero_baseline, true)
  const { pptx } = await E.compile(E.compose(story('line', [2061, 2059, 2047, 2042]), kit, { deckId: 'd' }).deck, kit, {})
  const xml = await (await (await import('jszip')).default.loadAsync(pptx)).file(/ppt\/charts\/chart\d+\.xml/)[0].async('string')
  assert.match(xml, /<c:min val="20\d\d"\/>/)
})

await ok('KPI figures on one slide share a size; timed scripts lead the speaker notes', async () => {
  const kit = Object.values(SAMPLE_KITS)[0]()
  const story = { schema_version: 'daypilot.storyline/v1', title: 'T', talk: { minutes: 1, wpm: 140 }, slides: [
    { id: 'k', type: 'kpis', title: 'Numbers', seconds: 35, script: 'Say this first.', notes: 'Pause here.', kpis: [{ value: '4–5×', label: 'Growth' }, { value: '700M+', label: 'Users' }, { value: 'Gold', label: 'Maths' }, { value: '2–6×', label: 'Efficiency' }] },
    { id: 'e', type: 'closing', title: 'End', seconds: 25, script: 'Thank you.' },
  ] }
  const r = await build(story, kit)
  const values = r.scene.slides[0].objects.filter((o) => /__kpi\d+__value$/.test(o.id))
  assert.equal(values.length, 4)
  assert.equal(new Set(values.map((v) => v.pt)).size, 1, JSON.stringify(values.map((v) => v.pt)))
  assert.match(r.inspection.slides[0].notes, /^\[0:35 on this slide · from 0:00 · 3 words\]\s+Say this first\.\s+Guidance: Pause here\./)
  assert.match(r.inspection.slides[1].notes, /\[0:25 on this slide · from 0:35 · 2 words\]/)
})

console.log(`presentation-engine: ${checks} checks passed`)
