"""
One-shot exploration script — logs in and dumps the booking page structure.
Run once, then delete. Output saved to explore_output.txt.
"""
import asyncio
import os
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PWTimeoutError

load_dotenv()
EMAIL = os.environ["ZHS_EMAIL"]
PASSWORD = os.environ["ZHS_PASSWORD"]

BOOKING_URL = (
    "https://kurse.zhs-muenchen.de/de/product-offers/"
    "21114da0-4246-42b1-bab6-8d7ac49bb14f"
)
LOGIN_URL = "https://kurse.zhs-muenchen.de/auth/login"

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        print("→ Navigating to login…")
        await page.goto(LOGIN_URL, wait_until="networkidle")

        # Click "Login with Email" then wait for email field to appear
        try:
            btn = page.get_by_test_id("login-with-email")
            await btn.wait_for(timeout=5000)
            await btn.click()
            await page.get_by_placeholder("Enter your email").wait_for(timeout=8000)
        except PWTimeoutError:
            pass  # already on the email form

        await page.screenshot(path="debug_login.png")
        await page.get_by_placeholder("Enter your email").fill(EMAIL)
        await page.get_by_placeholder("Enter your password").fill(PASSWORD)
        await page.get_by_role("button", name="Sign in").click()
        await page.wait_for_load_state("networkidle")

        current = page.url
        print(f"→ After login URL: {current}")
        if "login" in current:
            print("ERROR: Still on login page — credentials may be wrong.")
            await browser.close()
            return

        print("→ Login OK. Opening booking page…")
        await page.goto(BOOKING_URL, wait_until="networkidle")
        await page.wait_for_timeout(2000)

        # Accept cookies if banner is present
        try:
            await page.get_by_text("Akzeptieren").click(timeout=3000)
            await page.wait_for_timeout(1000)
        except Exception:
            pass

        # Dump all input, select, button elements and any class containing "slot"
        result = await page.evaluate("""() => {
            const lines = [];
            // all form controls
            document.querySelectorAll('select, input, button').forEach(el => {
                lines.push(`TAG=${el.tagName} id=${el.id} name=${el.name} type=${el.type} class="${el.className}" text="${el.innerText?.slice(0,60)}"`);
            });
            lines.push('--- SLOT-LIKE ELEMENTS ---');
            document.querySelectorAll('[class*="slot"],[class*="Slot"],[class*="time"],[class*="Time"],[class*="booking"],[class*="Booking"]').forEach(el => {
                lines.push(`TAG=${el.tagName} class="${el.className}" text="${el.innerText?.slice(0,80)}"`);
            });
            return lines.join('\\n');
        }""")

        with open("explore_output.txt", "w") as f:
            f.write(f"Final URL: {page.url}\n\n")
            f.write(result)

        print("→ Done. Output written to explore_output.txt")
        await browser.close()

asyncio.run(main())
