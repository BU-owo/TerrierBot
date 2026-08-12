# TerrierBot

TerrierBot is the Discord bot for the Terrier Hub community at Boston University. It combines campus-specific utilities, community tools, and moderation helpers into one bot that can be used with either the `=` prefix or the `/` slash-command system.

## What TerrierBot can do

TerrierBot currently supports:

- BU course and department lookups through the `class` and `search` features
- BU club discovery through `club`
- RateMyProfessors lookups through `rmp`
- Live MBTA Green Line ETA checks through `mbta`
- Community features such as `hello`, `love`, `banner`, `boost`, and `pride`
- Anonymous feedback and moderation tools such as `feedbacksetup`, `warn`, `warncount`, `warninfo`, `mywarns`, and `warnremove`
- Server management features such as the starboard, Positivity Tuesday automation, and ping roles
- Self-service role removal through `leavepolitics`

## Requirements

Before running TerrierBot, make sure you have:

- Python 3.11+ recommended
- A Discord bot application created in the Discord developer portal
- A bot token available either from a `token.txt` file or the `DISCORD_TOKEN` environment variable
- The necessary bot permissions and intents enabled for your server

## Installation

1. Clone or download this repository.
2. Open a terminal in the project folder.
3. Create and activate a virtual environment:

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

4. Install the required dependencies:

```bash
pip install -r requirements.txt
```

## Discord bot setup

1. Go to the Discord developer portal and create a new application.
2. Open the Bot tab and create a bot user.
3. Copy the bot token and store it in one of these places:
   - `token.txt` in the project root, or
   - the environment variable `DISCORD_TOKEN`
4. In the Bot settings, enable the intents needed by the bot, including Server Members Intent and Message Content Intent.
5. Generate an invite URL under OAuth2 > URL Generator with the bot scope and the permissions your server needs.
6. Invite the bot to the target server.

## Running the bot

From the project folder, start the bot with:

```bash
# Windows
venv\Scripts\activate
python bot.py
```

```bash
# macOS / Linux
source venv/bin/activate
python bot.py
```

Slash commands now sync automatically on startup for joined guilds. If needed, an owner can still run `=sync` as a manual fallback.

## Command reference

Most commands support the `=` prefix, and many also support slash commands. The built-in `=help` command provides a quick overview inside Discord.

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
| `=roleboost` / `/roleboost` | Give a booster a role tied to their booster status (booster-role required) |
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
| `=leavepolitics` / `/leavepolitics` | Leave the Politics role/channel (re-apply needed to rejoin) |
| `=sync` | Sync slash commands to the current server (owner only) |
| `=cog load` / `=cog reload` / `=cog unload` / `=cog list` | Manage cogs during development or maintenance (owner only) |

## Permissions and notes

- Positivity Tuesday and the starboard require Manage Server permissions.
- Warning commands require moderation access that fits your server’s workflow.
- Owner-only maintenance commands are available for bot upkeep and debugging.
- The bot stores small pieces of state in `terrierbot.shelve` and reads the token from `token.txt` or `DISCORD_TOKEN` when it starts.

## Troubleshooting

- If the bot does not start, confirm that your token is present and that the file is readable.
- If slash commands do not appear after a restart, run `=sync` while the bot is connected to the server.
- If a feature does not work as expected, verify that the bot has the required permissions in the relevant channel or server.
- If you are developing or reloading cogs, use the owner-only cog commands to test changes without restarting the whole bot.

## Project layout

```text
TerrierBot/
├── bot.py               # Main entry point and help command
├── *.py                 # Individual cog modules for commands and features
├── requirements.txt     # Python dependencies
├── token.txt            # Discord bot token (not committed)
└── terrierbot.shelve    # Small on-disk state store for bot settings
```
