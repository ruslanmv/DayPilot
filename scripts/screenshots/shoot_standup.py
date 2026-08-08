#!/usr/bin/env python3
"""Capture Daily Standup screenshots for the docs.

Shoots the real SPA against a real API with a real seeded draft, so what the
documentation shows is what the product produces. Nothing here fabricates
content — see ``seed_standup.py``, which runs the actual collector and compiler.
"""
import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright

BASE = os.getenv("SHOOT_BASE", "http://127.0.0.1:8099")
OUT = Path(os.getenv("SHOOT_OUT", "docs/assets/screenshots/standup")).resolve()
CHROME = os.getenv("SHOOT_CHROME", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")

SHOTS = [
    ("standup-review", "#/standup", ".dp-standup__section"),
    ("standup-home-card", "#/home", ".dp-standupcard"),
]

SETUP_DONE = (
    "try{localStorage.setItem('daypilot.setup', JSON.stringify({"
    "version:2,status:'completed',aiReady:true,"
    "completedSteps:{provider:true,profile:true,mailbox:false,knowledge:false},"
    "completedAt:new Date().toISOString()}));"
    "localStorage.setItem('daypilot.onboarded','true');"
    "localStorage.setItem('daypilot.aiReady','true');}catch(e){}"
)


async def shoot(page, name, hash_, wait_sel, out, *, full_page=False):
    await page.goto(f"{BASE}/{hash_}", wait_until="networkidle")
    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass
    await page.wait_for_timeout(700)
    try:
        await page.wait_for_selector(wait_sel, timeout=10000)
    except Exception as exc:
        print(f"  !! {name}: selector {wait_sel} not found — {exc}")
    await page.wait_for_timeout(900)
    path = out / f"{name}.png"
    await page.screenshot(path=str(path), full_page=full_page)
    print(f"shot: {path}")


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, executable_path=CHROME,
                                           args=["--no-sandbox"])
        ctx = await browser.new_context(viewport={"width": 1440, "height": 980},
                                        device_scale_factor=2, color_scheme="dark")
        await ctx.add_init_script(SETUP_DONE)
        page = await ctx.new_page()
        for name, hash_, sel in SHOTS:
            await shoot(page, name, hash_, sel, OUT)

        # The evidence drawer showing what one bullet is based on — the answer
        # to "why does it say I did that?", which is the point of the surface.
        await page.goto(f"{BASE}/#/standup", wait_until="networkidle")
        await page.wait_for_selector(".dp-standup__bullet:not([disabled])", timeout=10000)
        await page.click(".dp-standup__bullet:not([disabled])")
        await page.wait_for_timeout(700)
        await page.screenshot(path=str(OUT / "standup-evidence.png"))
        print(f"shot: {OUT / 'standup-evidence.png'}")

        # Setup. Reached from the review's own settings control, which is the
        # same component Settings → Integrations → Automations renders.
        setup = await browser.new_context(viewport={"width": 1440, "height": 1240},
                                          device_scale_factor=2, color_scheme="dark")
        await setup.add_init_script(SETUP_DONE)
        sp = await setup.new_page()
        await sp.goto(f"{BASE}/#/standup", wait_until="networkidle")
        await sp.wait_for_selector(".dp-standup__close", timeout=10000)
        await sp.click(".dp-standup__close")
        await sp.wait_for_selector(".dp-standupsetup", timeout=8000)
        await sp.wait_for_timeout(900)
        await sp.screenshot(path=str(OUT / "standup-setup.png"))
        print(f"shot: {OUT / 'standup-setup.png'}")

        # Phone: approving from a phone at 18:05 is the common case.
        mob = await browser.new_context(viewport={"width": 414, "height": 896},
                                        device_scale_factor=2, color_scheme="dark")
        await mob.add_init_script(SETUP_DONE)
        mp = await mob.new_page()
        await shoot(mp, "standup-review-mobile", "#/standup", ".dp-standup__section", OUT,
                    full_page=True)

        await browser.close()
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
