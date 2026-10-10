# Telegram Form Control Bot (Python)

A Telegram bot that queues form links, runs your form engine, shows preview, and only submits after your tap unless auto submit is enabled.

## What is included

- Python 3.11+ async bot using `python-telegram-bot`
- Strict allowlist by Telegram user ID
- URL detection with queueing one-by-one
- Preview with screenshot + summary + actions
- Edit flow with inline buttons and flagged field prompts
- Submit / retry / cancel flow
- Special handling for captcha, login-needed, wallet-connect, scam warning, timeout, crashes
- SQLite storage for applications, answer cache, settings, and profile fields
- CSV export command
- Clean engine adapter interface with placeholders

## Project files

- `main.py` - startup and config
- `handlers.py` - commands, messages, buttons
- `queue_manager.py` - sequential worker and job state
- `engine_adapter.py` - 4-function interface wrapper (placeholder)
- `database.py` - SQLite data access
- `messages.py` - all chat text in one place
- `.env.example` - env template
- `requirements.txt` - dependencies

## Setup

```bash
cd telegram_bot
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

Fill `.env`:

- `BOT_TOKEN`
- `ALLOWED_USER_ID` (your own Telegram user id)

## Run

```bash
python main.py
```

---

## Build order checklist you asked for

### Step 1: Skeleton with user lock

Run:
```bash
python main.py
```

Test checklist:
- Bot starts without errors
- `/start` works for your user id
- Another user gets no reply at all

### Step 2: Link handling and queue

Run:
```bash
python main.py
```

Test checklist:
- Send one URL and get instant "on it" message
- Send multiple URLs in one message and all get queued
- Queue status visible with `/status`
- Duplicate URL warning appears with Continue/Skip

### Step 3: Preview and buttons

Run:
```bash
python main.py
```

Test checklist:
- Preview screenshot arrives
- Summary includes form title, answers, flagged fields
- Long summary splits into multiple messages
- Submit/Edit/Cancel buttons appear

### Step 4: Editing flow

Run:
```bash
python main.py
```

Test checklist:
- Tap Edit, choose field, send new value
- Preview refreshes after edit
- Flagged fields prompt one-by-one
- `/skip` works for optional flagged fields

### Step 5: Special situations

Use URLs containing keywords to simulate placeholders:
- `captcha` -> captcha pause
- `login` -> login needed
- `wallet` -> wallet connect/manual
- `timeout` -> timeout warning

Test checklist:
- Bot never goes silent
- Captcha sends Done button and resumes on tap
- Warnings are short and clear

### Step 6: Commands and database

Run:
```bash
python main.py
```

Test checklist:
- `/recent`, `/search`, `/export` return data
- `/autosubmit on|off` updates behavior
- `/profile` shows and edits fields
- DB file is created and grows with usage

---

## Connect your real Playwright engine

Keep bot code untouched and only replace internals in `engine_adapter.py`:

- `prepare_form(url)`
- `update_answer(job_id, field_label, new_answer)`
- `submit_form(job_id)`
- `cancel_job(job_id)`

Return the same dataclass shapes.

## Safety notes

- Never provide seed phrase/private key
- The bot rejects those edits
- Access is limited to one Telegram user id
- Secrets are only from `.env`

---

## Hosting options for always-on run (Playwright friendly)

### 1) Railway (cheap, easiest)

Pros:
- Simple deploy from GitHub
- Can run long-lived worker process
- Supports Playwright with Docker

Limits:
- Free tier is limited and may sleep or run out fast
- Usually low-cost paid usage is needed for reliable 24/7

Best for: low effort deployment with minimal ops.

### 2) Fly.io (low cost, flexible)

Pros:
- Good for long-running processes
- Can run Chromium in container
- More control over resources

Limits:
- Slightly more setup than Railway
- Free allowance changes over time and can be tight

Best for: builder-friendly infra with good control.

### 3) Self-host on cheap VPS (Hetzner/Contabo/etc.)

Pros:
- Full control
- Stable for Playwright + persistent sessions
- Usually best price per performance

Limits:
- Not free
- You handle updates, uptime, and security

Best for: reliable production and less platform limits.

### Honest note about "free"

Pure free serverless hosts often fail for Playwright because browser binaries, memory, and long worker runtime are restricted. For this use case, very cheap always-on VM/container is usually the practical answer.
