#!/usr/bin/env python3
"""Capture the README product tour from the running app.

Every image in the README used to be a one-off taken by hand months apart, so
they drifted: different themes, different data, screens that no longer look
like that. These are all taken in one pass, from one seeded workspace, at one
size, against the app as it is right now.

Retina (device_scale_factor=2) on a 1440x900 desktop and a 414x896 phone —
GitHub scales images down, so a 1x capture reads as soft on the very displays
this product is sold on.
"""
import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright

BASE = os.getenv("SHOOT_BASE", "http://127.0.0.1:8099")
OUT = Path(os.getenv("SHOOT_OUT", "docs/assets/screenshots/tour")).resolve()
CHROME = os.getenv("SHOOT_CHROME", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")

DESKTOP = {"width": 1440, "height": 900}
PHONE = {"width": 414, "height": 896}

# First-run setup would otherwise cover every shot with the wizard. The chat
# pointer is the same thing a returning user's browser holds — which of their
# saved conversations is open; the conversation itself is seeded server-side.
CHAT_SESSION_ID = "screenshot-tour-conversation"
SETUP_DONE = (
    "try{localStorage.setItem('daypilot.setup', JSON.stringify({"
    "version:2,status:'completed',aiReady:true,"
    "completedSteps:{provider:true,profile:true,mailbox:true,knowledge:true},"
    "completedAt:new Date().toISOString()}));"
    "localStorage.setItem('daypilot.onboarded','true');"
    "localStorage.setItem('daypilot.aiReady','true');"
    f"localStorage.setItem('daypilot.chat.session','{CHAT_SESSION_ID}');"
    "}catch(e){}"
)


async def goto(page, hash_: str, wait: str | None = None, ms: int = 900) -> None:
    await page.goto(f"{BASE}/{hash_}", wait_until="networkidle")
    await page.wait_for_timeout(400)
    if wait:
        try:
            await page.wait_for_selector(wait, timeout=8000)
        except Exception as exc:  # noqa: BLE001 - a missing pane is worth seeing
            print(f"    (selector {wait} not found — {exc})")
    # A screen that autofocuses draws a focus ring the moment it mounts, which
    # photographs as a stray box around a heading.
    await page.evaluate("() => { const a = document.activeElement; if (a && a.blur) a.blur() }")
    await page.wait_for_timeout(ms)


async def snap(page, name: str) -> None:
    path = OUT / f"{name}.png"
    await page.screenshot(path=str(path), full_page=False)
    print(f"shot: {path.name}")


async def open_settings(page, section_title: str) -> None:
    """Open Settings (⌘,) and select a section by its visible name.

    Driven through the real keyboard shortcut and the real nav rail rather than
    a test hook, so a shortcut that broke would break the screenshots too.
    """
    await page.keyboard.press("Control+Comma")
    await page.wait_for_selector(".dp-settings-panel", timeout=8000)
    await page.get_by_role("button", name=section_title, exact=True).click()
    await page.wait_for_timeout(900)


async def open_from_palette(page, option: str, wait: str, name: str) -> None:
    """Open a command-palette action and photograph what it opens.

    Each one is reset by reloading Home rather than by pressing Escape: a
    multi-step wizard deliberately does not close on Escape, and a modal left
    open swallows the clicks meant for the next shot.
    """
    await page.keyboard.press("Control+k")
    await page.wait_for_selector(".dp-palette", timeout=6000)
    await page.get_by_role("option", name=option).click()
    try:
        await page.wait_for_selector(wait, timeout=8000)
        await page.wait_for_timeout(900)
        await snap(page, name)
    except Exception as exc:  # noqa: BLE001
        print(f"    ({name} skipped — {str(exc).splitlines()[0]})")
    await reset(page)


async def reset(page) -> None:
    """Back to a clean Home.

    A plain `goto` to the same `#/home` is a same-document navigation, so React
    keeps its state and any open modal stays up to swallow the next click.
    """
    await page.goto(f"{BASE}/#/home")
    await page.reload(wait_until="networkidle")
    await page.wait_for_selector(".dp-home", timeout=8000)
    await page.wait_for_timeout(400)


async def open_first_email(page) -> None:
    try:
        await page.locator(".dp-msgrow").first.click()
        await page.wait_for_timeout(900)
    except Exception as exc:  # noqa: BLE001
        print(f"    (no message to open — {exc})")


async def close_overlay(page) -> None:
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(400)


async def desktop_tour(page) -> None:
    # --- Home: the hero. Everything below the fold is the seeded day.
    await goto(page, "#/home", ".dp-home")
    await snap(page, "home")

    # --- Command palette (⌘K) over Home.
    await page.keyboard.press("Control+k")
    await page.wait_for_selector(".dp-palette", timeout=6000)
    await page.wait_for_timeout(500)
    await snap(page, "command-palette")
    await close_overlay(page)

    # --- Focus Mode: the "what do I do now" screen, entered the way a user does.
    await page.keyboard.press("f")
    try:
        await page.wait_for_selector(".dp-focus", timeout=6000)
        await page.wait_for_timeout(600)
        await snap(page, "focus-mode")
    except Exception as exc:  # noqa: BLE001
        print(f"    (focus mode skipped — {exc})")
    await close_overlay(page)

    # --- Approval Center: the governance claim, now reading the real queue.
    await goto(page, "#/home", ".dp-home")
    await page.keyboard.press("Control+k")
    await page.wait_for_selector(".dp-palette", timeout=6000)
    await page.get_by_role("option", name="Approval Center").click()
    await page.wait_for_selector('[aria-label="Approval Center"]', timeout=6000)
    await page.wait_for_timeout(800)
    await snap(page, "approval-center")
    await close_overlay(page)

    # --- The rest of the primary nav.
    for name, hash_, wait in [
        ("planning", "#/planning", ".dp-pl__main"),
        ("projects", "#/projects", ".dp-view"),
        ("documents", "#/documents", ".dp-view"),
    ]:
        await goto(page, hash_, wait)
        await snap(page, name)

    # Email with a message open — the empty reading pane says nothing about the
    # five-region layout or the assistant beside it.
    await goto(page, "#/email", ".dp-mail")
    await open_first_email(page)
    await snap(page, "email")

    # --- The three flows the README shows as their own screens. Each is a real
    # command-palette action, opened the way a user opens it.
    await goto(page, "#/home", ".dp-home")
    for option, wait, name in [
        ("New project", ".dp-pw", "project-wizard"),
        ("Review AI Patches · GitPilot", ".dp-modal-backdrop", "patch-review"),
        ("Matrix Designer · Batch Roadmap", ".dp-modal-backdrop", "matrix-designer"),
    ]:
        await open_from_palette(page, option, wait, name)

    # --- Settings sections that the README shows individually.
    await goto(page, "#/home", ".dp-home")
    for name, title in [
        ("ai-providers", "AI providers"),
        ("knowledge-sources", "Knowledge sources"),
        ("mail-settings", "Mail settings"),
        ("integrations", "Integrations"),
    ]:
        await open_settings(page, title)
        await snap(page, name)
        await close_overlay(page)


async def light_theme_tour(page) -> None:
    """The Email workspace in light theme — the one screen the README pairs."""
    await goto(page, "#/email", ".dp-mail")
    await open_first_email(page)
    await snap(page, "email-light")


async def phone_tour(page) -> None:
    await goto(page, "#/home", ".dp-m__page")
    await snap(page, "mobile-home")

    # The full-screen AI chat, opened from Home's own button.
    try:
        await page.get_by_role("button", name="Ask the AI Assistant").click()
        await page.wait_for_timeout(900)
        await snap(page, "mobile-ai")
        await close_overlay(page)
    except Exception as exc:  # noqa: BLE001
        print(f"    (mobile AI skipped — {exc})")

    # The navigation drawer.
    await goto(page, "#/home", ".dp-m__page")
    try:
        await page.get_by_role("button", name="Open menu").click()
        await page.wait_for_timeout(700)
        await snap(page, "mobile-drawer")
    except Exception as exc:  # noqa: BLE001
        print(f"    (mobile drawer skipped — {exc})")

    await goto(page, "#/standup", ".dp-standup")
    await snap(page, "mobile-standup")


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, executable_path=CHROME,
                                           args=["--no-sandbox"])
        try:
            dark = await browser.new_context(viewport=DESKTOP, device_scale_factor=2,
                                             color_scheme="dark")
            await dark.add_init_script(SETUP_DONE)
            await desktop_tour(await dark.new_page())

            # First run, in a browser that has never seen DayPilot — the only
            # shot that must NOT have the setup-complete flag.
            fresh = await browser.new_context(viewport=DESKTOP, device_scale_factor=2,
                                              color_scheme="dark")
            page = await fresh.new_page()
            await goto(page, "#/home", ".dp-onb, .dp-wizard, .dp-modal-backdrop")
            await snap(page, "onboarding")

            light = await browser.new_context(viewport=DESKTOP, device_scale_factor=2,
                                              color_scheme="light")
            await light.add_init_script(SETUP_DONE)
            await light_theme_tour(await light.new_page())

            phone = await browser.new_context(viewport=PHONE, device_scale_factor=2,
                                              color_scheme="dark")
            await phone.add_init_script(SETUP_DONE)
            await phone_tour(await phone.new_page())
        finally:
            await browser.close()
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
