/**
 * Pure-module checks for the dmind batches (B1 onward). Run with: node tests/ui/dmind-modules.mjs
 * Each section is one batch; the shared contract corpus lives in tests/ui/dmind.mjs.
 */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { loadDiagramModules } from './_load.mjs'

const m = await loadDiagramModules()
const fixture = JSON.parse(
  fs.readFileSync(new URL('../../packages/dmind-contract/order-system.dmind.json', import.meta.url)),
)
const bytes = (s) => new TextEncoder().encode(s)
let checks = 0
const section = (name, fn) => {
  const before = checks
  fn()
  console.log(`  ${name}: ${checks - before} checks`)
}
const ok = (fn) => {
  fn()
  checks++
}

// ---------------------------------------------------------------- B1 .dmind file
section('B1 .dmind file', () => {
  const f = m.dmindFile
  ok(() => {
    const text = f.serializeDmind(fixture)
    assert.ok(text.endsWith('}\n') && text.startsWith('{\n  "schema_version"'))
    const back = f.importFile('order.dmind', bytes(text))
    assert.equal(back.kind, 'diagram')
    assert.equal(back.via, 'dmind')
    assert.deepEqual(back.diagram, fixture)
    assert.equal(back.report.total, 0)
  })
  ok(() => {
    const extended = structuredClone(fixture)
    extended.future = { a: 1 }
    extended.nodes[0].icon = 'star'
    extended.edges[0].weight = 3
    extended.metadata.custom = true
    const text = f.serializeDmind(extended)
    const { diagram, report } = f.importFile('x.dmind', bytes(text))
    assert.deepEqual(diagram, extended, 'unknown fields survive open and save')
    assert.deepEqual(report.topLevel, ['future'])
    assert.deepEqual(report.nodeKeys, ['icon'])
    assert.deepEqual(report.edgeKeys, ['weight'])
    assert.deepEqual(report.metadataKeys, ['custom'])
    assert.match(f.describeUnknown(report), /Kept 4 field\(s\)/)
    assert.equal(f.describeUnknown({ total: 0 }), '')
    assert.deepEqual(f.importFile('x.dmind', bytes(f.serializeDmind(diagram))).diagram, extended)
  })
  ok(() => {
    const withBom = new Uint8Array([0xef, 0xbb, 0xbf, ...bytes(JSON.stringify(fixture))])
    assert.deepEqual(f.importFile('bom.dmind', withBom).diagram, fixture)
    assert.equal(f.detectForm(withBom), 'json')
    assert.equal(f.detectForm(bytes('  \n {')), 'json')
    assert.equal(f.detectForm(new Uint8Array([0x50, 0x4b, 3, 4])), 'zip')
    assert.equal(f.detectForm(bytes('hello')), 'unknown')
    assert.equal(f.detectForm(new Uint8Array()), 'unknown')
  })
  ok(() => {
    assert.throws(() => f.importFile('bad.dmind', new Uint8Array([0xff, 0xfe, 0x7b])), /not valid UTF-8|not a dmind/)
    assert.throws(() => f.importFile('bad.dmind', bytes('{"schema_version": ')), /not valid JSON/)
    assert.throws(() => f.importFile('bad.dmind', bytes('hello')), /should be JSON/)
    assert.throws(() => f.importFile('v2.dmind', bytes('{"schema_version":"dmind/v2"}')), /dmind\/v2.*Update DayPilot/)
    assert.throws(() => f.importFile('x.dmind', bytes('{"schema_version":"dmind/v1"}')), /./)
    assert.throws(() => f.importFile('big.dmind', new Uint8Array(2_000_001)), /smaller than 2 MB/)
    assert.throws(() => f.importFile('doc.pdf', bytes('%PDF')), /Supported attachments/)
    assert.throws(() => f.importFile('bundle.dmind', new Uint8Array([0x50, 0x4b, 3, 4])), /ZIP/)
  })
  ok(() => {
    const text = f.importFile('notes.md', bytes('- one\n  - two'))
    assert.deepEqual(text, { kind: 'text', text: '- one\n  - two', name: 'notes.md' })
    assert.throws(() => f.importFile('notes.txt', bytes('x'.repeat(100_001))), /100000/)
    const bundle = {
      schema_version: 'matrix.designer.bundle/v1',
      project: 'P',
      source: { idea: 'i' },
      batch_roadmap: [{ id: 'b1', name: 'One', purpose: 'p' }],
    }
    const viaBundle = f.importFile('bundle.json', bytes(JSON.stringify(bundle)))
    assert.equal(viaBundle.via, 'bundle')
    assert.deepEqual(viaBundle.diagram.metadata.design_bundle, bundle)
  })
  ok(() => {
    assert.equal(f.dmindFileName('Order processing'), 'Order-processing.dmind')
    assert.equal(f.dmindFileName('A/B: C?*'), 'A-B-C.dmind')
    assert.equal(f.dmindFileName('../../etc/passwd'), 'etc-passwd.dmind')
    assert.equal(f.dmindFileName('   '), 'diagram.dmind')
    assert.equal(f.dmindFileName('订单 流程'), '订单-流程.dmind')
    assert.ok(f.dmindFileName('x'.repeat(300)).length <= 86)
  })
  ok(() => {
    // A hostile key cannot reach Object.prototype through open, report or save.
    const hostile = '{"__proto__":{"polluted":true},' + JSON.stringify(fixture).slice(1)
    const { diagram, report } = f.importFile('h.dmind', bytes(hostile))
    assert.equal({}.polluted, undefined)
    assert.equal(Object.hasOwn(diagram, '__proto__'), true)
    assert.deepEqual(report.topLevel, ['__proto__'])
    assert.equal({}.polluted, undefined)
    f.serializeDmind(diagram)
    assert.equal({}.polluted, undefined)
  })
})


// ---------------------------------------------------------------- B2 reliable workspace
const asyncSection = async (name, fn) => {
  const before = checks
  await fn()
  console.log(`  ${name}: ${checks - before} checks`)
}
await asyncSection('B2 draft store', async () => {
  const d = m.draftStore
  const store = new d.MemoryStore()
  const rec = (id, at, kind = 'draft') => ({ id, kind, document: structuredClone(fixture), saved: null, updatedAt: at })
  await d.putDraft(store, 'ann@x', 'ws1', rec('a', 1))
  await d.putDraft(store, 'ann@x', 'ws2', rec('b', 2))
  await d.putDraft(store, 'bob@x', 'ws1', rec('c', 3))
  await d.putDraft(store, 'ann@x"],["', 'ws1', rec('tricky', 4)) // JSON-looking ids cannot cross scopes
  assert.deepEqual((await d.listDrafts(store, 'ann@x', 'ws1')).map((r) => r.id), ['a'])
  assert.deepEqual((await d.listDrafts(store, 'ann@x', 'ws2')).map((r) => r.id), ['b'])
  assert.deepEqual((await d.listDrafts(store, 'bob@x', 'ws1')).map((r) => r.id), ['c'])
  assert.deepEqual((await d.listDrafts(store, 'ann@x"],["', 'ws1')).map((r) => r.id), ['tricky'])
  assert.deepEqual(await d.listDrafts(store, 'ann', 'ws1'), [])
  checks += 5
  // Records are copies: mutating what was stored or read never changes the store.
  const stored = rec('copy', 5)
  await d.putDraft(store, 'ann@x', 'ws1', stored)
  stored.document.title = 'mutated'
  const read = (await d.listDrafts(store, 'ann@x', 'ws1')).find((r) => r.id === 'copy')
  assert.notEqual(read.document.title, 'mutated')
  read.document.title = 'also mutated'
  assert.notEqual((await store.get(d.draftKey('ann@x', 'ws1', 'copy'))).document.title, 'also mutated')
  assert.equal((await d.listDrafts(store, 'ann@x', 'ws1'))[0].id, 'copy') // newest first
  checks += 3
  // Only unsaved drafts are pruned; conflict copies are kept until the person resolves them.
  const busy = new d.MemoryStore()
  await d.putDraft(busy, 'u', 'w', rec('keep-conflict', 0, 'conflict'))
  for (let i = 1; i <= 30; i++) await d.putDraft(busy, 'u', 'w', rec('d' + i, i))
  const all = await d.listDrafts(busy, 'u', 'w')
  assert.equal(all.filter((r) => r.kind === 'draft').length, d.MAX_DRAFTS_PER_SCOPE)
  assert.ok(all.some((r) => r.id === 'keep-conflict'))
  assert.ok(all.some((r) => r.id === 'd30') && !all.some((r) => r.id === 'd1'))
  checks += 3
  await d.removeDraft(busy, 'u', 'w', 'd30')
  assert.ok(!(await d.listDrafts(busy, 'u', 'w')).some((r) => r.id === 'd30'))
  await d.clearScope(store, 'ann@x', 'ws1')
  assert.deepEqual(await d.listDrafts(store, 'ann@x', 'ws1'), [])
  assert.equal((await d.listDrafts(store, 'ann@x', 'ws2')).length, 1) // other scopes untouched
  await d.clearAllDrafts(store)
  assert.deepEqual(await d.listDrafts(store, 'bob@x', 'ws1'), [])
  checks += 4
  assert.equal(store.durable, false)
  assert.equal((await d.openDraftStore(undefined)).durable, false) // no IndexedDB: memory fallback
  const broken = { open: () => { throw new Error('blocked') } }
  assert.equal((await d.openDraftStore(broken)).durable, false)
  assert.equal(d.draftsEnabled({ getItem: () => 'off' }), false)
  assert.equal(d.draftsEnabled({ getItem: () => null }), true)
  assert.equal(d.draftsEnabled({ getItem: () => { throw new Error('denied') } }), true)
  checks += 6
})

await asyncSection('B2 save retries', async () => {
  const q = m.saveQueue
  const fail = (status, error = 'x') => ({ ok: false, error, status })
  assert.equal(q.retryable({ ok: true, data: 1 }), false)
  for (const s of [undefined, 408, 429, 500, 502, 503, 504]) assert.equal(q.retryable(fail(s)), true, String(s))
  for (const s of [400, 401, 403, 404, 409, 422, 501]) assert.equal(q.retryable(fail(s)), false, String(s))
  checks += 3
  const delays = []
  let calls = 0
  const flaky = async () => (++calls < 3 ? fail(undefined, 'offline') : { ok: true, data: 'saved' })
  const r = await q.withRetry(flaky, { sleep: async (ms) => delays.push(ms), random: () => 1, onRetry: () => {} })
  assert.deepEqual(r, { ok: true, data: 'saved' })
  assert.deepEqual(delays, [600, 1200]) // exponential backoff
  assert.equal(calls, 3)
  calls = 0
  const never = async () => (calls++, fail(502))
  const gave = await q.withRetry(never, { attempts: 4, sleep: async () => {}, random: () => 0.5 })
  assert.equal(gave.ok, false)
  assert.equal(calls, 4)
  calls = 0
  const conflict = async () => (calls++, fail(409, 'changed elsewhere'))
  await q.withRetry(conflict, { sleep: async () => { throw new Error('must not wait') } })
  assert.equal(calls, 1) // a 409 is final, never retried
  const seen = []
  calls = 0
  await q.withRetry(never, { attempts: 3, sleep: async () => {}, random: () => 0, onRetry: (n, ms) => seen.push([n, ms]) })
  assert.deepEqual(seen, [[2, 300], [3, 600]])
  checks += 8
  assert.equal(q.sameContent({ a: 1, b: { c: [1, 2], d: 3 } }, { b: { d: 3, c: [1, 2] }, a: 1 }), true)
  assert.equal(q.sameContent({ a: 1 }, { a: 2 }), false)
  assert.equal(q.sameContent([1, 2], [2, 1]), false)
  assert.deepEqual(q.normalizeTags(['  Mixed   Case ', 'mixed case', 'B|x', '', 'x'.repeat(41)]), ['mixed case', 'bx'])
  assert.equal(q.normalizeTags(Array.from({ length: 30 }, (_, i) => 't' + i)).length, 20)
  checks += 5
})

section('B2 revision diff', () => {
  const diff = m.diff
  ok(() => {
    const d = diff.diffDiagrams(fixture, structuredClone(fixture))
    assert.equal(d.empty, true)
    assert.deepEqual(d.summary, [])
  })
  ok(() => {
    const after = structuredClone(fixture)
    after.title = 'Order system v2'
    after.nodes[1].label = 'Validate the order'
    after.nodes[2].notes = 'retry at most 3 times'
    after.nodes[3].collapsed = true
    after.nodes.push({ id: 'ship', label: 'Ship order' })
    after.edges[3].label = 'valid order'
    after.edges.push({ id: 'f4', source: 'payment', target: 'ship', kind: 'flow', label: 'paid' })
    after.edges = after.edges.filter((e) => e.id !== 'b3')
    const d = diff.diffDiagrams(fixture, after)
    assert.equal(d.empty, false)
    assert.deepEqual(d.title, ['Order processing system', 'Order system v2'])
    assert.deepEqual(d.nodes.added.map((n) => n.id), ['ship'])
    assert.deepEqual(d.nodes.changed.map((c) => [c.id, c.fields]), [
      ['validate', ['label']], ['payment', ['notes']], ['confirm', ['collapsed']],
    ])
    assert.deepEqual(d.edges.added.map((e) => e.id), ['f4'])
    assert.deepEqual(d.edges.removed.map((e) => e.id), ['b3'])
    assert.deepEqual(d.edges.changed.map((c) => [c.id, c.fields]), [['f1', ['label']]])
    assert.ok(d.summary.includes('Renamed "Validate order" → "Validate the order"'))
    assert.ok(d.summary.includes('Added topic "Ship order"'))
    assert.ok(d.summary.some((l) => l.startsWith('Added flow link "Charge payment" → "Ship order"')))
  })
  ok(() => {
    // Moving topics is reported on its own and never as an edit; a reverse diff mirrors the forward one.
    const a = structuredClone(fixture)
    a.nodes[0].position = { x: 0, y: 0 }
    const b = structuredClone(a)
    b.nodes[0].position = { x: 50, y: 20 }
    const d = diff.diffDiagrams(a, b)
    assert.deepEqual(d.nodes.moved, ['root'])
    assert.deepEqual(d.nodes.changed, [])
    assert.deepEqual(d.summary, ['Moved 1 topic(s)'])
    const noPosition = diff.diffDiagrams(fixture, b) // layout appearing is not a "move"
    assert.deepEqual(noPosition.nodes.moved, [])
    const there = diff.diffDiagrams(fixture, b), back = diff.diffDiagrams(b, fixture)
    assert.equal(there.empty, back.empty)
    const longLabel = structuredClone(fixture)
    longLabel.nodes[0].label = 'L'.repeat(80)
    assert.ok(diff.diffDiagrams(fixture, longLabel).summary[0].length < 100)
  })
})


section('B2 display helpers', () => {
  const t = m.format.relativeTime
  const now = Date.parse('2026-10-02T12:00:00Z')
  ok(() => {
    assert.equal(t(now - 5_000, now), 'just now')
    assert.equal(t(now + 60_000, now), 'just now') // clock skew never shows the future
    assert.equal(t(now - 5 * 60_000, now), '5 min ago')
    assert.equal(t(now - 3 * 3600_000, now), '3 h ago')
    assert.equal(t(now - 2 * 86400_000, now), '2 d ago')
    assert.equal(t('2026-01-05T10:00:00Z', now), '2026-01-05')
    assert.equal(t(null, now), '')
    assert.equal(t('not a date', now), '')
  })
})

console.log(`dmind modules: ${checks} checks passed`)
