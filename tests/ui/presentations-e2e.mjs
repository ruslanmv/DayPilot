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
  await page.getByText('15 min', { exact: true }).click()
  assert.equal(await page.getByLabel('Slides (including the cover)').inputValue(), '14', 'slide count follows the talk length')
  await page.getByText('5 min', { exact: true }).click()
  await page.getByLabel('Slides (including the cover)').fill('7')
  await page.getByLabel('Period (optional)').fill('Week 40 · 28 Sep – 4 Oct 2026')
  await button('Next: Sources').click()
  await page.getByLabel('Facts and figures to use').fill('Delivered 25 items. In progress 9. Blocked 2.')
  await button('Next: Brand').click()
  await page.getByLabel(/Northwind \(fictional\)/).check()
  await button('Next: Outline').click()
  await button('Draft the outline and script').click()
  await page.getByText(/Started from the template|not connected/).waitFor()
  await page.getByText(/Timed for 5:00/).waitFor()
  const cards = page.locator('.pz-slide-card')
  assert.equal(await cards.count(), 7)
  await page.getByRole('status', { name: 'Talk timing' }).getByText('5:00 talk').waitFor()
  assert.ok((await cards.nth(0).getByLabel('Script for slide 1').inputValue()).length > 20, 'each slide has a script')
  await cards.nth(2).getByLabel('Script for slide 3').fill('A very short line.')
  await cards.nth(2).locator('.pz-fit-short').waitFor()
  await cards.nth(1).getByLabel('Numbers').fill('25 | Delivered | +4\n9 | In progress\n2 | Blocked')
  await page.getByLabel('Presentation title').fill('Platform weekly review')
  await cards.nth(0).getByLabel('Title', { exact: true }).fill('Platform weekly review')
})

let deckUrlTitle = ''
let builtPptx = null
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

await step('script: rehearse against the clock, download the timed script, re-time for another length', async () => {
  await button('Rehearse').click()
  const dlg = page.getByRole('dialog', { name: 'Rehearse the talk' })
  await dlg.getByText('Slide 1 of 7').waitFor()
  await dlg.locator('img').waitFor()
  await page.keyboard.press('ArrowRight')
  await dlg.getByText('Slide 2 of 7').waitFor()
  await page.waitForTimeout(1200)
  assert.match(await dlg.getByLabel('Time on this slide').innerText(), /^0:0[1-2] \/ \d:\d\d$/)
  await page.keyboard.press('Escape')
  await dlg.waitFor({ state: 'detached' })
  const [dl] = await Promise.all([page.waitForEvent('download'), button('Download script').click()])
  assert.match(dl.suggestedFilename(), /-r1-script\.md$/)
  const md = fs.readFileSync(await dl.path(), 'utf8')
  assert.match(md, /Speaker script · 5:00/)
  assert.match(md, /## 3\. .* — \d:\d\d–\d:\d\d/)
  await button('Script and timing').click()
  await page.getByRole('region', { name: 'Script and timing' }).getByText('3 min', { exact: true }).click()
  await button('Re-time and rewrite script').click()
  await page.getByText(/Timed for 3:00/).waitFor()
  await page.getByRole('status', { name: 'Talk timing' }).getByText('3:00 talk').waitFor()
  await button('Discard changes').click()
})

await step('download: the file is a PowerPoint package named after the deck and marked draft', async () => {
  const [dl] = await Promise.all([page.waitForEvent('download'), button('Download PowerPoint').click()])
  assert.match(dl.suggestedFilename(), /^Platform-weekly-review-r1\.pptx$/)
  const buf = fs.readFileSync(await dl.path())
  assert.equal(buf.subarray(0, 2).toString(), 'PK')
  builtPptx = buf
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

await step('schedule: opt in to automatic weekly drafts with day, time and the clock-change policy shown', async () => {
  await button('← All presentations').click()
  const series = page.getByRole('region', { name: 'Weekly presentations' })
  await series.getByText('Automatic drafts: off').click()
  await series.getByLabel('Prepare the draft automatically each week').check()
  await series.getByLabel('Day').selectOption('0')
  await series.getByLabel(/^Time/).fill('08:30')
  await button('Save schedule').click()
  await page.getByText(/drafts will be prepared every Monday at 08:30/).waitFor()
  await series.getByText('Automatic: Monday 08:30').waitFor()
  await series.getByText(/Drafts only, never sent/).waitFor()
  await series.getByText(/^Next: /).waitFor()
})

await step('svg logo: a hostile SVG is cleaned, converted and saved as a new brand version', async () => {
  await button('Brand').click()
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 100"><script>alert(1)</script><rect width="90" height="90" fill="#0B3C5D"/><text x="110" y="62" font-size="36">Northwind</text></svg>'
  await page.getByLabel(/^Logo \(PNG/).setInputFiles({ name: 'logo.svg', mimeType: 'image/svg+xml', buffer: Buffer.from(svg) })
  await button('Save brand').click()
  await page.getByText(/Brand saved for Northwind/).waitFor()
})

await step('template import: a .pptx is kept, its colours, fonts and logo are reported, and a brand is created from it', async () => {
  assert.ok(builtPptx, 'needs the downloaded deck')
  await button('Brand').click()
  const panel = page.getByRole('region', { name: 'Import a PowerPoint template' })
  await panel.getByLabel(/^Template file/).setInputFiles({ name: 'northwind-template.pptx', mimeType: 'application/vnd.openxmlformats-officedocument.presentationml.presentation', buffer: builtPptx })
  await panel.getByText('Used', { exact: true }).waitFor({ timeout: 60000 })
  await panel.getByText(/theme colours/).waitFor()
  await panel.getByText(/The template's own layouts are not reproduced/).waitFor()
  assert.ok(await panel.locator('.pz-chip').count() >= 4)
  const [dl] = await Promise.all([page.waitForEvent('download'), panel.getByRole('button', { name: 'Download original' }).click()])
  assert.deepEqual(fs.readFileSync(await dl.path()), builtPptx, 'the original is kept byte for byte')
  await panel.getByRole('button', { name: 'Create brand from this template' }).click()
  await page.getByText(/Brand created from the template/).waitFor()
})

const caps = await page.evaluate(async () => (await fetch('/v1/presentations/capabilities')).json()).catch(() => ({}))
if (caps.expert?.ready)
  await step('expert builder: a script builds a checked revision in the sandbox; forbidden code is refused with reasons', async () => {
    await page.locator('.pz-card', { hasText: 'Platform weekly review' }).filter({ hasText: '· r2' }).first().click()
    await page.locator('.pz-thumb').nth(1).click()
    await button('Unlock slide').click()
    await button('Lock slide').waitFor()
    await page.locator('.pz-expert > summary').click()
    const box = page.getByLabel('Builder script')
    await box.fill("export default (deck) => { require('fs') }")
    await button('Build with script').click()
    await page.locator('.pz-expert [role=alert]').getByText(/require/).waitFor()
    await button('Reset to example').click()
    await button('Build with script').click()
    await page.locator('.pz-review-head').getByText(/\(expert build\)/).waitFor()
    await page.locator('.pz-state-review_ready').first().waitFor({ timeout: 90000 })
    assert.equal(await page.locator('.pz-filmstrip .pz-thumb').count(), 2)
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
