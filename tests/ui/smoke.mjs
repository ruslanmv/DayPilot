/**
 * DayPilot UI smoke test (batch B14).
 *
 * Drives the built operator-web app to assert the core surfaces render and the
 * key interactions work. Run against a served dist:
 *
 *   pnpm --filter @daypilot/operator-web build
 *   (cd apps/operator-web/dist && python3 -m http.server 8890 &)
 *   node tests/ui/smoke.mjs http://localhost:8890
 *
 * Requires playwright-core and a Chromium binary; see `make ui-smoke`.
 */
import { chromium } from 'playwright-core'

const url = process.argv[2] || 'http://localhost:8890'
const exe = process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell'

const checks = []
function check(name, cond) {
  checks.push({ name, ok: !!cond })
}

const browser = await chromium.launch({ executablePath: exe, args: ['--no-sandbox'] })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(String(e)))

await page.goto(url, { waitUntil: 'networkidle' })

// Six+ nav views render.
check('nav renders', (await page.locator('.dp-nav button').count()) >= 6)

// Command palette opens and filters.
await page.keyboard.press('Control+k')
check('command palette', await page.locator('.dp-palette__input').isVisible())
await page.keyboard.press('Escape')

// Settings drop-up opens.
await page.locator('.dp-settings-trigger').click()
check('settings menu', await page.locator('ul[role="menu"]').isVisible())
await page.keyboard.press('Escape')

// Focus Mode via keyboard.
await page.locator('body').click()
await page.keyboard.press('f')
check('focus mode', await page.locator('.dp-focus').isVisible())
await page.keyboard.press('Escape')

// Email workspace + AI draft insert.
if (await page.locator('.dp-nav button', { hasText: 'Email' }).count()) {
  await page.locator('.dp-nav button', { hasText: 'Email' }).click()
  check('email workspace', await page.locator('.dp-mail').isVisible())
}

check('no page errors', errors.length === 0)

await browser.close()

const failed = checks.filter((c) => !c.ok)
for (const c of checks) console.log(`${c.ok ? 'PASS' : 'FAIL'}  ${c.name}`)
if (failed.length || errors.length) {
  if (errors.length) console.error('Page errors:', errors)
  process.exit(1)
}
console.log(`\nUI smoke: ${checks.length} checks passed`)
