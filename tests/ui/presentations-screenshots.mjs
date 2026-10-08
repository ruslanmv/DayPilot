/**
 * README screenshots for Presentations, captured from the real app and the real rendered deck.
 * Run through scripts/presentations_screenshots.sh.
 */
import fs from 'node:fs'
import zlib from 'node:zlib'
import { createRequire } from 'node:module'

const base = (process.argv[2] || 'http://127.0.0.1:8890').replace(/\/$/, '')
const out = new URL('../../docs/assets/screenshots/presentations/', import.meta.url)
fs.mkdirSync(out, { recursive: true })
let chromium
for (const root of [process.env.PLAYWRIGHT_CORE_ROOT, import.meta.url, '/opt/node-tools/'].filter(Boolean)) {
  try { ({ chromium } = createRequire(root)('playwright-core')); break } catch { /* next */ }
}
function logo() {
  // A fictional wordmark-like logo: a navy block and an orange dot on transparent white.
  const w = 360, h = 120
  const chunk = (t, d) => { const l = Buffer.alloc(4); l.writeUInt32BE(d.length); const td = Buffer.concat([Buffer.from(t), d]); const c = Buffer.alloc(4); c.writeUInt32BE(zlib.crc32(td)); return Buffer.concat([l, td, c]) }
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 6
  const rows = []
  for (let y = 0; y < h; y++) {
    const r = [0]
    for (let x = 0; x < w; x++) {
      const inBlock = x > 10 && x < 110 && y > 10 && y < 110
      const dx = x - 60, dy = y - 60
      const dot = dx * dx + dy * dy < 900
      const bar = x > 130 && x < 350 && ((y > 30 && y < 52) || (y > 68 && y < 90 && x < 280))
      r.push(...(dot ? [224, 122, 31, 255] : inBlock ? [11, 60, 93, 255] : bar ? [11, 60, 93, 255] : [255, 255, 255, 0]))
    }
    rows.push(Buffer.from(r))
  }
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(Buffer.concat(rows))), chunk('IEND', Buffer.alloc(0))])
}
const browser = await chromium.launch({ args: ['--no-sandbox'], executablePath: process.env.CHROMIUM_PATH || undefined })
const page = await (await browser.newContext({ viewport: { width: 1500, height: 1000 } })).newPage()
page.setDefaultTimeout(15000)
page.on('dialog', (d) => d.accept())
const button = (name) => page.getByRole('button', { name, exact: true })
const shot = (name, opts = {}) => page.screenshot({ path: new URL(name + '.png', out).pathname, ...opts })
const top = () => page.evaluate(() => { document.querySelectorAll('*').forEach((e) => { if (e.scrollTop) e.scrollTop = 0 }); window.scrollTo(0, 0) })

await page.goto(base + '/#/presentations', { waitUntil: 'networkidle' })
if (await page.getByPlaceholder('Acme workspace').count()) {
  await page.getByPlaceholder('Acme workspace').fill('Northwind')
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
await page.locator('.pz-empty').getByRole('button', { name: 'Set up brand' }).click()
await page.getByLabel('Company name').fill('Northwind Analytics (fictional)')
await page.getByLabel(/^Logo \(PNG/).setInputFiles({ name: 'logo.png', mimeType: 'image/png', buffer: logo() })
await page.getByLabel('Main colour hex').fill('#0B3C5D')
await page.getByLabel('Accent hex').fill('#E07A1F')
await page.getByLabel('Heading font').selectOption('Cambria')
await page.getByLabel('Footer text').fill('Northwind Analytics · FICTIONAL · Internal')
await page.waitForTimeout(300)
await shot('1-brand')
await button('Save brand').click()
await page.getByText(/Brand saved/).waitFor()

await button('New presentation').click()
await page.getByLabel('Weekly update').check()
await page.getByLabel('What is it about?').fill('Weekly delivery review for the platform team: what shipped, the payment API risk and the decision we need.')
await page.getByLabel('Slides (including the cover)').fill('7')
await page.getByLabel('Period (optional)').fill('Week 40 · 28 Sep – 4 Oct 2026')
await button('Next: Sources').click()
await page.getByLabel('Facts and figures to use').fill('Delivered 25 items, 9 in progress, 2 blocked. Daily: Mon 4, Tue 5, Wed 3, Thu 6, Fri 7.')
await button('Next: Brand').click()
await button('Next: Outline').click()
await button('Draft the outline').click()
await page.locator('.pz-slide-card').first().waitFor()
const cards = page.locator('.pz-slide-card')
await page.getByLabel('Presentation title').fill('Platform weekly review')
await cards.nth(0).getByLabel('Title', { exact: true }).fill('Platform weekly review')
await cards.nth(1).getByLabel('Numbers').fill('25 | Delivered | +4 vs last week\n9 | In progress\n2 | Blocked | −1 vs last week')
await cards.nth(2).getByLabel('Points').fill('Payment adapter shipped behind a flag\nSearch latency down 18% after index rebuild\nOnboarding flow live for 3 pilot customers')
await cards.nth(2).getByLabel('Takeaway (optional)').fill('The platform is ready for the October beta.')
await cards.nth(3).getByLabel('Data').fill('Mon | Tue | Wed | Thu | Fri\nDelivered | 4 | 5 | 3 | 6 | 7')
await cards.nth(3).getByLabel('Title', { exact: true }).fill('Throughput peaked on Friday')
await cards.nth(3).getByLabel('Chart title').fill('Items delivered per day')
await cards.nth(4).getByLabel('Table').fill('Risk | Impact | Owner | Next step\nPayment provider API change | High | Platform | Adapter by Wed\nTwo engineers on leave | Medium | Delivery | Defer search tuning')
await cards.nth(5).getByLabel('Recommendation').fill('Adapt to the new payment API now and move search tuning one week.')
await cards.nth(5).getByLabel('Options').fill('Adapt now (recommended)\nWait for provider v2')
await cards.nth(5).getByLabel('What you need').fill('Approve the one-week shift by Friday.')
await cards.nth(6).getByLabel('Next steps').fill('Ship the payment adapter\nRe-plan search tuning for W42\nPublish the beta invite list')
await top()
await shot('2-outline')
await button('Build presentation').click()
await page.locator('.pz-state-review_ready').first().waitFor({ timeout: 120000 })
await page.locator('.pz-canvas img').waitFor()
await page.locator('.pz-thumb').nth(3).click()
await page.waitForTimeout(800)
await top()
await shot('3-review')
// Contact sheet of the actual rendered slides.
const thumbs = page.locator('.pz-filmstrip img')
const n = await thumbs.count()
fs.mkdirSync(new URL('slides/', out), { recursive: true })
for (let i = 0; i < n; i++) {
  await page.locator('.pz-thumb').nth(i).click()
  await page.waitForTimeout(500)
  await page.locator('.pz-canvas img').screenshot({ path: new URL(`slides/slide-${i + 1}.png`, out).pathname })
}
await button('← All presentations').click()
await page.locator('.pz-card img').first().waitFor()
await top()
await shot('4-library')
await browser.close()
console.log(`screenshots written (${n} slides)`)
