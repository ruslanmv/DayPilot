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

console.log(`dmind modules: ${checks} checks passed`)
