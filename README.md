# tennis-zh

Monitors the [shz  tennis booking page](https://kurse.zhs-muenchen.de/de/product-offers/21114da0-4246-42b1-bab6-8d7ac49bb14f) and sends a Telegram notification the moment a clay court slot opens from 17:00 onwards.

- Checks all clay courts (Tennisplatz 2–17), skips Kunststoff courts (20/21/22)
- Filters to today's date and slots starting at 17:00 or later
- Two run modes: **loop mode** (local Mac) and **single-run mode** (GitHub Actions CI)

---

## Option A — Run locally on your Mac

### 1 — Install dependencies

```bash
cd tennis-zh
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

Edit `.env`:

```
ZHS_EMAIL=your_zh_email
ZHS_PASSWORD=your_zh_password
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

The workflow at `.github/workflows/check-slots.yml` runs the checker automatically every 15 minutes from 01:00–16:00 Munich time (CEST), with no Mac required.

### 1 — Add repository secrets

Go to your repo on GitHub → **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret name | Value |
|---|---|
| `ZHS_EMAIL` | Your login email |
| `ZHS_PASSWORD` | Your password |
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |

### 2 — Push the workflow file

The workflow activates automatically once `.github/workflows/check-slots.yml` is on the default branch (`main`). After pushing, go to the **Actions** tab on GitHub — the workflow should show a schedule trigger.

### 3 — Manual trigger

On the Actions tab → click **Tennis Slot Checker** → **Run workflow** to test it immediately.

> **Note:** In single-run mode (CI), there is no deduplication between runs. If a slot stays open, you'll receive a notification every 15 minutes until you book it — this is intentional.

---

## Configuration reference

| Variable | Default | Description |
|---|---|---|
| `ZHS_EMAIL` | required | login email |
| `ZHS_PASSWORD` | required | login password |
| `TELEGRAM_BOT_TOKEN` | required | Telegram bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | required | Your Telegram chat ID |
| `CHECK_INTERVAL_SECONDS` | `300` | Seconds between checks (loop mode only) |
| `HEADLESS` | `true` | Set to `false` to watch the browser (local only) |
| `RUN_ONCE` | `false` | Set to `true` to check once and exit (used by CI) |

---

## Notes

- `.env` is gitignored — your credentials never leave your machine.
- The script re-authenticates automatically if the ZHS session expires.
- Clay courts only: Tennisplatz 20/21/22 (Kunststoff) are skipped automatically.
- checker.pygold (is the gold version that works in both ci (scheduled), terminal )...the issue is that the scheduled runs dont really work properly...the freuqncy is really bad

