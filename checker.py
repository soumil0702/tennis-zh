"""
Availability Slot Checker
Monitors for open fields from 17:00 onwards
and sends a Telegram notification the moment one appears.
"""

import asyncio
import os
import re
import logging
from datetime import date, timedelta

import requests
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PWTimeoutError

load_dotenv()
# ── Config ────────────────────────────────────────────────────────────────────
EMAIL = os.environ["ZHS_EMAIL"]
PASSWORD = os.environ["ZHS_PASSWORD"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_SECONDS", "120"))
MAX_RUNTIME = int(os.getenv("MAX_RUNTIME_SECONDS", "0"))  # 0 = run forever (local); set >0 in CI

BOOKING_URL = (
    "https://kurse.zhs-muenchen.de/de/product-offers/"
    "21114da0-4246-42b1-bab6-8d7ac49bb14f"
)
LOGIN_URL = "https://kurse.zhs-muenchen.de/auth/login"
NOTIFY_FROM_HOUR = 17  # check slots starting from 17:00
NOTIFY_TO_HOUR = 20    # check slots only before 21:00 (exclusive) — no need to notify for late-night slots			

# German month names used in the date label on the page
GERMAN_MONTHS = [
    "", "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember"
]

# Courts to skip (Kunststoff — artificial surface, not wanted)
SKIP_COURTS = {
    "Tennisplatz 2", "Tennisplatz 3", "Tennisplatz 4", "Tennisplatz 5",
    "Tennisplatz 19", "Tennisplatz 20", "Tennisplatz 21", "Tennisplatz 22",
}


def _easter(year: int) -> date:
    """Calculate Easter Sunday for a given year (Anonymous Gregorian algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(114 + h + l - 7 * m, 31)
    return date(year, month, day + 1)


def _bayern_holidays(year: int) -> set[date]:
    """Return Bayern public holidays relevant to tennis season for a given year."""
    easter = _easter(year)
    return {
        date(year, 5, 1),        # Labour Day (fixed)
        easter + timedelta(39),  # Ascension Day
        easter + timedelta(50),  # Whit Monday
        easter + timedelta(60),  # Corpus Christi
        date(year, 8, 15),       # Assumption Day (fixed)
        date(year, 10, 3),       # Day of German Unity (fixed)
    }


def get_min_hour(d: date) -> int:
    """Return the minimum bookable hour for a given date.
    Weekends and Bayern public holidays: 13:00 (1 PM) onwards.
    Regular weekdays: 17:00 (5 PM) onwards.
    """
    if d.weekday() >= 5 or d in _bayern_holidays(d.year):
        return 13
    return NOTIFY_FROM_HOUR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Telegram ──────────────────────────────────────────────────────────────────
def send_telegram(message: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}

    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        log.info("Telegram notification sent.")
    except requests.RequestException as exc:
        log.error("Failed to send Telegram message: %s", exc)


# ── Browser helpers ───────────────────────────────────────────────────────────
async def login(page) -> None:
    log.info("Navigating to login page…")
    await page.goto(LOGIN_URL, wait_until="networkidle")

    # Step 1: click "Login with Email" (vs university SSO)
    try:
        btn = page.get_by_test_id("login-with-email")
        await btn.wait_for(timeout=5000)
        await btn.click()
        await page.get_by_test_id("login-email-input").wait_for(timeout=8000)
    except PWTimeoutError:
        pass  # already on email form

    # Step 2: fill credentials and submit
    await page.get_by_test_id("login-email-input").fill(EMAIL)
    await page.get_by_test_id("login-password-input").fill(PASSWORD)
    await page.get_by_test_id("login-button").click()
    await page.wait_for_load_state("networkidle")

    if "login" in page.url:
        raise RuntimeError("Login failed — check ZHS_EMAIL and ZHS_PASSWORD in .env")
    log.info("Logged in successfully.")


async def check_slots(page) -> list[dict]:
    """
    Cycles through every court in the carousel (skipping Kunststoff courts)
    and collects available slots ("Verfügbar", not disabled) with start hour
    >= NOTIFY_FROM_HOUR and < NOTIFY_TO_HOUR.
    Returns list of dicts with keys: court, time, date_label.
    """
    log.info("Opening booking page…")
    await page.goto(BOOKING_URL, wait_until="load")

    # Accept cookie banner if it appears
    try:
        await page.get_by_role("button", name="Akzeptieren").click(timeout=3000)
        await page.wait_for_timeout(500)
    except PWTimeoutError:
        pass

    # Wait for the court carousel to load
    prev_btn = page.get_by_role("button", name="Previous item")
    next_btn = page.get_by_role("button", name="Next item")
    await prev_btn.wait_for(timeout=10000)

    # Rewind to the very first court
    while not await prev_btn.is_disabled():
        await prev_btn.click()
        await page.locator("li button").first.wait_for(timeout=10000)

    available_slots = []

    # Build a label→min_hour map for the 3 days visible on the page
    today = date.today()
    dates_to_check = {}
    for _d in range(3):
        _target = today + timedelta(_d)
        _label = f"{_target.day}. {GERMAN_MONTHS[_target.month]}"
        dates_to_check[_label] = get_min_hour(_target)
    log.info("Checking %d days: %s — slots up to %02d:00",
             len(dates_to_check), ", ".join(dates_to_check), NOTIFY_TO_HOUR)

    while True:
        court_name = (await page.locator("h3").first.inner_text()).strip()
        # Skip Kunststoff courts
        base_name = court_name.split(" -")[0].strip()
        if base_name in SKIP_COURTS:
            log.info("Skipping %s (Kunststoff)", court_name)
        else:
            log.info("Checking court: %s", court_name)

            # Each date section is a div with these classes containing
            # [0] a heading div with the date text, [1] a div with the slot list.
            date_sections = page.locator("div.flex.flex-col.gap-y-8")
            section_count = await date_sections.count()

            for s in range(section_count):
                section = date_sections.nth(s)
                date_heading = await section.locator("> div").first.inner_text()
                date_heading = date_heading.strip().replace("\n", " ")
                # Only process sections for dates we care about
                matched_min_hour = None
                for _lbl, _mh in dates_to_check.items():
                    if _lbl in date_heading:
                        matched_min_hour = _mh
                        break
                if matched_min_hour is None:
                    continue

                slot_buttons = section.locator("li button:not([disabled])")
                btn_count = await slot_buttons.count()

                for i in range(btn_count):
                    text = (await slot_buttons.nth(i).inner_text()).strip().replace("\n", " ")

                    if "Verfügbar" not in text:
                        continue

                    # Extract start hour from e.g. "17:00 - 18:00 Uhr, Verfügbar"
                    match = re.search(r"(\d{1,2}):(\d{2})", text)
                    if not match:
                        continue
                    start_hour = int(match.group(1))
                    if start_hour < matched_min_hour or start_hour >= NOTIFY_TO_HOUR:
                        continue

                    available_slots.append({
                        "court": court_name,
                        "time": text,
                        "date_label": date_heading,
                    })

        if await next_btn.is_disabled():
            break
        await next_btn.click()
        # Wait for slot buttons to fully reload for the new court before continuing
        await page.locator("li button").first.wait_for(timeout=10000)

    return available_slots


# ── Shared notification helper ────────────────────────────────────────────────
def notify_slots(slots: list[dict]) -> None:
    # Group slots by date, preserving the order they were found
    by_date: dict[str, list[dict]] = {}
    for s in slots:
        by_date.setdefault(s["date_label"], []).append(s)

    sections = []
    for day_label, day_slots in by_date.items():
        lines = "\n".join(f"  • {s['court']}  —  {s['time']}" for s in day_slots)
        sections.append(f"<b>{day_label}</b>\n{lines}")

    body = "\n\n".join(sections)
    message = (
        f"🎾 <b>Tennis slot available!</b>\n\n"
        f"{body}\n\n"
        f"<a href='{BOOKING_URL}'>Book now →</a>"
    )
    send_telegram(message)
    log.info("Notified: %d slot(s).", len(slots))


# ── Main loop ─────────────────────────────────────────────────────────────────
async def run() -> None:
    run_once = os.getenv("RUN_ONCE", "false").lower() == "true"

    async with async_playwright() as pw:
        headless = os.getenv("HEADLESS", "true").lower() != "false"
        browser = await pw.chromium.launch(headless=headless, slow_mo=50 if not headless else 0)
        context = await browser.new_context(timezone_id="Europe/Berlin")
        page = await context.new_page()

        # Log in once; session is kept in `context`
        await login(page)

        if run_once:
            # ── Single-run mode (used by GitHub Actions) ──────────────────────
            # Checks once, sends a notification if any slots are found, then exits.
            # No deduplication — if a slot is still open on the next scheduled run,
            # you'll be notified again (intentional: better to over-notify than miss it).
            log.info("Single-run mode. Looking for slots from %02d:00 to %02d:00…", NOTIFY_FROM_HOUR, NOTIFY_TO_HOUR)
            try:
                slots = await check_slots(page)
                if slots:
                    notify_slots(slots)
                else:
                    log.info("No open slots from %02d:00 to %02d:00 found.", NOTIFY_FROM_HOUR, NOTIFY_TO_HOUR)
            except Exception as exc:
                log.error("Error during check: %s", exc, exc_info=True)

        else:
            # ── Loop mode (local Mac and CI long-running) ─────────────────────
            # Runs continuously, re-checking every CHECK_INTERVAL seconds.
            # Tracks notified slots so you don't get duplicate Telegram messages
            # for the same slot within the same session.
            # Exits cleanly after MAX_RUNTIME_SECONDS if set (used by CI to stay
            # within the GitHub Actions 6-hour job limit).
            notified_slots: set[str] = set()
            import time as _time
            start_time = _time.monotonic()

            log.info(
                "Starting check loop every %d seconds...",
                CHECK_INTERVAL,
            )
            if MAX_RUNTIME:
                log.info("Will exit after %d seconds (~%.1f hours).", MAX_RUNTIME, MAX_RUNTIME / 3600)

            while True:
                try:
                    slots = await check_slots(page)
                    new_slots = [
                        s for s in slots
                        if f"{s['court']}|{s['time']}|{s['date_label']}" not in notified_slots
                    ]
                    if new_slots:
                        notify_slots(new_slots)
                        for s in new_slots:
                            notified_slots.add(f"{s['court']}|{s['time']}|{s['date_label']}")
                    else:
                        log.info(
                            "No open slots from %02d:00 to %02d:00 found across all courts. Waiting %ds…",
                            get_min_hour(date.today()), NOTIFY_TO_HOUR, CHECK_INTERVAL,
                        )

                except Exception as exc:
                    log.error("Error during check: %s", exc, exc_info=True)
                    # Only re-login if the session has actually expired
                    # (i.e. we got redirected back to the login page)
                    if "login" in page.url:
                        log.info("Session expired — re-logging in…")
                        try:
                            await login(page)
                        except Exception as login_exc:
                            log.error("Re-login failed: %s", login_exc)

                if MAX_RUNTIME and (_time.monotonic() - start_time) >= MAX_RUNTIME:
                    log.info("Max runtime reached (%ds). Exiting cleanly.", MAX_RUNTIME)
                    break

                await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(run())
