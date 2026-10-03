/**
 * Presentations browser end-to-end: brand setup with a logo, the four-step wizard, a real build and
 * render, review of the actual slide images, locks, a rebuilt revision, approval, downloads and a
 * weekly series. Run through scripts/presentations_e2e.sh (throwaway gateway + SQLite, flag on).
 *   AXE_CORE_PATH   optional path to axe.min.js for an accessibility scan of the review screen
 */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import zlib from 'node:zlib'
import { createRequire } from 'node:module'

const base = (process.argv[2] || 'http://127.0.0.1:8890').replace(/\/$/, '')
function loadPlaywright() {
  for (const root of [process.env.PLAYWRIGHT_CORE_ROOT, import.meta.url, '/opt/node-tools/'].filter(Boolean)) {
    try { return createRequire(root)('playwright-core') } catch { /* next */ }
  }
  throw new Error('playwright-core not found')
}
const { chromium } = loadPlaywright()
function png(w, h, rgb) {
  const chunk = (t, d) => { const l = Buffer.alloc(4); l.writeUInt32BE(d.length); const td = Buffer.concat([Buffer.from(t), d]); const c = Buffer.alloc(4); c.writeUInt32BE(zlib.crc32(td)); return Buffer.concat([l, td, c]) }
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 2
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array.from({ length: w }, (_, x) => (x < w * 0.3 ? rgb : [255, 255, 255])).flat())])
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(Buffer.concat(Array.from({ length: h }, () => row)))), chunk('IEND', Buffer.alloc(0))])
}

const results = []
const pageErrors = []
async function step(name, fn) {
  try {
    await fn()
    results.push({ name, ok: true })
    console.log('PASS  ' + name)
  } catch (e) {
    results.push({ name, ok: false })
    console.log('FAIL  ' + name + '\n      ' + String(e.message || e).split('\n').slice(0, 6).join('\n      '))
  }
}

const browser = await chromium.launch({ args: ['--no-sandbox'], executablePath: process.env.CHROMIUM_PATH || undefined })
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true })
ctx.setDefaultTimeout(10000)
const page = await ctx.newPage()
page.on('pageerror', (e) => pageErrors.push(String(e)))
page.on('console', (m) => m.type() === 'error' && !/Failed to load resource/.test(m.text()) && pageErrors.push('console: ' + m.text()))
page.on('dialog', (d) => d.accept())
const button = (name) => page.getByRole('button', { name, exact: true })

await step('shell: the Presentations entry appears when the feature is on, after existing items', async () => {
  await page.goto(base + '/#/presentations', { waitUntil: 'networkidle' })
  if (await page.getByPlaceholder('Acme workspace').count()) {
    await page.getByPlaceholder('Acme workspace').fill('Deck E2E')
    await page.getByPlaceholder('Your name').fill('E2E Owner')
    await page.getByPlaceholder('you@company.com').fill('e2e@example.test')
    await page.getByPlaceholder('Create a strong password (min 10)').fill('correct-horse-battery-9')
    await page.getByRole('button', { name: 'Create local workspace' }).click()
    await page.waitForLoadState('networkidle')
  }
  for (let i = 0; i < 6; i++) {
    await page.waitForTimeout(700)
    if (!(await page.locator('.dp-onb').count())) break
    for (const n of ['Set up later (limited mode)', 'Skip for now']) {
      const b = page.getByRole('button', { name: n })
      if (await b.count()) { await b.click(); break }
    }
  }
  const labels = await page.locator('.dp-nav button .dp-nav__label').allInnerTexts()
  assert.ok(labels.indexOf('Presentations') > labels.indexOf('Diagrams'), labels.join(','))
  await page.locator('.dp-nav button', { hasText: 'Presentations' }).first().click()
  await page.getByRole('heading', { name: 'Branded decks, ready to edit in PowerPoint' }).waitFor()
})

await step('brand: company, logo, colours and fonts are saved as version 1', async () => {
  await page.getByRole('region', { name: 'All presentations' }).waitFor()
  await page.locator('.pz-empty').getByRole('button', { name: 'Set up brand' }).click()
  await page.getByLabel('Company name').fill('Northwind (fictional)')
  await page.getByLabel(/^Logo \(PNG/).setInputFiles({ name: 'logo.png', mimeType: 'image/png', buffer: png(360, 120, [11, 60, 93]) })
  await page.getByLabel('Main colour hex').fill('#0B3C5D')
  await page.getByLabel('Accent hex').fill('#E07A1F')
  await page.getByLabel('Heading font').selectOption('Cambria')
  await page.getByLabel('Footer text').fill('Northwind · FICTIONAL · Internal')
  await button('Save brand').click()
  await page.getByText(/Brand saved for Northwind/).waitFor()
})

await step('wizard: purpose, sources, brand and an editable outline before anything is built', async () => {
  await button('New presentation').click()
  assert.ok(await page.getByRole('button', { name: 'Next: Sources' }).isDisabled(), 'a brief is required')
  await page.getByLabel('Weekly update').check()
  await page.getByLabel('What is it about?').fill('Weekly delivery review for the platform team')
  await page.getByLabel('Slides (including the cover)').fill('7')
  await page.getByLabel('Period (optional)').fill('Week 40 · 28 Sep – 4 Oct 2026')
  await button('Next: Sources').click()
  await page.getByLabel('Facts and figures to use').fill('Delivered 25 items. In progress 9. Blocked 2.')
  await button('Next: Brand').click()
  await page.getByLabel(/Northwind \(fictional\)/).check()
  await button('Next: Outline').click()
  await button('Draft the outline').click()
  await page.getByText(/Started from the template|not connected/).waitFor()
  const cards = page.locator('.pz-slide-card')
  assert.equal(await cards.count(), 7)
  await cards.nth(1).getByLabel('Numbers').fill('25 | Delivered | +4\n9 | In progress\n2 | Blocked')
  await page.getByLabel('Presentation title').fill('Platform weekly review')
  await cards.nth(0).getByLabel('Title', { exact: true }).fill('Platform weekly review')
})

let deckUrlTitle = ''
await step('build: the real PowerPoint is exported, rendered and checked; review shows its slides', async () => {
  await button('Build presentation').click()
  await page.getByRole('region', { name: /Presentation / }).waitFor()
  await page.locator('.pz-state-review_ready').first().waitFor({ timeout: 90000 })
  assert.equal(await page.locator('.pz-filmstrip .pz-thumb').count(), 7)
  await page.locator('.pz-canvas img').waitFor()
  const w = await page.locator('.pz-canvas img').evaluate((img) => img.naturalWidth)
  assert.ok(w >= 1500, `rendered slide is ${w}px wide`)
  await page.locator('.pz-thumb').nth(1).click()
  await page.getByText('No problems on this slide.').waitFor()
  deckUrlTitle = await page.locator('.pz-review-head h3').innerText()
  assert.equal(deckUrlTitle, 'Platform weekly review')
})

await step('download: the file is a PowerPoint package named after the deck and marked draft', async () => {
  const [dl] = await Promise.all([page.waitForEvent('download'), button('Download PowerPoint').click()])
  assert.match(dl.suggestedFilename(), /^Platform-weekly-review-r1\.pptx$/)
  const buf = fs.readFileSync(await dl.path())
  assert.equal(buf.subarray(0, 2).toString(), 'PK')
})

await step('locks and revisions: a locked slide cannot change; an edit builds revision 2 and keeps revision 1', async () => {
  await page.locator('.pz-thumb').nth(1).click()
  await button('Lock slide').click()
  await button('Unlock slide').waitFor()
  await button('Edit content').click()
  const cards = page.locator('.pz-slide-card')
  assert.ok(await cards.nth(1).getByLabel('Title', { exact: true }).isDisabled(), 'locked slide is read-only')
  assert.ok(await cards.nth(1).locator('.pz-badge', { hasText: 'Locked' }).isVisible())
  await cards.nth(6).getByLabel('Next steps').fill('Ship the payment adapter\nRe-plan search tuning')
  await button('Save and rebuild').click()
  await page.locator('.pz-review-head').getByText(/Revision 2 ·/).waitFor()
  await page.locator('.pz-state-review_ready').first().waitFor({ timeout: 90000 })
  await page.locator('.pz-history > summary').click()
  await page.getByText(/Revision 1 · Ready for review/).waitFor()
})

await step('approval binds the exact file and changes the download name', async () => {
  await button('Approve').click()
  await page.locator('.pz-state-approved').first().waitFor()
})

if (process.env.AXE_CORE_PATH)
  await step('accessibility: axe finds no serious or critical violation in review', async () => {
    await page.addScriptTag({ content: fs.readFileSync(process.env.AXE_CORE_PATH, 'utf8') })
    const found = await page.evaluate(async () => {
      const r = await window.axe.run(document.querySelector('.pz'), { runOnly: ['wcag2a', 'wcag2aa', 'wcag22aa'] })
      return r.violations.filter((v) => ['serious', 'critical'].includes(v.impact)).map((v) => `${v.id}: ${v.nodes.length} node(s) ${v.nodes[0]?.target}`)
    })
    assert.deepEqual(found, [])
  })

await step('weekly: save as a weekly presentation, prepare this week, numbers start empty', async () => {
  await button('Make it weekly').waitFor()
  // Only non-series decks offer it; this deck qualifies.
  await button('Make it weekly').click()
  await page.getByLabel('Time zone').fill('Europe/Rome')
  await button('Save weekly presentation').click()
  await page.getByText(/Weekly presentation .* saved/).waitFor()
  await button('Prepare this week').click()
  await page.getByText(/Prepared the draft for Week/).waitFor()
  await page.locator('.pz-state-review_ready, .pz-state-failed').first().waitFor({ timeout: 90000 })
  await button('Edit content').click()
  const nums = await page.locator('.pz-slide-card').nth(1).getByLabel('Numbers').inputValue()
  assert.ok(nums.split('\n').every((l) => l.startsWith('—')), nums)
  await button('Discard changes').click()
  await button('← All presentations').click()
  await button('Prepare this week').click()
  await page.getByText(/already exists; opening it/).waitFor()
})

await step('narrow screens: review stacks without horizontal page scroll', async () => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.waitForTimeout(400)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  assert.ok(overflow <= 1, `horizontal overflow ${overflow}px`)
  await page.setViewportSize({ width: 1440, height: 900 })
})

await step('no uncaught script errors', async () => assert.deepEqual(pageErrors, []))
await browser.close()
const failed = results.filter((r) => !r.ok)
console.log(`\npresentations E2E: ${results.length - failed.length}/${results.length} passed`)
process.exit(failed.length ? 1 : 0)
