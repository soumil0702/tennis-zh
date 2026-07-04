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
CHECK_INTERVAL_SECONDS=300
HEADLESS=true
```

### 4 — Run (loop mode)

```bash
source .venv/bin/activate
python3 checker.py
```

Checks every `CHECK_INTERVAL_SECONDS` seconds (default 300 = 5 min) until you stop it with `Ctrl+C`.  
Deduplication is active — you won't get re-notified for the same slot within the same session.

To run in the background:

```bash
nohup python3 checker.py > checker.log 2>&1 &
echo "PID: $!"
```

Stop it with `kill <PID>`. Watch the log with `tail -f checker.log`.

> **Note:** The script pauses when your Mac sleeps. For uninterrupted monitoring use Option B.

---

## Option B — GitHub Actions (runs automatically in the cloud)

The workflow at `.github/workflows/check-slots.yml` runs the checker automatically from 01:00–16:00 Munich time (CEST), with no Mac required. It uses a 3-hour cron schedule, with each job running in loop mode for 3.5 hours — ensuring continuous coverage with a small overlap.

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
| `CHECK_INTERVAL_SECONDS` | `300` | Seconds between checks (loop mode only) |
| `HEADLESS` | `true` | Set to `false` to watch the browser (local only) |
| `RUN_ONCE` | `false` | Set to `true` to check once and exit (single-shot use) |
| `MAX_RUNTIME_SECONDS` | `0` | Exit after N seconds (0 = run forever). Set to `12600` in CI (3.5 h) |

---

## Notes

- `.env` is gitignored — your credentials never leave your machine.
- The script re-authenticates automatically if the session expires.
- Unwanted resource categories are filtered out automatically based on internal configuration.

