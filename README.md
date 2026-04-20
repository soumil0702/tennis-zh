# tennis-zh

Monitors the tennis booking page and sends a Telegram message the moment a court slot opens up from 17:00 onwards.

## Setup

### 1 — Install dependencies

```bash
cd tennis-zh
python -m venv .venv
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

Edit `.env` and fill in:

```
ZHS_PASSWORD=your_actual_password
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 4 — Run

```bash
python checker.py
```

The script checks every 5 minutes (configurable via `CHECK_INTERVAL_SECONDS` in `.env`).  
The moment a free slot appears from 17:00 you get a Telegram push notification with a direct booking link.

## Notes

- `.env` is gitignored — your password never leaves your machine.
- The script re-authenticates automatically if the session expires.
- Set `headless=False` in `checker.py` temporarily if you want to watch the browser during debugging.
