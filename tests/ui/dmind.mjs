/** Pure graph/export checks. Run with node tests/ui/dmind.mjs. */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { createRequire } from 'node:module'
const require = createRequire(
  new URL('../../packages/ui-bridge/package.json', import.meta.url),
)
const ts = require('typescript')
const source = fs.readFileSync(
  new URL('../../packages/ui-bridge/src/diagrams/dmind.ts', import.meta.url),
  'utf8',
)
const code = ts.transpileModule(source, {
  compilerOptions: {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.ESNext,
  },
}).outputText
const dmind = await import(
  'data:text/javascript;base64,' + Buffer.from(code).toString('base64')
)
const fixture = JSON.parse(
  fs.readFileSync(
    new URL(
      '../../packages/dmind-contract/order-system.dmind.json',
      import.meta.url,
    ),
  ),
)
assert.deepEqual(dmind.validateDiagram(fixture), fixture)
const d = dmind.fromOutline(
  'Order process',
  'Receive\n  Validate\nCharge',
  'mindmap',
)
assert.equal(d.edges[1].source, 'n1')
assert.equal(dmind.graphAnalysis(fixture).feedback, true)
const collapsed = structuredClone(d)
collapsed.nodes[0].collapsed = true
assert.equal(dmind.visibleNodes(collapsed).length, 1)
assert.equal(dmind.toMarkdown(collapsed).includes('Validate'), true)
const unsafe = structuredClone(fixture)
unsafe.nodes[0].label = '"><script>alert(1)</script>\nclick n0 "https://evil"'
unsafe.nodes[0].notes = '</pre><script>alert(1)</script>'
unsafe.edges[0].label = '\"] --> injected["run"]'
const html = dmind.toShareHtml(unsafe)
assert.equal(html.includes('<script>'), false)
assert.equal(dmind.toSvg(unsafe).includes('<script>'), false)
assert.equal(dmind.toMermaid(unsafe).includes('click n0 "https'), false)
assert.equal(dmind.toCodingBrief(unsafe).includes('UNTRUSTED'), true)
assert.throws(() =>
  dmind.validateDiagram({ ...fixture, schema_version: 'dmind/v2' }),
)
const bad = structuredClone(fixture)
bad.edges[0].target = 'ghost'
assert.throws(() => dmind.validateDiagram(bad))
const cycle = dmind.fromOutline('Root', 'A\n  B', 'mindmap')
cycle.edges.push({ id: 'cycle', source: 'n2', target: 'root', kind: 'branch' })
assert.throws(() => dmind.validateDiagram(cycle))
const large = dmind.fromOutline(
  'Large',
  Array.from({ length: 999 }, (_, i) => 'Node ' + i).join('\n'),
  'mindmap',
)
assert.equal(dmind.layout(large).nodes.length, 1000)
assert.throws(() =>
  dmind.fromOutline('Large', 'Node\n'.repeat(1000), 'mindmap'),
)
console.log(
  'dmind graph, limits, loops, collapse and safe portable exports: passed',
)
