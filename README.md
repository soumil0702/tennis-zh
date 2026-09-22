# availability-checker


A headless browser automation tool that monitors a booking portal and sends a Telegram notification when a preferred time slot becomes available.

- Filters by resource type and skips unwanted categories
- Filters to today's date and slots at or after a configured start time
- Two run modes: **loop mode** (local Mac and GitHub Actions CI)

---

## Option A — Run locally on your Mac

### 1 — Install dependencies

```bash
cd availability-checker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2 — Create your Telegram bot (one-time, ~2 min)

1. Open Telegram → search for **@BotFather** → send `/newbot`
2. Follow the prompts, copy the **token** it gives you
3. Message your new bot once (any text), then open:  
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`  
   Copy the `"id"` value under `"chat"` — that's your **Chat ID**

### 3 — Configure credentials

```bash
cp .env.example .env
```
For notification credentials message me — you would need to provide these in the `.env`.
Edit `.env`:

```
SERVICE_EMAIL=your_email
SERVICE_PASSWORD=your_password
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
CHECK_INTERVAL_SECONDS=120
HEADLESS=true
```

### 4 — Run (loop mode)

```bash
source .venv/bin/activate
python3 checker.py
```

Checks every `CHECK_INTERVAL_SECONDS` seconds (default 120 = 2 min) until you stop it with `Ctrl+C`.  
Deduplication is active — you won't get re-notified for the same slot within the same session.

To run in the background:

```bash
nohup python3 checker.py > checker.log 2>&1 &
echo "PID: $!"
```

Stop it with `kill <PID>`. Watch the log with `tail -f checker.log`.

> **Note:** The script pauses when your Mac sleeps. For uninterrupted monitoring use Option B.

### 5 — Debug mode (Playwright Inspector)

To step through the browser automation interactively and inspect what the script is doing:

```bash
PWDEBUG=1 python3 checker.py
```

This opens the **Playwright Inspector** — a separate window that lets you pause, step through each action, and inspect page elements in real time. The browser will also run in non-headless mode automatically (no need to set `HEADLESS=false`).

Useful when:
- The bot stops finding slots unexpectedly and you want to see what the page looks like
- The website has changed its layout and you need to inspect element selectors
- You want to verify which courts and dates are being scanned

> **Note:** Debug mode runs in single-step mode — you must click **Resume** in the Inspector to advance. Not suitable for normal monitoring use.

---

## Option B — GitHub Actions (runs automatically in the cloud)

The workflow at `.github/workflows/check-slots.yml` runs the checker automatically from 01:00–16:00 Munich time (CEST), with no Mac required. It uses a 3-hour cron schedule, with each job running in loop mode for 3.5 hours — ensuring continuous coverage with a small overlap. The CHECK_INTERVAL_SECONDS is 120s


### 1 — Add repository secrets

Go to your repo on GitHub → **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret name | Value |
|---|---|
| `SERVICE_EMAIL` | Your login email |
| `SERVICE_PASSWORD` | Your password |
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |

### 2 — Push the workflow file

The workflow activates automatically once `.github/workflows/check-slots.yml` is on the default branch (`main`). After pushing, go to the **Actions** tab on GitHub — the workflow should show a schedule trigger.

### 3 — Manual trigger

On the Actions tab → click **Tennis Slot Checker** → **Run workflow** to test it immediately.

> **Note:** Each CI job runs in loop mode with deduplication within the session. Across job restarts (every 3 hours) you may get re-notified for slots that are still open — this is intentional.

---

## Configuration reference

| Variable | Default | Description |
|---|---|---|
| `SERVICE_EMAIL` | required | login email |
| `SERVICE_PASSWORD` | required | login password |
| `TELEGRAM_BOT_TOKEN` | required | Telegram bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | required | Your Telegram chat ID |
| `CHECK_INTERVAL_SECONDS` | `120` | Seconds between checks (loop mode only) |
| `HEADLESS` | `true` | Set to `false` to watch the browser (local only) |
| `RUN_ONCE` | `false` | Set to `true` to check once and exit (single-shot use) |
| `MAX_RUNTIME_SECONDS` | `0` | Exit after N seconds (0 = run forever). Set to `12600` in CI (3.5 h) |

---

## Cart-Hold Bot (`hold.py`)

Some bookings can't be freely cancelled — cancellation is only possible up to 24h in advance,
otherwise the payment is lost. `hold.py` works around this by keeping one specific slot in your
cart (which reserves it for 15 minutes) without actually checking out, refreshing the hold every
few minutes so you have time to decide whether you actually want to book it. **It never completes
checkout itself** — when you decide to book, open the site yourself in your own browser (same
account, same cart) and check out there.

Run it locally (manual/local use only — not wired into GitHub Actions):

```bash
source .venv/bin/activate
python3 hold.py --court "Tennisplatz 6" --date 2026-09-07 --time 17:00
```

`--court`/`--date`/`--time` can also be set via `TARGET_COURT`, `TARGET_DATE` (`YYYY-MM-DD`), and
`TARGET_TIME` (`HH:MM`) in `.env` instead of CLI args.

| Variable | Default | Description |
|---|---|---|
| `HOLD_REFRESH_SECONDS` | `780` (13 min) | How often to refresh the cart hold (must stay under the 15-min limit) |
| `MAX_HOLD_SECONDS` | `10800` (3 h) | Auto-release the hold after this long, so it doesn't block the slot indefinitely. `0` = no cap (not recommended) |
| `REMINDER_INTERVAL_SECONDS` | `3600` (1 h) | How often to send a Telegram reminder that the hold is still active |

The bot exits and sends a Telegram alert if the target slot becomes unavailable (e.g. someone else
booked it) or once `MAX_HOLD_SECONDS` is reached — in the latter case the hold simply stops
refreshing and lapses naturally within 15 minutes.

---

## Notes

- `.env` is gitignored — your credentials never leave your machine.
- The script re-authenticates automatically if the session expires.
- Unwanted resource categories are filtered out automatically based on internal configuration.
- Holding a slot in your cart without booking it blocks that slot for everyone else during the
  hold — please use `hold.py` responsibly and keep `MAX_HOLD_SECONDS` reasonable.


