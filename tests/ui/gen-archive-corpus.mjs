/**
 * Regenerate packages/dmind-contract/archive-cases.json (and copy it to Matrix Designer's
 * examples/dmind/). Run only when the bundle format or its refusal rules change:
 *
 *   node tests/ui/gen-archive-corpus.mjs
 *
 * The file holds real archives as hex: ones every reader must open, ones every reader must refuse,
 * and the deterministic writer's expected output. TypeScript and Python tests both consume it.
 */
import fs from 'node:fs'
import { loadDiagramModules } from './_load.mjs'
import { archiveTools, bundleTools, sha256 } from './_archives.mjs'

const m = await loadDiagramModules()
const { craft, good, hostile } = archiveTools(m)
const T = await bundleTools(m)
const hex = (b) => Buffer.from(b).toString('hex')
const entryHashes = async (bytes) => Object.fromEntries([...(await m.zip.readZip(bytes))].map(([n, d]) => [n, sha256(d)]))

const mixed = craft([{ name: 'x/', data: '' }, { name: 'x/one', data: 'a'.repeat(1000), method: 8 }, { name: 'two', data: '' }])
const corpus = {
  contract: 'dmind-bundle/v1',
  _readme:
    'Real archives as hex, shared by DayPilot (TypeScript) and Matrix Designer (Python). zip.valid must open with the listed entry hashes; zip.refused and bundle.refused must be refused by every reader (the limits override applies to the case that has one); bundle.valid must unpack to the listed document and attachments; writer lists inputs whose output bytes every writer must reproduce exactly. Regenerate with tests/ui/gen-archive-corpus.mjs and keep both repositories identical: tests pin its digest.',
  limits: m.zip.BUNDLE_LIMITS,
  zip: {
    valid: [
      { name: 'stored, deflated and folder entries', hex: hex(good), entries: await entryHashes(good) },
      { name: 'folder, deflated and empty entries', hex: hex(mixed), entries: await entryHashes(mixed) },
    ],
    refused: [
      ...hostile.map(([name, archive, , limits]) => ({ name, hex: hex(archive), ...(limits ? { limits } : {}) })),
      { name: 'tight custom limits', hex: hex(craft([{ name: 'a', data: 'hello world' }])), limits: { ...m.zip.BUNDLE_LIMITS, maxEntryBytes: 5 } },
    ],
  },
  bundle: {
    valid: [
      {
        name: 'one PNG and one PDF attached to topics',
        hex: hex(T.packed),
        document_sha256: sha256(T.files.get('document.json')),
        assets: Object.fromEntries([...T.store].map(([ref, d]) => [ref, d.type])),
      },
    ],
    refused: T.cases.map(([name, archive]) => ({ name, hex: hex(archive) })),
  },
  writer: [
    {
      name: 'two stored entries',
      entries: [
        { name: 'a.txt', text: 'hello\n' },
        { name: 'b/c.txt', text: 'world\n' },
      ],
      sha256: sha256(m.zip.writeZip([{ name: 'a.txt', data: new TextEncoder().encode('hello\n') }, { name: 'b/c.txt', data: new TextEncoder().encode('world\n') }])),
    },
  ],
}
const text = JSON.stringify(corpus, null, 1) + '\n'
const out = new URL('../../packages/dmind-contract/archive-cases.json', import.meta.url)
fs.writeFileSync(out, text)
console.log(`wrote ${out.pathname}: ${corpus.zip.refused.length} refused archives, ${corpus.bundle.refused.length} refused bundles, ${(text.length / 1024).toFixed(0)} KB`)
const matrixCopy = new URL('../../../matrix-designer/examples/dmind/archive-cases.json', import.meta.url)
if (fs.existsSync(new URL('./', matrixCopy))) {
  fs.writeFileSync(matrixCopy, text)
  console.log('copied to Matrix Designer examples/dmind/')
}
