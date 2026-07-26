#!/usr/bin/env python3
"""Capture DayPilot agents-UI screenshots for the docs (hash-routed SPA)."""
import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright

BASE = os.getenv("SHOOT_BASE", "http://127.0.0.1:8099")
OUT = Path(os.getenv("SHOOT_OUT", "docs/assets/screenshots/agents")).resolve()
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

ROUTES = [
    ("agents-directory", "#/agents", ".dp-agentcard"),
    ("agent-workspace", "#/agents/scarlett", ".dp-taskrail"),
    ("add-agent", "#/agents/add", ".dp-method"),
]


SETUP_DONE = (
    "try{localStorage.setItem('daypilot.setup', JSON.stringify({"
    "version:2,status:'completed',aiReady:true,"
    "completedSteps:{provider:true,profile:true,mailbox:false,knowledge:false},"
    "completedAt:new Date().toISOString()}));"
    "localStorage.setItem('daypilot.onboarded','true');"
    "localStorage.setItem('daypilot.aiReady','true');}catch(e){}"
)


async def prep(ctx):
    """Mark first-run setup complete so the onboarding wizard never overlays."""
    await ctx.add_init_script(SETUP_DONE)


async def settle(page, ms=1100):
    await page.wait_for_timeout(ms)


async def shoot(page, name, hash_, wait_sel, out):
    await page.goto(f"{BASE}/{hash_}", wait_until="networkidle")
    # Dismiss any first-run overlay that might cover the view.
    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass
    await settle(page, 700)
    try:
        await page.wait_for_selector(wait_sel, timeout=8000)
    except Exception as exc:
        print(f"  ({name}: selector {wait_sel} not found — {exc})")
    await settle(page, 900)
    path = out / f"{name}.png"
    await page.screenshot(path=str(path), full_page=False)
    print(f"shot: {path}")


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, executable_path=CHROME,
                                            args=["--no-sandbox"])
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900},
                                        device_scale_factor=2, color_scheme="dark")
        await prep(ctx)
        page = await ctx.new_page()
        for name, hash_, sel in ROUTES:
            await shoot(page, name, hash_, sel, OUT)

        # Bonus: mobile workspace (task rail collapses under the chat).
        mob = await browser.new_context(viewport={"width": 414, "height": 896},
                                        device_scale_factor=2, color_scheme="dark")
        await prep(mob)
        mp = await mob.new_page()
        await shoot(mp, "agent-workspace-mobile", "#/agents/scarlett", ".dp-taskrail", OUT)

        await browser.close()
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
