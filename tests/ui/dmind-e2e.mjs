/**
 * dmind browser end-to-end (batch B0). Drives the real operator-web build against the real
 * gateway and database: first-run session, wizard preview gate, editing, undo/redo, drag/pan/zoom,
 * persistence, revisions, stale-save conflicts, archive, draft recovery, every export, imports,
 * narrow layout and hostile text.
 *
 *   scripts/dmind_e2e.sh            # builds, starts a throwaway gateway + SQLite, runs this
 *   node tests/ui/dmind-e2e.mjs http://127.0.0.1:8890     # against an already running app
 *
 * Optional environment:
 *   E2E_DESIGNER=1   the gateway is wired to a live Matrix Designer; test the success path
 *                    (default: designer unreachable; test the honest-failure path)
 *   AXE_CORE_PATH    path to axe.min.js; runs an axe scan of the editor when provided
 *   DMIND_E2E_PERF=1 print 100/500/1000-node timings (informational)
 *   PLAYWRIGHT_CORE_ROOT / CHROMIUM_PATH   where to find playwright-core / a Chromium binary
 */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import zlib from 'node:zlib'
import { createRequire } from 'node:module'

const base = (process.argv[2] || 'http://127.0.0.1:8890').replace(/\/$/, '')
const withDesigner = process.env.E2E_DESIGNER === '1'
const withUrlFetch = process.env.E2E_URL_FETCH === '1' // the gateway has DAYPILOT_DMIND_URL_FETCH=true

function loadPlaywright() {
  const roots = [process.env.PLAYWRIGHT_CORE_ROOT, import.meta.url, '/opt/node-tools/'].filter(Boolean)
  for (const root of roots) {
    try {
      return createRequire(root)('playwright-core')
    } catch {
      /* try the next location */
    }
  }
  throw new Error('playwright-core not found: install it or set PLAYWRIGHT_CORE_ROOT')
}
const { chromium } = loadPlaywright()
const fixture = new URL('../../packages/dmind-contract/order-system.dmind.json', import.meta.url)


// ---- file builders for the input tests (no third-party libraries)
function storeZip(entries) {
  const parts = [], central = []
  let offset = 0
  for (const [name, content] of Object.entries(entries)) {
    const data = Buffer.from(content), nameBuf = Buffer.from(name)
    const crc = zlib.crc32(data)
    const local = Buffer.alloc(30)
    local.writeUInt32LE(0x04034b50, 0); local.writeUInt16LE(20, 4); local.writeUInt32LE(crc, 14)
    local.writeUInt32LE(data.length, 18); local.writeUInt32LE(data.length, 22); local.writeUInt16LE(nameBuf.length, 26)
    parts.push(local, nameBuf, data)
    const entry = Buffer.alloc(46)
    entry.writeUInt32LE(0x02014b50, 0); entry.writeUInt16LE(20, 4); entry.writeUInt16LE(20, 6); entry.writeUInt32LE(crc, 16)
    entry.writeUInt32LE(data.length, 20); entry.writeUInt32LE(data.length, 24); entry.writeUInt16LE(nameBuf.length, 28)
    entry.writeUInt32LE(offset, 42)
    central.push(entry, nameBuf)
    offset += 30 + nameBuf.length + data.length
  }
  const centralBuf = Buffer.concat(central)
  const end = Buffer.alloc(22)
  end.writeUInt32LE(0x06054b50, 0); end.writeUInt16LE(central.length / 2, 8); end.writeUInt16LE(central.length / 2, 10)
  end.writeUInt32LE(centralBuf.length, 12); end.writeUInt32LE(offset, 16)
  return Buffer.concat([...parts, centralBuf, end])
}
function docxBuffer(paragraphs) {
  const W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
  const body = paragraphs
    .map(([text, style]) => `<w:p>${style ? `<w:pPr><w:pStyle w:val="${style}"/></w:pPr>` : ''}<w:r><w:t>${text}</w:t></w:r></w:p>`)
    .join('')
  return storeZip({
    '[Content_Types].xml': '<Types/>',
    'word/document.xml': `<?xml version="1.0"?><w:document xmlns:w="${W}"><w:body>${body}</w:body></w:document>`,
  })
}
function pdfBuffer(lines) {
  const stream = 'BT /F1 12 Tf 72 720 Td 14 TL ' + lines.map((l) => `(${l}) Tj`).join(' T* ') + ' ET'
  const objs = [
    '<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
  ]
  let out = '%PDF-1.4\n'
  const offsets = []
  objs.forEach((o, i) => { offsets.push(out.length); out += `${i + 1} 0 obj\n${o}\nendobj\n` })
  const xref = out.length
  out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n` + offsets.map((o) => String(o).padStart(10, '0') + ' 00000 n \n').join('')
  out += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`
  return Buffer.from(out, 'latin1')
}

const results = []
const pageErrors = []
const dialogs = []
async function step(name, fn) {
  try {
    await fn()
    results.push({ name, ok: true })
    console.log('PASS  ' + name)
  } catch (e) {
    results.push({ name, ok: false, error: String(e.message || e).split('\n').slice(0, 6).join('\n') })
    console.log('FAIL  ' + name + '\n      ' + results.at(-1).error.replace(/\n/g, '\n      '))
  }
}

const browser = await chromium.launch({
  args: ['--no-sandbox'],
  executablePath: process.env.CHROMIUM_PATH || undefined,
})
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true })
ctx.setDefaultTimeout(8000)
function watch(page) {
  page.on('pageerror', (e) => pageErrors.push(String(e)))
  page.on('console', (m) => {
    // Deliberate 4xx/5xx probes log a network line; real script errors are what we fail on.
    if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) pageErrors.push('console: ' + m.text())
  })
  page.on('dialog', (d) => {
    dialogs.push(`${d.type()}: ${d.message()}`)
    d.accept()
  })
  return page
}

const nodes = (p) => p.locator('.dmind-canvas [data-node]')
const status = (p) => p.locator('.dmind-status')
const button = (p, name) => p.getByRole('button', { name, exact: typeof name === 'string' })
const save = (p) => p.getByRole('button', { name: /^Save( · r\d+)?$/ })
const inspectorLabel = (p) => p.locator('.dmind-inspector').getByLabel('Label', { exact: true })
const tx = async (locator) => {
  const [x, y] = (await locator.getAttribute('transform')).match(/-?[\d.]+/g).map(Number)
  return { x, y }
}

// First-run onboarding appears a moment after sign-in and has two steps.
async function dismissOnboarding(page) {
  for (let i = 0; i < 6; i++) {
    await page.waitForTimeout(700)
    if (!(await page.locator('.dp-onb').count())) return
    for (const name of ['Set up later (limited mode)', 'Skip for now']) {
      const b = page.getByRole('button', { name })
      if (await b.count()) {
        await b.click()
        break
      }
    }
  }
}

async function ready(page) {
  await page.goto(base + '/#/diagrams', { waitUntil: 'networkidle' })
  if (await page.getByPlaceholder('Acme workspace').count()) {
    await page.getByPlaceholder('Acme workspace').fill('dmind E2E')
    await page.getByPlaceholder('Your name').fill('E2E Owner')
    await page.getByPlaceholder('you@company.com').fill('e2e@example.test')
    await page.getByPlaceholder('Create a strong password (min 10)').fill('correct-horse-battery-9')
    await page.getByRole('button', { name: 'Create local workspace' }).click()
    await page.waitForLoadState('networkidle')
  }
  await dismissOnboarding(page)
  await page.locator('.dp-nav button', { hasText: 'Diagrams' }).first().click()
  await page.getByRole('heading', { name: 'Turn ideas into diagrams' }).waitFor()
}

async function wizard(page, { topic, outline, kind = 'mindmap', designer = false }) {
  await button(page, 'New diagram').click()
  await page.getByLabel('Topic', { exact: true }).fill(topic)
  await page.getByLabel('Brainstorm or outline').fill(outline)
  await button(page, 'Next: structure').click()
  await page.getByLabel('Diagram type').selectOption(kind)
  if (designer) await page.getByLabel(/Ask Matrix Designer/).check()
  await button(page, 'Generate preview').click()
}
async function useDiagram(page) {
  await button(page, 'Use this diagram').click()
  await page.locator('.dmind-editor').waitFor()
}
async function exportAs(page, format) {
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByLabel('Export diagram').selectOption(format),
  ])
  return { name: download.suggestedFilename(), text: fs.readFileSync(await download.path(), 'utf8') }
}

const outline = 'Receive order\n  Validate items\n  Reserve stock\nCharge payment\n  Success\n  Retry or cancel'
const page = watch(await ctx.newPage())
let savedId = ''

await step('shell: Diagrams tab present and every existing view still renders', async () => {
  await ready(page)
  const labels = await page.locator('.dp-nav button').allTextContents()
  for (const view of ['Home', 'Planning', 'Calendar', 'Tasks', 'Projects', 'Email', 'Documents', 'Agents', 'Diagrams'])
    assert.ok(labels.some((l) => l.includes(view)), 'missing nav ' + view)
  for (const view of ['Home', 'Planning', 'Calendar', 'Tasks', 'Projects', 'Email', 'Documents', 'Agents']) {
    await page.locator('.dp-nav button', { hasText: view }).first().click()
    await page.waitForTimeout(150)
    assert.ok(await page.locator('main, [role="main"], .dp-main').first().isVisible(), view + ' did not render')
  }
  await page.locator('.dp-nav button', { hasText: 'Diagrams' }).first().click()
  await page.getByRole('heading', { name: 'Turn ideas into diagrams' }).waitFor()
})

await step('wizard: Source -> Structure -> Review; preview never replaces the editor', async () => {
  await button(page, 'New diagram').click()
  assert.ok(await button(page, 'Next: structure').isDisabled(), 'needs a topic first')
  await page.getByLabel('Topic', { exact: true }).fill('<img src=x onerror="window.__xss=1">Order processing')
  await page.getByLabel('Brainstorm or outline').fill(outline)
  await button(page, 'Next: structure').click()
  assert.match(await page.locator('.dmind-wizard').innerText(), /works without AI or a network connection/)
  await button(page, 'Back').click()
  assert.equal(await page.getByLabel('Topic', { exact: true }).inputValue(), '<img src=x onerror="window.__xss=1">Order processing')
  await page.getByLabel('Topic', { exact: true }).fill('Order processing')
  await button(page, 'Next: structure').click()
  await button(page, 'Generate preview').click()
  assert.equal(await page.locator('.dmind-preview li').count(), 7)
  assert.equal(await page.locator('.dmind-editor').count(), 0, 'editor must wait for the person to accept')
  await button(page, 'Back').click()
  await button(page, 'Generate preview').click()
  await useDiagram(page)
  assert.equal(await nodes(page).count(), 7)
  assert.equal(await page.evaluate(() => window.__xss), undefined)
})

await step('editor: label edit, undo/redo, add child/sibling, collapse keeps full exports', async () => {
  await nodes(page).nth(1).click()
  await inspectorLabel(page).fill('Receive and log order')
  await page.locator('[data-node][aria-label="Receive and log order"]').waitFor()
  assert.ok(await button(page, 'Undo').isEnabled())
  await button(page, 'Undo').click()
  await page.locator('[data-node][aria-label="Receive order"]').waitFor()
  await button(page, 'Redo').click()
  await page.locator('[data-node][aria-label="Receive and log order"]').waitFor()
  await button(page, 'Undo').click()
  const before = await nodes(page).count()
  await button(page, 'Add child · Insert').click()
  await button(page, 'Add sibling').click()
  assert.equal(await nodes(page).count(), before + 2)
  await button(page, 'Undo').click()
  await button(page, 'Undo').click()
  assert.equal(await nodes(page).count(), before)
  await nodes(page).nth(1).click() // Receive order has two children
  await button(page, 'Collapse branch').click()
  assert.equal(await nodes(page).count(), before - 2)
  const md = await exportAs(page, 'md')
  assert.ok(md.text.includes('Validate items') && md.text.includes('Reserve stock'), 'folded topics must stay in exports')
  await button(page, 'Expand branch').click()
  assert.equal(await nodes(page).count(), before)
})

await step('editor: keyboard create, delete, undo and redo; focus is visible', async () => {
  const before = await nodes(page).count()
  await nodes(page).nth(3).focus()
  await page.keyboard.press('Enter')
  assert.equal(await nodes(page).nth(3).getAttribute('aria-pressed'), 'true')
  await page.keyboard.press('Insert')
  assert.equal(await nodes(page).count(), before + 1)
  await page.keyboard.press('Delete')
  assert.equal(await nodes(page).count(), before)
  await page.keyboard.press('Control+z')
  assert.equal(await nodes(page).count(), before + 1)
  await page.keyboard.press('Control+Shift+z')
  assert.equal(await nodes(page).count(), before)
  await nodes(page).nth(2).focus()
  const ring = await nodes(page).nth(2).evaluate((g) => {
    const s = getComputedStyle(g)
    return `${s.outlineStyle}/${s.outlineWidth}`
  })
  assert.ok(!ring.startsWith('none'), 'focused topic needs a visible focus ring, got ' + ring)
})

await step('editor: labeled links, feedback loop warning and rejected branch cycle', async () => {
  const panel = page.locator('.dmind-inspector')
  await page.locator('[data-node]', { hasText: 'Charge payment' }).click()
  await panel.getByLabel('Target').selectOption({ label: 'Charge payment' })
  await panel.getByLabel('Link type').selectOption('flow')
  await panel.getByLabel('Condition / link label').fill('temporary failure; retry')
  await button(page, 'Add link').click()
  assert.match(await panel.innerText(), /temporary failure; retry/)
  assert.match(await page.locator('.dmind-editor').innerText(), /Feedback loop/)
  const links = await panel.locator('li').count()
  await panel.getByLabel('Target').selectOption({ label: 'Order processing' })
  await panel.getByLabel('Link type').selectOption('branch')
  await button(page, 'Add link').click()
  assert.match(await status(page).innerText(), /cycle|one parent/i)
  assert.equal(await panel.locator('li').count(), links, 'a rejected link must not change the diagram')
})

await step('canvas: drag moves a topic, auto-layout restores, zoom and pan work', async () => {
  const node = nodes(page).nth(2)
  const start = await tx(node)
  const box = await node.boundingBox()
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 + 60, box.y + box.height / 2 + 30, { steps: 8 })
  await page.mouse.up()
  const moved = await tx(nodes(page).nth(2))
  assert.ok(Math.abs(moved.x - start.x - 60) < 3 && Math.abs(moved.y - start.y - 30) < 3, JSON.stringify({ start, moved }))
  await button(page, 'Auto-layout').click()
  assert.deepEqual(await tx(nodes(page).nth(2)), start)
  const svg = page.locator('.dmind-canvas svg')
  const width = Number(await svg.getAttribute('width'))
  await page.getByLabel('Canvas zoom').fill('2')
  assert.ok(Math.abs(Number(await svg.getAttribute('width')) - width * 2) < 2)
  const canvas = page.locator('.dmind-canvas')
  const scroll0 = await canvas.evaluate((c) => c.scrollLeft)
  const cb = await canvas.boundingBox()
  await page.mouse.move(cb.x + cb.width - 30, cb.y + 30)
  await page.mouse.down()
  await page.mouse.move(cb.x + cb.width - 180, cb.y + 30, { steps: 6 })
  await page.mouse.up()
  assert.ok((await canvas.evaluate((c) => c.scrollLeft)) > scroll0, 'dragging the background pans')
  await page.getByLabel('Canvas zoom').fill('1')
})

await step('persistence: save, reopen, revisions append, restore never rewrites history', async () => {
  await page.getByLabel('Diagram title').fill('Order processing v1')
  await save(page).click()
  await page.getByText(/Saved revision 1/).waitFor()
  await page.getByLabel('Diagram title').fill('Order processing v2')
  await save(page).click()
  await page.getByText(/Saved revision 2/).waitFor()
  await page.reload({ waitUntil: 'networkidle' })
  await page.getByRole('heading', { name: 'Turn ideas into diagrams' }).waitFor()
  await page.locator('.dmind-saved button', { hasText: 'Order processing v2' }).click()
  await page.getByText(/Loaded revision 2/).waitFor()
  await button(page, 'Load saved revisions').click()
  await button(page, 'Restore r1').click()
  await page.getByText(/Save to append a new revision/).waitFor()
  assert.equal(await page.getByLabel('Diagram title').inputValue(), 'Order processing v1')
  await save(page).click()
  await page.getByText(/Saved revision 3/).waitFor()
  await button(page, 'Load saved revisions').click()
  for (const r of ['Restore r3', 'Restore r2', 'Restore r1']) await button(page, r).waitFor()
  savedId = (await page.evaluate(() => fetch('/v1/diagrams', { headers: { 'X-Workspace-Id': 'default' } }).then((r) => r.json()))).items[0].id
})

await step('conflict: a stale tab gets 409, keeps its draft, and can save a copy', async () => {
  const tab2 = watch(await ctx.newPage())
  await ready(tab2)
  await tab2.locator('.dmind-saved button', { hasText: 'Order processing v1' }).first().click()
  await tab2.getByText(/Loaded revision 3/).waitFor()
  await page.getByLabel('Diagram title').fill('Edited in tab one')
  await save(page).click()
  await page.getByText(/Saved revision 4/).waitFor()
  await tab2.getByLabel('Diagram title').fill('Edited in tab two')
  await save(tab2).click()
  await tab2.getByText(/changed elsewhere/).waitFor()
  assert.equal(await tab2.getByLabel('Diagram title').inputValue(), 'Edited in tab two')
  await button(tab2, 'Save a copy').click()
  await tab2.getByText(/Saved revision 1/).waitFor()
  await tab2.locator('.dmind-saved button', { hasText: 'Edited in tab one' }).first().waitFor()
  await tab2.locator('.dmind-saved button', { hasText: 'Edited in tab two' }).first().waitFor()
  await tab2.close()
})

await step('archive: ordinary saves keep the state; archived diagrams stay recoverable', async () => {
  await button(page, 'Archive diagram').click()
  await page.getByText(/· archived/).first().waitFor()
  await page.locator('.dmind-saved button', { hasText: 'Edited in tab one' }).waitFor({ state: 'detached' })
  await page.getByLabel('Include archived').check()
  await page.locator('.dmind-saved button', { hasText: 'Edited in tab one' }).first().waitFor()
  await page.getByLabel('Diagram title').fill('Edited while archived')
  await save(page).click()
  await page.getByText(/Saved revision \d+ · archived/).waitFor()
  await button(page, 'Unarchive diagram').click()
  await page.getByText(/Saved revision \d+$/).waitFor()
  await page.getByLabel('Include archived').uncheck()
  await page.locator('.dmind-saved button', { hasText: 'Edited while archived' }).waitFor()
})

await step('draft recovery: unsaved work survives a reload', async () => {
  await page.getByLabel('Diagram title').fill('Unsaved idea')
  await page.locator('.dmind-draft', { hasText: 'Unsaved idea' }).waitFor() // autosaved to IndexedDB
  await page.reload({ waitUntil: 'networkidle' })
  await page.getByRole('heading', { name: 'Turn ideas into diagrams' }).waitFor()
  await button(page, 'Recover browser draft').click()
  await page.getByText(/Recovered browser draft/).waitFor()
  assert.equal(await page.getByLabel('Diagram title').inputValue(), 'Unsaved idea')
})

await step('exports: portable, escaped, script-free and self-contained', async () => {
  await nodes(page).first().click()
  await inspectorLabel(page).fill('"><script>window.__xss=2</script>')
  await page.locator('.dmind-inspector').getByLabel('Notes / algorithm').fill('</pre><script>window.__xss=3</script>')
  const json = await exportAs(page, 'json')
  assert.ok(json.name.endsWith('.dmind'), json.name)
  const doc = JSON.parse(json.text)
  assert.equal(doc.schema_version, 'dmind/v1')
  assert.equal(doc.nodes.length, await nodes(page).count())
  assert.equal(doc.metadata.generator, 'outline')
  assert.equal((await exportAs(page, 'mermaid')).text.startsWith('flowchart TD'), true)
  const svg = (await exportAs(page, 'svg')).text
  assert.ok(svg.includes('<svg') && !svg.includes('<script'))
  const brief = (await exportAs(page, 'coding')).text
  assert.ok(brief.includes('UNTRUSTED') && brief.includes('Acceptance checklist'))
  const html = (await exportAs(page, 'html')).text
  assert.ok(!/<script/i.test(html) && html.includes('Content-Security-Policy'))
  const viewer = await ctx.newPage()
  const requests = []
  viewer.on('request', (r) => requests.push(r.url()))
  await viewer.setContent(html)
  assert.equal(await viewer.evaluate(() => window.__xss), undefined)
  assert.equal(await viewer.locator('script, img, iframe, link').count(), 0)
  assert.ok(requests.every((u) => u.startsWith('about:') || u.startsWith('data:')), requests.join())
  await viewer.close()
})

await step('imports: text, dmind JSON copy, Matrix bundle; bad files are refused clearly', async () => {
  const file = page.getByLabel('Import source or diagram')
  await button(page, 'New diagram').click()
  await file.setInputFiles({ name: 'ideas.md', mimeType: 'text/markdown', buffer: Buffer.from('- one\n  - two\n- three') })
  await page.getByText(/Text loaded/).waitFor()
  assert.equal(await page.getByLabel('Topic', { exact: true }).inputValue(), 'ideas')
  await file.setInputFiles({ name: 'scan.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4') })
  await page.getByText(/Supported attachments/).waitFor()
  await file.setInputFiles({ name: 'huge.txt', mimeType: 'text/plain', buffer: Buffer.alloc(2_100_000, 97) })
  await page.getByText(/smaller than 2 MB/).waitFor()
  await file.setInputFiles({ name: 'broken.json', mimeType: 'application/json', buffer: Buffer.from('{"schema_version":"dmind/v2"}') })
  await page.getByText(/dmind\/v2.*Update DayPilot/).waitFor()
  await file.setInputFiles({ name: 'order.dmind.json', mimeType: 'application/json', buffer: fs.readFileSync(fixture) })
  await page.locator('.dmind-preview').waitFor()
  assert.equal(await page.locator('.dmind-preview li').count(), 4)
  await useDiagram(page)
  await save(page).click()
  await page.getByText(/Saved revision 1/).waitFor()
  await page.locator('.dmind-saved button', { hasText: 'Order processing system' }).first().waitFor() // saved as a copy
  // Drag and drop a .dmind file onto the workspace: opens a preview, keeps unknown fields.
  const dropped = { ...JSON.parse(fs.readFileSync(fixture, 'utf8')), future_field: { keep: true } }
  const dt = await page.evaluateHandle((text) => {
    const d = new DataTransfer()
    d.items.add(new File([text], 'dropped.dmind', { type: 'application/vnd.dmind+json' }))
    return d
  }, JSON.stringify(dropped))
  await page.dispatchEvent('section.dmind', 'dragover', { dataTransfer: dt })
  assert.ok(await page.locator('section.dmind-dropping').count(), 'drop target is highlighted')
  await page.dispatchEvent('section.dmind', 'drop', { dataTransfer: dt })
  await page.locator('.dmind-preview').waitFor()
  assert.match(await status(page).innerText(), /Kept 1 field\(s\).*future_field/)
  await useDiagram(page)
  assert.deepEqual(JSON.parse((await exportAs(page, 'json')).text).future_field, { keep: true })
  const bundle = {
    schema_version: 'matrix.designer.bundle/v1',
    project: 'Inventory app',
    source: { idea: 'Manage stock' },
    batch_roadmap: [
      { id: 'b1', name: 'Foundation', purpose: 'Skeleton' },
      { id: 'b2', name: 'Stock API', purpose: 'CRUD', depends_on: ['b1'] },
    ],
  }
  await button(page, 'New diagram').click()
  await page.getByLabel('Import source or diagram').setInputFiles({ name: 'bundle.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(bundle)) })
  await page.locator('.dmind-preview').waitFor()
  assert.equal(await page.locator('.dmind-preview li').count(), 3)
  await useDiagram(page)
  const original = JSON.parse((await exportAs(page, 'original')).text)
  assert.deepEqual(original, bundle, 'the untouched original bundle is exported separately')
})

await step(withDesigner ? 'matrix: designer proposal and handoff return a fresh validated bundle' : 'matrix: unreachable designer is reported honestly and nothing is created', async () => {
  const count = await nodes(page).count()
  if (!withDesigner) {
    await button(page, 'Generate Design Bundle').click()
    await page.getByText(/Matrix Designer is unavailable|rejected|unreachable/).waitFor()
    await wizard(page, { topic: 'Inventory web app', outline: '', designer: true })
    await page.getByText(/Matrix Designer is unavailable/).waitFor()
    assert.equal(await page.locator('.dmind-preview').count(), 0)
    assert.ok(await page.getByRole('button', { name: 'Generate preview' }).count(), 'the wizard stays on Structure')
    await button(page, 'Close wizard').click()
    assert.equal(await nodes(page).count(), count, 'a failed proposal never touches the open diagram')
    await button(page, 'New diagram').click()
    await page.getByLabel('Topic', { exact: true }).fill('Next run')
    await button(page, 'Next: structure').click()
    assert.equal(await page.getByLabel(/Ask Matrix Designer/).isChecked(), false, 'provider use is opt-in per run')
    await button(page, 'Close wizard').click()
  } else {
    const [download] = await Promise.all([page.waitForEvent('download'), button(page, 'Generate Design Bundle').click()])
    const bundle = JSON.parse(fs.readFileSync(await download.path(), 'utf8'))
    assert.equal(bundle.schema_version, 'matrix.designer.bundle/v1')
    assert.ok(bundle.source.references[0].note.includes('UNTRUSTED'))
    await page.getByText(/validation:/).waitFor()
    await button(page, 'Export validation report').waitFor()
    await wizard(page, { topic: 'Inventory web application', outline: '', designer: true })
    await page.locator('.dmind-preview').waitFor()
    await useDiagram(page)
    assert.ok(await page.getByLabel('Export diagram').locator('option', { hasText: 'Original Matrix Design Bundle' }).count())
    await button(page, 'New diagram').click()
    await page.getByLabel('Topic', { exact: true }).fill('Next run')
    await button(page, 'Next: structure').click()
    assert.equal(await page.getByLabel(/Ask Matrix Designer/).isChecked(), false, 'provider use is opt-in per run')
    await button(page, 'Close wizard').click()
  }
})

// ---------------------------------------------------------------- B2 reliable workspace
const poll = async (fn, what, ms = 8000) => {
  const end = Date.now() + ms
  for (;;) {
    const v = await fn()
    if (v) return v
    if (Date.now() > end) throw new Error('timed out waiting for ' + what)
    await page.waitForTimeout(100)
  }
}
const chip = (name) => page.locator('.dmind-tags').getByRole('button', { name, exact: true })
const savedItems = (p) => p.locator('.dmind-saved button[aria-pressed]')
const api = (p, method, path, body) =>
  p.evaluate(
    async ([method, path, body]) => {
      const csrf = ((document.cookie.match(/(?:^|;\s*)dp_csrf=([^;]+)/) || [])[1]) || ''
      const r = await fetch(path, {
        method,
        headers: { 'Content-Type': 'application/json', 'X-Workspace-Id': 'default', 'X-CSRF-Token': decodeURIComponent(csrf) },
        body: body ? JSON.stringify(body) : undefined,
      })
      return { status: r.status, body: await r.json().catch(() => null) }
    },
    [method, path, body],
  )
const tiny = (title, tags) => ({
  schema_version: 'dmind/v1', id: 'x', title, kind: 'mindmap', nodes: [{ id: 'n', label: 'topic' }], edges: [], metadata: { tags },
})

await step('workspace: 55 diagrams page in, search and tag filters work', async () => {
  for (let i = 0; i < 55; i++) await api(page, 'POST', '/v1/diagrams', { document: tiny('Bulk ' + String(i).padStart(2, '0'), [i % 2 ? 'even-tag' : 'odd-tag']) })
  await page.getByLabel('Include archived').check()
  await button(page, 'Refresh').click()
  await poll(async () => (await savedItems(page).count()) === 50, 'the first page of 50')
  await button(page, 'Load more').click()
  await poll(async () => (await savedItems(page).count()) >= 55, 'the rest of the list')
  assert.equal(await page.getByRole('button', { name: 'Load more' }).count(), 0, 'no more pages')
  await page.getByLabel('Search diagrams').fill('Bulk 07')
  await poll(async () => (await savedItems(page).count()) === 1, 'search narrowing to one')
  assert.match(await savedItems(page).first().innerText(), /Bulk 07/)
  await page.getByLabel('Search diagrams').fill('')
  await chip('#odd-tag').click()
  await poll(async () => (await savedItems(page).count()) === 28, '28 diagrams with the tag')
  await chip('#odd-tag').click()
  await poll(async () => (await savedItems(page).count()) >= 50, 'the unfiltered list again')
  await page.getByLabel('Include archived').uncheck()
})

await step('details: tags are normalised and the diagram can be found by them', async () => {
  await page.getByLabel('Search diagrams').fill('Bulk 00')
  await poll(async () => (await savedItems(page).count()) === 1, 'Bulk 00')
  await savedItems(page).first().click()
  await page.getByText(/Loaded revision 1/).waitFor()
  await page.getByLabel('Tags', { exact: true }).fill('  Needs Review , needs review, Q3 ')
  await page.getByLabel('Tags', { exact: true }).blur()
  await page.getByLabel('Tags', { exact: true }).waitFor()
  assert.equal(await page.getByLabel('Tags', { exact: true }).inputValue(), 'needs review, q3')
  await save(page).click()
  await page.getByText(/Saved revision 2/).waitFor()
  await chip('#needs review').waitFor()
})

await step('resilience: a save retries through a dropped connection and a failure keeps the work', async () => {
  try {
  await page.getByLabel('Diagram title').fill('Bulk 00 edited')
  await ctx.setOffline(true)
  await save(page).click()
  await page.getByText(/Retrying \(\d\/4\)/).waitFor()
  await ctx.setOffline(false)
  await page.getByText(/Saved revision 3/).waitFor()
  // Offline for good: the person is told, and the edit survives in the drafts list.
  await page.getByLabel('Diagram title').fill('Bulk 00 offline edit')
  await ctx.setOffline(true)
  await save(page).click()
  await page.getByText(/Could not reach the server/).waitFor({ timeout: 15000 })
  await page.locator('.dmind-draft', { hasText: 'Bulk 00 offline edit' }).waitFor()
  await ctx.setOffline(false)
  await save(page).click()
  await page.getByText(/Saved revision 4/).waitFor()
  assert.equal(await page.locator('.dmind-draft', { hasText: 'Bulk 00 offline edit' }).count(), 0, 'a saved draft is cleared')
  } finally {
    await ctx.setOffline(false)
  }
})

await step('history: revisions page, compare and restore', async () => {
  const found = await api(page, 'GET', '/v1/diagrams?q=Bulk 00&limit=5')
  const { id, revision } = found.body.items[0]
  const doc = (await api(page, 'GET', '/v1/diagrams/' + id)).body.document
  for (let r = revision; r < revision + 22; r++) {
    doc.title = 'Bulk 00 v' + (r + 1)
    assert.equal((await api(page, 'PUT', '/v1/diagrams/' + id, { document: doc, expectedRevision: r })).status, 200)
  }
  await page.getByLabel('Search diagrams').fill('Bulk 00')
  await savedItems(page).first().click()
  await page.getByText(/Loaded revision 26/).waitFor()
  await button(page, 'Load saved revisions').click()
  await poll(async () => (await page.locator('.dmind-rev').count()) === 20, 'the first 20 revisions')
  await button(page, 'Load older revisions').click()
  await poll(async () => (await page.locator('.dmind-rev').count()) === 26, 'all 26 revisions')
  assert.equal(await page.getByRole('button', { name: 'Load older revisions' }).count(), 0)
  await page.getByLabel('Compare r1 with the current draft').click()
  await page.getByLabel('Revision changes').waitFor()
  assert.match(await page.getByLabel('Revision changes').innerText(), /Title: "Bulk 00" → "Bulk 00 v26"/)
  await page.getByLabel('Search diagrams').fill('')
})

await step('drafts: shared live across tabs, optional, and cleared when discarded', async () => {
  const tab2 = watch(await ctx.newPage())
  await ready(tab2)
  await wizard(page, { topic: 'Cross tab draft', outline: 'One\n  Two' })
  await useDiagram(page)
  await tab2.locator('.dmind-draft', { hasText: 'Cross tab draft' }).waitFor() // announced, no reload
  await tab2.getByLabel('Discard draft Cross tab draft').click()
  await page.locator('.dmind-draft', { hasText: 'Cross tab draft' }).waitFor({ state: 'detached' })
  await tab2.close()
  // Opting out stores nothing new and clears what was kept.
  await page.getByLabel('Keep drafts in this browser').uncheck()
  await page.getByLabel('Diagram title').fill('Never stored')
  await page.waitForTimeout(700)
  assert.equal(await page.locator('.dmind-draft').count(), 0)
  await page.getByLabel('Keep drafts in this browser').check()
  await page.getByLabel('Diagram title').fill('Stored again')
  await page.locator('.dmind-draft', { hasText: 'Stored again' }).waitFor()
})

// ---------------------------------------------------------------- B3 inputs
await step('inputs: documents are extracted for review, never auto-added, and cited by topics', async () => {
  await button(page, 'New diagram').click()
  const add = page.getByLabel('Add a document')
  const docx = docxBuffer([
    ['Order process', 'Title'], ['Intake', 'Heading1'], ['Receive the order', null], ['Check stock', null],
    ['Billing', 'Heading1'], ['Charge the card', null],
  ])
  await add.setInputFiles({ name: 'process.docx', mimeType: 'application/octet-stream', buffer: docx })
  const preview = page.getByRole('region', { name: 'Extraction preview' })
  await preview.waitFor()
  assert.match(await preview.getByLabel('Extracted text').inputValue(), /^Order process\nIntake\n {2}Receive the order/)
  assert.match(await preview.innerText(), /process\.docx \(docx/)
  assert.equal(await page.getByLabel('Brainstorm or outline').inputValue(), '', 'nothing enters the outline until it is accepted')
  await button(page, 'Use this text').click()
  assert.equal(await page.getByLabel('Topic', { exact: true }).inputValue(), 'process')
  assert.match(await page.getByLabel('Brainstorm or outline').inputValue(), /Charge the card/)
  assert.equal(await page.getByLabel('Sources').locator('li').count(), 1)
  // A PDF can be previewed and discarded without changing anything.
  await add.setInputFiles({ name: 'notes.pdf', mimeType: 'application/pdf', buffer: pdfBuffer(['Refund policy', 'Within 30 days']) })
  await preview.waitFor()
  assert.match(await preview.getByLabel('Extracted text').inputValue(), /Refund policy\nWithin 30 days/)
  await button(page, 'Discard').click()
  assert.equal(await preview.count(), 0)
  assert.equal(await page.getByLabel('Sources').locator('li').count(), 1)
  // Refusals are specific and leave the outline alone.
  await add.setInputFiles({ name: 'tool.exe', mimeType: 'application/octet-stream', buffer: Buffer.from('MZ\x90\0') })
  await page.getByRole('alert').filter({ hasText: /Supported documents/ }).waitFor()
  await add.setInputFiles({ name: 'evil.docx', mimeType: 'application/octet-stream', buffer: storeZip({ 'word/document.xml': '<!DOCTYPE d [<!ENTITY a "x">]><d/>' }) })
  await page.getByRole('alert').filter({ hasText: /DTD or entity/ }).waitFor()
  await add.setInputFiles({ name: 'huge.txt', mimeType: 'text/plain', buffer: Buffer.alloc(10_100_000, 97) })
  await page.getByRole('alert').filter({ hasText: /smaller than 10 MB/ }).waitFor()
  assert.match(await page.getByLabel('Brainstorm or outline').inputValue(), /Charge the card/)
  // The accepted source is cited by the topics generated from it.
  await button(page, 'Next: structure').click()
  await page.getByLabel(/Ask Matrix Designer/).check()
  assert.match(await page.locator('.dmind-wizard').innerText(), /including the extracted text of 1 source/)
  await page.getByLabel(/Ask Matrix Designer/).uncheck()
  await button(page, 'Generate preview').click()
  await useDiagram(page)
  await page.locator('[data-node][aria-label="Charge the card"]').click()
  const cites = page.getByLabel('Topic sources')
  await cites.waitFor()
  assert.match(await cites.innerText(), /process\.docx \(docx, \d+ bytes\), line 6/)
})

await step(withUrlFetch ? 'inputs: URL fetching refuses private addresses end to end' : 'inputs: URL fetching is off until an administrator enables it', async () => {
  await button(page, 'New diagram').click()
  const address = page.getByLabel('Web page address')
  if (!withUrlFetch) {
    assert.ok(await address.isDisabled())
    assert.match(await page.locator('.dmind-sources').innerText(), /turned off on this server/)
    const none = []
    page.on('request', (r) => r.url().includes('fetch-url') && none.push(r.url()))
    assert.ok(await button(page, 'Fetch page').isDisabled())
    assert.deepEqual(none, [])
    return
  }
  assert.match(await page.locator('.dmind-sources').innerText(), /Nothing is fetched automatically/)
  for (const url of [base + '/', 'http://127.0.0.1/', 'http://localhost/', 'http://[::1]/', 'http://169.254.169.254/latest/meta-data/', 'file:///etc/passwd', 'http://user:pw@example.org/']) {
    await address.fill(url)
    await button(page, 'Fetch page').click()
    await page.getByRole('alert').waitFor()
    assert.match(await page.getByRole('alert').innerText(), /private or reserved|Only http|credentials|could not be resolved|Only ports/, url)
    assert.equal(await page.getByRole('region', { name: 'Extraction preview' }).count(), 0)
  }
})

// ---------------------------------------------------------------- B4 layouts and rich editing
const boxes = (p = page) =>
  p.evaluate(() =>
    [...document.querySelectorAll('.dmind-canvas [data-node]')].map((g) => {
      const [x, y] = g.getAttribute('transform').match(/-?[\d.]+/g).map(Number)
      return { id: g.dataset.node, label: g.getAttribute('aria-label'), x, y }
    }),
  )
const overlapsIn = (bs) => {
  const hits = []
  for (let i = 0; i < bs.length; i++)
    for (let j = i + 1; j < bs.length; j++)
      if (Math.abs(bs[i].x - bs[j].x) < 200 && Math.abs(bs[i].y - bs[j].y) < 64) hits.push([bs[i].label, bs[j].label])
  return hits
}
const topic = (name) => page.locator(`[data-node][aria-label="${name}"]`)
const levelOf = (name) =>
  page.evaluate((n) => [...document.querySelectorAll('[role=treeitem]')].find((li) => li.querySelector('input').value === n)?.getAttribute('aria-level'), name)
const centre = async (name) => {
  await topic(name).scrollIntoViewIfNeeded()
  const b = await topic(name).boundingBox()
  return { x: b.x + b.width / 2, y: b.y + b.height / 2 }
}
const PROJECT = 'Plan\n  Research\n    Interviews\n    Survey\n  Build\n    API\n    UI\n  Launch\n    Docs\n    Announce\nRisks\n  Schedule\n  Budget'

await step('layouts: every layout is free of overlaps, recorded, and undoable', async () => {
  await wizard(page, { topic: 'Project', outline: PROJECT })
  await useDiagram(page)
  const seen = new Set()
  for (const id of ['tree', 'orgchart', 'radial', 'fishbone', 'layered', 'grid', 'columns']) {
    await page.getByLabel('Layout', { exact: true }).selectOption(id)
    const bs = await boxes()
    assert.equal(bs.length, 14)
    assert.deepEqual(overlapsIn(bs), [], id)
    seen.add(JSON.stringify(bs.map((b) => [b.x, b.y])))
    assert.equal(JSON.parse((await exportAs(page, 'json')).text).metadata.layout, id)
  }
  // 'Flow (top down)' follows flow links; with branches only it matches the org chart, so 6 differ.
  assert.equal(seen.size, 6, 'each layout arranges the topics differently')
  await button(page, 'Undo').click()
  assert.equal(await page.getByLabel('Layout', { exact: true }).inputValue(), 'grid')
  // A flowchart reads top to bottom by default and keeps its loop out of the way.
  await wizard(page, { topic: 'Retry flow', outline: 'Start\nCharge\nConfirm', kind: 'flowchart' })
  await useDiagram(page)
  const flow = await boxes()
  const y = Object.fromEntries(flow.map((b) => [b.label, b.y]))
  assert.ok(y.Start < y.Charge && y.Charge < y.Confirm, 'steps run downward')
  assert.equal(await page.getByLabel('Layout', { exact: true }).inputValue(), 'layered')
  await wizard(page, { topic: 'Project', outline: PROJECT })
  await useDiagram(page)
})

await step('selection: several topics move, style and delete together', async () => {
  await topic('Interviews').click()
  await topic('Survey').click({ modifiers: ['Control'] })
  await page.getByText(/2 topics selected/).waitFor()
  const before = Object.fromEntries((await boxes()).map((b) => [b.label, b]))
  const from = await centre('Interviews')
  await page.mouse.move(from.x, from.y)
  await page.mouse.down()
  await page.mouse.move(from.x + 40, from.y + 20, { steps: 6 })
  await page.mouse.up()
  const after = Object.fromEntries((await boxes()).map((b) => [b.label, b]))
  for (const name of ['Interviews', 'Survey']) assert.ok(Math.abs(after[name].x - before[name].x - 40) < 2 && Math.abs(after[name].y - before[name].y - 20) < 2, name)
  assert.equal(after.API.x, before.API.x, 'unselected topics stay put')
  assert.match(await page.locator('.dmind-inspector').innerText(), /2 topics selected/, 'dragging a group keeps it selected')
  await page.getByRole('button', { name: 'Accent Red' }).click()
  for (const name of ['Interviews', 'Survey'])
    assert.equal(await topic(name).locator('rect').first().evaluate((r) => getComputedStyle(r).stroke), 'rgb(220, 38, 38)', name)
  await page.getByRole('button', { name: 'Star', exact: true }).click()
  assert.ok((await topic('Interviews, Star').count()) + (await page.locator('[data-node][aria-label*="Star"]').count()) >= 2)
  await page.getByRole('button', { name: 'Star', exact: true }).click()
  assert.equal(await page.locator('[data-node][aria-label*="Star"]').count(), 0, 'toggling again clears the marker for the whole selection')
  const count = (await boxes()).length
  await page.keyboard.press('Delete')
  assert.equal((await boxes()).length, count - 2)
  await button(page, 'Undo').click()
  assert.equal((await boxes()).length, count)
  await topic('Plan').focus()
  await page.keyboard.press('Control+a')
  const total = (await boxes()).length
  await page.getByText(new RegExp(`${total} topics selected`)).waitFor()
  await page.keyboard.press('Escape')
  await topic('Plan').click()
})

await step('structure: move under, Alt-drag and cycle protection', async () => {
  await topic('Budget').click()
  await page.getByLabel('Move under').selectOption({ label: 'Research' })
  assert.equal(await levelOf('Budget'), '4') // Project > Plan > Research > Budget
  await topic('Research').click()
  const options = await page.getByLabel('Move under').locator('option').allTextContents()
  for (const forbidden of ['Research', 'Interviews', 'Survey', 'Budget'])
    assert.ok(!options.includes(forbidden), `${forbidden} cannot be a parent of Research`)
  assert.ok(options.includes('Risks'))
  assert.equal(await levelOf('Docs'), '4')
  await page.getByLabel('Canvas zoom').fill('0.6') // both topics in view; dragging scales with zoom
  const docs = await centre('Docs'), api = await centre('API')
  await page.keyboard.down('Alt')
  await page.mouse.move(docs.x, docs.y)
  await page.mouse.down()
  await page.mouse.move(api.x, api.y, { steps: 8 })
  await page.mouse.up()
  await page.keyboard.up('Alt')
  await page.getByText(/Moved under API/).waitFor()
  assert.equal(await levelOf('Docs'), '5')
  await button(page, 'Undo').click()
  assert.equal(await levelOf('Docs'), '4')
  await page.getByLabel('Canvas zoom').fill('1')
})

await step('context menu: right-click and keyboard, with focus returned', async () => {
  const before = (await boxes()).length
  await topic('Docs').click({ button: 'right' })
  const menu = page.getByRole('menu', { name: 'Topic menu' })
  await menu.waitFor()
  assert.equal(await page.evaluate(() => document.activeElement?.textContent), 'Add child')
  await page.keyboard.press('ArrowDown')
  assert.equal(await page.evaluate(() => document.activeElement?.textContent), 'Add sibling')
  await page.keyboard.press('Enter')
  assert.equal(await menu.count(), 0)
  assert.equal((await boxes()).length, before + 1)
  await button(page, 'Undo').click()
  await topic('Docs').focus()
  await page.keyboard.press('Shift+F10')
  await menu.waitFor()
  await page.keyboard.press('Escape')
  await menu.waitFor({ state: 'detached' })
  await poll(async () => (await page.evaluate(() => document.activeElement?.getAttribute('aria-label'))) === 'Docs', 'focus back on the topic')
})

await step('appearance: markers, accents and links are safe and portable', async () => {
  await topic('Announce').click()
  const link = page.locator('.dmind-inspector').getByLabel('Link', { exact: true })
  for (const bad of ['javascript:alert(1)', 'data:text/html,<b>x', 'https://user:pw@example.org/', 'https://exa mple.org/', 'ftp://example.org/']) {
    await link.fill(bad)
    await link.press('Enter')
    await page.locator('.dmind-inspector').getByRole('alert').filter({ hasText: /Only http and https/ }).waitFor()
    assert.equal(await page.getByRole('link', { name: /Open link/ }).count(), 0, bad)
  }
  await link.fill('https://example.org/spec')
  await link.press('Enter')
  const open = page.getByRole('link', { name: /Open link/ })
  assert.equal(await open.getAttribute('href'), 'https://example.org/spec')
  assert.match(await open.getAttribute('rel'), /noopener/)
  assert.equal(await open.getAttribute('target'), '_blank')
  await page.getByRole('button', { name: 'Warning', exact: true }).click()
  await page.locator('[data-node][aria-label="Announce, Warning, has a link"]').waitFor()
  assert.match((await topic('Announce, Warning, has a link').textContent()) || '', /⚠ ↗/)
  const md = (await exportAs(page, 'md')).text
  assert.ok(md.includes('Announce') && md.includes('[Warning] <https://example.org/spec>'), md)
  const svg = (await exportAs(page, 'svg')).text
  assert.ok(svg.includes('⚠') && svg.includes('↗') && !svg.includes('javascript:'))
  const saved = JSON.parse((await exportAs(page, 'json')).text)
  const node = saved.nodes.find((n) => n.label === 'Announce')
  assert.deepEqual([node.metadata.markers, node.metadata.link], [['warning'], 'https://example.org/spec'])
})

await step('outline: edits stay in sync, typing is one undo step, structure is keyboard-editable', async () => {
  const input = (name) => page.locator('input[data-outline]').evaluateAll((els, n) => els.findIndex((e) => e.value === n), name)
  const row = async (name) => page.locator('input[data-outline]').nth(await input(name))
  const survey = await row('Survey')
  await survey.fill('Survey v2')
  await survey.press('End')
  await survey.pressSequentially('abc', { delay: 25 })
  await topic('Survey v2abc').waitFor()
  await button(page, 'Undo').click()
  await topic('Survey').waitFor() // one undo undoes the whole burst of typing
  await button(page, 'Redo').click()
  await topic('Survey v2abc').waitFor()
  const r = await row('Survey v2abc')
  assert.equal(await levelOf('Survey v2abc'), '4', 'start level')
  await r.focus()
  await page.keyboard.press('Alt+ArrowRight') // under the previous sibling, Interviews
  assert.equal(await levelOf('Survey v2abc'), '5', 'after indent')
  await page.keyboard.press('Alt+ArrowLeft')
  assert.equal(await levelOf('Survey v2abc'), '4', 'after outdent')
  await page.keyboard.press('Alt+ArrowUp')
  const order = await page.locator('input[data-outline]').evaluateAll((els) => els.map((e) => e.value))
  assert.ok(order.indexOf('Survey v2abc') < order.indexOf('Interviews'), 'moved above its sibling')
  const count = (await boxes()).length
  await page.keyboard.press('Enter') // a sibling below, focused for typing
  await poll(async () => (await page.evaluate(() => document.activeElement?.value)) === 'New idea', 'the new row to take focus')
  await page.keyboard.type('Fresh topic')
  await topic('Fresh topic').waitFor()
  assert.equal((await boxes()).length, count + 1)
  assert.equal(await levelOf('Fresh topic'), '4', 'new sibling level')
  const rows = await page.locator('input[data-outline]').evaluateAll((els) => els.map((e) => e.value))
  assert.equal(rows[rows.indexOf('Survey v2abc') + 1], 'Fresh topic', 'directly below the topic it was added from')
  await page.keyboard.press('ArrowUp')
  assert.equal(await page.evaluate(() => document.activeElement?.value), 'Survey v2abc')
})

await step('keyboard: arrows navigate, Alt+arrows nudge, F2 renames, minus and plus fold', async () => {
  await topic('Plan').focus()
  await page.keyboard.press('ArrowRight')
  await poll(async () => (await page.evaluate(() => document.activeElement?.getAttribute('aria-label'))) !== 'Plan', 'focus to move to a neighbouring topic')
  assert.equal(await page.evaluate(() => document.activeElement?.getAttribute('aria-pressed')), 'true')
  await topic('Build').focus()
  const before = (await boxes()).find((b) => b.label === 'Build')
  await page.keyboard.press('Alt+ArrowRight')
  await page.keyboard.press('Shift+Alt+ArrowDown')
  const after = (await boxes()).find((b) => b.label === 'Build')
  assert.deepEqual([after.x - before.x, after.y - before.y], [10, 50])
  const total = (await boxes()).length
  await page.keyboard.press('-')
  assert.equal((await boxes()).length, total - 2, 'Build hides API and UI')
  await page.locator('[data-node][aria-label="Build, collapsed"]').focus()
  await page.keyboard.press('+')
  assert.equal((await boxes()).length, total)
  await topic('Build').focus()
  await page.keyboard.press('F2')
  assert.equal(await page.evaluate(() => document.activeElement?.closest('.dmind-inspector') !== null), true)
})

await step('layout engine: a 420-level chain opens (it used to fail validation)', async () => {
  const chain = Array.from({ length: 420 }, (_, i) => '\t'.repeat(i + 1) + 'L' + i).join('\n')
  await wizard(page, { topic: 'Deep chain', outline: chain })
  await page.locator('.dmind-preview').waitFor()
  await useDiagram(page)
  assert.equal((await boxes()).length, 421)
  const bs = await boxes()
  assert.ok(bs.every((b) => Math.abs(b.x) <= 100000 && Math.abs(b.y) <= 100000))
})

await step('layout: usable at phone width without horizontal page scroll', async () => {
  const phone = watch(await (await browser.newContext({ viewport: { width: 390, height: 800 }, storageState: await ctx.storageState() })).newPage())
  await phone.goto(base + '/#/diagrams', { waitUntil: 'networkidle' })
  await dismissOnboarding(phone)
  await phone.getByRole('heading', { name: 'Turn ideas into diagrams' }).waitFor()
  await wizard(phone, { topic: 'Phone map', outline: 'A\n  B\nC' })
  await useDiagram(phone)
  const overflow = await phone.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  assert.ok(overflow <= 1, 'horizontal overflow of ' + overflow + 'px')
  await phone.screenshot({ path: process.env.DMIND_E2E_SHOT_DIR ? process.env.DMIND_E2E_SHOT_DIR + '/phone.png' : undefined })
  await phone.close()
})

if (process.env.AXE_CORE_PATH)
  await step('accessibility: axe finds no serious or critical violation in the editor', async () => {
    await page.addScriptTag({ content: fs.readFileSync(process.env.AXE_CORE_PATH, 'utf8') })
    const found = await page.evaluate(async () => {
      const r = await window.axe.run(document.querySelector('.dmind'), { runOnly: ['wcag2a', 'wcag2aa', 'wcag22aa'] })
      return r.violations.filter((v) => ['serious', 'critical'].includes(v.impact)).map((v) => `${v.id}: ${v.nodes.length} node(s)`)
    })
    assert.deepEqual(found, [])
  })

if (process.env.DMIND_E2E_PERF === '1')
  await step('performance: informational timings (headless Chromium, this machine)', async () => {
    page.setDefaultTimeout(30000)
    for (const size of [100, 500, 1000]) {
      const lines = Array.from({ length: size - 1 }, (_, i) => (i % 7 === 0 ? '' : '  ') + 'Topic ' + i).join('\n')
      await button(page, 'New diagram').click()
      await page.getByLabel('Topic', { exact: true }).fill('Perf ' + size)
      await page.getByLabel('Brainstorm or outline').fill(lines)
      await button(page, 'Next: structure').click()
      await button(page, 'Generate preview').click()
      await button(page, 'Use this diagram').waitFor()
      const t0 = Date.now()
      await button(page, 'Use this diagram').click()
      await nodes(page).first().waitFor()
      const open = Date.now() - t0
      await nodes(page).first().click()
      const edits = []
      for (let i = 0; i < 20; i++)
        edits.push(
          await page.evaluate(async () => {
            const el = document.querySelector('.dmind-inspector input')
            const t = performance.now()
            Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, el.value + 'x')
            el.dispatchEvent(new Event('input', { bubbles: true }))
            await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))
            return performance.now() - t
          }),
        )
      edits.sort((a, b) => a - b)
      const box = await nodes(page).first().boundingBox()
      await page.mouse.move(box.x + 20, box.y + 20)
      await page.mouse.down()
      const t1 = Date.now()
      for (let i = 0; i < 30; i++) await page.mouse.move(box.x + 20 + i * 3, box.y + 20 + i * 2)
      const drag = (Date.now() - t1) / 30
      await page.mouse.up()
      console.log(`  perf ${size} nodes: open ${open} ms, edit p50 ${edits[10].toFixed(0)} ms / p95 ${edits[18].toFixed(0)} ms, drag ${drag.toFixed(0)} ms per move (includes automation round-trip)`)
    }
  })

await step('refine: solver checks are shown; a patch for another state or a malformed one is refused', async () => {
  await wizard(page, { topic: 'Refine', outline: 'A\n  B\nC' })
  await page.locator('.dmind-preview').waitFor()
  await useDiagram(page)
  await page.locator('.dmind-refine > summary').click()
  await page.getByLabel('Patch proposal').first().waitFor()
  const box = page.locator('textarea[aria-label="Patch proposal"]')
  const review = page.getByRole('button', { name: 'Review changes' })
  const stale = { schema: 'dmind-patch/v1', base: { id: 'someone-else', hash: '0'.repeat(64) }, origin: 'model', summary: 's', ops: [{ op: 'set_title', title: 'X' }] }
  await box.fill(JSON.stringify(stale))
  await review.click()
  assert.match(await page.getByRole('alert').last().innerText(), /changed after this proposal/)
  await box.fill(JSON.stringify({ ...stale, ops: [{ op: 'drop_table' }] }))
  await review.click()
  assert.match(await page.getByRole('alert').last().innerText(), /unknown operation/)
  await box.fill('not json')
  await review.click()
  await page.getByRole('alert').last().waitFor()
  assert.equal(await page.getByRole('button', { name: 'Apply', exact: true }).count(), 0)
})

await step('import-only adapters: OPML opens as a preview and reports what was not carried over; old XMind is refused clearly', async () => {
  const file = page.getByLabel('Import source or diagram')
  await button(page, 'New diagram').click()
  const opml = '<opml version="2.0"><head><title>From OPML</title></head><body><outline text="Root" type="rss"><outline text="Child one"/><outline text="Child two"/></outline></body></opml>'
  await file.setInputFiles({ name: 'plan.opml', mimeType: 'text/x-opml', buffer: Buffer.from(opml) })
  await page.locator('.dmind-preview').waitFor()
  assert.equal(await page.locator('.dmind-preview li').count(), 3)
  await page.getByText(/Not carried over: attribute type \(1\)/).waitFor()
  await button(page, 'New diagram').click()
  await file.setInputFiles({ name: 'old.xmind', mimeType: 'application/octet-stream', buffer: Buffer.from('not a zip') })
  await page.getByText(/XMind|ZIP|archive/i).first().waitFor()
})

await step('no uncaught script errors during the whole run', async () => {
  assert.deepEqual(pageErrors, [])
})

await browser.close()
const failed = results.filter((r) => !r.ok)
console.log(`\ndmind E2E: ${results.length - failed.length}/${results.length} passed (${dialogs.length} confirm dialog(s) auto-accepted)`)
process.exit(failed.length ? 1 : 0)
