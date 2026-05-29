# TerrierBot
TerrierBot is the bot for Terrier Hub (Boston University Discord Server)
https://discord.gg/bostonuniversity

## Setup

To setup TerrierBot:
1. Put the bot token into a file called `token.txt`
2. Create a python virtual environment (`python3 -m venv ven`)
3. Enter the virtual environment (`source ven/bin/activate` on bash or zsh systems, `ven\Scripts\activate.bat` on windows cmd, check [https://docs.python.org/3/library/venv.html] for more details)
4. Install the required packages (`pip install -r requirements.txt`)

You only need to do this setup once.

## Running

To run TerrierBot:
1. Make sure you're in the python virtual environment (see step 3 of setup)
2. Run with `python bot.py`

## Positivity Tuesday

TerrierBot includes a positivity feature that can post this message at a configurable cadence:

"Happy Positivity Tuesday! You have been selected to make a positive comment toward a member of the server."

Use these commands in a server (requires Manage Server permission):

- `=positivity` shows current status and interval
- `=positivity enable [x]` enables the feature, optionally setting the interval to every x messages
- `=positivity disable` disables the feature
- `=positivity interval <x>` updates the interval to every x messages
MyBU Student (PeopleSoft) and serves it through slash commands.  
Uses Playwright for browser-based SSO + Duo login, SQLite for caching, and
APScheduler to re-scrape every 60 minutes and post change alerts.

### Folder structure (course feature files)

```
TerrierBot/
├── bot.py               ← main entry point (loads all cogs incl. course)
├── courseCog.py         ← slash commands + APScheduler
├── scraper.py           ← Playwright scraper with session.json handling
├── database.py          ← SQLite schema, CRUD, change detection
├── .env                 ← your secrets (gitignored — copy from .env.example)
├── .env.example         ← configuration template
├── session.json         ← saved BU SSO cookies (gitignored, auto-generated)
└── courses.db           ← SQLite database (gitignored, auto-generated)
```

---

## Mac Setup

### 1  Prerequisites

Python 3.11 or newer is required.

```bash
# check version
python3 --version
# install via Homebrew if needed
brew install python@3.12
```

### 2  Virtual environment

```bash
cd /path/to/TerrierBot
python3 -m venv ven
source ven/bin/activate
```

### 3  Install dependencies

```bash
pip install -r requirements.txt
```

### 4  Install Playwright + Chromium

```bash
playwright install chromium
```

This downloads a ~150 MB Chromium binary managed entirely by Playwright.

### 5  Create a Discord bot

1. Go to <https://discord.com/developers/applications> → **New Application**.
2. **Bot** tab → **Add Bot** → copy the token.
3. Enable **Server Members Intent** (needed for watch-DM delivery).
4. **OAuth2 → URL Generator**: scopes `bot` + `applications.commands`,
   permissions `Send Messages` + `Embed Links` → invite to your server.

### 6  Configure `.env`

```bash
cp .env.example .env
nano .env   # or open in your editor
```

| Variable | Description |
|---|---|
| `DISCORD_TOKEN` | Bot token from step 5 |
| `ALERT_CHANNEL_ID` | Channel ID for change-alert embeds (right-click → Copy ID) |
| `SEMESTER_CODE` | PeopleSoft term value for Fall 2026 — **see note below** |
| `SEMESTER_LABEL` | Display label stored in DB (default: `Fall 2026`) |
| `DEPARTMENTS` | Comma-separated subject codes, e.g. `CS,MA,EC,PY` |
| `SCRAPE_INTERVAL_MINUTES` | Re-scrape cadence in minutes (default: `60`) |
| `DEBUG_SCRAPER` | `true` to dump screenshots/HTML on parse errors |

> **Finding `SEMESTER_CODE`:** On first run a real browser opens for SSO.
> Once logged in, right-click the **Term** dropdown on the Class Search page,
> choose Inspect, find the `<option value="...">` for *Fall 2026*, and paste
> that value into `SEMESTER_CODE`.  Typical BU format: a 4-digit number.

The bot still falls back to `token.txt` if `DISCORD_TOKEN` is not set in `.env`.

### 7  Run the bot

```bash
source ven/bin/activate   # if not already active
python bot.py
```

**First run only** — a visible Chromium window opens:

1. Sign in with your BU Kerberos ID and password.
2. Complete Duo MFA.
3. Wait until the Class Search page fully loads.  
   TerrierBot detects this automatically and saves cookies to `session.json`.

All subsequent runs are fully headless.

---

## Slash commands (course feature)

| Command | Description |
|---|---|
| `/courses department:CS` | All Fall 2026 sections for a department as rich embeds |
| `/seats course:CS112` | Open / total seats for every section of a course |
| `/watch course:CS112` | Subscribe to DM alerts when a course changes |
| `/unwatch course:CS112` | Remove a watch subscription |
| `/lastsynced` | Timestamp and stats from the last scrape |

Each course embed shows: course number, title, instructor, days/time,
building/room, units, and a visual seat bar (open / total).  
Change alerts fire for **seats, instructor, schedule, or location** changes,
broadcasting to `ALERT_CHANNEL_ID` and DMing all watchers.

---

## Troubleshooting selectors

If BU updates PeopleSoft and scraping breaks, set `DEBUG_SCRAPER=true` in `.env`.
The scraper will save `debug_<DEPT>.png` and `debug_<DEPT>.html` on parse errors.
Open them, find the correct element IDs, and update the `_SEL` dict in `scraper.py`.

---

## Original Setup

To setup TerrierBot (original / existing features):
1. Put the bot token into a file called `token.txt`  
   *(or use `DISCORD_TOKEN` in `.env` — preferred)*
2. Create a python virtual environment (`python3 -m venv ven`)
3. Enter the virtual environment (`source ven/bin/activate` on bash or zsh systems, `ven\Scripts\activate.bat` on windows cmd, check [https://docs.python.org/3/library/venv.html] for more details)
4. Install the required packages (`pip install -r requirements.txt`)

You only need to do this setup once.

## Running

To run TerrierBot:
1. Make sure you're in the python virtual environment (see step 3 of setup)
2. Run with `python bot.py`

## Positivity Tuesday

TerrierBot includes a positivity feature that can post this message at a configurable cadence:

"Happy Positivity Tuesday! You have been selected to make a positive comment toward a member of the server."

Use these commands in a server (requires Manage Server permission):

- `=positivity` shows current status and interval
- `=positivity enable [x]` enables the feature, optionally setting the interval to every x messages
- `=positivity disable` disables the feature
- `=positivity interval <x>` updates the interval to every x messages
