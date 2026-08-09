#!/usr/bin/env python3
"""Capture the Slack communication workspace from the running app.

Taken against the seeded workspace with the feature flags on, in the same pass
and at the same size as the rest of the tour. Nothing here is staged: the
"Draft ready" badges, the provenance chips and the counts are whatever the real
pipeline produced from ``seed_slack.py``.

The assistant shot deliberately shows a *proposal* rather than an applied
change — [Use this] [Insert] [Try again] is the product's central claim, and a
screenshot of an already-rewritten draft would show the opposite.
"""
import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright

BASE = os.getenv("SHOOT_BASE", "http://127.0.0.1:8099")
OUT = Path(os.getenv("SHOOT_OUT_SLACK", "docs/assets/screenshots/slack")).resolve()
CHROME = os.getenv("SHOOT_CHROME", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")

DESKTOP = {"width": 1536, "height": 1024}
PHONE = {"width": 414, "height": 896}

SETUP_DONE = (
    "try{localStorage.setItem('daypilot.setup', JSON.stringify({"
    "version:2,status:'completed',aiReady:true,"
    "completedSteps:{provider:true,profile:true,mailbox:true,knowledge:true},"
    "completedAt:new Date().toISOString()}));"
    "localStorage.setItem('daypilot.onboarded','true');"
    "localStorage.setItem('daypilot.aiReady','true');"
    "}catch(e){}"
)


async def snap(page, name: str) -> None:
    path = OUT / f"{name}.png"
    await page.screenshot(path=str(path), full_page=False)
    print(f"shot: {path.name}")


async def open_slack(page) -> None:
    """Land on the Slack workspace from a clean reload.

    A plain `goto` to the same hash is a same-document navigation, so React
    keeps whatever modal was open to swallow the next click.
    """
    await page.goto(f"{BASE}/#/slack")
    await page.reload(wait_until="networkidle")
    await page.wait_for_selector(".dp-slack", timeout=10000)
    await page.wait_for_timeout(900)


async def desktop(page) -> None:
    await open_slack(page)
    await snap(page, "slack-workspace")

    # The first conversation is the one with a prepared reply — click it the way
    # a user does rather than deep-linking, so a broken row breaks the shot.
    try:
        await page.locator(".dp-slack__row").first.click()
        await page.wait_for_selector(".dp-slack__draft-card", timeout=8000)
        await page.wait_for_timeout(700)
        await snap(page, "slack-draft")
    except Exception as exc:  # noqa: BLE001 - a missing draft is worth seeing
        print(f"    (draft shot skipped — {str(exc).splitlines()[0]})")

    # Provenance: what the draft was built from, expanded.
    try:
        await page.get_by_role("button", name="View sources").click()
        await page.wait_for_timeout(600)
        await snap(page, "slack-sources")
        await page.get_by_role("button", name="Hide sources").click()
        await page.wait_for_timeout(300)
    except Exception as exc:  # noqa: BLE001
        print(f"    (sources shot skipped — {str(exc).splitlines()[0]})")

    # The assistant proposing a rewrite, with the draft still untouched behind it.
    try:
        ask = page.get_by_label("Ask AI to refine the message")
        await ask.fill("Please improve the draft. Make it more concise and add a clear next step.")
        await ask.press("Enter")
        await page.wait_for_selector(".dp-slack__proposal-actions", timeout=8000)
        await page.wait_for_timeout(700)
        await snap(page, "slack-assistant")
    except Exception as exc:  # noqa: BLE001
        print(f"    (assistant shot skipped — {str(exc).splitlines()[0]})")

    # Settings → Slack, where the connection, the drafting scope and the
    # context allow-list live — including the locked "never automatically send".
    try:
        await page.keyboard.press("Control+Comma")
        await page.wait_for_selector(".dp-settings-panel", timeout=8000)
        await page.get_by_label("Settings sections").get_by_role(
            "button", name="Slack", exact=True).click()
        # Park the pointer off the rail: leaving it where it clicked photographs
        # a hover state on the item *below* the selected one, which reads as two
        # sections being active at once.
        await page.mouse.move(1400, 60)
        await page.wait_for_timeout(1100)
        await snap(page, "slack-settings")

        # Scroll to the claim the whole feature rests on. It lives in section 4,
        # below the fold, and a screenshot that stops at "AI drafting" leaves the
        # locked "never automatically send" row undocumented.
        await page.get_by_text("Never automatically send a Slack message").scroll_into_view_if_needed()
        await page.wait_for_timeout(700)
        await snap(page, "slack-settings-privacy")
    except Exception as exc:  # noqa: BLE001
        print(f"    (settings shot skipped — {str(exc).splitlines()[0]})")


async def phone(page) -> None:
    await open_slack(page)
    await snap(page, "slack-phone")


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=CHROME)
        try:
            context = await browser.new_context(viewport=DESKTOP, device_scale_factor=2)
            await context.add_init_script(SETUP_DONE)
            page = await context.new_page()
            await desktop(page)
            await context.close()

            context = await browser.new_context(
                viewport=PHONE, device_scale_factor=2, is_mobile=True, has_touch=True)
            await context.add_init_script(SETUP_DONE)
            page = await context.new_page()
            await phone(page)
            await context.close()
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
