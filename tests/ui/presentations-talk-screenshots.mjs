/**
 * README screenshots for timed speaker scripts, using the example deck in
 * docs/presentations/examples/superintelligence (brand with its SVG logo, storyline with scripts).
 * Run against a gateway with DAYPILOT_PRESENTATIONS=true and the web UI built:
 *   node tests/ui/presentations-talk-screenshots.mjs http://127.0.0.1:8890
 */
import fs from 'node:fs'
import { createRequire } from 'node:module'

const base = (process.argv[2] || 'http://127.0.0.1:8890').replace(/\/$/, '')
const example = new URL('../../docs/presentations/examples/superintelligence/', import.meta.url)
const out = new URL('../../docs/assets/screenshots/presentations/', import.meta.url)
fs.mkdirSync(out, { recursive: true })
let chromium
for (const root of [process.env.PLAYWRIGHT_CORE_ROOT, import.meta.url, '/opt/node-tools/'].filter(Boolean)) {
  try { ({ chromium } = createRequire(root)('playwright-core')); break } catch { /* next */ }
}
const browser = await chromium.launch({ args: ['--no-sandbox'], executablePath: process.env.CHROMIUM_PATH || undefined })
const page = await (await browser.newContext({ viewport: { width: 1500, height: 1000 } })).newPage()
page.setDefaultTimeout(20000)
const button = (name) => page.getByRole('button', { name, exact: true })
const shot = (name, opts = {}) => page.screenshot({ path: new URL(name + '.png', out).pathname, ...opts })

await page.goto(base + '/#/presentations', { waitUntil: 'networkidle' })
if (await page.getByPlaceholder('Acme workspace').count()) {
  await page.getByPlaceholder('Acme workspace').fill('DayPilot')
  await page.getByPlaceholder('Your name').fill('Alex Rivera')
  await page.getByPlaceholder('you@company.com').fill('alex@example.test')
  await page.getByPlaceholder('Create a strong password (min 10)').fill('correct-horse-battery-9')
  await page.getByRole('button', { name: 'Create local workspace' }).click()
  await page.waitForLoadState('networkidle')
}
for (let i = 0; i < 6; i++) {
  await page.waitForTimeout(700)
  if (!(await page.locator('.dp-onb').count())) break
  for (const n of ['Set up later (limited mode)', 'Skip for now']) { const b = page.getByRole('button', { name: n }); if (await b.count()) { await b.click(); break } }
}
await page.locator('.dp-nav button', { hasText: 'Presentations' }).first().click()

// Brand with the example's SVG logo (cleaned and converted to a transparent PNG by the server).
await page.locator('.pz-empty').getByRole('button', { name: 'Set up brand' }).click()
await page.getByLabel('Company name').fill('DayPilot')
await page.getByLabel(/^Logo \(PNG/).setInputFiles({ name: 'logo.svg', mimeType: 'image/svg+xml', buffer: fs.readFileSync(new URL('logo.svg', example)) })
await page.getByLabel('Main colour hex').fill('#1B2A6B')
await page.getByLabel('Accent hex').fill('#0FA3B1')
await page.getByLabel('Text hex').fill('#16203A')
await page.getByLabel('Footer text').fill('DayPilot · Leadership briefing')
await button('Save brand').click()
await page.getByText(/Brand saved for DayPilot/).waitFor()

// The wizard's first step: talk length drives the slide count and the script.
await button('New presentation').click()
await page.getByLabel('What is it about?').fill('Superintelligence: where we are and what comes next. The evidence today, the expert outlook, and how we should prepare.')
await page.getByLabel('Audience').fill('Leadership team')
await page.getByText('5 min', { exact: true }).click()
await page.locator('.pz-panel[aria-label="New presentation"]').screenshot({ path: new URL('5-talk-length.png', out).pathname })
await button('Cancel').click()

// The example storyline (with its timed script) becomes a deck through the same API the wizard uses.
const storyline = JSON.parse(fs.readFileSync(new URL('storyline.json', example), 'utf8'))
const deckId = await page.evaluate(async (storyline) => {
  const csrf = decodeURIComponent((document.cookie.match(/(?:^|;\s*)dp_csrf=([^;]+)/) || [])[1] || '')
  const h = { 'Content-Type': 'application/json', 'X-Workspace-Id': 'default', 'X-CSRF-Token': csrf }
  const companies = await (await fetch('/v1/presentations/companies', { headers: h, credentials: 'include' })).json()
  const r = await fetch('/v1/presentations/decks', { method: 'POST', headers: h, credentials: 'include', body: JSON.stringify({ companyId: companies.items[0].id, storyline }) })
  return (await r.json()).id
}, storyline)
if (!deckId) throw new Error('deck not created')
await page.reload({ waitUntil: 'networkidle' })
await page.locator('.dp-nav button', { hasText: 'Presentations' }).first().click()
await page.locator('.pz-card', { hasText: 'Superintelligence' }).first().click()
await page.locator('.pz-state-review_ready').first().waitFor({ timeout: 120000 })
await page.locator('.pz-thumb').nth(3).click()
await page.locator('.pz-canvas img').waitFor()
await page.waitForTimeout(600)
await shot('6-review-script')

await button('Edit content').click()
await page.getByRole('status', { name: 'Talk timing' }).waitFor()
await page.locator('.pz-slide-card').nth(3).scrollIntoViewIfNeeded()
await page.evaluate(() => window.scrollBy(0, -260))
await page.waitForTimeout(300)
await shot('7-script-editor')
await button('Discard changes').click()

await button('Rehearse').click()
const dlg = page.getByRole('dialog', { name: 'Rehearse the talk' })
await dlg.locator('img').waitFor()
await page.keyboard.press('ArrowRight')
await page.keyboard.press('ArrowRight')
await page.keyboard.press('ArrowRight')
await dlg.locator('img').waitFor()
await page.waitForTimeout(3200)
await shot('8-rehearse')
await browser.close()
console.log('talk screenshots written')
