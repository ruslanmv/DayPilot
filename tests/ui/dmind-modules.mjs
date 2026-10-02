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


// ---------------------------------------------------------------- B3 provenance
section('B3 provenance', () => {
  const { provenance: pv, dmind } = m
  const ref = (id, name) => ({ id, kind: 'file', name, bytes: 10, extractor: 'docx' })
  ok(() => {
    const a = { ref: ref('src1', 'spec.docx'), text: 'Billing\n  Charge card\n  Retry\n\nRefunds' }
    const b = { ref: { id: 'src2', kind: 'url', url: 'https://example.org/p', extractor: 'html' }, text: '- Retry\n- Audit log' }
    const typed = 'Charge card\nRetry\nAudit log\nSomething I wrote\nRefunds'
    const base = dmind.fromOutline('Payments', typed, 'mindmap')
    const d = pv.attachProvenance(base, [a, b])
    const byLabel = (l) => d.nodes.find((n) => n.label === l)
    assert.deepEqual(byLabel('Charge card').metadata.provenance, [{ source: 'src1', line: 2 }])
    assert.deepEqual(byLabel('Retry').metadata.provenance, [{ source: 'src1', line: 3 }, { source: 'src2', line: 1 }])
    assert.deepEqual(byLabel('Audit log').metadata.provenance, [{ source: 'src2', line: 2 }])
    assert.deepEqual(byLabel('Refunds').metadata.provenance, [{ source: 'src1', line: 5 }]) // blank lines still count
    assert.equal(byLabel('Something I wrote').metadata, undefined) // the person's own topics cite nothing
    assert.equal(d.nodes[0].metadata, undefined) // and neither does the typed root
    assert.deepEqual(d.metadata.sources.map((s) => s.id), ['src1', 'src2'])
    assert.equal(base.nodes[1].metadata, undefined, 'the input diagram is never mutated')
    assert.equal(base.metadata.sources, undefined)
    dmind.validateDiagram(d)
  })
  ok(() => {
    // Matching is by content: markers, spacing and order do not matter; unused sources are not attached.
    const src = { ref: ref('src1', 'a.md'), text: '## Heading  with   gaps\n1. Numbered item' }
    const unused = { ref: ref('src2', 'unused.md'), text: 'Nothing matches here' }
    const d = pv.attachProvenance(dmind.fromOutline('T', 'Numbered item\nHeading with gaps', 'flowchart'), [src, unused])
    assert.equal(d.nodes.filter((n) => n.metadata?.provenance).length, 2)
    assert.deepEqual(d.metadata.sources.map((s) => s.id), ['src1'])
    const none = pv.attachProvenance(dmind.fromOutline('T', 'x', 'mindmap'), [unused])
    assert.equal(none.metadata.sources, undefined)
    const same = dmind.fromOutline('T', 'x', 'mindmap')
    assert.equal(pv.attachProvenance(same, []), same)
  })
  ok(() => {
    const dup = { ref: ref('src1', 'dup.txt'), text: Array.from({ length: 6 }, () => 'Same line').join('\n') }
    const d = pv.attachProvenance(dmind.fromOutline('T', 'Same line', 'mindmap'), [dup])
    assert.equal(d.nodes[1].metadata.provenance.length, pv.MAX_CITATIONS)
    assert.deepEqual(d.nodes[1].metadata.provenance.map((c) => c.line), [1, 2, 3])
  })
  ok(() => {
    const d = pv.attachProvenance(dmind.fromOutline('T', 'Alpha', 'mindmap'), [{ ref: ref('src1', 'a.docx'), text: 'Alpha' }])
    const id = d.nodes[1].id
    assert.deepEqual(pv.citationsFor(d, id), [{ text: 'a.docx (docx, 10 bytes), line 1' }])
    assert.deepEqual(pv.citationsFor(d, 'root'), [])
    assert.deepEqual(pv.citationsFor(d, 'ghost'), [])
    assert.equal(pv.sourceId(0), 'src1')
    assert.equal(pv.describeSource({ id: 'x', kind: 'url', url: 'https://e.org/', pages: 3 }), 'https://e.org/ (3 pages)')
    assert.equal(pv.describeSource({ id: 'x', kind: 'file' }), 'document')
    // Provenance rides along through save, open and export like any metadata.
    const text = m.dmindFile.serializeDmind(d)
    assert.deepEqual(m.dmindFile.importFile('x.dmind', new TextEncoder().encode(text)).diagram, d)
  })
})


// ---------------------------------------------------------------- B4 layouts
section('B4 layouts', () => {
  const { layouts: L, dmind } = m
  const NAMES = L.LAYOUTS.map((l) => l.id)
  const rng = (seed) => () => {
    seed |= 0
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
  /** A random tree of n topics: each topic hangs under an earlier one (biased towards recent ones). */
  const tree = (n, seed, kind = 'mindmap', extraLinks = 0) => {
    const r = rng(seed)
    const nodes = [{ id: 'n0', label: 'Root' }]
    const edges = []
    for (let i = 1; i < n; i++) {
      const parent = Math.max(0, i - 1 - Math.floor(r() * r() * Math.min(i, 8)))
      nodes.push({ id: 'n' + i, label: 'Topic ' + i })
      edges.push({ id: 'b' + i, source: 'n' + parent, target: 'n' + i, kind: kind === 'flowchart' ? 'flow' : 'branch' })
    }
    for (let k = 0; k < extraLinks; k++)
      edges.push({ id: 'x' + k, source: 'n' + Math.floor(r() * n), target: 'n' + Math.floor(r() * n), kind: r() < 0.5 ? 'flow' : 'dependency' })
    return { schema_version: 'dmind/v1', id: 't', title: 'T', kind, nodes, edges }
  }
  const star = (n) => ({
    schema_version: 'dmind/v1', id: 's', title: 'S', kind: 'mindmap',
    nodes: Array.from({ length: n }, (_, i) => ({ id: 'n' + i, label: 'Topic ' + i })),
    edges: Array.from({ length: n - 1 }, (_, i) => ({ id: 'b' + i, source: 'n0', target: 'n' + (i + 1), kind: 'branch' })),
  })
  const kary = (k, levels) => {
    const nodes = [{ id: 'n0', label: 'Root' }], edges = []
    let frontier = ['n0']
    for (let l = 0; l < levels; l++) {
      const next = []
      for (const p of frontier) for (let c = 0; c < k; c++) {
        const id = 'n' + nodes.length
        nodes.push({ id, label: id }); edges.push({ id: 'b' + edges.length, source: p, target: id, kind: 'branch' }); next.push(id)
      }
      frontier = next
    }
    return { schema_version: 'dmind/v1', id: 'k', title: 'K', kind: 'mindmap', nodes, edges }
  }
  const overlaps = (pos) => {
    const boxes = [...pos].map(([id, p]) => ({ id, ...p }))
    const hits = []
    for (let i = 0; i < boxes.length; i++)
      for (let j = i + 1; j < boxes.length; j++)
        if (Math.abs(boxes[i].x - boxes[j].x) < L.NODE_W && Math.abs(boxes[i].y - boxes[j].y) < L.NODE_H) hits.push([boxes[i].id, boxes[j].id])
    return hits
  }
  ok(() => {
    for (const name of NAMES)
      for (const [n, seed] of [[1, 1], [2, 2], [7, 3], [30, 4], [90, 5], [150, 6]]) {
        const d = tree(n, seed, 'mindmap', n > 3 ? 4 : 0)
        const pos = L.computeLayout(d, name)
        assert.equal(pos.size, n, `${name} positions every topic`)
        for (const p of pos.values()) {
          assert.ok(Number.isInteger(p.x) && Number.isInteger(p.y) && Math.abs(p.x) <= 100000 && Math.abs(p.y) <= 100000, `${name} stays in bounds`)
        }
        assert.deepEqual(overlaps(pos), [], `${name} with ${n} topics (seed ${seed}) must not overlap`)
        assert.deepEqual([...L.computeLayout(d, name)], [...pos], `${name} is deterministic`)
        dmind.validateDiagram(L.applyLayout(d, name))
      }
  })
  ok(() => {
    // Wide trees are where spacing matters: a 60-way star and balanced 3-ary and 5-ary trees.
    for (const name of NAMES)
      for (const [label, d] of [['star', star(61)], ['3-ary', kary(3, 4)], ['5-ary', kary(5, 3)]]) {
        const pos = L.computeLayout(d, name)
        assert.deepEqual(overlaps(pos), [], `${name} on a ${label} tree`)
        for (const p of pos.values()) assert.ok(Math.abs(p.x) <= 100000 && Math.abs(p.y) <= 100000)
      }
  })
  ok(() => {
    // Disconnected pieces, isolated topics, self links and pure cycles all lay out.
    const d = {
      schema_version: 'dmind/v1', id: 'x', title: 'X', kind: 'system',
      nodes: ['a', 'b', 'c', 'd', 'e', 'f'].map((id) => ({ id, label: id })),
      edges: [
        { id: '1', source: 'a', target: 'b', kind: 'flow' }, { id: '2', source: 'b', target: 'a', kind: 'flow' },
        { id: '3', source: 'c', target: 'c', kind: 'relationship' }, { id: '4', source: 'd', target: 'e', kind: 'dependency' },
      ],
    }
    for (const name of NAMES) {
      const pos = L.computeLayout(d, name)
      assert.equal(pos.size, 6)
      assert.deepEqual(overlaps(pos), [], name)
    }
  })
  ok(() => {
    // Very deep chains stay inside the position bound (the old column layout did not past ~385 levels).
    for (const depth of [100, 450, 1000]) {
      const nodes = Array.from({ length: depth }, (_, i) => ({ id: 'n' + i, label: 'L' + i }))
      const edges = nodes.slice(1).map((n, i) => ({ id: 'e' + i, source: 'n' + i, target: n.id, kind: 'branch' }))
      const chain = { schema_version: 'dmind/v1', id: 'c', title: 'C', kind: 'mindmap', nodes, edges }
      for (const name of NAMES) {
        const pos = L.computeLayout(chain, name)
        for (const p of pos.values()) assert.ok(Math.abs(p.x) <= 100000 && Math.abs(p.y) <= 100000 && Number.isFinite(p.x + p.y), `${name} depth ${depth}`)
      }
      dmind.validateDiagram(dmind.layout(chain, true))
    }
    const tabs = dmind.fromOutline('Deep', Array.from({ length: 440 }, (_, i) => '\t'.repeat(i + 1) + 'L' + i).join('\n'), 'mindmap')
    dmind.validateDiagram(dmind.layout(tabs)) // a reachable input that used to fail validation after layout
  })
  ok(() => {
    const t = tree(40, 9)
    const tr = L.computeLayout(t, 'tree'), h = L.hierarchy(t)
    for (const [child, parent] of h.parent) {
      assert.ok(tr.get(parent).x < tr.get(child).x, 'children are to the right of their parent')
      const org = L.computeLayout(t, 'orgchart')
      assert.ok(org.get(parent).y < org.get(child).y, 'org chart children are below their parent')
    }
    const org = L.computeLayout(t, 'orgchart')
    for (const [id, kids] of h.children)
      if (kids.length) {
        const xs = kids.map((k) => org.get(k).x)
        assert.ok(Math.abs(org.get(id).x - (Math.min(...xs) + Math.max(...xs)) / 2) <= 1, 'a parent is centred over its children')
      }
    const rad = L.computeLayout(t, 'radial')
    const centre = rad.get('n0')
    const dist = (id) => Math.hypot(rad.get(id).x - centre.x, rad.get(id).y - centre.y)
    for (const [child, parent] of h.parent) assert.ok(dist(child) > dist(parent), 'radial rings grow outward')
  })
  ok(() => {
    const fish = { schema_version: 'dmind/v1', id: 'f', title: 'F', kind: 'mindmap',
      nodes: ['head', 'c1', 'c2', 'c3', 'r1', 'r2'].map((id) => ({ id, label: id })),
      edges: [['head', 'c1'], ['head', 'c2'], ['head', 'c3'], ['c1', 'r1'], ['c1', 'r2']].map(([s, t], i) => ({ id: 'e' + i, source: s, target: t, kind: 'branch' })) }
    const p = L.computeLayout(fish, 'fishbone')
    for (const c of ['c1', 'c2', 'c3']) assert.ok(p.get(c).x < p.get('head').x, 'causes sit left of the head')
    assert.ok(p.get('c1').y < p.get('head').y && p.get('c2').y > p.get('head').y && p.get('c3').y < p.get('head').y, 'categories alternate above and below the spine')
    assert.ok(p.get('r1').y < p.get('c1').y && p.get('r2').y < p.get('r1').y, 'ribs move away from the spine')
  })
  ok(() => {
    const flow = { schema_version: 'dmind/v1', id: 'l', title: 'L', kind: 'flowchart',
      nodes: ['a', 'b', 'c', 'd', 'e'].map((id) => ({ id, label: id })),
      edges: [['a', 'b'], ['b', 'c'], ['c', 'a'], ['a', 'd'], ['d', 'c'], ['c', 'e']].map(([s, t], i) => ({ id: 'e' + i, source: s, target: t, kind: 'flow' })) }
    const p = L.computeLayout(flow, 'layered')
    assert.ok(p.get('a').y < p.get('b').y && p.get('b').y < p.get('c').y && p.get('c').y < p.get('e').y, 'the loop does not reverse the flow')
    assert.equal(p.get('b').y, p.get('d').y, 'alternatives share a layer')
    assert.deepEqual(overlaps(p), [])
    assert.equal(L.defaultLayout(flow), 'layered')
    assert.equal(L.defaultLayout(tree(3, 1)), 'tree')
    assert.equal(L.defaultLayout({ ...tree(3, 1), metadata: { layout: 'radial' } }), 'radial')
    assert.equal(L.defaultLayout({ ...tree(3, 1), metadata: { layout: 'nonsense' } }), 'tree')
    assert.equal(L.isLayoutName('grid'), true)
    assert.equal(L.isLayoutName('__proto__'), false)
  })
  ok(() => {
    const d = tree(20, 3)
    const applied = L.applyLayout(d, 'radial')
    assert.equal(applied.metadata.layout, 'radial')
    assert.ok(applied.nodes.every((n) => n.position))
    assert.equal(d.nodes[0].position, undefined, 'applying a layout never mutates its input')
    // layout() keeps saved positions and fills only the missing ones with the chosen layout.
    const partial = structuredClone(d)
    partial.metadata = { layout: 'grid' }
    partial.nodes[3].position = { x: 5, y: 6 }
    const filled = dmind.layout(partial)
    assert.deepEqual(filled.nodes[3].position, { x: 5, y: 6 })
    assert.ok(filled.nodes.every((n) => n.position))
    assert.notDeepEqual(dmind.layout(partial, true).nodes[3].position, { x: 5, y: 6 })
  })
  ok(() => {
    for (const [a, b] of [[{ x: 0, y: 0 }, { x: 400, y: 20 }], [{ x: 400, y: 20 }, { x: 0, y: 0 }], [{ x: 0, y: 0 }, { x: 30, y: 300 }], [{ x: 30, y: 300 }, { x: 0, y: 0 }], [{ x: 10, y: 10 }, { x: 10, y: 10 }]]) {
      const g = L.edgePath(a, b)
      assert.match(g.d, /^M-?[\d.]+,-?[\d.]+ C/)
      assert.ok(!/NaN|Infinity/.test(g.d) && Number.isFinite(g.mid.x + g.mid.y))
    }
    assert.match(L.edgePath({ x: 0, y: 0 }, { x: 400, y: 0 }).d, /^M200,32 /) // leaves through the right side
    assert.match(L.edgePath({ x: 0, y: 0 }, { x: 0, y: 300 }).d, /^M100,64 /) // or the bottom
  })
  ok(() => {
    // 1000 topics lay out quickly in every engine.
    const big = tree(1000, 11, 'mindmap', 300)
    for (const name of NAMES) {
      const t0 = performance.now()
      const pos = L.computeLayout(big, name)
      const ms = performance.now() - t0
      assert.equal(pos.size, 1000)
      assert.ok(ms < 3000, `${name} took ${Math.round(ms)} ms`)
    }
  })
})


// ---------------------------------------------------------------- B4 editing, styles, outline
section('B4 editing', () => {
  const { edit: E, style: S, outline: O, dmind } = m
  const doc = () => dmind.fromOutline('Root', 'A\n  A1\n  A2\n    A2x\nB\n  B1\nC', 'mindmap')
  // ids: root, n1=A, n2=A1, n3=A2, n4=A2x, n5=B, n6=B1, n7=C
  const label = (d, id) => d.nodes.find((n) => n.id === id)?.label
  const parents = (d) => Object.fromEntries(d.edges.filter((e) => e.kind === 'branch').map((e) => [e.target, e.source]))
  ok(() => {
    const d = doc()
    assert.deepEqual([...E.descendants(d, 'n1')].sort(), ['n2', 'n3', 'n4'])
    assert.deepEqual([...E.descendants(d, 'n7')], [])
    assert.deepEqual(E.validParents(d, 'n1').sort(), ['n5', 'n6', 'n7', 'root'])
    assert.equal(E.parentOf(d, 'n4'), 'n3')
    assert.equal(E.parentOf(d, 'root'), null)
    const moved = E.reparent(d, 'n1', 'n5')
    assert.equal(parents(moved.diagram).n1, 'n5')
    assert.equal(parents(moved.diagram).n3, 'n1', 'the branch travels with its topic')
    dmind.validateDiagram(moved.diagram)
    assert.equal(d.edges.length, moved.diagram.edges.length)
    assert.equal(parents(d).n1, 'root', 'the input is never mutated')
    const orphan = E.reparent(d, 'n2', null)
    assert.equal(parents(orphan.diagram).n2, undefined)
    assert.equal(E.reparent(d, 'n2', 'n1').diagram, d, 'moving under the current parent changes nothing')
    for (const [id, to] of [['n1', 'n1'], ['n1', 'n4'], ['root', 'n6'], ['n3', 'n4']]) assert.match(E.reparent(d, id, to).error, /itself or one of its own branches/)
    assert.match(E.reparent(d, 'ghost', 'n1').error, /no longer exists/)
    assert.match(E.reparent(d, 'n1', 'ghost').error, /no longer exists/)
  })
  ok(() => {
    const d = doc()
    const out = E.removeBranches(d, ['n1', 'n3', 'n5']) // overlapping subtrees are fine
    assert.deepEqual(out.nodes.map((n) => n.id), ['root', 'n7'])
    assert.deepEqual(out.edges.map((e) => e.target), ['n7'])
    dmind.validateDiagram(out)
    assert.equal(E.removeBranches(d, d.nodes.map((n) => n.id)), null)
    assert.equal(E.removeBranches(d, ['root']), null)
    assert.equal(E.removeBranches(d, []), null)
    assert.equal(E.removeBranches(d, ['ghost']), null)
    const linked = structuredClone(d)
    linked.edges.push({ id: 'x', source: 'n7', target: 'n2', kind: 'flow' })
    assert.ok(!E.removeBranches(linked, ['n1']).edges.some((e) => e.id === 'x'), 'links to removed topics go too')
  })
  ok(() => {
    const d = doc()
    const moved = E.moveNodes(d, ['n1', 'n2'], 30, -10)
    const before = dmind.layout(d)
    for (const n of moved.nodes) {
      const was = before.nodes.find((x) => x.id === n.id).position
      const shift = ['n1', 'n2'].includes(n.id) ? { x: 30, y: -10 } : { x: 0, y: 0 }
      assert.deepEqual(n.position, { x: was.x + shift.x, y: was.y + shift.y }, n.id)
    }
    assert.equal(d.nodes[1].position, undefined)
    const far = E.moveNodes(d, ['n1'], 1e9, -1e9)
    assert.deepEqual(far.nodes[1].position, { x: 99000, y: -99000 })
    dmind.validateDiagram(far)
    assert.deepEqual(E.moveNodes(d, [], 5, 5).nodes.map((n) => n.position), before.nodes.map((n) => n.position))
  })
  ok(() => {
    const d = doc()
    const a = E.setNodeMeta(d, ['n1', 'n2'], 'accent', 'sky')
    assert.equal(a.nodes[1].metadata.accent, 'sky')
    assert.equal(a.nodes[3].metadata, undefined)
    const b = E.setNodeMeta(a, ['n1'], 'accent', undefined)
    assert.equal(b.nodes[1].metadata, undefined, 'removing the last key removes the empty object')
    const withTwo = E.setNodeMeta(E.setNodeMeta(d, ['n1'], 'a', 1), ['n1'], 'b', { deep: [1] })
    assert.deepEqual(E.setNodeMeta(withTwo, ['n1'], 'a', undefined).nodes[1].metadata, { b: { deep: [1] } })
    const value = { shared: [1] }
    const c = E.setNodeMeta(d, ['n1'], 'k', value)
    value.shared.push(2)
    assert.deepEqual(c.nodes[1].metadata.k, { shared: [1] }, 'values are copied')
    assert.equal(E.patchNodes(d, ['n7'], { collapsed: true }).nodes[7].collapsed, true)
    assert.equal(d.nodes[7].collapsed, undefined)
  })
  ok(() => {
    const d = doc()
    const one = E.toggleMarker(d, ['n1'], 'star')
    assert.deepEqual(one.nodes[1].metadata.markers, ['star'])
    assert.equal(E.toggleMarker(one, ['n1'], 'star').nodes[1].metadata, undefined, 'toggling off cleans up')
    const mixed = E.toggleMarker(one, ['n1', 'n2'], 'star') // not all have it: add to the rest
    assert.deepEqual([mixed.nodes[1], mixed.nodes[2]].map((n) => n.metadata.markers), [['star'], ['star']])
    assert.equal(E.toggleMarker(mixed, ['n1', 'n2'], 'star').nodes[2].metadata, undefined)
    let many = d
    for (const id of ['flag', 'star', 'check', 'warning', 'question', 'idea', 'clock']) many = E.toggleMarker(many, ['n1'], id)
    assert.deepEqual(many.nodes[1].metadata.markers, ['flag', 'star', 'check', 'warning', 'question'], `at most ${S.MAX_MARKERS}`)
    assert.equal(E.toggleMarker(d, ['n1'], 'nonsense'), d)
    assert.deepEqual(S.cleanMarkers(['star', 'star', 'x', 7, 'flag', 'check', 'warning', 'idea', 'clock']), ['star', 'flag', 'check', 'warning', 'idea'])
    assert.deepEqual(S.cleanMarkers('star'), [])
    assert.equal(S.markerNames(['flag', 'priority-1']), 'Flag, Priority 1')
    assert.equal(S.markerById('star').glyph, '★')
    assert.equal(S.accentById('nope'), undefined)
  })
  ok(() => {
    for (const bg of ['#172033', '#ffffff'])
      for (const a of S.ACCENTS) assert.ok(S.contrast(a.hex, bg) >= 3, `${a.id} on ${bg}: ${S.contrast(a.hex, bg).toFixed(2)}`)
    assert.ok(Math.abs(S.contrast('#000000', '#ffffff') - 21) < 1e-9)
    assert.ok(Math.abs(S.contrast('#777777', '#777777') - 1) < 1e-9)
    assert.equal(new Set(S.ACCENTS.map((a) => a.id)).size, S.ACCENTS.length)
    assert.equal(new Set(S.MARKERS.map((a) => a.glyph)).size, S.MARKERS.length)
  })
  ok(() => {
    for (const good of ['http://a.b', 'https://example.org/path?x=1&y=2#frag', '  https://example.org/x  ', 'HTTPS://EXAMPLE.ORG/', 'http://[::1]:8080/x', 'https://例え.jp/パス'])
      assert.ok(E.safeHref(good), good)
    assert.equal(E.safeHref(' https://example.org/a '), 'https://example.org/a')
    assert.equal(E.safeHref('https://例え.jp/'), 'https://xn--r8jz45g.jp/')
    for (const bad of ['javascript:alert(1)', 'JaVaScRiPt:alert(1)', 'java\nscript:alert(1)', 'data:text/html,<script>', 'vbscript:x', 'file:///etc/passwd', 'blob:http://x/1', '//evil.example', 'ftp://x.org', 'mailto:a@b.c',
      'http://user:pw@x.org/', 'http://user@x.org/', 'http://', 'https://exa mple.org', 'http://x.org/a\nb', 'http://x.org/a\tb', 'http://x.org/a\x00b', 'http://x.org/a\x7fb', 'http://x.org/a\u2028b', 'x'.repeat(10), 'http://x.org/' + 'a'.repeat(2100), '', '   ', null, undefined, 5, {}, ['http://x.org']])
      assert.equal(E.safeHref(bad), null, String(bad))
  })
  ok(() => {
    const grid = new Map([['a', { x: 0, y: 0 }], ['b', { x: 300, y: 10 }], ['c', { x: 600, y: 0 }], ['d', { x: 10, y: 200 }], ['e', { x: 320, y: 220 }], ['far', { x: 900, y: 900 }]])
    assert.equal(E.nearestInDirection(grid, 'a', 'right'), 'b')
    assert.equal(E.nearestInDirection(grid, 'b', 'right'), 'c')
    assert.equal(E.nearestInDirection(grid, 'a', 'down'), 'd')
    assert.equal(E.nearestInDirection(grid, 'd', 'up'), 'a')
    assert.equal(E.nearestInDirection(grid, 'e', 'left'), 'd')
    assert.equal(E.nearestInDirection(grid, 'a', 'left'), null)
    assert.equal(E.nearestInDirection(grid, 'a', 'up'), null)
    assert.equal(E.nearestInDirection(grid, 'ghost', 'up'), null)
    assert.equal(E.nearestInDirection(grid, 'a', 'right', new Set(['c', 'e'])), 'c', 'hidden topics are skipped')
    const tie = new Map([['o', { x: 0, y: 0 }], ['p', { x: 100, y: 0 }], ['q', { x: 100, y: 0 }]])
    assert.equal(E.nearestInDirection(tie, 'o', 'right'), 'p', 'ties resolve the same way every time')
  })
  ok(() => {
    const d = doc()
    assert.deepEqual(O.outlineRows(d).map((r) => [r.label, r.depth]), [['Root', 0], ['A', 1], ['A1', 2], ['A2', 2], ['A2x', 3], ['B', 1], ['B1', 2], ['C', 1]])
    const folded = E.patchNodes(d, ['n1'], { collapsed: true })
    assert.deepEqual(O.outlineRows(folded).map((r) => r.label), ['Root', 'A', 'B', 'B1', 'C'])
    assert.equal(O.outlineRows(folded)[1].hasChildren, true)
    assert.equal(O.outlineRows(folded, true).length, 8)
    assert.deepEqual(O.outlineRows({ ...d, edges: [] }).map((r) => r.depth), new Array(8).fill(0))
  })
  ok(() => {
    const d = doc()
    assert.equal(O.indentNode(d, 'n2'), null, 'the first child has nothing to indent under')
    assert.equal(O.indentNode(d, 'root'), null)
    assert.equal(O.indentNode(d, 'ghost'), null)
    const out = O.indentNode(d, 'n3') // A2 becomes the last child of A1
    assert.equal(parents(out)['n3'], 'n2')
    assert.deepEqual(O.outlineRows(out).map((r) => [r.label, r.depth]).slice(1, 6), [['A', 1], ['A1', 2], ['A2', 3], ['A2x', 4], ['B', 1]])
    const into = O.indentNode(d, 'n5') // B goes under A, after A's existing children
    assert.deepEqual(O.outlineRows(into).map((r) => r.label), ['Root', 'A', 'A1', 'A2', 'A2x', 'B', 'B1', 'C'])
    assert.equal(parents(into).n5, 'n1')
    assert.deepEqual(O.outlineRows(into).map((r) => r.depth), [0, 1, 2, 2, 3, 2, 3, 1])
    const out2 = O.outdentNode(d, 'n4') // A2x becomes a sibling of A2, right after it
    assert.equal(parents(out2).n4, 'n1')
    assert.deepEqual(O.outlineRows(out2).map((r) => [r.label, r.depth]).slice(1, 6), [['A', 1], ['A1', 2], ['A2', 2], ['A2x', 2], ['B', 1]])
    const top = O.outdentNode(d, 'n1') // a child of the root becomes a root, after it
    assert.equal(parents(top).n1, undefined)
    assert.equal(O.outdentNode(top, 'n1'), null)
    assert.equal(O.outdentNode(d, 'root'), null)
    for (const r of [out, into, out2, top]) dmind.validateDiagram(r)
  })
  ok(() => {
    const d = doc()
    assert.equal(O.moveSibling(d, 'n2', -1), null)
    assert.equal(O.moveSibling(d, 'n7', 1), null)
    const down = O.moveSibling(d, 'n1', 1) // A below B, taking its branch with it
    assert.deepEqual(O.outlineRows(down).map((r) => r.label), ['Root', 'B', 'B1', 'A', 'A1', 'A2', 'A2x', 'C'])
    const up = O.moveSibling(down, 'n1', -1)
    assert.deepEqual(O.outlineRows(up).map((r) => r.label), O.outlineRows(d).map((r) => r.label))
    assert.equal(d.nodes[1].id, 'n1', 'the input is never mutated')
    dmind.validateDiagram(down)
  })
  ok(() => {
    // The flags a row carries must match what the operations do, for any shape of outline.
    let seed = 99
    const rnd = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296)
    for (let round = 0; round < 25; round++) {
      let d = dmind.fromOutline('Root', Array.from({ length: 30 }, (_, i) => '  '.repeat(Math.floor(rnd() * 5)) + 'T' + i).join('\\n'), 'mindmap')
      for (let k = 0; k < 5; k++) {
        const pick = d.nodes[Math.floor(rnd() * d.nodes.length)].id
        d = O.moveSibling(d, pick, rnd() < 0.5 ? -1 : 1) ?? d
      }
      for (const r of O.outlineRows(d, true)) {
        assert.equal(r.canIndent, O.indentNode(d, r.id) !== null, 'indent ' + r.id)
        assert.equal(r.canOutdent, O.outdentNode(d, r.id) !== null, 'outdent ' + r.id)
        assert.equal(r.canMoveUp, O.moveSibling(d, r.id, -1) !== null, 'up ' + r.id)
        assert.equal(r.canMoveDown, O.moveSibling(d, r.id, 1) !== null, 'down ' + r.id)
      }
    }
    const rows = O.outlineRows(doc())
    assert.deepEqual(rows.map((r) => [r.label, r.canIndent, r.canOutdent, r.canMoveUp, r.canMoveDown]).slice(0, 3), [
      ['Root', false, false, false, false],
      ['A', false, true, false, true],
      ['A1', false, true, false, true],
    ])
  })
  ok(() => {
    const d = doc()
    const mid = O.addSiblingAfter(d, 'n2', 'Between') // A1 -> new -> A2, all children of A
    assert.deepEqual(O.outlineRows(mid.diagram).map((r) => r.label).slice(1, 7), ['A', 'A1', 'Between', 'A2', 'A2x', 'B'])
    assert.equal(parents(mid.diagram)[mid.id], 'n1')
    const top = O.addSiblingAfter(d, 'n1') // after A's whole branch, still a child of the root
    assert.deepEqual(O.outlineRows(top.diagram).map((r) => r.label), ['Root', 'A', 'A1', 'A2', 'A2x', 'New idea', 'B', 'B1', 'C'])
    assert.equal(parents(top.diagram)[top.id], 'root')
    const afterRoot = O.addSiblingAfter(d, 'root') // the root has no parent: a second top-level topic
    assert.equal(parents(afterRoot.diagram)[afterRoot.id], undefined)
    assert.equal(O.addSiblingAfter(d, 'ghost'), null)
    for (const r of [mid, top, afterRoot]) dmind.validateDiagram(r.diagram)
    assert.equal(d.nodes.length, 8, 'the input is never mutated')
  })
  ok(() => {
    // 300 random operations in a row: the result is always a valid forest with the same topics.
    let seed = 7
    const rnd = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296)
    let d = dmind.fromOutline('Root', Array.from({ length: 40 }, (_, i) => '  '.repeat(Math.floor(rnd() * 4)) + 'T' + i).join('\n'), 'mindmap')
    const ids = d.nodes.map((n) => n.id).sort()
    for (let i = 0; i < 300; i++) {
      const pick = d.nodes[Math.floor(rnd() * d.nodes.length)].id
      const op = Math.floor(rnd() * 5)
      const next = op === 0 ? O.indentNode(d, pick) : op === 1 ? O.outdentNode(d, pick) : op === 2 ? O.moveSibling(d, pick, rnd() < 0.5 ? -1 : 1)
        : op === 3 ? (() => { const t = d.nodes[Math.floor(rnd() * d.nodes.length)].id; const r = E.reparent(d, pick, rnd() < 0.1 ? null : t); return r.diagram ?? null })()
        : E.moveNodes(d, [pick], 10, 10)
      if (next) d = dmind.validateDiagram(next)
      assert.deepEqual(d.nodes.map((n) => n.id).sort(), ids)
      assert.equal(O.outlineRows(d, true).length, ids.length, 'every topic appears exactly once in the outline')
    }
  })
})


section('B4 typing history and styled exports', () => {
  const { dmind, edit: E } = m
  const base = dmind.fromOutline('Root', 'A', 'mindmap')
  const titled = (n) => ({ ...base, title: 'T' + n })
  ok(() => {
    let h = dmind.startHistory(base)
    h = dmind.commitHistory(h, titled(1), 'label:a', 1000)
    h = dmind.commitHistory(h, titled(2), 'label:a', 1400)
    h = dmind.commitHistory(h, titled(3), 'label:a', 1900)
    assert.equal(h.past.length, 1, 'keystrokes within a second share one undo step')
    assert.equal(h.present.title, 'T3')
    assert.equal(dmind.undoHistory(h).present.title, base.title, 'undo returns to before the first keystroke')
    h = dmind.commitHistory(h, titled(4), 'label:a', 3500) // a pause starts a new step
    assert.equal(h.past.length, 2)
    h = dmind.commitHistory(h, titled(5), 'notes:a', 3600) // another field is a separate step
    assert.equal(h.past.length, 3)
    h = dmind.commitHistory(h, titled(6), undefined, 3700) // untyped edits never merge
    h = dmind.commitHistory(h, titled(7), undefined, 3700)
    assert.equal(h.past.length, 5)
    let u = dmind.undoHistory(h)
    u = dmind.commitHistory(u, titled(8), 'notes:a', 3800)
    assert.equal(u.future.length, 0)
    assert.equal(dmind.undoHistory(u).present.title, 'T6', 'redo state is never merged into')
    assert.equal(dmind.commitHistory(null, titled(1), 'k', 5).coalesce.key, 'k')
    assert.equal(dmind.undoHistory(h).coalesce, undefined)
  })
  ok(() => {
    let d = dmind.fromOutline('Root', 'Plan', 'mindmap')
    d = E.setNodeMeta(d, ['n1'], 'accent', 'red')
    d = E.toggleMarker(d, ['n1'], 'star')
    d = E.toggleMarker(d, ['n1'], 'priority-2')
    d = E.setNodeMeta(d, ['n1'], 'link', 'https://example.org/spec?a=1&b=2')
    const svg = dmind.toSvg(d)
    assert.ok(svg.includes('#dc2626') && svg.includes('★ ②') && svg.includes('↗'))
    assert.ok(svg.includes('[Star, Priority 2]') && svg.includes('https://example.org/spec?a=1&amp;b=2'))
    const md = dmind.toMarkdown(d)
    assert.ok(md.includes('- Plan (n1) [Star, Priority 2] <https://example.org/spec?a=1&b=2>'), md)
    const hostile = E.setNodeMeta(E.setNodeMeta(d, ['n1'], 'link', 'javascript:alert(1)'), ['n1'], 'accent', '"><script>')
    const bad = E.setNodeMeta(hostile, ['n1'], 'markers', ['x', '<b>'])
    assert.ok(!dmind.toSvg(bad).includes('↗'), 'an unsafe link is never offered')
    assert.ok(!dmind.toMarkdown(bad).includes('<javascript'))
    assert.ok(!dmind.toSvg(bad).includes('<script>') && !dmind.toSvg(bad).includes('<b>'))
    assert.ok(dmind.toSvg(bad).includes('stroke="#6366f1"'), 'an unknown accent falls back to the default')
    assert.ok(!dmind.toShareHtml(bad).includes('<script>'))
  })
  ok(() => {
    // Connectors in exports follow the layout: no straight centre-to-centre lines remain.
    const d = dmind.fromOutline('Root', 'A\n  B\nC', 'mindmap')
    const svg = dmind.toSvg(d)
    assert.equal((svg.match(/<path d="M[^"]* C/g) || []).length, d.edges.length)
    assert.ok(!/<path d="M[\d.]+,[\d.]+ L[^"]*" stroke/.test(svg))
    const loop = { ...d, edges: [...d.edges, { id: 'self', source: 'n1', target: 'n1', kind: 'flow', label: 'retry' }] }
    assert.ok(dmind.toSvg(loop).includes('retry'))
  })
})

console.log(`dmind modules: ${checks} checks passed`)
