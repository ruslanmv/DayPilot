/**
 * Pure-module checks for the dmind batches (B1 onward). Run with: node tests/ui/dmind-modules.mjs
 * Each section is one batch; the shared contract corpus lives in tests/ui/dmind.mjs.
 */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { loadDiagramModules } from './_load.mjs'
import { PNG, PDF, archiveTools, bundleTools, sha256 as sha } from './_archives.mjs'

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


// ---------------------------------------------------------------- B5 bundle: zip, assets, bundle
import zlib from 'node:zlib'
import crypto from 'node:crypto'
const JPG = Uint8Array.from([0xff, 0xd8, 0xff, 0xe0, 0, 16, 74, 70, 73, 70])
const GIF = new TextEncoder().encode('GIF89a\x01\x00\x01\x00')
const WEBP = Uint8Array.from([...new TextEncoder().encode('RIFF'), 0, 0, 0, 0, ...new TextEncoder().encode('WEBPVP8 ')])

const { craft, good, hostile } = archiveTools(m)

await asyncSection('B5 zip reader and writer', async () => {
  const z = m.zip
  const bytes = (s) => new TextEncoder().encode(s)
  const refused = async (label, archive, pattern, limits) => {
    await assert.rejects(() => z.readZip(archive, limits), (e) => e instanceof z.ZipError && pattern.test(e.message), label)
    checks++
  }
  // the crafter itself builds a valid archive, so every failure below is due to its one falsified field
  const read = await z.readZip(good)
  assert.deepEqual([...read.keys()], ['a.txt', 'dir/b.txt'])
  assert.equal(new TextDecoder().decode(read.get('dir/b.txt')), 'world')
  checks += 2
  // writer: round trip, determinism, content including empty and large entries
  const big = crypto.randomBytes(3_000_000)
  const entries = [{ name: 'manifest.json', data: bytes('{}\n') }, { name: 'empty', data: new Uint8Array() }, { name: 'assets/big.bin', data: new Uint8Array(big) }]
  const packed = z.writeZip(entries)
  const back = await z.readZip(packed)
  assert.deepEqual([...back.keys()], entries.map((e) => e.name))
  assert.equal(back.get('empty').length, 0)
  assert.equal(Buffer.compare(Buffer.from(back.get('assets/big.bin')), big), 0)
  assert.equal(Buffer.compare(Buffer.from(z.writeZip(entries)), Buffer.from(packed)), 0, 'the same input gives the same bytes')
  const golden = z.writeZip([{ name: 'a.txt', data: bytes('hello\n') }, { name: 'b/c.txt', data: bytes('world\n') }])
  // 2 locals (41 + 43 bytes) + 2 directory records (51 + 53) + the 22-byte end record
  assert.equal(golden.length, 41 + 43 + 51 + 53 + 22)
  assert.equal(sha(golden), 'f2ef9f3fb79969a29ee189ff5da4fcefff153f7bb88f91c8f0e7a8f18cf9b1b8', 'the writer output is pinned; Matrix Designer pins the same digest')
  assert.equal(z.crc32(bytes('123456789')), 0xcbf43926, 'the standard CRC-32 check value')
  checks += 8
  // writer refuses what a bundle never contains
  for (const bad of ['../x', '/x', 'a/../b', 'a\\b', 'C:x', '', 'é.txt', 'dir/', 'a\u0000b', 'x'.repeat(201)])
    assert.throws(() => z.writeZip([{ name: bad, data: new Uint8Array() }]), z.ZipError, JSON.stringify(bad))
  assert.throws(() => z.writeZip([{ name: 'A', data: new Uint8Array() }, { name: 'a', data: new Uint8Array() }]), /Duplicate/)
  checks += 11
  for (const [label, archive, pattern, limits] of hostile) await refused(label, archive, pattern, limits)
  await refused('tight custom limits', craft([{ name: 'a', data: 'hello world' }]), /too large/, { ...z.BUNDLE_LIMITS, maxEntryBytes: 5 })
  // a read that survives: stored and deflated entries, directory entries, and a Python-style comment-free archive
  const mixed = await z.readZip(craft([{ name: 'x/', data: '' }, { name: 'x/one', data: 'a'.repeat(1000), method: 8 }, { name: 'two', data: '' }]))
  assert.equal(mixed.get('x/one').length, 1000)
  assert.equal(mixed.get('two').length, 0)
  checks += 2
  globalThis.__goldenZip = golden
})


await asyncSection('B5 attachments and bundles', async () => {
  const { assets: A, bundle: Bn, dmind, dmindFile: F, zip: z } = m
  const bytes = (s) => new TextEncoder().encode(s)
  const sniff = A.sniffType
  // type comes from the bytes, never the name
  assert.equal(sniff(PNG), 'image/png'); assert.equal(sniff(JPG), 'image/jpeg'); assert.equal(sniff(GIF), 'image/gif')
  assert.equal(sniff(bytes('GIF87a....')), 'image/gif'); assert.equal(sniff(WEBP), 'image/webp'); assert.equal(sniff(PDF), 'application/pdf')
  assert.equal(sniff(PNG, 'photo.pdf'), 'image/png', 'the name never overrides the bytes')
  assert.equal(sniff(bytes('# Notes\n- a'), 'notes.md'), 'text/markdown')
  assert.equal(sniff(bytes('plain'), 'notes.txt'), 'text/plain')
  assert.equal(sniff(bytes('plain')), null, 'text needs a text file name')
  assert.equal(sniff(bytes('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'), 'x.txt'), null, 'SVG is refused even when renamed')
  assert.equal(sniff(bytes('<?xml version="1.0"?><svg/>'), 'x.md'), null)
  assert.equal(sniff(bytes('<!DOCTYPE svg PUBLIC ""><svg/>'), 'x.txt'), null)
  assert.equal(sniff(Uint8Array.from([0x61, 0, 0x62]), 'x.txt'), null, 'a NUL byte is not text')
  assert.equal(sniff(Uint8Array.from([0xff, 0xfe, 0x41]), 'x.txt'), null, 'invalid UTF-8 is not text')
  for (const junk of [new Uint8Array(), bytes('MZ\x90\x00'), bytes('\x7fELF'), bytes('PK\x03\x04'), bytes('<html><script>'), bytes('RIFF....WAVE')])
    assert.equal(sniff(junk, 'f.bin'), null, 'unknown bytes are never an allowed type')
  assert.equal(sniff(bytes('MZ\x90\x00'), 'f.txt'), null, 'a text file name does not make binary data text')
  checks += 2
  assert.equal(await A.sha256Hex(bytes('abc')), 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
  assert.equal(A.cleanFileName('../../a/b\\c.png'), 'c.png'); assert.equal(A.cleanFileName('a\u0001b .txt'), 'ab.txt')
  assert.equal(A.cleanFileName('  '), 'file'); assert.equal(A.cleanFileName('x'.repeat(300)).length, 120)
  assert.equal(A.formatBytes(12), '12 B'); assert.equal(A.formatBytes(1500), '1.5 kB'); assert.equal(A.formatBytes(250_000), '250 kB'); assert.equal(A.formatBytes(2_500_000), '2.5 MB')
  assert.ok(A.isAssetRef('sha256:' + 'a'.repeat(64)) && !A.isAssetRef('sha256:xyz') && !A.isAssetRef('a'.repeat(64)))
  checks += 5

  // attaching, refusing, and removing
  let d = dmind.fromOutline('Spec', 'Design\nBuild', 'mindmap')
  const a1 = await A.attachFile(d, 'n1', { name: 'sketch.png', bytes: PNG })
  assert.ok(!a1.error)
  assert.deepEqual(a1.diagram.nodes[1].metadata.attachments, [{ asset: 'sha256:' + sha(PNG), name: 'sketch.png', type: 'image/png', bytes: PNG.length }])
  assert.equal(d.nodes[1].metadata, undefined, 'the input is never mutated')
  assert.equal(a1.data.type, 'image/png')
  dmind.validateDiagram(a1.diagram)
  assert.match((await A.attachFile(a1.diagram, 'n1', { name: 'again.png', bytes: PNG })).error, /already attached/)
  assert.match((await A.attachFile(d, 'ghost', { name: 'x.png', bytes: PNG })).error, /no longer exists/)
  assert.match((await A.attachFile(d, 'n1', { name: 'x.png', bytes: new Uint8Array() })).error, /empty/)
  assert.match((await A.attachFile(d, 'n1', { name: 'x.bin', bytes: bytes('MZ') })).error, /PNG, JPEG, GIF or WebP/)
  assert.match((await A.attachFile(d, 'n1', { name: 'x.svg', bytes: bytes('<svg/>') })).error, /SVG is not allowed/)
  assert.match((await A.attachFile(d, 'n1', { name: 'big.png', bytes: new Uint8Array([...PNG, ...new Uint8Array(A.MAX_ASSET_BYTES)]) })).error, /smaller than 5 MB/)
  let many = d
  for (let i = 0; i < A.MAX_ATTACHMENTS_PER_TOPIC; i++) many = (await A.attachFile(many, 'n1', { name: `f${i}.txt`, bytes: bytes('file ' + i) })).diagram
  assert.match((await A.attachFile(many, 'n1', { name: 'one-more.txt', bytes: bytes('overflow') })).error, /10 attachments/)
  let wide = dmind.fromOutline('Wide', 'a\nb\nc\nd\ne\nf', 'mindmap')
  for (let i = 0; i < A.MAX_ASSETS; i++) wide = (await A.attachFile(wide, 'n' + (1 + (i % 6)), { name: `w${i}.txt`, bytes: bytes('w ' + i) })).diagram
  assert.match((await A.attachFile(wide, 'root', { name: 'last.txt', bytes: bytes('over the cap') })).error, /50 different attachments/)
  assert.equal(A.allAttachments(wide).length, A.MAX_ASSETS)
  const sameFileTwice = await A.attachFile(a1.diagram, 'n2', { name: 'copy.png', bytes: PNG }) // one asset, two topics
  assert.equal(A.allAttachments(sameFileTwice.diagram).length, 1)
  const removed = A.removeAttachment(a1.diagram, 'n1', a1.ref)
  assert.equal(removed.nodes[1].metadata, undefined, 'removing the last attachment removes the empty metadata')
  assert.deepEqual(A.attachmentsOf({ id: 'x', label: 'x', metadata: { attachments: [null, 5, { asset: 'bad' }, { asset: 'sha256:' + 'b'.repeat(64), name: 'ok.pdf', type: 'application/pdf', bytes: 3 }, { asset: 'sha256:' + 'b'.repeat(64), name: 'x', type: 'image/svg+xml', bytes: 3 }] } }).map((a) => a.name), ['ok.pdf'])
  assert.deepEqual(A.attachmentsOf({ id: 'x', label: 'x', metadata: { attachments: 'nope' } }), [])
  checks += 17

  // bundles: round trip, determinism, and everything a tampered bundle must trip over
  const store = new Map([[a1.ref, a1.data]])
  const withPdf = await A.attachFile(a1.diagram, 'n2', { name: 'brief.pdf', bytes: PDF })
  store.set(withPdf.ref, withPdf.data)
  const doc = withPdf.diagram
  const packed = await Bn.packBundle(doc, store)
  assert.equal(String.fromCharCode(packed[0], packed[1]), 'PK')
  const opened = await Bn.unpackBundle(packed)
  assert.deepEqual(opened.diagram, doc)
  assert.deepEqual([...opened.assets.keys()].sort(), [a1.ref, withPdf.ref].sort())
  assert.equal(Buffer.compare(Buffer.from(opened.assets.get(a1.ref).bytes), Buffer.from(PNG)), 0)
  assert.deepEqual(opened.warnings, [])
  assert.equal(Buffer.compare(Buffer.from(await Bn.packBundle(doc, new Map([...store].reverse()))), Buffer.from(packed)), 0, 'asset order never changes the bytes')
  const files = await z.readZip(packed)
  assert.deepEqual([...files.keys()], ['manifest.json', 'document.json', ...[a1.ref, withPdf.ref].map((r) => r.slice(7)).sort().map((h) => `assets/${h}.${h === sha(PNG) ? 'png' : 'pdf'}`)])
  const manifest = JSON.parse(new TextDecoder().decode(files.get('manifest.json')))
  assert.equal(manifest.format, 'dmind-bundle/v1')
  assert.deepEqual(Object.keys(manifest), ['assets', 'document', 'format'], 'keys are sorted for stable bytes')
  assert.equal(manifest.document.sha256, sha(files.get('document.json')))
  checks += 10
  // an unreferenced asset is left out; a missing one is reported, not invented
  const extra = new Map([...store, ['sha256:' + 'c'.repeat(64), { bytes: bytes('x'), name: 'x.txt', type: 'text/plain' }]])
  assert.equal((await Bn.unpackBundle(await Bn.packBundle(doc, extra))).assets.size, 2)
  const partial = await Bn.unpackBundle(await Bn.packBundle(doc, new Map([[a1.ref, a1.data]])))
  assert.match(partial.warnings[0], /1 attachment\(s\) are referenced but not included/)
  assert.equal(Bn.missingAssets(doc, new Map([[a1.ref, a1.data]])).length, 1)
  await assert.rejects(() => Bn.packBundle(doc, new Map([[a1.ref, { ...a1.data, bytes: bytes('tampered') }]])), /does not match its recorded hash/)
  checks += 4

  const T = await bundleTools(m)
  for (const [label, archive, pattern] of T.cases) {
    await assert.rejects(() => Bn.unpackBundle(archive), (e) => pattern.test(e.message), label)
    checks++
  }
  await assert.rejects(() => Bn.unpackBundle(bytes('definitely not a zip')), /not a valid ZIP/)
  checks += 3

  // through the file layer: .dmind opens in either form, and export picks the right one
  const asJson = await F.exportDmind(dmind.fromOutline('Plain', 'x', 'mindmap'), new Map())
  assert.equal(asJson.form, 'json'); assert.equal(asJson.mime, F.DMIND_MIME); assert.ok(asJson.name.endsWith('.dmind'))
  const asBundle = await F.exportDmind(doc, store)
  assert.equal(asBundle.form, 'bundle'); assert.deepEqual(asBundle.missing, [])
  const partialExport = await F.exportDmind(doc, new Map([[a1.ref, a1.data]]))
  assert.equal(partialExport.form, 'bundle'); assert.equal(partialExport.missing.length, 1)
  const noBytes = await F.exportDmind(doc, new Map())
  assert.equal(noBytes.form, 'json'); assert.equal(noBytes.missing.length, 2, 'attachments without bytes are reported')
  const viaAny = await F.importAny('spec.dmind', asBundle.bytes)
  assert.equal(viaAny.via, 'dmind-bundle'); assert.equal(viaAny.assets.size, 2); assert.deepEqual(viaAny.diagram, doc)
  const jsonAny = await F.importAny('x.dmind', asJson.bytes)
  assert.equal(jsonAny.via, 'dmind')
  await assert.rejects(() => F.importAny('spec.zip', asBundle.bytes), /Only .dmind files/)
  await assert.rejects(() => F.importAny('evil.dmind', craft([{ name: '../x', data: 'x' }])), /unsafe entry name/)
  const oversized = new Uint8Array(62_000_001)
  oversized.set([0x50, 0x4b, 3, 4])
  await assert.rejects(() => F.importAny('big.dmind', oversized), /smaller than 62 MB/)
  assert.throws(() => F.importFile('spec.dmind', asBundle.bytes), /ZIP/)
  checks += 15
})


await asyncSection('B5 shared archive corpus', async () => {
  const corpus = JSON.parse(fs.readFileSync(new URL('../../packages/dmind-contract/archive-cases.json', import.meta.url)))
  const unhex = (h) => new Uint8Array(Buffer.from(h, 'hex'))
  const { zip: z, bundle: Bn, assets: A } = m
  assert.equal(corpus.contract, 'dmind-bundle/v1')
  assert.deepEqual(corpus.limits, z.BUNDLE_LIMITS)
  for (const c of corpus.zip.valid) {
    const read = await z.readZip(unhex(c.hex))
    assert.deepEqual(Object.fromEntries([...read].map(([n, d]) => [n, sha(d)])), c.entries, c.name)
    checks++
  }
  for (const c of corpus.zip.refused) {
    await assert.rejects(() => z.readZip(unhex(c.hex), c.limits ?? z.BUNDLE_LIMITS), z.ZipError, c.name)
    checks++
  }
  for (const c of corpus.bundle.valid) {
    const u = await Bn.unpackBundle(unhex(c.hex))
    assert.equal(sha(new TextEncoder().encode(JSON.stringify(u.diagram, null, 2) + '\n')), c.document_sha256)
    assert.deepEqual(Object.fromEntries([...u.assets].map(([ref, d]) => [ref, d.type])), c.assets)
    checks += 2
  }
  for (const c of corpus.bundle.refused) {
    await assert.rejects(() => Bn.unpackBundle(unhex(c.hex)), Error, c.name)
    checks++
  }
  for (const c of corpus.writer) {
    const out = z.writeZip(c.entries.map((e) => ({ name: e.name, data: new TextEncoder().encode(e.text) })))
    assert.equal(sha(out), c.sha256, c.name)
    checks++
  }
  assert.ok(corpus.zip.refused.length >= 35 && corpus.bundle.refused.length >= 20)
})

await asyncSection('B6 analysis and patches', async () => {
  const { analysis: an, patch: pt, dmind: dm } = m
  const mk = (kind, labels, edges) => ({
    schema_version: 'dmind/v1', id: 'd1', title: 'T', kind,
    nodes: labels.map((l, i) => ({ id: 'n' + i, label: l })),
    edges: edges.map(([s, t, k], i) => ({ id: 'e' + i, source: 'n' + s, target: 'n' + t, kind: k || 'flow' })),
  })
  const codes = (r) => r.findings.map((f) => f.code).sort()
  // order and acyclic
  let r = an.analyse(mk('flowchart', ['a', 'b', 'c'], [[0, 1], [1, 2]]))
  assert.deepEqual(r.order, ['n0', 'n1', 'n2']); assert.deepEqual(codes(r), []); checks += 2
  // loop with exit: info only; loop without exit: warning; order null
  r = an.analyse(mk('flowchart', ['a', 'b', 'c'], [[0, 1], [1, 0], [1, 2]]))
  assert.equal(r.order, null); assert.deepEqual(codes(r), ['cycle'])
  r = an.analyse(mk('flowchart', ['a', 'b', 'c'], [[0, 1], [1, 2], [2, 1]]))
  assert.deepEqual(codes(r), ['cycle', 'no_exit']); checks += 3
  // self loop is a loop; unreachable island that is itself acyclic; orphans; all results solver-labelled
  r = an.analyse(mk('flowchart', ['a', 'b', 'c', 'd', 'e'], [[0, 0], [2, 3], [3, 3]]))
  assert.ok(r.findings.every((f) => f.origin === 'solver') && r.origin === 'solver')
  assert.ok(codes(r).includes('no_exit') && codes(r).includes('orphan')); checks += 2
  r = an.analyse(mk('flowchart', ['a', 'b', 'c', 'd'], [[0, 1], [2, 3], [3, 2], [3, 1]]))
  assert.ok(!codes(r).includes('unreachable')) // reachable through a loop start is not flagged
  // branch links are hierarchy, not ordering
  r = an.analyse(mk('mindmap', ['r', 'a', 'b'], [[0, 1, 'branch'], [1, 2, 'branch'], [2, 0, 'branch']]))
  assert.equal(r.order?.length, 3); assert.deepEqual(codes(r), []); checks += 2
  // deep chain: iterative, no stack overflow
  const chain = mk('flowchart', Array.from({ length: 1000 }, (_, i) => 'n' + i), Array.from({ length: 999 }, (_, i) => [i, i + 1]))
  assert.equal(an.analyse(chain).order.length, 1000)
  const ring = mk('flowchart', Array.from({ length: 1000 }, (_, i) => 'n' + i), Array.from({ length: 1000 }, (_, i) => [i, (i + 1) % 1000]))
  assert.equal(an.analyse(ring).components.filter((c) => c.length === 1000).length, 1); checks += 2

  // patches
  const base = dm.fromOutline('Root', 'A\n  B\nC', 'mindmap')
  const h0 = await pt.hashDiagram(base)
  assert.match(h0, /^[0-9a-f]{64}$/)
  assert.equal(h0, await pt.hashDiagram(structuredClone(base)))
  assert.notEqual(h0, await pt.hashDiagram({ ...base, title: 'X' })); checks += 3
  const ops = [
    { op: 'update_node', id: 'n1', set: { label: 'Alpha' } },
    { op: 'add_node', node: { id: 'z1', label: 'New' } },
    { op: 'add_edge', edge: { id: 'ez', source: 'root', target: 'z1', kind: 'branch' } },
    { op: 'remove_node', id: 'n3' },
  ]
  const p = await pt.makePatch(base, 'model', 'tidy', ops)
  const res = await pt.applyPatch(base, p)
  assert.ok(res.ok); assert.ok(res.diff.summary.length >= 3)
  assert.ok(res.diagram.nodes.some((n) => n.label === 'Alpha') && !res.diagram.nodes.some((n) => n.id === 'n3'))
  assert.ok(!res.diagram.edges.some((e) => e.source === 'n3' || e.target === 'n3'))
  assert.equal(base.nodes.find((n) => n.id === 'n1').label, 'A') // input untouched
  checks += 5
  // stale: the document moved on
  const moved = { ...base, title: 'Changed' }
  let bad = await pt.applyPatch(moved, p); assert.equal(bad.reason, 'stale')
  bad = await pt.applyPatch({ ...base, id: 'other' }, p); assert.equal(bad.reason, 'stale'); checks += 2
  // all-or-nothing and contract validation
  const refuse = async (opsList, why) => {
    const r2 = await pt.applyPatch(base, await pt.makePatch(base, 'model', 's', opsList))
    assert.equal(r2.ok, false, why); assert.equal(r2.reason, 'invalid', why); checks++
  }
  await refuse([{ op: 'update_node', id: 'n1', set: { label: 'ok' } }, { op: 'remove_node', id: 'ghost' }], 'unknown topic')
  await refuse([{ op: 'add_node', node: { id: 'n1', label: 'dup' } }], 'duplicate id')
  await refuse([{ op: 'add_edge', edge: { id: 'q', source: 'n1', target: 'ghost', kind: 'flow' } }], 'dangling link')
  await refuse([{ op: 'add_edge', edge: { id: 'q', source: 'n2', target: 'root', kind: 'branch' } }], 'branch cycle')
  await refuse([{ op: 'update_node', id: 'n1', set: { label: '' } }], 'empty label')
  await refuse([{ op: 'add_node', node: { id: 'bad id!', label: 'x' } }], 'unsafe id')
  await refuse([{ op: 'set_title', title: ' ' }], 'blank title')
  await refuse(base.nodes.map((n) => ({ op: 'remove_node', id: n.id })), 'remove everything')
  // untrusted patch JSON: unknown ops and fields, pollution, size
  const must = (v) => assert.throws(() => pt.parsePatch(v)); const good = JSON.parse(JSON.stringify(p))
  must(null); must({ ...good, schema: 'x' }); must({ ...good, extra: 1 }); must({ ...good, origin: 'admin' })
  must({ ...good, ops: [] }); must({ ...good, ops: Array(201).fill(ops[0]) }); must({ ...good, base: { id: 'd', hash: 'zz' } })
  must({ ...good, ops: [{ op: 'drop_table' }] }); must({ ...good, ops: [{ op: 'update_node', id: 'n1', set: { position: { x: 1, y: 1 } } }] })
  must({ ...good, ops: [{ op: 'update_node', id: 'n1', set: JSON.parse('{"__proto__":{"x":1}}') }] })
  must({ ...good, ops: [{ op: 'update_node', id: 'n1', set: {} }] }); must({ ...good, ops: [{ op: 'remove_node', id: 'n1', cascade: true }] })
  checks += 12
  assert.equal(pt.parsePatch(good).summary, 'tidy'); checks++
  const viaJson = await pt.applyPatch(base, JSON.parse('{"schema":"dmind-patch/v1","base":{"id":"' + base.id + '","hash":"' + h0 + '"},"origin":"model","summary":"s","ops":[{"op":"set_title","title":"Renamed"}]}'))
  assert.ok(viaJson.ok && viaJson.diagram.title === 'Renamed'); checks++
  // shared corpus: the same file Matrix Designer's Python port runs
  const pc = JSON.parse(fs.readFileSync(new URL('../../packages/dmind-contract/patch-cases.json', import.meta.url)))
  assert.equal(await pt.hashDiagram(pc.base), pc.base_hash); checks++
  for (const c of pc.cases) {
    const r3 = await pt.applyPatch(structuredClone(pc.base), c.patch)
    if (c.expect === 'ok') assert.equal(await pt.hashDiagram(r3.diagram), c.result_digest, c.name)
    else assert.equal(r3.reason, c.expect, c.name)
    checks++
  }
})

console.log(`dmind modules: ${checks} checks passed`)
