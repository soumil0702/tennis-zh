"""
Cart-Hold Bot
Repeatedly re-adds one or more court slots (configured via TARGET_SLOTS in .env)
to the cart before their 15-min hold expires, so you have time to decide
whether to actually book them. Clears the cart on startup first.
Does NOT complete checkout — do that yourself in your own browser session.
"""

import asyncio
import os
import re
import time
from datetime import date

from playwright.async_api import async_playwright, TimeoutError as PWTimeoutError

from common import log, login, send_telegram
from checker import BOOKING_URL, GERMAN_MONTHS

HOLD_REFRESH_SECONDS = int(os.getenv("HOLD_REFRESH_SECONDS", "780"))     # 13 min, safely under the 15-min hold
MAX_HOLD_SECONDS = int(os.getenv("MAX_HOLD_SECONDS", "10800"))          # 3h auto-release; 0 = no cap
REMINDER_INTERVAL_SECONDS = int(os.getenv("REMINDER_INTERVAL_SECONDS", "3600"))  # hourly Telegram reminder


MAX_SLOTS = int(os.getenv("MAX_SLOTS", "3"))  # sanity cap on how many slots can be held at once


def parse_slot_spec(spec: str) -> tuple[str, str, str]:
    """Parses one 'Court|YYYY-MM-DD|HH:MM' spec into its (court, date, time) parts."""
    parts = [p.strip() for p in spec.split("|")]
    if len(parts) != 3:
        raise ValueError(f'Invalid slot spec {spec!r}, expected "Court|YYYY-MM-DD|HH:MM"')
    return parts[0], parts[1], parts[2]


def load_slots() -> list[tuple[str, str, str]]:
    """Reads TARGET_SLOTS from .env: semicolon-separated 'Court|YYYY-MM-DD|HH:MM' entries."""
    env_slots = os.getenv("TARGET_SLOTS", "")
    x=env_slots.split(";");
    print("x is ", x)
    specs = [parse_slot_spec(s) for s in env_slots.split(";") if s.strip()]
    if not specs:
        raise SystemExit(
            'TARGET_SLOTS is required in .env, e.g.:\n'
            'TARGET_SLOTS=Tennisplatz 6|2026-09-12|17:00;Tennisplatz 7|2026-09-13|19:00'
        )
    if len(specs) > MAX_SLOTS:
        raise SystemExit(f"Too many slots ({len(specs)}) — max is {MAX_SLOTS} (override with MAX_SLOTS)")
    return specs


async def accept_cookies(page) -> None:
    try:
        await page.get_by_role("button", name="Akzeptieren").click(timeout=3000)
        await page.wait_for_timeout(500)
    except PWTimeoutError:
        pass


async def close_cart_drawer(page) -> None:
    try:
        await page.get_by_role("button", name="Close panel").click(timeout=3000)
    except PWTimeoutError:
        pass


async def clear_cart(page) -> None:
    """Removes every item currently in the cart (including anything added manually),
    so a leftover unrelated item can't be mistaken for one of our target slots."""
    await page.goto(BOOKING_URL, wait_until="load")
    await accept_cookies(page)
    # label = await page.get_by_role("button", name=re.compile(r"items in cart")).get_attribute("aria-label");
    # print("label is ", label)
    # if (label or "").startswith("0"):
    #     return
    await page.get_by_role("button", name=re.compile(r"items in cart")).click()
    removed = 0
    await page.wait_for_timeout(500)
    remove_btn = page.locator('[data-testid^="product-item-"]:visible').get_by_role("button", name="Entfernen").first
    while await remove_btn.count() > 0 and removed < 20:
        await remove_btn.click()
        await page.wait_for_timeout(500)
        removed += 1
    await close_cart_drawer(page)
    if removed:
        log.warning("Cleared %d pre-existing cart item(s) (including any added manually) before starting.", removed)


async def navigate_to_court(page, court_name: str) -> bool:
    """Rewinds the carousel to the start, then advances until the target court is shown."""
    prev_btn = page.get_by_role("button", name="Previous item")
    next_btn = page.get_by_role("button", name="Next item")
    await prev_btn.wait_for(timeout=1000)

    while not await prev_btn.is_disabled():
        await prev_btn.click()
        await page.locator("li button").first.wait_for(timeout=10000)

    while True:
        current = (await page.locator("h3").first.inner_text()).strip()
        if current.split(" -")[0].strip() == court_name:
            log.info("Can confirm I navigated to court: %s successfully", court_name)
            return True
        if await next_btn.is_disabled():
            return False
        await next_btn.click()
        await page.locator("li button").first.wait_for(timeout=10000)


async def find_slot_button(page, date_label: str, target_hour: int, target_minute: int):
    """Returns (locator, status_text) for the slot matching date_label + start time, or (None, None)."""
    date_sections = page.locator("div.flex.flex-col.gap-y-8")
    section_count = await date_sections.count()

    for s in range(section_count):
        section = date_sections.nth(s)
        heading = (await section.locator("> div").first.inner_text()).strip().replace("\n", " ")
        if date_label not in heading:
            continue

        buttons = section.locator("li button")
        btn_count = await buttons.count()
        log.info("*******+Inside find_slot_button()...the number of buttons found is:  %d", btn_count)
        for i in range(btn_count):
            btn = buttons.nth(i)
            text = (await btn.inner_text()).strip().replace("\n", " ")
            log.info("*******+Inside find_slot_button()...the text is:  %s", text)
            match = re.search(r"(\d{1,2}):(\d{2})", text)
            if not match:
                continue
            if int(match.group(1)) == target_hour and int(match.group(2)) == target_minute:
                return btn, text
    return None, None


async def add_slot_to_cart(page, date_label: str, target_hour: int, target_minute: int, slot_btn) -> bool:
    """Adds the slot to cart and confirms by re-reading the slot's own status afterward
    (the site can show a different/no toast when it silently rejects the request,
    e.g. when you already have that exact slot booked)."""
    await slot_btn.click()
    await page.get_by_test_id("save-button").wait_for(timeout=8000)
    await page.get_by_test_id("save-button").click()
    try:
        await page.get_by_text("Produkt erfolgreich zum Warenkorb hinzugefügt.").wait_for(timeout=5000)
    except PWTimeoutError:
        pass  # fall through to the authoritative status re-check below
    await close_cart_drawer(page)
    # The slot list re-renders asynchronously after adding; retry a couple of times.
    text = None
    for _ in range(3):
        _, text = await find_slot_button(page, date_label, target_hour, target_minute)
        if text is not None and "Bereits im Warenkorb" in text:
            break
        await page.wait_for_timeout(1000)
    if text is None or "Bereits im Warenkorb" not in text:
        log.error("Add did not take effect (status: %r) — the site likely rejected the request.", text)
        return False
    return True


async def hold_once(page, court: str, date_label: str, target_hour: int, target_minute: int) -> bool:
    """Adds the target slot to cart, assuming the cart was already cleared this cycle
    (the site's 15-min timer only resets on a fully empty cart, not on a per-item swap)."""
    # Reload fresh for each slot: a previous slot's selection modal can leave an
    # inert-but-click-blocking overlay in the DOM otherwise.
    await page.goto(BOOKING_URL, wait_until="load")
    await accept_cookies(page)

    if not await navigate_to_court(page, court):
        log.error("Court %r not found in carousel.", court)
        return False

    # Feels redundant so i commented it out!
    #  slot_btn, text = await find_slot_button(page, date_label, target_hour, target_minute)
    # if slot_btn is None:
    #     log.error("Slot %s %02d:%02d not found on the page (outside the 3-day window?).", date_label, target_hour, target_minute)
    #     return False

    # The slot list can briefly show a stale/loading status right after page load;
    # re-read it once more after a short settle delay before trusting it.
    await page.wait_for_timeout(1500)
    slot_btn, text = await find_slot_button(page, date_label, target_hour, target_minute)
    if slot_btn is None:
        log.error("Slot %s %02d:%02d disappeared after settling.", date_label, target_hour, target_minute)
        return False

    if "Bereits gebucht" in text:
        log.error("You already have this exact slot booked (%r) — nothing to hold.", text)
        return False

    if "Bereits im Warenkorb" in text:
        # Only expected if the same slot appears twice in TARGET_SLOTS.
        log.info("Slot already in cart this cycle — skipping duplicate add.")
        return True

    if "Verfügbar" not in text:
        # Retry before giving up — the site occasionally serves a stale/transitional snapshot
        # (e.g. during morning cache refreshes) where statuses are wrong for a few seconds.
        for attempt in range(3):
            # await page.wait_for_timeout(1000)
            slot_btn, text = await find_slot_button(page, date_label, target_hour, target_minute)
            if text is not None and "Verfügbar" in text:
                log.info("Slot recovered to Verfügbar after %d retry(s).", attempt + 1)
                break
            await page.reload(wait_until="load")
        else:
            log.error("Slot is not available after retries (status: %r) — someone else may have booked it.", text)
            return False

    if not await add_slot_to_cart(page, date_label, target_hour, target_minute, slot_btn):
        return False
    log.info("Slot added to cart.")
    return True


def build_slots(specs: list[tuple[str, str, str]]) -> list[dict]:
    slots = []
    for court, date_str, time_str in specs:
        d = date.fromisoformat(date_str)
        date_label = f"{d.day}. {GERMAN_MONTHS[d.month]}"
        hour, minute = (int(p) for p in time_str.split(":"))
        slots.append({
            "court": court,
            "date_label": date_label,
            "hour": hour,
            "minute": minute,
            "active": True,
            "label": f"{court} on {date_label} at {hour:02d}:{minute:02d}",
        })
    return slots


async def run() -> None:
    specs = load_slots()
    slots = build_slots(specs)

    async with async_playwright() as pw:
        headless = os.getenv("HEADLESS", "true").lower() != "false"
        browser = await pw.chromium.launch(headless=headless, slow_mo=50 if not headless else 0)
        context = await browser.new_context(timezone_id="Europe/Berlin")
        page = await context.new_page()

        await login(page)

        log.info(
            "Holding %d slot(s): %s — refreshing every %ds, auto-release after %ds.",
            len(slots), "; ".join(s["label"] for s in slots), HOLD_REFRESH_SECONDS, MAX_HOLD_SECONDS,
        )

        start_time = time.monotonic()
        last_reminder = start_time

        while True: 
            # Cleared every cycle: the site's 15-min countdown only resets on a fully
            # empty cart, so a full clear + fresh re-add is required to actually renew it.
            await clear_cart(page)

            for slot in slots:
                if not slot["active"]:
                    continue
                try:
                    ok = await hold_once(page, slot["court"], slot["date_label"], slot["hour"], slot["minute"])
                    if not ok:
                        slot["active"] = False
                        send_telegram(f"⚠️ Cart-hold stopped: {slot['label']} is no longer available.")
                except Exception as exc:
                    log.error("Error holding %s: %s", slot["label"], exc, exc_info=True)
                    slot["active"] = False
                    send_telegram(
                        f"⚠️ Cart-hold stopped in an uncertain state for {slot['label']}. "
                        "Please check the cart manually."
                    )

            active_slots = [s for s in slots if s["active"]]
            if not active_slots:
                log.info("No active slots left — exiting.")
                break

            now = time.monotonic()
            if now - last_reminder >= REMINDER_INTERVAL_SECONDS:
                held = "\n".join(f"  • {s['label']}" for s in active_slots)
                send_telegram(f"🎾 Still holding:\n{held}\n\n<a href='{BOOKING_URL}'>Book now →</a>")
                last_reminder = now

            if MAX_HOLD_SECONDS and (now - start_time) >= MAX_HOLD_SECONDS:
                held = "\n".join(f"  • {s['label']}" for s in active_slots)
                log.info("Max hold duration reached (%ds). Releasing and exiting.", MAX_HOLD_SECONDS)
                send_telegram(
                    f"⏱️ Auto-released after {MAX_HOLD_SECONDS}s:\n{held}\n\n"
                    "Decide now or they will expire naturally within 15 min."
                )
                break

            await asyncio.sleep(HOLD_REFRESH_SECONDS)


if __name__ == "__main__":
    asyncio.run(run())
