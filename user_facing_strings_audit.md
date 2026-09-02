# TerrierBot — User-Facing Strings Audit

Every string a member or mod can actually see in Discord: command replies, embed
titles/descriptions/fields/footers, DM text, button/select labels, modal labels
and placeholders, and error messages. Grouped by file, then by the
function/command/class it lives in. Logging statements, code comments, and
internal/variable names are excluded. Nothing has been reworded — this is
extraction only. Placeholders are left as `{...}` / f-string expressions.

---

## `bot.py`

**`on_ready` (startup message, once per hour max)**
- "Hello, I have restarted and am ready to help! 🐾"

**`on_command_error`**
- "Too many people running this command at a time" (MaxConcurrencyReached)
- "{type(error.original).__name__}: {error.original}" (CommandInvokeError)
- "Sorry, you can't run that!" (NotOwner)
- "That's not a real person." (MemberNotFound / UserNotFound)
- "You are on cooldown. Chill out for {error.retry_after}s" (CommandOnCooldown)
- "Missing argument {error.param}" (MissingRequiredArgument)
- "Error - {type(error).__name__}: {error}" (fallback)

**`on_app_command_error`**
- "{type(error.original).__name__}: {error.original}" or `str(error)` (sent ephemerally)

**`status_command` (`/status`)**
- "This command can only be used in a server."
- "You do not have permission to run that!"
- Embed title: "TerrierBot Status"
- Field names: "Uptime (this run)", "Uptime % (UptimeRobot)", "Git Commit", "Python", "Last Restart (UTC)", "Loaded Cogs", "Recent Errors"
- "24h: {..}%  •  7d: {..}%  •  30d: {..}%" / "Unavailable"

**`sync` (`=sync`)**
- "Synced {len(synced)} slash command(s) to this server."

**`disconnect` (`=disconnect`)**
- "Bye!"

**`delete` (`=delete`)**
- "I've never messaged here!"

**`cog` group (`=cog`)**
- "Invalid cog command"

**`loadCog` / `unloadCog` / `reloadCog` (`=cog load|unload|reload`)**
- "Loaded Cog \"{}\"" / "Unloaded Cog \"{}\"" / "Reloaded Cog \"{}\""

**`listCogs` (`=cog list`)**
- "**Loaded Cogs:**\n{}\n**Unloaded Cogs:**\n{}"

---

## `cogs/utility/helpCog.py`

**`help_command` (`=help`) — embed**
- Title: "🐾 TerrierBot Commands 🐾"
- Description: "Use the `=` prefix or `/` slash commands where available!"
- Field "──── ⋆⁺₊✧🐾✧₊⁺⋆ ────\n✧ Moderation ✧":
  - "🐕 `/mywarns` — see your active warnings"
  - "📝 `/warnappeal` — appeal one of your warnings"
  - "🤫 `/snitch` — send an anonymous, silent alert to the mods"
- Field "──── ⋆⁺₊✧🐾✧₊⁺⋆ ────\n✧ Tools ✧":
  - "📚 `=class` / `/class` — look up a BU course from the Bulletin"
  - "⭐ `=rmp` / `/rmp` — look up a professor on RateMyProfessors"
  - "🐾 `=club` / `/club` — search for BU clubs on Terrier Central"
  - "🚋 `=mbta` / `/mbta` — check how far Green Line trains are from a station (leave blank for the BU stops)"
  - "🌈 `=mbtgay` / `/mbtgay` — track down the MBTA Pride Train (car #3706), if it's out riding today"
  - "📣 `/pingrole` — ping one of our community roles — events, food, gaming, and more — with a message"
  - "🔒 `=lockin` / `/lockin` — lock yourself out of the server for a set time to focus (can't be undone early)"
  - "⏳ `=lockinleft` / `/lockinleft` — check how much time is left on your lock-in"
  - "🥰 `=uwu` / `/uwu` — uwu-ify your own message"
- Field "──── ⋆⁺₊✧🐾✧₊⁺⋆ ────\n✧ Birthdays ✧":
  - "🎉 `=birthday set` / `/birthday set` `<month> <day>` — save (or update) your birthday"
- Footer: "⋆⁺₊✧ ✧₊⁺⋆ — woof! — ⋆⁺₊✧ ✧₊⁺⋆"

---

## `cogs/utility/testCog.py`

**`test` / `test_slash`**
- "This is a test cog by so selene featuring owo"

---

## `cogs/utility/membersCog.py`

**`exportmembers`**
- "Here are the server members:"

**`exportprunecandidates`**
- "Found {candidate_count} prune candidates using role filter only."

**`exportmembersbycategory`**
- "Could not find `{self.category_roles_csv_path}` in the bot folder."
- `str(exc)` (ValueError from CSV load)
- "Here is the categorized member export:"

---

## `cogs/utility/embedCog.py`

**`_build_embedreg_sequence` (`=embedreg`) — 4-embed sequence**
- Embed 1 title: "Incoming Student Course Registration is SOON (June 9th and June 11th @ 9am EST)"
- Embed 1 description: "My little gumdrops,\n\nWelcome to BU! ... " (full onboarding message, transfer/first-year registration times, "View your registration time in your timezone: Transfer Students: <t:...:t> / First-Year Students: <t:...:t>")
- Embed 2 title: "✅ Your Tasks for RIGHT NOW! — Part 1: Figure out what classes to take!"
  - Field "College Guides": guide links per school + "Some are more helpful than others..."
  - Field "The Bulletin": "This is called [the bulletin](...). It is your best friend. ..."
  - Field "AP / IB Scores": guidance + credit chart links
  - Field "First-Year Writing": TOEFL note + WR120 link
  - Field "Wtf is the HUB?": HUB explainer, "26 requirements", transfer note
  - Field "Course Load": "A typical course load is 16 credits... I don't recommend taking under 16 your first semester."
  - Field "Other Notes": "Your schedule will be unique... DM me your major and any AP/IB credits you expect and I can give you a suggestion! I respond faster and more accurately lol"
- Embed 3 title: "✅ Your Tasks for RIGHT NOW! — Part 2: Pick your times and professors + Register!"
  - Fields "1. Check for Holds", "2. Learn how to use MyBU", "3. How to pick classes", "4. Register!", "Full classes?" (full body text each)
- Embed 4 title: "*** Tips from me! ***"
  - Description: "**You are undecided.** ... **Flexibility is key.** ... **You are not forced to register within your major...** ... **Build Community!** ... **FY101** is a cool 1-credit option... **Shop.** ... Good luck jellybeans! ❤️\n\n— OwO"

**`_build_embedhousing_sequence` (`=embedhousing`) — 5-embed sequence**
- Embed 1 title: "🏠 Housing FAQ"; description: "Got housing questions? Here's everything you need to know "
- Embed 2 title: "🏠 Housing FAQ — Part 1: The Basics"
  - "Wait I hate my housing, how do I change it?" — "You really can't, but here's what you can try: 1. Email housing and ask nicely 2. Find someone to direct swap with 3. Deal with it"
  - "Is [insert building name] really that bad?" — "All buildings have their pros/cons... So no, it's not that bad."
  - "What is my dorm assignment like?" — link out
  - "How do I find my roommate's email?" — directory/social lookup tips
  - "What do I pack?" — packing list links
- Embed 3 title: "🏠 Housing FAQ — Part 2: Logistics & Living"
  - "Fenway/West/Danielsen is SOOOOOO FAR from my classes!!!! What do I do?" — "There are shuttles, and walking is great... None of it is really that far!"
  - "How do I survive in the summer without AC?" — "Fans. Many fans. ... Know that you'll be complaining about the cold in 2 weeks...."
  - "How do I make friends?" — floor/RA social tips, "KEEP YOUR DOOR OPEN WHEN YOU ARE IN!"
  - "What if I don't like my roommate???" — conflict-resolution guidance, RA mediator note
- Embed 4 title: "🏠 Housing FAQ — Part 3: Stuff & Rules"
  - "Do I need to bring a fridge or microwave?" — microfridge rules
  - "Can I bring my pet!!!!!" — "Girl. No."
  - "Who's going to stop me from bringing beer, my pet hamster, and a microwave?" — BU room-entry rights explainer, "Please don't be an idiot."
  - "Can I order Amazon to my dorm?" — "Yes! Your shipping address is in your housing portal."
  - "Wait, housing came out?" — "Yes, for some people. Be patient if you haven't received it!"
- Embed 5 title: "🚿 I'm scared of the communal bathrooms!"; description: "That's completely normal! It just takes some getting used to. Here are some tips:"
  - "Showers (cs majors please disregard)" — shower shoe/caddy/robe tips
  - "Toilets & Sinks" — cleanliness reminders
  - "General" — "Do you care when you see someone brushing their teeth or shaving at a sink? No? Then why do you think anyone else cares about you..."

**`_build_embedmodhandbook_sequence` (`=embedmodhandbook`) — 7-embed sequence**
- Embed 1 title: "🛡️ Terrier Hub Moderator Handbook"; description: mission statement + "As moderators, we:" bullet list; field "Contents" (numbered TOC); footer "Last updated: August 2026"
- Embed 2 title: "✅ Responsibilities & Moderation Approach"
  - Field "Responsibilities" — bullet list incl. "Assassinate scammers, bots, and spam quickly"
  - Field "Moderation Approach" — fairness/impartiality bullets
  - Field "Engaging Without Bias" — full paragraph
- Embed 3 title: "⚖️ Punishments"
  - Field "For Community Members" — Verbal Warning / Delete Message / Time Out / Warning / Ban blocks (When/Vote/Method for each)
  - Field "For Bots" — "TerrierBot `/ban` ... When in doubt, time out."
  - Field "Warnings as a Log" — "a warning isn't a strike toward an automatic ban, it's a log entry..."
- Embed 4 title: "📜 The Rules"; description: numbered rules 1–9 + "Always follow [Discord Community Guidelines](...)."
  - Field "📚 Academic Integrity Policy" — "ZERO TOLERANCE... Any academic misconduct will result in a ban."
- Embed 5 title: "📋 Policies & Moderator Tools"
  - Fields "Teamwork", "Professionalism", "Server Practices", "Moderator Tools", "Moderation Commands" (full bullet bodies)
- Embed 6 title: "🗣️ Communication, Voting & Appeals"
  - Fields "Communication", "Voting", "Appeals", "Confession Bans" (full bodies)
- Embed 7 title: "🎓 Term Length & Mod Channels"
  - Field "Term Length" — Moderator Emeritus explainer
  - Field "Mod Channels" — channel list with descriptions ("please ignore" for the doomer channel)

**`_build_embedrules_sequence` (`=embedrules`)**
- Title: "Terrier Hub Rules"; description: numbered rules 1–9 + Discord Guidelines link
- Field "📚 Academic Integrity Policy" — zero-tolerance/ban text
- Field "⚖️ Punishment" — Timeouts/Warning Policy/Ban Policy + "*Use `/warnappeal` to appeal a warning.*"
- Field "📣 Reporting" — "Ping **@Moderator** for help.", "`/snitch` for an immediate, silent alert.", "Create a ticket in {channel} to discuss a concern.", "Use the Anonymous Feedback Form for anonymous feedback."
- Footer: "This is an unofficial, student-run server not affiliated with Boston University. Posts here don't reflect BU's views. Participate at your own discretion."

**`EmbedModal` (`/embed`)**
- Modal title: "Send Embed"
- Field labels/placeholders: "Title" / "Embed title (optional)"; "Body (supports # headings, **bold**)" / "# Big heading\n## Smaller heading\n\nRegular text, **bold**, *italic*, > quote..."; "Body (cont.)" / "Continued text here..."; "Color (hex, e.g. #cc0000)" / "#cc0000"; "Footer" / "Footer text (optional)"
- "Invalid color — use hex like `#cc0000`."
- "Embed sent! ✅"

**`embed_slash` / `send_embed` (`=embed`)**
- "That command is not for you." (non-owner)
- "Provide JSON inline or attach a .json/.txt file."
- "Invalid JSON: {e}"
- "JSON must be an object `{...}` or array `[...]`."
- "No valid embed objects found."

---

## `cogs/campus/classCog.py`

**`lookup_course` (error paths, surfaced by `=class`/`/class`)**
- "Please give a course code. Example: =class CAS CH 101"
- "I couldn't understand that course code. Try: =class CAS CH 101, =class CASCH101, or =class CH 101"
- "Not a real school code."
- "We don't have that school code '{school}'."
- "{school} does not use subject code {subject}."
- "I don't know that subject code '{subject}'. Include school code, e.g. =class CAS {subject} 100"
- "Subject code {subject} is in multiple schools: {', '.join(ambiguous)}. Please include school code to clarify! e.g. =class CAS {subject} {number}"
- "I don't have a bulletin path mapping for {school} yet."
- "Bulletin lookup failed: {type(exc).__name__}: {exc}"
- "Course not found on the BU Bulletin: {school} {subject} {number}\n{url}"

**Embed built by `lookup_course`**
- Field names: "Units", "Prereqs", "BU Hub", "Description", "📅 Fall 2026"
- "_Not offered Fall 2026._"
- "_+{n} more lecture section(s) — use 📋 All Sections_"
- "_{n} lab/discussion section(s) — use 📋 All Sections_"

**`_AllSectionsButton`**
- Button label: "All Sections"
- Embed title: "Fall 2026 — {school} {subject} {number}"
- Field names: "Lectures ({n})", "Labs / Discussions ({n})"

**`_RMPButton`**
- "RMP cog is not loaded."
- "No RMP data found."

**`class_` / `class_slash`**
- "Unknown class lookup error."

---

## `cogs/campus/endCog.py`

**`build_message` (hourly countdown, `=end`/`/end`)** — one random line is posted per bucket; every line in each bucket:

- *Commencement day:*
  - "🎓 **IT'S ALL UNIVERSITY COMMENCEMENT DAY!!!** Good job gamers!"
  - "🏛️ **TODAY IS COMMENCEMENT!** Time to go stand in the field and feel hot :) because it is summer"
  - "🎊 **COMMENCEMENT DAY HAS ARRIVED AND I AM GOING FERAL!!!** ARF ARF WOOF BARK GRRRRRRRRRRRRR MEOW MEOW ARF ARF BARK GROWL ARRRRGGGG WOOF"
  - "🐾 **TODAY WE GRADUATE.** Unless youre a silly freshman! Because they do not graduate yet :)"
  - "🎺 **ALL UNIVERSITY COMMENCEMENT!!!** GO GET A JOB now haha members of the workforce XD"
  - "🥹 **IT IS COMMENCEMENT DAY.** You get ur diploma mailed to you btw the convocation one is fake LMAO!! 🐾"
  - "🎶 **COMMENCEMENT DAY BABYYYYY.** I'm gona pee myself in excitement. 😭🐾"
  - "🏅 **ALL UNIVERSITY COMMENCEMENT IS TODAY.** GO GET HEAT STROKE! 🥵"
  - "🐾 **TODAY YOU BECOME AN ALUMNI.** u should probably change ur discord role hehehehehe!!! 🎓📧"
- *Commencement week (templated on days left):*
  - "🎉 It's Commencement week! All University Commencement is in **{n}**. You should probably take photos or soomething"
  - "🥂 The celebrations have begun! Big day in **{n}**. Congrats to all future unemployed homeless people heheh  🐾"
  - "🎓 Commencement week is HERE. Big day in **{n}**. You should drink. Water? Choo choo 😭🚇"
  - "🌸 **{n}** until All University Commencement. Are you gonna go?. 🐾"
  - "🎊 We are **{n}** away from the big graduation ceremony YIPPEE 📸✨"
  - "🏛️ **{n}** until Commencement. You should take photos and stuff to remember the week or smyn? 📷😭"
  - "🎓 Commencement week!! **{n}** until the big day. Consume alcohol. 📸🐾"
  - "🥳 We are SO close. **{n}** Just like my ex wife RIP honey. 🐾"
  - "💐 **{n}** until Commencement. ooga booga ooga booga. 😭🙏"
  - "🎓 **{n}** until the big ceremony. DIscord dot com slash bostonuniversity. 🐾"
  - "🏛️ **{n}** until you are officially an alumni. I'm so emotional im crine. 😭☀️"
- *Finals over:*
  - "🎊 **FINALS ARE OVER!!!** You did it!!!! I hope you passed!!!!!!!!!!! 🎺🥁🎸"
  - "🥳 **THE LAST FINAL IS DONE.** You should probably burn all of your notes heheheh fire emoji ahahahaha. 🏁"
  - "🚨 **FINALS ARE FINISHED. RETURN TO YOUR NORMAL LIVES.** HAHAH IT SAYS NORMAL. Like Kass? fonny 🌿😭"
  - "💀 **YOU SURVIVED FINALS WEEK.** Unless you are dead now. In which case, you are not alive 🐾👑"
  - "🎉 **IT'S OVER IT'S OVER IT'S OVER!!!** JUMP INTO THE CHARLES RIVER NOW. 🥂"
  - "📚 **FINALS: DEFEATED.**  Good job gamers🍕"
  - "🏆 **THE FINAL FINAL HAS BEEN EATEN.**. nom nom nom nom nom 🕊️✨"
  - "🎊 **THE FINALS HAVE BEEN ENDED.** Take a shower. You stink. 🌿😭"
  - "🥳 **FINALS ARE DONE BABYYYYYYY.** I forgor wot i learned. 🐾🎉"
  - "💤 **NO MORE FINALS.** Nap time loserssssssss. 😴✨"
  - "🏁 **YOU MADE IT THROUGH FINALS.** You deserve a sweet treat. 😅☕"
  - "🎺 **FINALS ARE OVER.** BARK BARK BARK WOOF WOOF CONGRATS!!! 🐾🎊"
- *Last day of finals:*
  - "🏁 **IT'S THE LAST DAY OF FINALS!!!** mraowww 🐾🎊"
  - "😤 **TODAY IS THE LAST DAY OF FINALS.** im almost there aughhh. 🐾"
  - "🎊 **LAST DAY OF FINALS BABYYYYYYY.** YOU ARE SO CLOSE. 🐾😭"
  - "🧠 **ONE MORE FINAL.** glup glup glup glup 💙"
  - "🔥 **IT IS THE LAST DAY OF FINALS.** yippee!!!! most of yall are already done 📚🐾"
  - "😤 **LAST FINAL DAY!!!** Take a nap. 😴✨"
  - "💀 **THE END IS NEAR.** FINISH 🏁🎊"
- *Finals in progress (templated on day number / days left):*
  - "📝 Finals day {n}. **{n}** until it's all over. Are you alive?. ☕💪"
  - "😤 **{n}** left of finals. drink alochol 🧠"
  - "⚡ Finals are happening and so are you. **{n}** to go. The AI wrote this but i leaves it cuz funny. 🔥"
  - "💀 Finals day {n}. We are **{n}** from done. Lock in bitch. 🪑😭"
  - "🫠 Day {n} of finals. **{n}** remaining. Your brain is a sponge and the sponge is wet and the floor is lava. Claude wrote that. 🧠"
  - "☕ Finals day {n}. **{n}** left. Inject caffeine like heroin ⚡"
  - "😵 It is finals day {n} and we have **{n}** to go. You gonna survive bruv? 🐾"
  - "🔥 Finals day {n}. **{n}** days until it ends. 102838123 days until profs finish grading the exams. 😤"
  - "☕ Shoutout to celsius. Day {n} of finals. **{n}** left. Mmmmm celsius 🙏"
  - "📝 Finals day {n}. **{n}** left. Reminder: you are not failing. Gosh youre a genius. 🧠✨"
  - "😤 Finals day {n}. **{n}** left. Do you think youre gonna pass? 💪"
  - "🙈 Finals day {n}. **{n}** left. You should drop your class that you hate. 🙈"
  - "🥤 Finals day {n}. **{n}** until it's over. Don't pull all nighters. 💀"
  - "😵 It is finals day {n} and **{n}** remain. Don't do drugs. 🕯️"
  - "📝 Finals day {n}. **{n}** left. Drink a monster bitch. 🐾💪"
  - "☕ Day {n} of finals. **{n}** remaining. How many red bulls have you had kit??? ⚡😅"
  - "💀 Finals day {n}. **{n}** to go. MEOW MEOW MEOW KITBY. 📚🌙"
  - "🧠 Day {n}. **{n}** left of finals. Idk what a neuron is cuz im not a lame bio major but you might! 🔥"
  - "😤 Finals day {n}. **{n}** remaining. Close TIKTOK you stupid braindead zoomer! 👀📖"
  - "🎯 Finals day {n}. **{n}** to go. You got this muscle mommy! 💙🐾"
  - "😫 Day {n} of finals. **{n}** left. SCREEEEEEEEEEECHHHHHHH. 😱📚"
  - "🔋 Finals day {n}. **{n}** remaining. drink watah you pissah! 💧"
  - "😤 It's day {n}. **{n}** until we're free. eepy. 😴"
  - "🎪 Finals day {n}. **{n}** to go. My final week. 🎭"
  - "🧠 Day {n}. **{n}** left. should've majored in art history smh. 😵"
  - "💪 Finals day {n}. **{n}** remaining. YOUVE GOT THIS. 🐾"
  - "☕ Day {n} of finals. **{n}** to go. redbull is a food group??? 🤔"
  - "🌙 Finals day {n}. **{n}** until the end. Take a power nap! 😭"
  - "🔥 Day {n}. **{n}** left of finals. You're killing it king! ⚔️"
  - "📖 Finals day {n}. **{n}** remaining. No pressure or anything though. 😅"
- *Finals start today:*
  - "📝 **FINALS HAVE BEGUN.** LOCK THE FUCK IN 😅"
  - "😱 **IT'S FINALS SEASON, BABY.** you got dis gumdrops!!!1 🐾"
  - "☕ **FINALS START TODAY.** suffering time YIPPEEEEEEEEEE"
  - "📚 **FIRST FINAL DAY. LET'S GOOOOO.** YOU BETTER PASS. 🐾🔥"
  - "😤 **FINALS START NOW.** You're a genius. Gosh. 🧠💙"
  - "🧠 **TODAY FINALS BEGIN.** Final days or my finals day. 📚🐾"
  - "🔥 **FINALS SEASON.** If you dont have finals, you probably have projects you silly humanities major. 🐾☕"
- *Study period:*
  - "📖 Study period day {n}. Finals in **{n}**. Lock in 🖤📚"
  - "😬 Study period is upon us. **{n}** until finals begin. TAKE NOTES AND STUDY. ✍️"
  - "☕ **{n}** until finals. STOP. 🔥"
  - "🕯️ Study period day {n}. **{n}** until finals. Be sober. Eat. 🍕📚"
  - "📖 Study period day {n}. **{n}** until finals. STUDY BITCH STUDYC BTUCH. 💧📚"
  - "😤 Day {n} of study period. **{n}** until finals start. Touch grass and shower you stinker. 🌿"
  - "☕ Study period day {n}. Finals in **{n}**. Review your notes if you actually paid attention in class not playing Google Snake 📝😅"
  - "🕯️ Day {n} of study period. **{n}** until finals begin. MAKE SURE UR SLEEPING. 😴🌙"
  - "🧠 Study period day {n}. **{n}** until it's death time. 🐾💪"
- *Last day of classes:*
  - "🎉 **TODAY IS THE LAST DAY OF CLASSES!!!** TIME to LOCK IN for finals!!!!!!! 🏃‍♂️💨"
  - "🔔 **LAST. DAY. OF. CLASSES.** Consume an alcoholic beverage if legal. 🫡"
  - "📚 **IT'S THE LAST DAY OF CLASSES!** YIPPE YIPPEEE YYIPPEEEEEEEEEE"
  - "😭 **IT'S THE LAST DAY OF CLASSES!!!** I AM NUMB INSIDE AHA. 🐾"
  - "🔔 **THE LAST DAY OF CLASSES IS TODAY.** Congratulations on surviving my goat!!! 🐾🎉"
  - "😤 **IT IS THE LAST DAY OF CLASSES!!!** no more skoo! 🔥"
  - "🎊 **LAST DAY OF CLASSES WAHOOOO.** time to start those papers hehehehe. 📚😅"
  - "🐾 **TODAY IS THE LAST DAY OF CLASSES!!!** You smelly. 😭✨"
  - "💙 **LAST DAY OF CLASSES HAS ARRIVED GAMERS.**. 🏁🐾"
  - "📚 **IT'S THE LAST DAY OF CLASSES!** YOU DID IT BABYYYYYYYYY"
  - "📚 **IT'S THE LAST DAY OF CLASSES!** this is so exciting yayayaya"
  - "📚 **CLASSES ARE OVER TONIGHT!** Celebrate a bit before it is lock in time :)"
- *Weekend countdown (templated, day_name):*
  - "🌅 Happy {day}! No classes today, but you still gotta lock in. **{n}** until the last day of classes. 😴"
  - "🛌 Weekend time! **{n}** until classes end. Touch some grass. 🌿"
  - "☀️ It's {day}. **{n}** left of classes. WWAHHHHHHHHHHHHH. 🕊️"
  - "😴 It's {day} and that means no class. **{n}** until the last day of classes. Thank rhett. 🐾"
  - "🛋️ It's {day}! Rest up buttercup. **{n}** until the last day of classes. 💤🐾"
  - "🌿 Happy {day}! **{n}** until classes are done. Go outside and hunt for baby wabbit. ☀️"
  - "🎮 {day} detected! **{n}** left of classes. teehee. 🐾"
  - "☕ It's {day}. **{n}** until the last day of classes.. 🥞😌"
  - "😴 Weekend!!! **{n}** until the last day of classes. 🔋🐾"
- *1 day left:*
  - "🫡 **1 day left until the last day of classes.** Please please please please hurry up. 🚄💨"
  - "😤 **TOMORROW is the last day of classes.** ONE. MORE. DAY. I think you can survive this. 🐾"
  - "🚨 **1 DAY.** The last day of classes is TOMORROW. ALMOST THERE LOSERSSSSSSSSSSS. 💙"
  - "😭 **TOMORROW IS THE LAST DAY OF CLASSES RAHHHHHHHH.** just gonna survive 1 more! 🐾"
  - "🔥 **24 HOURS. THAT'S ALL.** LOCK IN BITCHES IT IS ALMOST OVER. 💪"
  - "🔥 **{n}** until the last day of classes. TOWOMOROWO!!!!!!!!!!!!!!!!!!! 👃✨"
  - "🚨 **ONE SINGLE DAY OF CLASSES REMAINS.** You are insane for making it this far honestly. 🐾"
  - "💙 **1 DAY LEFT UNTIL THE LAST DAY OF CLASSES.** I'm not crying you're crying. 😭🐾"
  - "🔥 **TOMORROW IS THE LAST DAY OF CLASSES.** So close I can taste it. It tastes like Celsius. ⚡😤"
  - "🏁 **1 DAY.** Either you're ready or you're panicking. Both are valid. One more push!!! 💪🐾"
  - "🎯 **THE FINAL DAY IS TOMORROW.** Like, THE last day of classes. Not finals. Those come after lol. 😅📚"
- *≤3 days left:*
  - "🔥 **{n}** until the last day of classes. We are SO close, just like my ex wife. 👃✨"
  - "😤 **{n}** left. Unlike your girlfriend, the semester is gonna finish. 💪"
  - "🏃 **{n}** until classes end. GO GO GO GO GO GO GO GO. 🎽"
  - "😤 **{n}** days of classes left. Almost there nerds!!!!! 🔥🐾"
  - "⚡ **{n}** until the last day of classes. you got this gumdrop! 🏁"
  - "🔥 **{n}** LEFT OF CLASSES. oh em gee bih. 😤🐾"
  - "💪 Only **{n}** until the last day of classes. skip class and get noodles. 😌"
  - "🏃 **{n}** days left. WOOF. 🐾🏁"
  - "😤 **{n}** until classes end. pls dont give up. 💙"
  - "🚀 **{n}** of classes remaining. You got this nerd!!!! 🐾⚡"
- *≤7 days left:*
  - "📅 **{n}** until the last day of classes. Less than a week. Skip the rest of your classes heehee 😅"
  - "⏳ **{n}** until classes end. Hold on a bit longer.... 🐾"
  - "🗓️ Only **{n}** of classes left! Don't forget we have finals after YIPPEE! 🎉"
  - "👀 **{n}** until the last day of classes. It REEKS in here. 😤"
  - "🎯 **{n}** days. I CAN FEEL IT COMOING HAHAHAHAHAHAA. 📅🔥"
  - "😤 **{n}** until classes wrap up. It's cwazy bro. 🙂"
  - "⏰ **{n}** days until the last class. you hoes have GOT THIS. 🐾"
  - "📖 **{n}** until the last day of classes. SKIP THE READINGS AND TAKE A NAP. 🫡"
  - "🤺 **{n}** left. Youre an academic eweapon my GOAT. 🗡️"
- *General countdown (>7 days):*
  - "📆 **{n}** until the last day of classes. ALLLLLLLLMOST THEREEEEEEEE 🌅"
  - "🐾 Terrier check-in! **{n}** until classes wrap up. You got dis! ❤️"
  - "⏰ **{n}** of classes remaining. GRIND BITCH, GRIND! 🧠"
  - "🗓️ **{n}** until the last day of classes. LOCK IN. 💙🐾"
  - "☕ **{n}** until the last day of classes. YOU WILL SRURVIVE TRUST!!!!! 🐾"
  - "🌅 **{n}** days left of class. That's {h} hours. That's {m} minutes. Guh. 😅"
  - "🔥 **{n}** left until the last day of classes. DESTROY THIS BITCH. 💪"
  - "🚀 T-minus **{n}** until we forget everything we learned yay! 🧪"
  - "💼 **{n}** until classes end. How are ya feeling? ⏱️"

**`build_scheduled_message` (10am/hourly announcement to #general)**
- "🎓 **Today is All University Commencement!** Congratulations to all graduating Terriers!!!!!!!!!!!! 🐾❤️"
- "🎓 **Commencement week!** All University Commencement is in **{n}**. Congratulations to all graduating Terriers! Y'all are awesom!!! 🐾"
- "✅ **Finals are over!** Great work this semester, gamers! 🐾"
- "🏁 **Today is the last day of finals!** Finish strong — you're almost there! 🐾🎊"
- "📝 **Finals — Day {n}.** **{n}** remaining until finals end. Good luck babyyyyyyy! 🐾"
- "📝 **Finals begin today!** They run through **{date}**. You've got this. DESTROY those exams. 🐾"
- "📖 **Study Period — Day {n}.** Finals begin in **{n}** on {date}. LOCK IN! 🐾"
- "🎉 **Today is the last day of classes!** Study period begins tomorrow. 🐾"
- "📅 **{n}** until the last day of classes ({date}). 🐾"

**`end` / `end_slash` (`=end`/`/end`, semester over)**
- "🎓 The semester is over! Congratulations, Terriers! Go live your life. 🐾❤️"

---

## `cogs/campus/startCog.py`

**`build_message` (semi-daily countdown to first day of classes, `=start`/`/start`)**

- *Classes begin:*
  - "📚 **CLASSES HAVE BEGUN!!!** wake up and get to class bro!"
  - "🎒 **TODAY IS DAY ONE.** like a hundred and smtn days to go WOO HOOOOOO"
  - "🐾 **IT'S HAPPENING. CLASSES START TODAY.** you got this!!!!!!"
  - "🔥 **FIRST DAY OF CLASSES BABYYYY.** go pretend you did the reading yahoo!!"
- *Matriculation day:*
  - "🎓 **TODAY IS MATRICULATION!!!** good job matriculants!"
  - "🐾 **WELCOME TO THE BOSTON UNIVERSITY OFFICIALLY.** now use those student discounts!"
  - "🏛️ **MATRICULATION DAY.** pump and circumcision!"
  - "🎺 **YOU ARE NOW OFFICIALLY MATRICULATED.** pls don't matriculate in your room with your roommate there!"
- *Orientation programming (templated, day_num/days left):*
  - "🎉 Orientation day {n}. Classes start in **{n}**. hope youre orienting well!"
  - "🐾 **{n}** until classes. Orientation is happening!! make friends you will never talk to again yaya!"
  - "🧭 Orientation day {n}. **{n}** left. waow i love icebreakers yay!"
  - "🥤 Day {n} of orientation. **{n}** until class starts. drink the free lemonade they give you!"
  - "🎪 Orientation day {n}. **{n}** to go. Make up your fun fact for the icebreaker game, make people think you are quirky!"
  - "🐾 **{n}** until classes. Day {n} of orientation. get the instagrams of the people around you"
  - "📛 Day {n}, orientation. **{n}** left. Invite people to discord dot gg slash bostonuniversity"
  - "🎶 Orientation day {n}. **{n}** until classes. clap clap clap clap round of apawse"
  - "🧃 Day {n} of orientation. **{n}** to go. drink alcohol"
  - "🏫 Orientation day {n}. **{n}** left. stealing from cityco is punishable by expulsion"
  - "🐾 **{n}** until classes. Orientation day {n}. I like your lanyard you look very cute in it uwu!"
  - "📸 Day {n} of orientation. **{n}** left. make new lifelong fwends!"
  - "🎯 Orientation day {n}. **{n}** to go. You are so brave good job!"
  - "🗺️ Day {n}, orientation. **{n}** until classes. Google Maps"
  - "🐾 **{n}** left. Orientation day {n}. become enemies with your roommate"
  - "🎈 Orientation day {n}. **{n}** to go. aquire free shit everywhere"
  - "📚 Day {n} of orientation. **{n}** unti classes. become lovers with your roommate"
  - "🐾 **{n}** left. Orientation day {n}. dont lose your BU ID silly"
  - "🎤 Orientation day {n}. **{n}** to go. Ask your orientation leader a difficult question"
  - "🚶 Day {n}, orientation. **{n}** until classes. do a practice walk of campus!!!!!"
  - "🐾 **{n}** left. Orientation day {n}. eat something green at least once this week!"
  - "🎓 Orientation day {n}. **{n}** to go. Memorize your BU ID number! Paste it in this chat as proof!"
  - "🧢 Day {n} of orientation. **{n}** until classes. wear the free shirt they gave you, you look adoworable!"
  - "🐾 **{n}** left. Orientation day {n}. almost done, hang in there puppy!!"
- *New student move-in:*
  - "📦 **MOVE-IN DAY FOR NEW STUDENTS!** Classes in **{n}**. CLEAN YOUR DESK AND BED THERE MIGHT BE SUSPICIOUS FLUIDS ON THEM"
  - "🐾 New Terriers moving in today!! **{n}** until classes. Dont call your new roommies slurs or mean things!"
  - "📦 **WELCOME NEW TERRIERS!** **{n}** until classes. put dead rodents in the microfridge"
  - "🧳 Move-in day for new students. **{n}** left. say hi to your RA!"
  - "📦 New students, its move-in day!! **{n}** until classes. keep your door open when youre in to make fwends!!!!"
  - "🐾 **{n}** left. Welcome to campus, new Terriers! growl arf arf arf grrrrrr"
  - "📦 Move-in day! **{n}** until classes. hydrate."
  - "🎒 New Terriers arriving today. **{n}** left. dont lose your key or you have to payyyyy"
- *Continuing student move-in:*
  - "📦 Continuing students moving in today. **{n}** until classes. welcome back to campus!"
  - "🐾 Welcome back!! **{n}** left until classes start. dont forget to say hi to your thub fwends!!"
  - "📦 Move-in for returning Terriers. **{n}** until classes. go find out if your fave restaurant still tasty"
  - "🐾 **{n}** left. Welcome back! reconnect with your campus freidns!!!!!"
  - "📦 Returning students, move-in day. **{n}** until classes. hey im walkin here!"
  - "🐾 Welcome back to campus! **{n}** left. clean your bed"
  - "📦 Continuing student move-in. **{n}** until classes. hide your valuables from your thieving roommie"
  - "🐾 **{n}** left until classes. Welcome back!! go say hi to a owo!"
  - "📦 Move-in day for returners. **{n}** until classes. be nice to ur ra"
  - "🐾 Welcome back Terriers! **{n}** left. get ready for classesssssssss"
  - "📦 Continuing students, its move-in day. **{n}** until classes. dont buy textbooks!!!!!!"
  - "🐾 **{n}** left. Welcome back! follow terrier hub on instagram!"
  - "📦 Move-in for returners. **{n}** until classes. find a campus squirrel and send a picture in this channel"
  - "🐾 Welcome back!! **{n}** left. be nice to the dining hall and facilities staff"
  - "📦 Continuing student move-in day. **{n}** until classes. START SEARCHING FOR FALL2026 HUZZ!"
  - "🐾 **{n}** left. Welcome back Terriers! dont start studying yet tho"
- *General pre-move-in countdown:*
  - "⏳ **{n}** until classes begin. enjoy the freedom while it lasts!"
  - "🐾 **{n}** left of summer. enjoy it while it lasts babyyyyy"
  - "🎒 **{n}** until Fall 2026 kicks off. get ready to learn knowledge!"
  - "☀️ **{n}** of summer left. go touch grass!"
  - "🐾 **{n}** until classes. DO NOT BUY TEXTBOOKS"
  - "🎓 **{n}** left until Fall 2026. emotionally prepare"
  - "🌅 **{n}** until classes begin. fix your fucked up sleep schedule brorito"
  - "🐾 **{n}** left of summer freedom. taco salad tasty"
  - "📚 **{n}** until classes start. pirate your textbooks!"
  - "🎒 **{n}** left. dont pack yet"
  - "🐾 **{n}** until Fall 2026. skoo time soon"
  - "🌊 **{n}** of summer remaining. go do something fun like video game or outside"
  - "🐾 **{n}** left until classes. spend more time on terrier hub!"
  - "🎓 **{n}** until Fall semester. get rested up!"
  - "🍂 **{n}** until classes start. send a flirtatious text to your roommate"
  - "🐾 **{n}** left of summer. do you know where your classes are?"
  - "📖 **{n}** until classes begin. ignore emails from professors...."
  - "🎒 **{n}** left. cant wait for the disaster known as fenway target...."
  - "🐾 **{n}** until Fall 2026 begins. are you taking an 8am?"
  - "☕ **{n}** until classes start. drink alcohol"
  - "🌞 **{n}** of summer left. go outside"
  - "🐾 **{n}** until classes. hug your pet if you have one!"
  - "🎓 **{n}** left until Fall 2026. what is the song of your summer?"
  - "📦 **{n}** until classes begin. RUBY CHAN! HAIIIIIII NANI HA SUKI? CHOCOMINTO YORI GA ANATA!"
  - "🐾 **{n}** left of summer. watch a whole season of something"
  - "🎒 **{n}** until Fall semester starts. it too hot out"
  - "🌻 **{n}** left of summer. buy things with money. you deserve a gift."
  - "🐾 **{n}** until classes. go to bed"
  - "📚 **{n}** until Fall 2026 begins. be brave, soldier...."
  - "🎓 **{n}** left. skool soon"
  - "🐾 **{n}** until classes start. are you excited for dining hall food?"
  - "🌤️ **{n}** of summer remaining. boston is gonna be snowy this year trust"
  - "🐾 **{n}** left until Fall 2026. make sure to pak your passpowort"
  - "🎒 **{n}** until classes begin. enjoy the privacy before getting to campus with your weird invasive roommate. Ping your roommate below:"
  - "📖 **{n}** left of summer. read yuri, not textbooks"
  - "🐾 **{n}** until Fall semester starts. practice flirting."
  - "🎓 **{n}** left. she sylla on my bus til I quiz."
  - "🌙 **{n}** until classes begin. your mum"
  - "🐾 **{n}** left of summer. how ar eyou feeling????!"
  - "📦 **{n}** until Fall 2026 starts. pack your towels?"
  - "🎒 **{n}** left. exciting!!!!!!!"
  - "🐾 **{n}** until classes begin. enjoy non dining hall cooked food while it lasts!"
  - "☀️ **{n}** of summer left. go get a tan or a sunburn or melanoma, your choice!"
  - "🎓 **{n}** until Fall semester starts. immunization requirement RFK says is bad!"
  - "🐾 **{n}** left until classes. send a meme to your RA if they emailed you"
  - "📚 **{n}** until Fall 2026 begins. Glup glup"
  - "🌊 **{n}** of summer remaining. arf arf arf growl!"
  - "🐾 **{n}** left. white claw"
  - "🎒 **{n}** until classes start. enjoy your summer bed...."
  - "🐾 **{n}** until Fall 2026. ar eyou working or chilling?"
  - "🎓 **{n}** left of summer. sooooo strwessful! >-<!"

**`start` / `start_slash` (classes already started)**
- "📚 Classes have started! Good luck this semester, Terriers. 🐾"

---

## `cogs/campus/rmpCog.py`

**`ClassLookupView.send_lookup` / buttons**
- "Class lookup cog is not loaded."
- "Unknown class lookup error."
- "This menu is no longer active." / "This button is no longer active."
- Select placeholder: "Pick a class to open its BU Bulletin page"

**`_build_rmp_response` (`=rmp`/`/rmp`)**
- "Please type in a professor name. Example: =rmp Melissa Gilliam or =rmp Gilliam"
- "RMP lookup failed: {type(exc).__name__}: {exc}"
- "I couldn't find anyone at BU with the name '{cleaned}'."
- Embed description: "RateMyProfessors result for {BU_DISPLAY_NAME}" / "No BU match found. Closest RateMyProfessors result for '{cleaned}' (might not be BU)."
- Field names: "Department", "Rating", "Difficulty", "# Ratings", "Would Take Again", "Reviewed Classes", "Per-Class Ratings", "Profile"
- Field name "Other matches" / "Other possible matches (might not be BU)"

**`_channel_warning_text` (posted after every `=rmp`/`/rmp` outside the RMP channel)**
- "{user.mention}, you really gotta be doing bot commands in {channel} bruh. OwO is gonna get mad and blame me, Terrier Bot {emoji}"

---

## `cogs/campus/searchCog.py`

**`_course_embed`**
- Footer: "Use =class {num} for live section listings & enrollment info"

**`ResultsView`**
- Select placeholder: "Pick a course for full details  ({start}–{end} of {total}{'+' if capped})"
- Dept-jump select placeholder: "📚  Jump to department..."
- Dept option label: "{key}  —  {count} course{'s' if count != 1 else ''}"
- Buttons: "◀ Prev", "Page {n} / {total}", "Next ▶", "🔍 New Search"
- Embed title: "🔍 BU Course Search Results"
- Description: "**{total}{'+'} course{'s'} found** — {query_summary}\n*Showing {start+1}–{end}*\n\n{lines}"
- Footer: "Select a course from the dropdown to see full details."
- "Course not found." (select callback)

**`_BackView`**
- Button: "← Modify Search"

**`SearchView`**
- School select placeholder: "🏛  Filter by school  (optional — pick one or more)"
- HUB select placeholder: "🎓  Filter by HUB unit  (optional — pick one or more)"
- Mode select placeholder: "HUB match mode: {'any selected unit' | 'all selected units'}"
- Mode options: "Match ANY selected HUB unit" / description "Course fulfills at least one of your chosen HUB units"; "Match ALL selected HUB units" / description "Course must fulfill every selected HUB unit"
- Button: "🔍  Search"
- Embed title: "🔍 BU Course Search"; description: "Use the dropdowns below to filter courses, then click **Search**.\nAll filters are optional — leave them blank to browse broadly."
- Field "Schools" value: "*Any*" (if none selected)
- Field name "HUB Units ({match any/all})"; value "*Any*" (if none selected)
- No-results embed: title "No Results Found"; description "No courses matched your filters. Try broadening your search."

**`SearchCog` commands**
- `=search` help text: "Search BU courses interactively, or pass filters directly.\nUsage:\n  =search ... " (full usage block with examples and school/HUB code lists)
- "No courses found with those filters. Try `=search` for the interactive form."

---

## `cogs/campus/clubCog.py`

**`_build_embed` / `_respond` / `club_slash`**
- Embed title: "BU Clubs — {display}"
- No-results embed description: "No active clubs found."
- Footer: "terriercentral.bu.edu"

**`ClubPaginationView`**
- Buttons: "◀", "· / ·", "▶"

**`club` (`=club`) docstring shown in help**
- "Search BU clubs. =club blood | =club political"

---

## `cogs/community/bannerCog.py`

**`BANNER_MESSAGE` (`=banner`/`/banner`, and weekly auto-post)**
- "## **Your photo or gif can be our server banner!**\nSubmit it to {channel} and it might get added!!! 🐾"

---

## `cogs/community/boostCog.py`

**`on_message` (server boost thank-you)**
- "🎉 **Congratulations, {mention}!**\n\nYou have officially joined the **Board of Trustees** by boosting the server.\n\n**Board of Trustees Benefits:**\n\n• Custom name color (holographic, solid, or gradient)  \n• Custom PNG or emoji next to your name (rule-compliant)  \n• One custom server emote added (rule-compliant)\n\n*Please message a moderator to claim your trustee benefits. Thank you for supporting the server!*"

**`BOOST_TEXT` (`=boost`/`/boost`)**
- "# **Join the Board of Trustees**\nSupport the server by boosting it and become a member of the **Board of Trustees**.\n**Trustee Benefits:**\n• Custom name color (holographic, solid, or gradient)\n• Custom PNG or emoji next to your name (rule-compliant)\n• One custom server emote added (rule-compliant)\n*Boost the server and message a moderator to claim your trustee benefits. Thank you for your support!*"

---

## `cogs/community/roleboostCog.py`

**`roleboost` (`=roleboost`/`/roleboost`)**
- "You don't have permission to use this command."
- "{user.display_name} doesn't have the booster role, so this can't be applied."
- "I don't have permission to assign that role."
- "Failed to assign role: {e}"
- "✅ Gave {user.mention} the {role.mention} role. It will be removed automatically if they lose the booster role."

**`on_member_update` (auto-removal announcement)**
- "{after.mention} is no longer boosting and lost {role_mention}."

---

## `cogs/community/loveCog.py`

**`love` / `love_slash`**
- ":heart: Terrier Love — Coming Soon! :heart:"

---

## `cogs/community/helloCog.py`

**`hello` / `hello_slash`**
- "Hello {display_name}! I am TerrierBot!"

---

## `cogs/community/pingroleCog.py`

**`pingrole` (`/pingrole`)**
- Dropdown choice labels: "{role name} ({role description})" for each of Eventee, Foodee, HungryLonger, FitnessFriend, StudyBuddy, MC, Val, SummerLocal
- "I can't find a role with that name."
- "{user.mention} has pinged {role.mention}: *{message}*"
- "Slow down! You can use /pingrole again in {n}s."
- "Something went wrong running that command."

---

## `cogs/community/positivityCog.py`

**On-message trigger**
- "Happy Positivity Tuesday, <@{author_id}>! 🌸✨ You have been selected to make a positive comment about yourself, a fellow member, or anything else. 💖"

**`positivity` group / slash equivalents**
- "This command can only be used in a server."
- "Positivity Tuesday is {'enabled'|'disabled'} in this server. Current interval: every {n} messages."
- "You silly goose, it is {day_name}!"
- "Interval must be at least 1 message."
- "Enabled Positivity Tuesday. I will send the message around every {n} messages."
- "Disabled Positivity Tuesday for this server."
- "Positivity interval is now every {n} messages."
- "Positivity cooldown list is currently empty."
- "Positivity cooldown list (most recent first): {names}"

---

## `cogs/community/prideCog.py`

**`PRIDE_MESSAGE` (auto-post + `=pride`/`/pride`)**
- "# Happy Pride! Pick a name color for the month of June by going to <id:customize>!\n{pride flag emoji row}"

**`pride` / `pride_slash`**
- "Posted the Pride message."
- "I could not post the Pride message. Please check channel access."

---

## `cogs/community/reactionCog.py`

No user-facing text — only emoji reactions added to messages (no strings sent).

---

## `cogs/community/reactionRoleCog.py`

**`PRESETS["Freshmen"]` (`/reactionrole`)**
- Embed title: "🧑‍🤝‍🧑 Freshmen Ping Role"
- Description: "Freshmen! Are you interested in being invited to do **[insert anything you want to do]** with people from this server? <@&...> is pingable by anyone in your class, and it will **only reach people who have opted in to be pinged** (no constant pings @'30).\n\n**React with 🧑‍🤝‍🧑 below to add the role.**\n\nPing when you are heading to the dining hall, exploring campus, getting coffee, going to an on campus event, etc.\n\n*This is for orientation week only.*"
- "You don't have permission to use this command." (MissingPermissions handler)
- "Reaction role posted." (ephemeral confirmation)

---

## `cogs/community/starboardCog.py`

**Star embed (`_build_star_embed`)**
- Field name: "" (blank); value: "[Jump to message]({url})"
- Footer: "Message ID: {id}"

**`/starboard` subcommands**
- "Starboard channel set to {channel.mention}."
- "Threshold must be at least 1."
- "Starboard threshold set to {n} ⭐."
- "Set a starboard channel first with `/starboard setchannel`."
- "Starboard enabled." / "Starboard disabled."
- Status embed title: "Starboard Status"; fields "Enabled", "Channel", "Threshold"

**`_build_leaderboard_embed` (`=starleaderboard`/`/starleaderboard`)**
- Title: "⭐ Star Leaderboard"
- "No stars have been given yet!"
- "{prefix} {name} — {stars} {star_word}"
- "This command can only be used in a server."

---

## `cogs/community/towokenCog.py`

**`TOWOKEN_TEXT` (auto-triggered after 12 commands, with 10-min cooldown)**
- "You have exceeded your Terrier Bot towoken limit {emoji}. Please purchase more towokens using the powoints earned by completing a variety of side quests, riddles, and puzzles.\nContact bridge trowoll OwO for more infowormation. {emoji} \n||/joke||"
- Button label: "Buy Towokens"

**`towoken` (`=towoken`/`/towoken`)**
- "You don't have permission to use this command."
- "Towoken notice is now {'enabled'|'disabled'}."

---

## `cogs/community/leavePoliticsCog.py`

**`LeaveConfirmView`**
- "This isn't your confirmation to click."
- Button: "Leave Politics" / "Cancel"
- "You've left Politics. You'll need to re-apply to get back into the channel."
- "Couldn't remove the role — I might be missing permissions. Ping a mod."
- "Cancelled — you're still in Politics!"

**`leavepolitics` (`=leavepolitics`/`/leavepolitics`)**
- "Couldn't find the Politics role — ping a mod."
- "You're not in Politics, so you obviously can't leave."
- "Are you sure.... You'll need to re-apply to get back into the politics channel."

---

## `cogs/community/joinPoliticsCog.py`

**`PoliticsApplicationModal`**
- Modal title: "Politics Channel Application"
- Text display (conduct code): "I agree to not use charged/loaded language like \"evil\" to describe things or groups, and to not stereotype or generalize a group of people.\n\nI agree to remain respectful and civil towards your fellow Terrier Hub members by assuming good intentions, not accusing others, and not personally attacking others."
- Label "Politics Channel Conduct Code"; radio options "I agree" / "I do not agree"
- Text display (punishments): "I understand that participating in #politics is a privilege, and violating any rules will result in 3 immediate warnings and removal from the channel."
- Label "Punishments"; radio options "I understand" / "I do not understand"
- "You must agree to the Conduct Code and acknowledge the Punishments policy to submit an application."
- "Thank you for your submission. The moderators will promptly review your application."

**`PoliticsApplicationStartView`**
- Button: "Start Application"
- "This can only be used in the server."
- "You're already in #politics."
- "You need to be a member of the server for at least {n} days before applying for #politics." *(tenure gate — kept per user request in this session)*

**`_handle_decision` (mod review buttons)**
- "You don't have permission to review applications."
- "This application has already been handled."
- Embed footer: "{Approved|Denied} by {reviewer.display_name}"
- DM (approved): "{mention} has been accepted to the #politics channel of Terrier Hub.\n\nPlease consult the moderators for any questions. If you would like to be removed from the channel, please run /leavepolitics"
- DM (denied): "{mention} has been denied access to the #politics channel of Terrier Hub.\n\nPlease consult the moderators with any questions by submitting a ticket in #rules."
- Button labels: "Approve" / "Deny"
- "Application {'approved'|'denied'}."

**`joinpolitics` (`=joinpolitics`/`/joinpolitics`)**
- "You can't use this command!"
- Embed description: "# Politics Channel Application\nTo gain access to {channel}, you must complete the application and agree to the rules in {channel}. A history of civil behavior in the server is required for acceptance.\n\nPlease submit a ticket in {channel} if you have any questions."

---

## `cogs/community/birthdayCog.py`

**Daily announcement (background task, posted to the announce channel)**
- "# {mention} is a birthday terrier today! Please wish them a happy birthday!" (1 person)
- "# {mention1, mention2, and mention3} are birthday terriers today! Please wish them a happy birthday!" (2+ people)
- Masked gif link line (no visible text)
- "*Add your birthday with the command /birthday set month date*"

**`birthday` (bare, prefix only)**
- "You haven't set your birthday yet. Run `=birthday set`."
- "Your birthday is {month} {day}! 🎂"

**`birthday set`**
- "\"{month_raw}\" isn't a real month — use a name like `March` or a number 1-12."
- "Come on... {month} only has {n} days."
- "Thank you! Your birthday is set to {month} {day}. 🎂"

**`birthday get`**
- "You have no birthday on file." / "{name} has no birthday on file."
- "Your birthday is {month} {day}." / "{name}'s birthday is {month} {day}."

**`birthday remove`**
- "You don't have a birthday here!" / "{name} doesn't have a birthday here!"
- "Your birthday has been removed and won't recur. If you're wearing the birthday role today, it'll still come off at the end of the day as usual."
- "{name}'s birthday has been removed and won't recur. If they're wearing the birthday role today, it'll still come off at the end of the day as usual."

**`birthday nearest`**
- "Couldn't find the main server."
- "No birthdays in the next two weeks. 🥲"
- Embed title: "🎂 Upcoming Birthdays"

**`birthday export`**
- "Oops! You can't run that... mods only!"
- File contents (not chat text, but a mod-facing artifact): "{MM-DD}: {user_id} ({display_name|unknown - left server})"

**`birthday override`**
- "Oops! You can't run that... mods only!"
- "Set {user.display_name}'s birthday to {month} {day}."

---

## `cogs/campus/mbtaCog.py`

**Board embeds**
- `_build_mbta_embed`: title "Green Line at BU!"; description "Cute train board for your BU stops"; field "Heads-Up Service Alerts 🚧" / "Service Status ✨" ("No active Green Line B alerts at these BU stops right now."); footer "Source: MBTA v3 API • Updated {time}"
- Direction lines: "API unavailable", "no live prediction", "arriving", "{n} min", "~{eta} (scheduled)"; status suffix "⚠️ {status}"
- `_build_station_embed`: description "🚊 {line names}"; field "Status" ("⚠️ MBTA API is currently unavailable. Please try again shortly."); field "Upcoming Trains"; field "Heads-Up Service Alerts 🚧" / "Service Status ✨" ("No active alerts for this station right now."); footer "Source: MBTA v3 API • Updated {time}"; ETA tag "🌈 Pride Train!" (replaces the branch tag when the shown train is the Pride Train)

**`mbta` / `mbta_slash` (`=mbta`/`/mbta`)**
- "Couldn't find a Green Line station matching **{station}**. Try the full or partial station name, e.g. `=mbta Coolidge Corner`."
- "A few stations match **{station}** — did you mean: {suggestions}?"

**`mbtgay` (`=mbtgay`/`/mbtgay`)**
- "🏳️‍🌈🌈 No sign of the Pride Train right now.... MBTA homophobic? 🌈🏳️‍🌈"
- Embed title: "🌈 Pride Train Tracker 🌈"
- Description: "✨🏳️‍🌈 Car #3706 is out riding the **{branch}**! 🏳️‍🌈✨\n\n🌈 {stopped at|arriving at|heading toward} {stop} 🌈"
- Footer: "Source: MBTA v3 API 🏳️‍🌈"

---

## `cogs/community/lockinCog.py`

**`lockin` (`=lockin`/`/lockin`)**
- "you're already locked in — ends <t:...:R> (<t:...:F>). can't stack or extend it, gotta ride it out."
- "couldn't parse that duration. try something like `30m`, `2h`, `1d`, or `1d2h30m`."
- "minimum lock-in is 5 minutes." / "maximum lock-in is 7 days."
- "lock-in role not found on this server — ping a mod."
- "couldn't assign the role — ping a mod."
- "locked in for {duration}. ends <t:...:F> (<t:...:R>). no take-backs, good luck 🔒"
- DM on lock-in end: "your lock-in is over — welcome back 🔓"

**`lockinleft` (`=lockinleft`/`/lockinleft`)**
- "you're not locked in right now."
- "{duration} left — ends <t:...:R> (<t:...:F>)."

**Member-log embed**
- Title: "🔒 Lock-in started"

---

## `cogs/community/feedbackCog.py`

**`FeedbackModal`**
- Modal title: "Anonymous Feedback"
- Field label: "Your feedback"; placeholder: "Share your thoughts anonymously..."
- "Your feedback has been submitted anonymously. Thank you!"
- Embed title: "Anonymous Feedback" (contains submitted text verbatim)

**`FeedbackView`**
- Button: "Submit Feedback"

**`feedbacksetup` (`=feedbacksetup`/`/feedbacksetup`)**
- Embed title: "Submit Anonymous Feedback"
- Description: "**Your identity is never recorded.** No username, ID, or metadata is logged. Only the text you write is forwarded to the moderation team."

---

## `cogs/community/trollCog.py`

**`_length_error`**
- "That's too long after uwu-ifying: {n} characters, {n} over Discord's 2000-character limit." *(this text is itself run through `owo_ify()` before being shown)*

**`troll` (`/troll`)**
- "Troll role not found in this server."
- "Could not find that user in this server."
- "Troll mode enabled for {member.mention}." / "Troll mode disabled for {member.mention}."
- "I don't have permission to modify that user's roles."
- "You don't have permission to use this command." (MissingPermissions handler)

**`uwu` (`=uwu`/`/uwu`)**
- "uwuified!" (slash ack)
- Fallback send prefix: "**{display_name} says:** {content}"

**`owo_ify` fallback**
- "w-w-w-... {random emoticon}" (when input text is empty)

---

## `cogs/logging/*Cog.py` (mod/audit log channels — mod-facing only)

These post exclusively to internal log channels (join/leave, member, server,
mod, message logs) — no commands, no replies to end users. Embed titles for
reference since mods read them directly:

- `joinLeaveCog.py`: "📥 Member joined", "📤 Member left" (+ "⚠️ **New account:** {n} day(s) old")
- `memberLogCog.py`: "✏️ Nickname changed", "🪪 Username/avatar changed"
- `serverLogCog.py`: "🎭 Member roles updated", "➕ Channel created", "➖ Channel deleted", "✏️ Channel renamed", "🔒 Channel permissions updated", "➕ Role created", "➖ Role deleted", "✏️ Role updated", "😀 Emoji updated"
- `modLogCog.py`: "👢 Member kicked", "🔨 Member banned", "🔓 Member unbanned", "🔇 Member timed out" / "🔇 Timeout updated" / "🔊 Timeout removed"
- `messageLogCog.py`: "**Message deleted in {channel}**", "*(no text content)*", "**Attachments:** {list}", "-# 🔨 Deleted by {mention}", "*(not seen by the bot before deletion — author/content unavailable)*", "🗑️ Bulk message delete", "{n} message(s) purged by {mention} in {channel}", "{n} message(s) deleted in {channel}", "...and {n} more", "+ {n} uncached message(s) — content unavailable"
- `logConfig.py` — `format_duration`: "0 minutes", "less than a minute", pluralized "{n} day(s)/hour(s)/minute(s)/second(s)"; `user_line`: "{mention} — **{user}** (`{id}`)"

---

## `cogs/logging/caseLogCog.py`

**`_ModLogsView` / `modlogs` (`=modlogs`/`/modlogs`)**
- "You don't have permission to use this."
- Embed title: "📋 Moderation case log"
- "No warns, kicks, timeouts, or bans on record."
- Footer: "{n} total entr{y|ies} — showing {start}-{end}" / "0 entries"
- Buttons: "◀ Prev", "Page {n} / {total}", "Next ▶"
- "Oops! You can't run that... mods only!"
- "Couldn't find a member matching `{input}`."
- Case-type labels shown per entry: "Kick", "Timeout", "Timeout cleared", "Ban", "Unban", "Warn" (with emoji), plus per-entry line format "{emoji} **{type}** — <t:...:R> by <@{mod}> — {reason}{duration} [— Appealed]"

---

## `cogs/moderation/warningsCog.py`

**`warn` (`=warn`/`/warn`)**
- "Oops! You can't run that... mods only!"
- "Invalid rule number. Valid rules: {list}"
- DM embed title: "You've received a warning"; fields "Rule", "Reason", "Appeals" ("Warnings can be appealed. To appeal, use the `/warnappeal` command."); footer "Warning ID: {id}"
- Confirmation embed title: "Warning #{id} issued"; footer "DM sent" / "Could not DM user (DMs closed)" / "DM skipped"
- Public in-channel line: "{user} has been warned."
- Mod-log embed title: "⚠️ Warning #{id} issued"

**`warncount`**
- "No active warnings."
- Embed title: "Active Warnings by User"
- "{mention} — {n} warning(s)" / "<@{id}> (left server) — {n} warning(s)"

**`warninfo`**
- "{user.mention} has no warnings on record."
- Embed title: "Warning history — {display_name}"
- Field value: "{reason}\nStatus: {Active|Removed}"

**`mywarns`**
- "You have no active warnings."
- Embed title: "Your active warnings"

**`warnremove`**
- "No active warning #{id} found."
- "Warning #{id} removed for <@{user_id}>."
- Mod-log embed title: "✅ Warning #{id} removed"

---

## `cogs/moderation/warnAppealCog.py`

**`_WarnAppealTextModal`**
- Modal title: "Appeal Warning"
- Field label: "Why should this warning be reconsidered?"
- "Couldn't deliver your appeal right now — please contact a moderator another way."
- Embed title: "⚖️ Warning appeal received"
- "Something went wrong sending your appeal — please try again later or contact a moderator another way."
- "Your appeal has been sent to the moderators."

**`_WarnSelect` / `_WarnSelectView`**
- Select placeholder: "Select a warning to appeal..."
- Option label: "#{id} — Rule {rule}: {rule_name} ({date})"

**`_WarnAppealResponseModal`**
- Modal title: "Accept Appeal" / "Reject Appeal"
- Field label: "Response message"
- Outcome field text: "✅ Accepted by {mod}\n{message}" / "❌ Rejected by {mod}\n{message}"
- DM (accepted): "Your warning appeal was accepted — the warning has been removed.\n\n**Moderator's message:** {message}"
- DM (rejected): "Your warning appeal was reviewed and denied. The warning stays on record.\n\n**Moderator's message:** {message}"
- " Couldn't DM the user — they may have DMs closed." (appended note)
- "Appeal {'accepted'|'rejected'}.{note}"

**Buttons**
- "Accept" / "Reject"

**`warnappeal` (`/warnappeal`)**
- "You have no warnings to appeal."
- "Select the warning you'd like to appeal:"

---

## `cogs/moderation/appealServerCog.py`

**`_AppealModal`**
- Modal title: "Ban Appeal"
- Field label: "Why should we reconsider?"
- "Couldn't reach Terrier Hub right now — please try again later or contact a moderator another way."
- "You don't appear to be banned from Terrier Hub."
- Embed title: "📨 Ban appeal received"
- "Your appeal has been sent to the moderators."

**`_AppealButtonView`**
- Button: "Appeal my ban"
- "This button can only be used in the appeals server."

**`_AppealDecisionModal`**
- Modal title: "Approve Appeal" / "Deny Appeal"
- Field label: "Note (optional)"
- "Couldn't reach Terrier Hub right now — please try again later."
- "Failed to unban that user: {exc}"
- Outcome field text: "✅ Approved by {mod} — {note}" / "❌ Denied by {mod} — {note}"
- DM (approved): "Your appeal for Terrier Hub was approved! You can rejoin here: https://discord.gg/bostonuniversity"
- DM (denied): "Your appeal for Terrier Hub was reviewed and denied." (+ "\n\n**Moderator note:** {note}" if provided)
- "Appeal {'approved'|'denied'}."

**Buttons**
- "Approve" / "Deny"

**`postappealbutton` (`=postappealbutton`)**
- "This command can only be run in the appeals server."
- Embed title: "Ban Appeals"; description: "If you were banned from Terrier Hub and want to appeal, click the button below."

**Shared decision-click guard**
- "You don't have permission to use this button."
- "Couldn't find the original appeal message."

---

## `cogs/moderation/snitchCog.py`

**`snitch` (`/snitch`)**
- "Report sent to mods."
- Embed title: "🚨 New snitch report"; fields "Reporting channel", "Reporting user", "Context" ("No context provided" if blank)
- Ping content: "🚨 New snitch report <@&{mod role}>"

---

## `cogs/moderation/ticketCog.py`

**`WELCOME_MESSAGE` (posted in new mod-application tickets)**
- "Thank you {mention} for your application. Please answer the following questions:\n\n**What kind of role do you envision having?**\n**What can the server improve on & how will you support that goal?**\n**Why do you want to be a mod?**\n**What experience / assets would you bring to the team?**\n\nPlease take your time. We will review your application and get back to you in the next few weeks.\n\n- Terrier Hub Moderation Team"

---

## `cogs/moderation/kickCog.py`

**`kick` (`=kick`/`/kick`)**
- "Oops! You can't run that... mods only!"
- "This command can only be used in a server."
- "I can't kick the server owner."
- "Mods can't be kicked via this command."
- "I can't kick that member — their top role is at or above my own."
- DM embed title: "You have been kicked"; description "You were kicked from **{guild}**.\n\n**Reason:** {reason}\n\nYou're welcome to rejoin with a new invite if you're given one."
- "I don't have permission to kick that member."
- "Failed to kick that member: {exc}"
- "Kicked {member} (`{id}`).{dm_note} Reason: {reason}"
- Mod-log embed title: "👢 Member kicked"

---

## `cogs/moderation/timeoutCog.py`

**`timeout` (`=timeout`/`/timeout`)**
- "Oops! You can't run that... mods only!"
- "This command can only be used in a server."
- "Couldn't parse `{duration}` as a duration. Use a number + unit: `30m`, `2h`, `1d`, `45s` (s/m/h/d)."
- "I can't time out the server owner."
- "Mods can't be timed out via this command."
- "I can't time out that member — their top role is at or above my own."
- "I don't have permission to time out that member."
- "Failed to time out that member: {exc}"
- "Timed out {member.mention} for {duration}{clamp_note}. Reason: {reason}"
- Public channel embed title: "🔇 Member timed out"; mod-log embed same title

**`untimeout` (`=untimeout`/`/untimeout`)**
- "{member.mention} isn't currently timed out."
- "I don't have permission to clear that member's timeout."
- "Failed to clear that member's timeout: {exc}"
- "Cleared {member.mention}'s timeout. Reason: {reason}"
- Embed title: "🔊 Timeout cleared"

---

## `cogs/moderation/hardmuteCog.py`

**`hardmute` (`=hardmute`/`/hardmute`)**
- "Oops! You can't run that... mods only!"
- "this command can only be used in a server."
- "{member.mention} is already hardmuted."
- "can't hardmute the server owner."
- "mods can't be hardmuted via this command."
- "can't hardmute that member — their top role is at or above my own."
- "hardmute role not found on this server — ping a mod."
- "couldn't assign the hardmute role — check my permissions."
- "🔇 hardmuted {member.mention} — they're confined to {channel} until `=unmute`."
- Mod-log embed title: "🔇 Member hardmuted"

**`unmute` (`=unmute`/`/unmute`)**
- "this command can only be used in a server."
- "{member.mention} isn't hardmuted."
- "🔊 unmuted {member.mention}, but couldn't restore all their roles — check my permissions."
- "🔊 unmuted {member.mention} — roles restored."
- Mod-log embed title: "🔊 Member unmuted"

---

## `cogs/moderation/lockdownCog.py`

**`lockdown` (`=lockdown`/`/lockdown`)**
- "Oops! You can't run that... mods only!"
- "This command can only be used in a text channel."
- "This channel is already locked."
- "Failed to lock this channel — check my permissions."
- Embed title: "🔒 Channel locked"; description "This channel has been locked by {mention}. Only moderators can send messages here."

**`unlock` (`=unlock`/`/unlock`)**
- "This channel isn't locked (per my tracking)."
- "Failed to unlock this channel — check my permissions. Lockdown state was kept, try again."
- Embed title: "🔓 Channel unlocked"; description "This channel has been unlocked by {mention}."

---

## `cogs/moderation/purgeCog.py`

**`purge` (`=purge`/`/purge`)**
- "Oops! You can't run that... mods only!"
- "This command can only be used in a text channel."
- "I don't have permission to delete messages here."
- "Failed to purge messages: {exc}"
- "🗑️ Purged {n} message(s)."

**`purgeafter` (`=purgeafter`/`/purgeafter`)**
- "You replied to a message and also passed a target — used the reply, ignored the argument."
- "Tell me which message to purge after — reply to it with `=purgeafter`, or pass its message ID or link: `=purgeafter <id_or_link>`."
- "That doesn't look like a message ID or a Discord message link. Reply to the message with `=purgeafter`, or pass its ID or link."
- "That message isn't in this channel — `=purgeafter` only purges within the current channel."
- "Couldn't find that message in this channel."
- "I don't have permission to read message history here."
- "Failed to fetch that message: {exc}"
- "🗑️ Purged {n} message(s) after {jump_url}."
- "⚠️ More than {cap} messages were posted after the target — only the {cap} closest to now were deleted; older messages were left untouched."

---

## `cogs/moderation/modCommandsCog.py`

**`modcommands` (`=modcommands`/`/modcommands`)**
- "Oops! You can't run that... mods only!"
- Embed title: "Moderation Commands"; description: "Quick reference for everything gated to the mod role — discipline, case-management, and a few other mod-only actions."
- Fields (name / syntax+usage): "📋 Case History", "⚠️ Warn", "🔇 Timeout / Untimeout", "🔇 Hardmute / Unmute", "👢 Kick", "🔨 Ban / Unban", "🧹 Purge", "🔒 Lockdown / Unlock", "🗳️ Modvote", "🏛️ Politics Application", "🚀 Roleboost" (each with its full usage description text)

---

## `cogs/moderation/modvoteCog.py`

**Group-level guard**
- "Oops! You can't run that... mods only!"

**Embeds**
- `_build_open_vote_embed`: title "🗳️ Mod Vote"; description "Target: {display}"; fields "Options", "Votes cast" ("{n} votes cast so far"), "Closes"; footer "Vote ID: {id}"
- `_build_closed_sticky_embed`: title "🗳️ Mod Vote (Closed)"; field "Status" ("Voting closed — see the results posted below.")
- `_build_results_embed`: title "🗳️ Mod Vote Results"; fields "Options", "Total votes", "Outcome" ("No votes were cast for any option." / "Tied — no clear outcome, mod judgment required." / "**{option}**")

**`handle_vote_click`**
- "You don't have permission to vote."
- "This vote has closed."
- "Your vote has been recorded: {option}."

**`/modvote start`**
- "This command can only be used in a server text channel."
- "Provide at least two comma-separated options."
- "Too many options — max {n}."
- "Duration must be at least 1 minute."
- "There's already an active modvote in this channel — close it before starting another."
- "Failed to post the vote message."
- "Started modvote `{id}` in {channel}, closing <t:...:R>."

**`/modvote close`**
- "Specify a vote_id."
- "No active modvote in this channel — specify a vote_id."
- "Unknown vote_id."
- "That vote is already closed."
- "Closed vote `{id}` and posted results."

---

## `cogs/moderation/scamImageCog.py`

**`_HashConfirmView`**
- "You don't have permission to use this button."
- "✅ Added {n} new hash(es) to blocklist." (+ "{n} already present (skipped).")
- Mod-log embed title: "✅ Scam hash(es) confirmed"
- "Cancelled — no hashes added."
- Mod-log embed title: "❌ Scam hash confirmation cancelled"
- Buttons: "Confirm" / "Cancel"

**`_handle_scam` (auto-timeout on known scam image)**
- "{mention}'s message was removed and they were timed out for {n} minutes (known scam image detected)."
- Mod-log embed title: "Scam image detected"

**`_handle_channel_spam`**
- Embed title: "⚠️ Possible cross-channel image spam"; description "{mention} ({id}) posted images in {n}+ channels within {n}s and has been timed out for {n} minutes. Please review and take further action if needed."

**`report_images` (context menu "Report Image(s)")**
- Context menu name: "Report Image(s)"
- "Oops! You can't run that... mods only!"
- "No images found on that message."
- Summary embed title: "🗑️ Scam wave cleanup"; description "Deleted **{n}** message(s) from {mention} across **{n}** channel(s) (image scam wave)\n\n{breakdown}"
- "Cleanup complete ({n} message(s) removed), but no images could be hashed."
- "{mention} Cleanup done ({n} message(s) removed).\n\nAdd these hash(es) to the blocklist?\n{hash_list}"
- "Confirmation prompt posted in the mod queue."

**`removehash` (`/removehash`)**
- "Oops! You can't run that... mods only!"
- "✅ Removed `{hash}` from the blocklist."
- "Hash not found in blocklist."

---

## `cogs/moderation/banCog.py`

**DM appeal intake (`on_message` in DMs)**
- "Couldn't deliver your appeal right now — please contact a moderator another way."
- Embed title: "📨 Ban appeal received"
- "Something went wrong sending your appeal — please try again later or contact a moderator another way."
- "Your appeal has been sent to the moderators. Thank you."

**`ban` (`=ban`/`/ban`)**
- "Oops! You can't run that... mods only!"
- "This command can only be used in a server."
- "You must select a rule."
- "Invalid rule number. Valid rules: {list}"
- "I can't ban the server owner."
- "Mods can't be banned via this command."
- "I can't ban that member — their top role is at or above my own."
- DM embed title: "You have been banned"; description: "You were banned from **{guild}**.\n\n**Rule:** {rule}\n**Reason:** {reason}\n\nThis ban is temporary — you'll be auto-unbanned <t:...:R>. (if temp)\n\nIf you believe this was a mistake, or would like a second chance, join our appeals server to submit an appeal: https://discord.gg/WtECbmPch6"
- "I don't have permission to ban that member."
- "Failed to ban that member: {exc}"
- "Banned {target} (`{id}`).{duration_note}{dm_note} Reason: {reason}"
- Mod-log embed title: "🔨 Member banned"; fields "DM status" ("✅ Appeal DM delivered." / "⚠️ DM undeliverable — no appeal path available for this user.")
- Public announce embed title: "🔨 Member banned" (no moderator identity)

**`unban` (`=unban`/`/unban`)**
- "This command can only be used in a server."
- "Couldn't parse `{input}` as a user ID."
- "User ID `{id}` isn't currently banned."
- "Failed to look up that ban: {exc}"
- "Failed to unban that user: {exc}"
- "Unbanned {target} (`{id}`). Reason: {reason}"
- Mod-log embed title: "🔓 Member unbanned"

**Auto-unban (background task)**
- Mod-log embed title: "⏰ Temporary ban expired — auto-unbanned"

**Duration converter error**
- "Couldn't parse `{argument}` as a duration. Use a number + unit: `30m`, `2h`, `1d`, `45s` (s/m/h/d)."

---

## Files with no user-facing text

- `cogs/community/reactionCog.py` — reacts with emoji only, no strings.
- `cogs/logging/logConfig.py` — shared helpers/constants only (covered above where its text is echoed by other cogs).
- `cogs/__init__.py`, `cogs/{campus,community,logging,moderation,utility}/__init__.py` — empty package markers.
