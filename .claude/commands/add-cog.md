---
description: Wire a new cog into TerrierBot
---

A new cog file has been added or referenced. Wire it in fully:

1. **bot.py**
   - Add the cog's name (without the "Cog" suffix) to `cogList`
   - Add it to `defaultCogs` as well, unless told it's optional/manual-load-only
   - Do NOT touch unrelated entries in either list

2. **Help command** (`help_command` in bot.py)
   - Add a line for the new command(s) under the most fitting existing embed field
     (Campus & BU Info / Community & Fun / Moderation & Feedback / Utility / Owner)
   - If it's a mod-only or owner-only command, note that in the help text like the
     existing entries do
   - Match the existing format exactly: `` `=cmd` or `/cmd` `<args>` - description ``

3. **README.md**
   - Add a row to the matching table in the "Command reference" section
   - If it's a whole new category, add a new table + heading consistent with the others
   - Update the "What TerrierBot can do" bullet list at the top if it's a notable feature

4. **Sanity checks**
   - Run `python -m py_compile <cogfile>.py` on the new cog before considering this done
   - Confirm the cog uses `from cogs.logConfig import` (not `from logConfig import`) if it
     imports logConfig
   - Do not refactor or rewrite the cog's own logic — only touch bot.py, help text, and README.md

Ask me for the cog's filename and a one-line description if it's not already obvious from context.