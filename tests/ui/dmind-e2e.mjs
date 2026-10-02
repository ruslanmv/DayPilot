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
import { createRequire } from 'node:module'

const base = (process.argv[2] || 'http://127.0.0.1:8890').replace(/\/$/, '')
const withDesigner = process.env.E2E_DESIGNER === '1'

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
  await page.locator('.dmind-library button', { hasText: 'Order processing v2' }).click()
  await page.getByText(/Loaded revision 2/).waitFor()
  await button(page, 'Load saved revisions').click()
  await button(page, 'Restore r1').click()
  assert.equal(await page.getByLabel('Diagram title').inputValue(), 'Order processing v1')
  assert.match(await status(page).innerText(), /Save to append a new revision/)
  await save(page).click()
  await page.getByText(/Saved revision 3/).waitFor()
  await button(page, 'Load saved revisions').click()
  for (const r of ['Restore r3', 'Restore r2', 'Restore r1']) await button(page, r).waitFor()
  savedId = (await page.evaluate(() => fetch('/v1/diagrams', { headers: { 'X-Workspace-Id': 'default' } }).then((r) => r.json()))).items[0].id
})

await step('conflict: a stale tab gets 409, keeps its draft, and can save a copy', async () => {
  const tab2 = watch(await ctx.newPage())
  await ready(tab2)
  await tab2.locator('.dmind-library button', { hasText: 'Order processing v1' }).first().click()
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
  await tab2.locator('.dmind-library button', { hasText: 'Edited in tab one' }).first().waitFor()
  await tab2.locator('.dmind-library button', { hasText: 'Edited in tab two' }).first().waitFor()
  await tab2.close()
})

await step('archive: ordinary saves keep the state; archived diagrams stay recoverable', async () => {
  await button(page, 'Archive diagram').click()
  await page.getByText(/· archived/).first().waitFor()
  await page.locator('.dmind-library button', { hasText: 'Edited in tab one' }).waitFor({ state: 'detached' })
  await page.getByLabel('Include archived').check()
  assert.equal(await page.locator('.dmind-library button', { hasText: 'Edited in tab one' }).count(), 1)
  await page.getByLabel('Diagram title').fill('Edited while archived')
  await save(page).click()
  await page.getByText(/Saved revision \d+ · archived/).waitFor()
  await button(page, 'Unarchive diagram').click()
  await page.getByText(/Saved revision \d+$/).waitFor()
  await page.getByLabel('Include archived').uncheck()
  await page.locator('.dmind-library button', { hasText: 'Edited while archived' }).waitFor()
})

await step('draft recovery: unsaved work survives a reload', async () => {
  await page.getByLabel('Diagram title').fill('Unsaved idea')
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
  assert.ok(json.name.endsWith('.json'))
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
  await page.getByText(/PDF and image extraction are planned/).waitFor()
  await file.setInputFiles({ name: 'huge.txt', mimeType: 'text/plain', buffer: Buffer.alloc(2_100_000, 97) })
  await page.getByText(/smaller than 2 MB/).waitFor()
  await file.setInputFiles({ name: 'broken.json', mimeType: 'application/json', buffer: Buffer.from('{"schema_version":"dmind/v2"}') })
  await page.getByText(/Unsupported diagram version/).waitFor()
  await file.setInputFiles({ name: 'order.dmind.json', mimeType: 'application/json', buffer: fs.readFileSync(fixture) })
  await page.locator('.dmind-preview').waitFor()
  assert.equal(await page.locator('.dmind-preview li').count(), 4)
  await useDiagram(page)
  await save(page).click()
  await page.getByText(/Saved revision 1/).waitFor()
  await page.locator('.dmind-library button', { hasText: 'Order processing system' }).first().waitFor() // saved as a copy
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

await step('no uncaught script errors during the whole run', async () => {
  assert.deepEqual(pageErrors, [])
})

await browser.close()
const failed = results.filter((r) => !r.ok)
console.log(`\ndmind E2E: ${results.length - failed.length}/${results.length} passed (${dialogs.length} confirm dialog(s) auto-accepted)`)
process.exit(failed.length ? 1 : 0)
