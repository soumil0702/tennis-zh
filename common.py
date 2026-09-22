"""
Shared config, logging, login and Telegram helpers used by checker.py and hold.py.
"""

import os
import logging

import requests
from dotenv import load_dotenv
from playwright.async_api import TimeoutError as PWTimeoutError

load_dotenv()

EMAIL = os.environ["ZHS_EMAIL"]
PASSWORD = os.environ["ZHS_PASSWORD"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

LOGIN_URL = "https://kurse.zhs-muenchen.de/auth/login"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def send_telegram(message: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}

    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        log.info("Telegram notification sent.")
    except requests.RequestException as exc:
        log.error("Failed to send Telegram message: %s", exc)


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
