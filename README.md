# TerrierBot

TerrierBot is the Discord bot for the Terrier Hub community at Boston University. It combines useful campus tools with server fun, moderation helpers, and a few community-management features that are easy to use from either the `=` prefix or `/` slash command system.

## What the bot can do

TerrierBot currently supports:

- BU course and department lookups via `class` and `search`
- BU club discovery via `club`
- RateMyProfessors lookups via `rmp`
- Live MBTA Green Line ETA checks via `mbta`
- Community features such as `hello`, `love`, `banner`, `boost`, and `pride`
- Anonymous feedback and moderation helpers such as `feedbacksetup`, `warn`, `warncount`, `warninfo`, `mywarns`, and `warnremove`
- A starboard and Positivity Tuesday automation for server management

## Setup

1. Put your Discord bot token in a file named `token.txt` in the project folder.
2. Create and activate a Python virtual environment.
3. Install the required packages:

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

4. Start the bot:

```bash
python bot.py
```

## Running the bot

From the project folder:

```bash
# Windows
venv\Scripts\activate
python bot.py
```

If you want slash commands to appear in a server, an owner can use the prefix command `=sync` once the bot is running in that guild.

## Command reference

Most commands support the `=` prefix and many also support slash commands. Use the built-in `=help` command for a quick overview.

### Campus and BU tools

| Command | Description |
| --- | --- |
| `=class` / `/class` | Look up BU Bulletin course information |
| `=club` / `/club` | Search Terrier Central clubs |
| `=rmp` / `/rmp` | Search RateMyProfessors for a BU instructor |
| `=search` / `/search` | Search BU courses by school, department, or HUB units |
| `=mbta` / `/mbta` | Check live MBTA Green Line ETAs |

### Community and fun

| Command | Description |
| --- | --- |
| `=hello` / `/hello` | Say hello to the bot |
| `=love` / `/love` | Share some Terrier love |
| `=banner` / `/banner` | Learn about banner submissions |
| `=boost` / `/boost` | See server boost perks |
| `=pride` / `/pride` | Send a Pride message |
| `=starleaderboard` / `/starleaderboard` | Show the most-starred posts |

### Moderation, feedback, and management

| Command | Description |
| --- | --- |
| `=positivity` / `/positivity ...` | Configure Positivity Tuesday automation (Manage Server required) |
| `=feedbacksetup` / `/feedbacksetup` | Post the anonymous feedback prompt |
| `/starboard ...` | Configure the starboard (Manage Server required) |
| `/pingrole` | Ping one of the community roles |
| `=warn` / `/warn` | Warn a member |
| `=warncount` / `/warncount` | List active warnings |
| `=warninfo` / `/warninfo` | Show a user's warning history |
| `=mywarns` / `/mywarns` | Show your own active warnings |
| `=warnremove` / `/warnremove` | Remove a warning |

### Utility and maintenance

| Command | Description |
| --- | --- |
| `=end` / `/end` | See how many days remain until the semester ends |
| `=test` / `/test` | Confirm that the bot is responding |
| `=help` | Show the command overview |
| `=sync` | Sync slash commands to the current server (owner only) |

## Permissions and notes

- Positivity Tuesday and the starboard require Manage Server permissions.
- Warning commands require the ability to manage messages or otherwise fit the server’s moderation workflow.
- Owner-only maintenance commands are available for bot upkeep and debugging.

## Project layout

```text
TerrierBot/
├── bot.py               # Main entry point and help command
├── *.py                 # Individual cog modules for commands and features
├── requirements.txt     # Python dependencies
├── token.txt            # Discord bot token (not committed)
└── terrierbot.shelve    # Small on-disk state store for bot settings
```
