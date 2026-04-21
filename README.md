# TerrierBot
TerrierBot is the bot for Terrier Hub (Boston University Discord Server)
https://discord.gg/bostonuniversity

## Setup

To setup TerrierBot:
1. Put the bot token into a file called `token.txt`
2. Create a python virtual environment (`python3 -m venv venv`)
3. Enter the virtual environment (`source venv/bin/activate` on bash or zsh systems, `venv\Scripts\activate.bat` on windows cmd, check [https://docs.python.org/3/library/venv.html] for more details)
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
