/**
 * Echo Show display mode (`/echo`) — browser end-to-end.
 *
 * Drives the real operator-web build against a real gateway that requires sign-in, over a
 * workspace seeded through the API (tests/ui/echo_seed.py). It checks:
 *
 *   - `/echo` is served as its own page and starts at the shared sign-in;
 *   - every number and list on the dashboard equals what the API returns (no invented data);
 *   - an approval needs two taps and is decided by the server, which records it;
 *   - reload keeps the section and the session; offline pauses decisions and says so;
 *   - a failing endpoint shows an error with Retry, and a failed refresh keeps the last data
 *     visible and marked "Not current"; an ended session asks to sign in again;
 *   - the desktop console at `/` still loads;
 *   - a matrix of CSS viewports (1920×1080 and the sizes Silk might report) has no clipped
 *     control, no horizontal scrolling and no touch target under 44 px.
 *
 *   scripts/echo_e2e.sh                               # build, throwaway gateway + seed, run
 *   node tests/ui/echo-e2e.mjs http://127.0.0.1:8891  # against a seeded, running gateway
 *
 * Optional: ECHO_SCREENSHOTS=<dir> saves screenshots; PLAYWRIGHT_CORE_ROOT / CHROMIUM_PATH
 * locate playwright and a Chromium binary.
 *
 * This is Chromium emulation with touch input. It is not Silk on an Echo Show: the on-device
 * checklist in docs/echo-show/README.md still has to be run on the hardware.
 */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { createRequire } from 'node:module'

const base = (process.argv[2] || 'http://127.0.0.1:8891').replace(/\/$/, '')
const shots = process.env.ECHO_SCREENSHOTS || ''
const EMAIL = process.env.ECHO_EMAIL || 'alex@example.com'
const PASSWORD = process.env.ECHO_PASSWORD || 'correct-horse-42'
// The seeded day: Saturday 10 October 2026, 10:40 in Berlin.
const NOW = new Date('2026-10-10T08:40:00Z')
const TZ = 'Europe/Berlin'

function loadPlaywright() {
  const roots = [process.env.PLAYWRIGHT_CORE_ROOT, import.meta.url, '/opt/node-tools/', '/opt/node22/lib/node_modules/']
  for (const root of roots.filter(Boolean)) {
    for (const name of ['playwright-core', 'playwright']) {
      try {
        return createRequire(root)(name)
      } catch {
        /* try the next location */
      }
    }
  }
  throw new Error('playwright not found: install playwright-core or set PLAYWRIGHT_CORE_ROOT')
}
const { chromium } = loadPlaywright()

let passed = 0
async function step(name, fn) {
  await fn()
  passed++
  console.log(`  ✓ ${name}`)
}
async function shot(page, name) {
  if (!shots) return
  fs.mkdirSync(shots, { recursive: true })
  await page.screenshot({ path: `${shots}/${name}.png` })
}

/** Controls that are clipped, off screen or too small; horizontal overflow anywhere. */
async function layoutProblems(page) {
  return page.evaluate(() => {
    const problems = []
    const vw = window.innerWidth
    if (document.documentElement.scrollWidth > vw + 1) problems.push(`page scrolls sideways (${document.documentElement.scrollWidth}px)`)
    const label = (el) => (el.getAttribute('aria-label') || el.textContent || el.tagName).trim().replace(/\s+/g, ' ').slice(0, 40)
    for (const el of document.querySelectorAll('.echo button, .echo input, .echo a')) {
      const r = el.getBoundingClientRect()
      if (r.width === 0 && r.height === 0) continue
      if (Math.min(r.width, r.height) < 44) problems.push(`target ${Math.round(r.width)}×${Math.round(r.height)} < 44px: ${label(el)}`)
      if (r.left < -1 || r.right > vw + 1) problems.push(`off screen: ${label(el)}`)
      // Walk out through the ancestors that clip. A scroll container that can scroll in an
      // axis can bring the control into view, so outer ancestors no longer matter for that axis.
      let reachX = true
      let reachY = true
      for (let a = el.parentElement; a && a !== document.body && (reachX || reachY); a = a.parentElement) {
        const cs = getComputedStyle(a)
        const clipsX = cs.overflowX !== 'visible' || /paint|content|strict/.test(cs.contain)
        const clipsY = cs.overflowY !== 'visible' || /paint|content|strict/.test(cs.contain)
        if (!clipsX && !clipsY) continue
        const ar = a.getBoundingClientRect()
        const canScrollY = /auto|scroll/.test(cs.overflowY) && a.scrollHeight > a.clientHeight
        const canScrollX = /auto|scroll/.test(cs.overflowX) && a.scrollWidth > a.clientWidth
        if (reachX && clipsX && !canScrollX && (r.left < ar.left - 1 || r.right > ar.right + 1)) problems.push(`clipped sideways: ${label(el)}`)
        if (reachY && clipsY && !canScrollY && (r.top < ar.top - 1 || r.bottom > ar.bottom + 1)) problems.push(`clipped: ${label(el)}`)
        if (canScrollX) reachX = false
        if (canScrollY) reachY = false
      }
    }
    for (const el of document.querySelectorAll('.echo-view, .echo-scroll, .echo-card, .echo-rail')) {
      if (el.scrollWidth > el.clientWidth + 1) problems.push(`sideways overflow in .${el.className.split(' ')[0]}`)
    }
    for (const el of document.querySelectorAll('.echo-card__title, .echo-stat__label, .echo-rail__label, .echo-btn, .echo-chip')) {
      if (el.scrollWidth > el.clientWidth + 1) problems.push(`text cut off: ${label(el)}`)
    }
    return [...new Set(problems)]
  })
}

async function newEchoPage(browser, viewport, opts = {}) {
  const ctx = await browser.newContext({
    viewport, deviceScaleFactor: opts.dpr || 1, hasTouch: true, timezoneId: TZ, locale: 'en-GB',
    storageState: opts.storageState,
  })
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.clock.setFixedTime(NOW)
  return { ctx, page, errors }
}

async function openSection(page, label) {
  await page.locator('.echo-rail__item', { hasText: label }).tap()
  await page.waitForFunction((l) => document.querySelector('.echo-rail__item.is-active')?.textContent?.includes(l), label)
  await page.waitForFunction(() => !document.querySelector('.echo-view .echo-skeleton'), null, { timeout: 15000 })
}

const api = async (ctx, path, init) => {
  const r = init ? await ctx.request.post(base + path, init) : await ctx.request.get(base + path)
  return { status: r.status(), body: r.status() === 204 ? null : await r.json() }
}

const executablePath = process.env.CHROMIUM_PATH || undefined
const browser = await chromium.launch({ executablePath, args: ['--no-sandbox'] })
console.log(`Echo display E2E against ${base}`)
try {
  const { ctx, page, errors } = await newEchoPage(browser, { width: 1920, height: 1080 })

  await step('/echo is its own page and starts at the shared sign-in', async () => {
    const res = await page.goto(base + '/echo')
    assert.equal(res.status(), 200)
    assert.equal(new URL(page.url()).pathname, '/echo')
    await page.waitForSelector('.dp-auth')
    assert.equal(await page.locator('.echo').count(), 0, 'no dashboard before sign-in')
    await shot(page, 'echo-signin-1920x1080')
  })

  await step('sign in with the touch keyboard flow', async () => {
    await page.locator('input[type=email]').tap()
    await page.keyboard.type(EMAIL)
    await page.locator('input[type=password]').tap()
    await page.keyboard.type(PASSWORD)
    await page.locator('button[type=submit]').tap()
    await page.waitForSelector('.echo-rail')
    assert.equal(await page.locator('.echo-rail__item').count(), 8, '7 sections + sign out')
    assert.match(await page.locator('.echo-header__greeting').innerText(), /^Good morning, Alex$/)
    assert.equal(await page.locator('.echo-clock').innerText(), '10:40')
  })

  const today = (await api(ctx, '/v1/today')).body
  await step('Today: tiles and Now/Next are exactly the API answer', async () => {
    await page.waitForFunction(() => document.querySelectorAll('.echo-stat__value')[0]?.textContent !== '—')
    const values = await page.locator('.echo-stat__value').allInnerTexts()
    const c = today.counts
    assert.deepEqual(values.map(Number), [c.approvals, c.blockers, c.aiRunning, c.projectsNeedAttention])
    assert.equal(await page.locator('.echo-now__title').innerText(), today.now.title)
    assert.equal(await page.locator('.echo-now__next-title').innerText(), today.next.title)
    const plan = (await api(ctx, '/v1/plans/2026-10-10')).body
    assert.equal(await page.locator('.echo-plan__item').count(), plan.blocks.length)
    assert.equal(await page.locator('.echo-rail__badge').innerText(), String(c.approvals))
    await shot(page, 'echo-today-1920x1080')
  })

  await step('Calendar: today and next days, cancelled and out-of-range events left out', async () => {
    await openSection(page, 'Calendar')
    assert.equal(new URL(page.url()).hash, '#/calendar')
    const titles = await page.locator('.echo-event__title').allInnerTexts()
    assert.ok(titles.includes('Client Alpha weekly sync'))
    assert.ok(!titles.some((t) => t.startsWith('Cancelled')), 'cancelled event shown')
    assert.ok(!titles.includes("Last quarter's offsite"), 'out-of-window event shown')
    assert.equal(await page.locator('.echo-event:has-text("Release check-in") .echo-chip--danger').innerText(), 'Overlaps')
    await shot(page, 'echo-calendar-1920x1080')
  })

  await step('Tasks: groups add up to the open tasks the API returns', async () => {
    await openSection(page, 'Tasks')
    const tasks = (await api(ctx, '/v1/tasks?limit=200')).body.items
    const open = tasks.filter((t) => t.status !== 'done')
    assert.match(await page.locator('.echo-tasks__bar').innerText(), new RegExp(`^${open.length} open tasks`))
    assert.equal(await page.locator('.echo-row--task').count(), open.length)
    const blocked = open.filter((t) => t.status === 'blocked').length
    assert.equal(blocked, today.counts.blockers, 'list and tile use the same rule')
    await shot(page, 'echo-tasks-1920x1080')
  })

  await step('Projects: every project, riskiest first', async () => {
    await openSection(page, 'Projects')
    const projects = (await api(ctx, '/v1/projects?limit=100')).body.items
    assert.equal(await page.locator('.echo-project').count(), projects.length)
    assert.equal(await page.locator('.echo-project').first().getAttribute('class'), 'echo-project is-high')
    await shot(page, 'echo-projects-1920x1080')
  })

  await step('Agents: runs as the API reports them', async () => {
    await openSection(page, 'Agents')
    const runs = (await api(ctx, '/v1/agents?limit=30')).body.items
    // The seed has fewer than ten finished runs, so every run is listed.
    assert.equal(await page.locator('.echo-row--run').count(), runs.length)
    assert.match(await page.locator('.echo-day__title').first().innerText(), new RegExp(`Running · ${today.counts.aiRunning}`))
    await shot(page, 'echo-agents-1920x1080')
  })

  await step('Assistant: availability is reported and a question gets the server reply', async () => {
    await openSection(page, 'Assistant')
    await page.waitForSelector('.echo-assistant__head .echo-chip')
    await page.locator('.echo-suggest button', { hasText: 'What needs my approval?' }).tap()
    await page.waitForSelector('.echo-msg--assistant:not(.echo-msg--busy)')
    const reply = await page.locator('.echo-msg--assistant p').first().innerText()
    assert.ok(reply.length > 0)
    await shot(page, 'echo-assistant-1920x1080')
    const open = page.locator('.echo-msg--assistant button', { hasText: 'Open Approvals' })
    if (await open.count()) {
      await open.tap()
      await page.waitForFunction(() => location.hash === '#/approvals')
    }
  })

  await step('Approvals: two taps, decided and recorded by the server', async () => {
    await openSection(page, 'Approvals')
    await shot(page, 'echo-approvals-1920x1080')
    const pending = (await api(ctx, '/v1/approvals?limit=50')).body.items.filter((a) => a.status === 'pending')
    assert.equal(await page.locator('.echo-approval').count(), pending.length)
    const target = pending.find((a) => a.risk === 'low') || pending[0]
    assert.ok(target, 'the seed leaves approvals pending')
    const card = page.locator('.echo-approval', { hasText: target.action })
    await card.locator('button', { hasText: /^Approve$/ }).tap()
    assert.equal(await card.locator('.echo-approval__confirm').innerText(), 'Approve this request?')
    let after = (await api(ctx, '/v1/approvals?limit=50')).body.items.find((a) => a.id === target.id)
    assert.equal(after.status, 'pending', 'one tap must not decide')
    await shot(page, 'echo-approvals-confirm-1920x1080')
    await card.locator('button', { hasText: 'Yes, approve' }).tap()
    await page.waitForFunction((t) => ![...document.querySelectorAll('.echo-approval__action')].some((e) => e.textContent === t), target.action)
    after = (await api(ctx, '/v1/approvals?limit=50')).body.items.find((a) => a.id === target.id)
    assert.equal(after.status, 'approved')
    await page.waitForFunction((n) => document.querySelector('.echo-rail__badge')?.textContent === String(n), pending.length - 1)
  })

  await step('reload keeps the section and the session', async () => {
    await page.reload()
    await page.waitForSelector('.echo-approval')
    assert.equal(new URL(page.url()).hash, '#/approvals')
    assert.equal(await page.locator('.dp-auth').count(), 0)
  })

  await step('/echo/?about reports the viewport for the on-device checklist', async () => {
    await page.goto(base + '/echo/?about#/approvals')
    await page.waitForSelector('.echo-banner--info')
    assert.match(await page.locator('.echo-banner--info').innerText(), /^CSS viewport 1920×1080 · pixel ratio 1 · secure true/)
    await page.goto(base + '/echo/#/approvals')
    await page.waitForSelector('.echo-approval')
    assert.equal(await page.locator('.echo-banner--info').count(), 0)
  })

  await step('offline: banner, last data kept, decisions paused; recovers when back', async () => {
    await ctx.setOffline(true)
    await page.waitForSelector('.echo-banner--warn')
    assert.match(await page.locator('.echo-banner--warn').innerText(), /Offline — showing what was loaded at \d\d:\d\d/)
    assert.ok(await page.locator('.echo-approval').count() > 0, 'data kept')
    assert.equal(await page.locator('.echo-approval button', { hasText: /^Approve$/ }).count(), 0)
    assert.ok(await page.locator('text=Decisions need a live connection.').first().isVisible())
    await shot(page, 'echo-offline-1920x1080')
    await ctx.setOffline(false)
    await page.waitForSelector('.echo-banner--warn', { state: 'detached' })
    await page.waitForSelector('.echo-approval button:has-text("Approve")')
  })

  await step('a failed refresh keeps data and marks it "Not current"', async () => {
    await openSection(page, 'Today')
    await page.route('**/v1/today*', (r) => r.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"down"}' }))
    await page.locator('button[aria-label="Refresh now"]').tap()
    await page.waitForSelector('.echo-card--now .echo-chip--warn')
    assert.equal(await page.locator('.echo-now__title').innerText(), today.now.title)
    assert.equal(await page.locator('.echo-status').innerText(), 'Reconnecting…')
    await shot(page, 'echo-stale-1920x1080')
    await page.unroute('**/v1/today*')
    await page.locator('button[aria-label="Refresh now"]').tap()
    await page.waitForSelector('.echo-card--now .echo-chip--warn', { state: 'detached' })
  })

  const storageState = await ctx.storageState()

  await step('an endpoint that fails before any data shows the error and Retry', async () => {
    const { ctx: c2, page: p2 } = await newEchoPage(browser, { width: 1920, height: 1080 }, { storageState })
    await p2.route('**/v1/projects*', (r) => r.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"boom"}' }))
    await p2.goto(base + '/echo/#/projects')
    await p2.waitForSelector('.echo-problem')
    assert.equal(await p2.locator('.echo-problem p').innerText(), 'DayPilot had a problem (HTTP 500).')
    await shot(p2, 'echo-error-1920x1080')
    await p2.unroute('**/v1/projects*')
    await p2.locator('.echo-problem button', { hasText: 'Retry' }).tap()
    await p2.waitForSelector('.echo-project')
    await c2.close()
  })

  await step('a session ended elsewhere asks to sign in again', async () => {
    // A session of its own, so ending it leaves the other contexts signed in.
    const { ctx: c3, page: p3 } = await newEchoPage(browser, { width: 1920, height: 1080 })
    const login = await c3.request.post(base + '/v1/auth/local/login', { data: { email: EMAIL, password: PASSWORD } })
    assert.equal(login.status(), 200)
    await p3.goto(base + '/echo/')
    await p3.waitForSelector('.echo-stat__value')
    const csrf = (await c3.cookies()).find((c) => c.name === 'dp_csrf')?.value || ''
    const out = await c3.request.post(base + '/v1/auth/logout', { headers: { 'X-CSRF-Token': csrf } })
    assert.equal(out.status(), 200)
    await p3.locator('button[aria-label="Refresh now"]').tap()
    await p3.waitForSelector('.echo-overlay [role=alertdialog]')
    await shot(p3, 'echo-session-ended-1920x1080')
    await p3.locator('button', { hasText: 'Sign in again' }).tap()
    await p3.waitForSelector('.dp-auth')
    await c3.close()
  })

  await step('the desktop console at / still loads', async () => {
    const { ctx: c4, page: p4, errors: e4 } = await newEchoPage(browser, { width: 1440, height: 900 }, { storageState })
    await p4.goto(base + '/')
    await p4.waitForSelector('.dp-nav, .dp-auth', { timeout: 20000 })
    assert.equal(await p4.locator('.echo').count(), 0)
    assert.deepEqual(e4, [])
    await c4.close()
  })

  // Sizes Silk could report on a 1920×1080 panel (DPR 1, 1.25, 1.5, 2), with and without its
  // toolbar, plus common smaller Echo/tablet viewports as a worst case.
  const matrix = [
    { width: 1920, height: 1080, dpr: 1 },
    { width: 1920, height: 1000, dpr: 1 },
    { width: 1536, height: 864, dpr: 1.25 },
    { width: 1366, height: 768, dpr: 1 },
    { width: 1280, height: 800, dpr: 1 },
    { width: 1280, height: 720, dpr: 1.5 },
    { width: 1024, height: 600, dpr: 1 },
    { width: 960, height: 540, dpr: 2 },
  ]
  const sections = ['Today', 'Calendar', 'Tasks', 'Projects', 'Assistant', 'Agents', 'Approvals']
  for (const v of matrix) {
    await step(`${v.width}×${v.height} @${v.dpr}x: no clipped control, no sideways scroll, targets ≥ 44px`, async () => {
      const { ctx: cv, page: pv, errors: ev } = await newEchoPage(browser, { width: v.width, height: v.height }, { dpr: v.dpr, storageState })
      await pv.goto(base + '/echo/#/today')
      await pv.waitForSelector('.echo-stat__value')
      const found = []
      for (const s of sections) {
        await openSection(pv, s)
        for (const p of await layoutProblems(pv)) found.push(`${s}: ${p}`)
        if (s === 'Today' || (v.width === 1280 && v.height === 720) || (v.width === 1024 && s === 'Approvals')) {
          await shot(pv, `echo-${s.toLowerCase()}-${v.width}x${v.height}`)
        }
      }
      assert.deepEqual(found, [])
      assert.deepEqual(ev, [])
      await cv.close()
    })
  }

  assert.deepEqual(errors, [])
  await ctx.close()
  console.log(`Echo display E2E: ${passed} checks passed`)
} finally {
  await browser.close()
}
