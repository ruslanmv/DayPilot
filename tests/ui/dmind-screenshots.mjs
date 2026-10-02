/**
 * Captures the README screenshots of the Diagrams tool against a running gateway.
 * Run through scripts/dmind_screenshots.sh (starts a throwaway gateway), or:
 *   node tests/ui/dmind-screenshots.mjs http://127.0.0.1:8890
 */
import { createRequire } from 'node:module'
import fs from 'node:fs'

const base = (process.argv[2] || 'http://127.0.0.1:8890').replace(/\/$/, '')
const out = new URL('../../docs/assets/screenshots/dmind/', import.meta.url)
fs.mkdirSync(out, { recursive: true })
let chromium
for (const root of [process.env.PLAYWRIGHT_CORE_ROOT, import.meta.url, '/opt/node-tools/'].filter(Boolean)) {
  try { ({ chromium } = createRequire(root)('playwright-core')); break } catch { /* next */ }
}
const browser = await chromium.launch({ args: ['--no-sandbox'], executablePath: process.env.CHROMIUM_PATH || undefined })
const page = await (await browser.newContext({ viewport: { width: 1500, height: 1150 } })).newPage()
page.setDefaultTimeout(10000)
page.on('dialog', (d) => d.accept())
const shot = (name, opts = {}) => page.screenshot({ path: new URL(name + '.png', out).pathname, ...opts })
const button = (name) => page.getByRole('button', { name, exact: true })

await page.goto(base + '/#/diagrams', { waitUntil: 'networkidle' })
if (await page.getByPlaceholder('Acme workspace').count()) {
  await page.getByPlaceholder('Acme workspace').fill('Acme')
  await page.getByPlaceholder('Your name').fill('Alex Rivera')
  await page.getByPlaceholder('you@company.com').fill('alex@example.test')
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
await page.locator('.dp-nav button', { hasText: 'Diagrams' }).first().click()
await page.getByRole('heading', { name: 'Turn ideas into diagrams' }).waitFor()

// 1. Start: topic and outline
await button('New diagram').click()
await page.getByLabel('Start from a template').selectOption('product-launch')
await page.waitForTimeout(300)
await shot('1-start')

// 2. Preview
await button('Next: structure').click()
await button('Generate preview').click()
await page.locator('.dmind-preview').waitFor()
await shot('2-preview')

// 3. Editor
await button('Use this diagram').click()
await page.locator('.dmind-editor').waitFor()
await page.locator('.dmind-canvas [data-node]').first().waitFor()
await page.waitForTimeout(400)
await page.evaluate(() => { document.querySelectorAll('*').forEach((e) => { if (e.scrollTop) e.scrollTop = 0 }); window.scrollTo(0, 0) })
await shot('3-editor')

// 4. Check and refine panel
await page.locator('.dmind-refine > summary').click()
await page.waitForTimeout(200)
await page.evaluate(() => { document.querySelectorAll('*').forEach((e) => { if (e.scrollTop) e.scrollTop = 0 }); window.scrollTo(0, 0) })
await shot('4-check-and-refine')
// 5. Tasks and timeline
await page.locator('.dmind-tasks > summary').click()
await button('Make tasks from leaf topics').click()
await page.getByLabel('Start date').fill('2026-03-02')
await button('Schedule').click()
await button('Show timeline').click()
await page.locator('.dmind-gantt svg').waitFor()
await page.locator('.dmind-tasks').screenshot({ path: new URL('5-tasks-timeline.png', out).pathname })

// 6. Present
await button('Present').click()
await page.keyboard.press('ArrowRight')
await page.waitForTimeout(300)
await shot('6-present')
await browser.close()
console.log('screenshots written to docs/assets/screenshots/dmind/')
