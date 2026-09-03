# TerrierBot Repo Overview

Discord bot (discord.py 2.7.1) for a BU-focused Discord server ("Terrier Hub", guild ID `1396541818245484665`). Single-process `bot.py` + a `cogs/` package organized into `campus/`, `community/`, `logging/`, `moderation/`, `utility/` subpackages. Prefix commands use `=`, most user-facing commands are hybrid (prefix + slash).

---

## 1. Cog inventory

Format: `path — description — commands — loaded?`. "Loaded?" reflects `bot.py`'s `cogList` (all extensions the bot knows how to load, shown in `=cog list`) vs `defaultCogs` (auto-loaded on startup in `setup_hook`).

### campus/
- **classCog.py** (`campus.class`, cog `"Class"`) — BU Bulletin course lookup, cross-referenced with a locally cached Fall 2026 CSV schedule. `=class <query>` / `/class query:`. Exposes `lookup_course()` used by rmpCog. **In defaultCogs.**
- **clubCog.py** (`campus.club`, `"Clubs"`) — searches BU clubs via the Campus Labs "Engage" public API. `=club <query>`, `=clubdebug <query>` (owner-only) / `/club query:`. **In defaultCogs.**
- **endCog.py** (`campus.end`, `"End"`) — end-of-semester countdown/hype posts (hourly + daily scheduled tasks). `=end` / `/end`. **In cogList but NOT in defaultCogs — not auto-loaded at startup, only reachable via `=cog load end`.**
- **mbtaCog.py** (`campus.mbta`, `"MBTA"`) — live MBTA Green Line ETA/alerts + "Pride Train" tracker via MBTA v3 API. `=mbta [station]` / `/mbta station:` (autocomplete); hybrid `mbtgay`/`/mbtgay`. **In defaultCogs.**
- **rmpCog.py** (`campus.rmp`, `"RMP"`) — RateMyProfessors GraphQL lookup with fuzzy matching + "look up this class" button. `=rmp <professor_name>` / `/rmp professor_name:`. **In defaultCogs.**
- **searchCog.py** (`"Search"`) — interactive/paginated BU course search by school/department/HUB filters from a CSV index. `=search [--hub][--all]` / `/search`. **Not in cogList or defaultCogs at all — orphaned, never loaded by the bot.**
- **startCog.py** (`campus.start`, `"Start"`) — start-of-semester countdown/hype posts, mirrors endCog. `=start` / `/start`. **In defaultCogs.**

### community/
- **bannerCog.py** (`community.banner`, `"Banner"`) — weekly reminder to submit banner photos, posted to a random channel. `=banner` / `/banner`. **In defaultCogs.**
- **birthdayCog.py** (`community.birthday`, `"Birthday"`) — self-service birthday tracking, auto role assign/remove, daily announcement, mod export/override. Hybrid group `birthday`: `set`, `get`, `remove`, `nearest`, `export` (mod), `override` (mod). **In defaultCogs.**
- **boostCog.py** (`community.boost`, `"Boost"`) — announces server boosts, lists booster perks. `=boost` / `/boost`. **In defaultCogs.**
- **feedbackCog.py** (`community.feedback`, `"Feedback"`) — anonymous feedback via persistent button+modal to mod queue. `=feedbacksetup` / `/feedbacksetup` (Manage Server). **In defaultCogs.**
- **helloCog.py** (`community.hello`, `"Hello"`) — trivial greeting. `=hello` / `/hello`. **In defaultCogs.**
- **joinPoliticsCog.py** (`community.joinPolitics`, `"JoinPolitics"`) — application flow (button→modal→mod approve/deny) for #politics access. `=joinpolitics` / `/joinpolitics` (mod-only, posts the start embed). **In defaultCogs.**
- **leavePoliticsCog.py** (`community.leavePolitics`, `"LeavePoliticsCog"`) — voluntary leave-#politics confirm/cancel flow. `=leavepolitics` / `/leavepolitics`. **In defaultCogs.**
- **lockinCog.py** (`community.lockin`, `"LockinCog"`) — self-service focus mode: strips roles for a duration, auto-restores. `=lockin <duration>` / `/lockin`, `=lockinleft` / `/lockinleft`. **In defaultCogs.**
- **loveCog.py** (`community.love`, `"Love"`) — placeholder "coming soon". `=love` / `/love`. **In defaultCogs.**
- **pingroleCog.py** (`"PingRoleCog"`) — ping one of 8 self-serve interest roles with a message, rate-limited. `/pingrole role: message:` (slash only). **In defaultCogs (`community.pingrole`).**
- **positivityCog.py** (`community.positivity`, `"Positivity"`) — "Positivity Tuesday" random-chatter shoutouts, per-guild config, auto on/off at midnight ET. Prefix/slash group `positivity`: `enable`, `disable`, `interval`, `cooldown`, `status`. **In defaultCogs.**
- **prideCog.py** (`"Pride"`) — posts a Pride-flag celebration message every 500 messages or on demand. `=pride` / `/pride`. **Not in cogList or defaultCogs at all — orphaned, never loaded by the bot.**
- **reactionCog.py** (`community.reaction`, `"Reaction"`) — sentiment-based auto-reaction when the bot is mentioned/replied to. No commands (listener only). **In defaultCogs.**
- **reactionRoleCog.py** (`community.reactionRole`, `"ReactionRole"`) — posts preset reaction-role embeds, grants/revokes role on emoji react. `/reactionrole preset:` (slash only, Manage Roles). **In defaultCogs.**
- **roleboostCog.py** (`community.roleboost`, `"RoleBoost"`) — mod grants a role to a booster; auto-revoked if boost lost. `=roleboost <user> <role>` / `/roleboost`. **In defaultCogs.**
- **starboardCog.py** (`community.starboard`, `"Starboard"`) — per-guild starboard + persistent star leaderboard. Slash group `/starboard`: `setchannel`, `threshold`, `enable`, `disable`, `status`; `=starleaderboard` / `/starleaderboard`. **In defaultCogs.**
- **towokenCog.py** (`community.towoken`, `"Towoken"`) — joke "rate limit" notice after 12 commands in a window. `=towoken enable|disable` / `/towoken` (mod-only toggle). **In defaultCogs.**
- **trollCog.py** (`community.troll`, `"TrollCog"`) — mod-toggleable "uwu-ify" mode via webhook-repost; self-service `/uwu`. `/troll mode: user:` (mod-gated), `=uwu`/`/uwu text:`. **In defaultCogs.**

### logging/
- **caseLogCog.py** (`logging.caseLog`, `"CaseLog"`) — aggregates kicks/timeouts/bans/hardmutes (own SQLite) + warnings (reads warningsCog's DB) into one paginated view; exports `record_case()` used bot-wide. `=modlogs <member>` / hybrid (mod-role gated). **In defaultCogs.**
- **joinLeaveCog.py** (`logging.joinLeave`, `"JoinLeave"`) — logs member joins/leaves. No commands. **In defaultCogs.**
- **logConfig.py** — **not a cog** (no `setup()`/`add_cog`), shared utility module: channel-ID constants, `MOD_ROLE_ID`, `MAIN_GUILD_ID`, colors, formatting helpers, in-memory cross-cog suppression registries. Imported by nearly every logging/moderation cog.
- **memberLogCog.py** (`logging.memberLog`, `"MemberLog"`) — logs nickname/username/avatar changes. No commands. **In defaultCogs.**
- **messageLogCog.py** (`logging.messageLog`, `"MessageLog"`) — logs deleted messages (single+bulk) with audit-log deleter lookup and purge attribution. No commands. **In defaultCogs.**
- **modLogCog.py** (`logging.modLog`, `"ModLog"`) — logs kicks/bans/timeouts via gateway events + audit log, suppressed when a richer embed was already posted by another mod cog. No commands. **In defaultCogs.**
- **serverLogCog.py** (`logging.serverLog`, `"ServerLog"`) — logs channel/role/emoji/member-role changes. No commands. **In defaultCogs.**

### moderation/
- **appealServerCog.py** (`moderation.appealServer`, `"AppealServer"`) — ban-appeal button/modal flow hosted in a separate appeals server. `postappealbutton` (owner-only prefix); rest is button/modal driven. **In defaultCogs.**
- **banCog.py** (`moderation.ban`, `"Ban"`) — ban/unban, temp-ban with auto-expiry, DM-based appeal intake, public ban announcements. `=ban <member> [rule][duration][reason]` / hybrid, `=unban <user_id>` / hybrid. **In defaultCogs.**
- **hardmuteCog.py** (`moderation.hardmute`, `"Hardmute"`) — strips roles + confines a member to one channel indefinitely. `=hardmute <member>`, `=unmute <member>` (hybrid). **In defaultCogs.**
- **kickCog.py** (`moderation.kick`, `"Kick"`) — kick with best-effort pre-kick DM. `=kick <member> [reason]` (hybrid). **In defaultCogs.**
- **lockdownCog.py** (`moderation.lockdown`, `"Lockdown"`) — locks/unlocks a channel (denies @everyone send/thread perms), in-memory snapshot restore. `=lockdown`, `=unlock` (hybrid). **In defaultCogs.**
- **modCommandsCog.py** (`moderation.modCommands`, `"ModCommands"`) — static mod command quick-reference embed (docs only, no state). `=modcommands` (hybrid). **In defaultCogs.**
- **modvoteCog.py** (`moderation.modvote`, `"ModVote"`) — anonymous mod voting on disciplining a member, persistent buttons, auto-close. `/modvote start|close` (slash group, mod-gated). **In defaultCogs.**
- **purgeCog.py** (`moderation.purge`, `"Purge"`) — bulk delete with purge attribution (feeds messageLogCog). `=purge <amount>`, `=purgeafter [target]` (hybrid). **In defaultCogs.**
- **scamImageCog.py** (`moderation.scamImage`, `"ScamImageCog"`) — perceptual-hash scam image detection/auto-timeout, cross-channel spam detection, report context menu. `/removehash <hash>` (slash), context menu "Report Image(s)". **In defaultCogs.**
- **snitchCog.py** (`moderation.snitch`, `"SnitchCog"`) — anonymous mod alert to the mod queue. `/snitch [context]` (slash only). **In defaultCogs.**
- **ticketCog.py** (`moderation.ticket`, `"TicketCog"`) — auto-handles TicketTool mod-application channels (renames, posts welcome). No commands (listener only). **In defaultCogs.**
- **timeoutCog.py** (`moderation.timeout`, `"Timeout"`) — manual timeout/untimeout with duration parsing. `=timeout <member> <duration>`, `=untimeout <member>` (hybrid). **In defaultCogs.**
- **warnAppealCog.py** (`moderation.warnAppeal`, `"WarnAppeal"`) — appeal one's own active warning via select+modal, mod accept/reject buttons. `/warnappeal` (slash only). **In defaultCogs.**
- **warningsCog.py** (`moderation.warnings`, `"WarningsCog"`) — core warning system (issue/list/inspect/remove), owns the canonical `warnings.db`. `=warn`, `=warncount`, `=warninfo`, `=mywarns`, `=warnremove` (hybrid). **In defaultCogs.**

### utility/
- **embedCog.py** (`utility.embed`, `"Embed"`) — owner-only rich embed composer + several hardcoded "campaign" embed sequences (registration/housing/mod handbook/rules). `/embed [channel]` (owner, modal); `embed`, `embedreg`, `embedhousing`, `embedmodhandbook`, `embedrules` (prefix). **In defaultCogs.**
- **helpCog.py** (`utility.help`, `"Help"`) — static categorized command-overview embed. `help` (prefix). **In defaultCogs.**
- **membersCog.py** (`utility.members`, `"Members"`) — owner-only member export/prune-report CSV tools. `exportmembers`, `exportprunecandidates`, `exportmembersbycategory` (prefix, guild-only). **In defaultCogs.**
- **testCog.py** (`utility.test`, `"Test"`) — connectivity check. `test` / `/test`; no-op `on_message` stub. **In defaultCogs.**

**Orphaned cogs (files exist, never loaded anywhere in `bot.py`):** `cogs/campus/searchCog.py`, `cogs/community/prideCog.py`.
**Loadable-but-not-auto-loaded:** `cogs/campus/endCog.py` (`campus.end` is in `cogList` but missing from `defaultCogs`).

---

## 2. Persistent storage map

### Shelve — `terrierbot.shelve` (repo root, gitignored via `*.shelve`)
Shared flat key-value store, opened independently by each cog via `shelve.open("terrierbot.shelve")` (relative path — process cwd dependent).

| Key(s) | Owner | Shape |
|---|---|---|
| `prefixes` | bot.py | `dict[guild_id:int, prefix:str]` |
| `error_alert_state`, `startup_failure_timestamps`, `startup_alerts_suppressed`, `startup_loop_alert_sent`, `last_startup_msg` | bot.py | crash-alert/cooldown bookkeeping |
| `banner_last_sent` | bannerCog | float timestamp — **note: computes `SHELVE_PATH` via `Path(__file__).resolve().parent.parent / "terrierbot.shelve"` instead of the bare relative string every other cog uses; verify this resolves to the same file given the deploy cwd** |
| `birthdays`, `birthday_announced_today`, `birthday_last_removed_date`, `birthday_current_holders` | birthdayCog | `{user_id_str: {month,day}}`; `{date, user_ids}`; iso date str; `list[int]` |
| `lockins` | lockinCog | `{user_id_str: {guild_id, role_id, end_timestamp, saved_role_ids}}` |
| `positivity_enabled_by_guild`, `positivity_interval_by_guild`, `positivity_count_by_guild`, `positivity_recent_selected_by_guild`, `positivity_opted_in_by_guild`, `positivity_manually_disabled_by_guild` | positivityCog | all `dict` keyed by `guild_id` |
| `reactionroles` | reactionRoleCog | `{message_id_str: role_id}` |
| `roleboost_assignments` | roleboostCog | `{member_id: role_id}` |
| `starboard_channel_by_guild`, `starboard_threshold_by_guild`, `starboard_enabled_by_guild`, `starboard_posted_messages`, `starboard_message_authors`, `starboard_message_star_counts`, `starboard_user_star_totals` | starboardCog | per-guild config + `guild→msg_id→...` maps |
| `towoken_enabled` | towokenCog | bool |
| `hardmutes` | hardmuteCog | `{user_id_str: {guild_id, saved_role_ids}}` — comment in code claims this shelve is also shared with "BanCog/LockinCog" for other keys, but banCog actually uses JSON (below), not shelve |

### SQLite — outside the repo, in `~/terrierbot_data/` (not gitignored via repo rules since it's outside the tree; not committed)
- **`casedb.sqlite3`** — owned by caseLogCog. Table `cases(id PK, user_id, moderator_id, case_type, reason, duration_seconds, created_at)`. Written via module-level `record_case()`, called by banCog, kickCog, timeoutCog, hardmuteCog, appealServerCog.
- **`warnings.db`** — owned by warningsCog. Table `warnings(id PK, user_id, moderator_id, rule, reason, warned_at, expires_at, active DEFAULT 1, removed_via)`. Read/written directly (by file path + schema, no shared accessor) by caseLogCog.py and warnAppealCog.py in addition to warningsCog.py itself.

### JSON — under `data/`
- **`data/birthday_migration.json`** (committed) — one-time idempotent seed, `{user_id_str: {month:int, day:int}}`. Consumed only by birthdayCog.
- **`data/scam_hashes.json`** (gitignored, present locally) — `list[str]` perceptual-hash hex strings. Owned by scamImageCog; falls back to a hardcoded 5-hash seed list if the file is absent.
- **`data/tempbans.json`** (gitignored, runtime-generated, not currently present) — `{"guild_id:user_id": {user_id, guild_id, unban_at, reason}}`. Owned by banCog.
- **`data/modvotes.json`** (gitignored, runtime-generated, not currently present) — `{"votes": {vote_id: {...}}, "sticky_by_channel": {channel_id: vote_id}}`. Owned by modvoteCog.
- **`data/pm2_restart_state.json`** (runtime-generated by `scripts/pm2-run-terrierbot.sh`, not a cog) — `{"timestamps": [int, ...]}`, tracks unexpected-exit timestamps for the PM2 restart-loop alert.
- **`sheets_service_account.json`** — listed in `.gitignore` but **no code in the repo actually loads it**; grep hits for "google/sheets" in towokenCog.py and embedCog.py are just plain Google Sites/Sheets URLs in message text, not credential usage. Looks vestigial.

### CSV — under `data/` (static reference data, mostly committed)
- **`data/Fall2026Courses.csv`** (committed, ~7.8MB) + **`data/BU_R0032B_SR_CLASS_SCHD_DOWNLD.csv`** (referenced by path, **not present in the repo** — classCog checks `.exists()` and silently skips if missing, so this is an optional/local-only registrar export, not a hard dependency) — both read by classCog for live section/instructor data.
- **`data/bu_courses_all.csv`** (committed, ~4.8MB) — primary dataset for searchCog (orphaned/unloaded, see §1) and also read by classCog just to augment its school→subject mapping.
- **`data/Category Roles - Copy of Sheet1.csv`** (committed) — category→role-name mapping, read only by membersCog's `exportmembersbycategory`.

---

## 3. Key constants & IDs

No central `config.py`/`constants.py`. IDs are defined per-cog as module-level (or method-local) literals; **`cogs/logging/logConfig.py`** is the closest thing to a shared constants module but only covers logging/mod-related IDs. Everything else is scattered and frequently duplicated by value rather than import.

**Guild IDs**
- `MAIN_GUILD_ID = 1396541818245484665` ("Terrier Hub") — defined in `logConfig.py`; redefined locally (same value) in `appealServerCog.py`.
- `APPEALS_GUILD_ID = 1541626494122598491` — dedicated ban-appeals server, `appealServerCog.py` only.

**Role IDs**
- `MOD_ROLE_ID = 1402095379935395934` — canonical definition in `logConfig.py`. Same numeric value is **independently redeclared** as: `joinPoliticsCog.MOD_ROLE_ID`, `roleboostCog.ROLEBOOST_MOD_ROLE_ID`, `modvoteCog.MOD_ROLE_ID`, `scamImageCog.SCAMCATCHER_ROLE_ID`, `ticketCog.MOD_ROLE_ID`, `embedCog`'s handbook-local `MOD_ROLE`, and `bot.py`'s `STATUS_ROLE_ID` (gates `/status`). `towokenCog.TOWOKEN_EXEMPT_USER_IDS = {1402095379935395934}` also reuses this value but as a *user*-ID exemption set — possible copy-paste mismatch of role vs. user ID.
- `BIRTHDAY_ROLE_ID = 1404879458992914484` (birthdayCog)
- `LOCKIN_ROLE_ID = 1410344839718895716` (lockinCog)
- `BOOST_ROLE_ID = 1415488019435098152` (roleboostCog — role granted to boosters)
- `POLITICS_ROLE_ID = 1477468718127775824` — duplicated identically in both `joinPoliticsCog.py` and `leavePoliticsCog.py`.
- `TROLL_ROLE_ID = 1529519978976379061` (trollCog)
- `HARDMUTE_ROLE_ID = 1441111071715758171` (hardmuteCog)
- `PRESETS["Freshmen"]["role_id"] = 1541770660710191134` (reactionRoleCog)
- `prune_role_id = 1474070492548956170` (membersCog)
- `pingroleCog.PINGROLES` — 8 role IDs: `1405219077693243434` (Eventee), `1412441490591842354` (Foodee), `1416190981102895136` (HungryLonger), `1422358773657243678` (FitnessFriend), `1425108753086287903` (StudyBuddy), `1458528619482710047` (MC), `1475971319366549534` (Val), `1503410327352508587` (SummerLocal)

**Channel IDs**
- `logConfig.LogChannels`: `JOIN_LEAVE=1441888109359796275`, `MEMBER=1441888363639603340`, `SERVER=1441888428735070400`, `MOD=1441889164898341098`, `MESSAGE=1441888579147141170`, `QUEUE=1541936565151080519` (consolidated mod-queue inbox — appeals, snitch reports, scam-hash confirms, politics apps), `ANNOUNCE=1470061524394709083`.
- `1396542256445391069` ("general"/announcements channel) — independently redeclared as `GENERAL_CHANNEL_ID` (endCog, startCog — startCog's copy has a `# TODO: confirm/replace channel id` comment), `BIRTHDAY_ANNOUNCE_CHANNEL_ID` (birthdayCog), `PRIDE_CHANNEL_ID` (prideCog, unloaded), and hardcoded directly in `bot.py`'s `on_ready` startup message.
- `1441925119202164886` — `bot.py`'s `ERROR_CHANNEL_ID`, same value as `roleboostCog.ANNOUNCE_CHANNEL_ID` and `embedCog`'s handbook-local `OWO_DOOMER_CHANNEL`.
- `RMP_CHANNEL_ID = 1404891150871040050` (rmpCog)
- `BANNER_CHANNELS = [1402962052812898404, 1403922809012355172]` (bannerCog)
- `POLITICS_CHANNEL_ID = 1477468981194391675` (joinPoliticsCog)
- `RULES_CHANNEL_ID = 1396542143803424768` — joinPoliticsCog and embedCog's handbook-local `RULES_CHANNEL` (same value, independently declared).
- `MOD_APP_CATEGORY_ID = 1528788382434726029` (ticketCog)
- `HARDMUTE_CHANNEL_ID = 1498345257455194242` (hardmuteCog)
- embedCog handbook-local only: `MOD_IMPORTANT_CHANNEL=1401924438341062798`, `MOD_FEET_CHANNEL=1446304077213597807`, `CONFESSION_REVIEW_CHANNEL=1441905934975635566`, `MOD_QUEUE_CHANNEL=1541936565151080519` (=`LogChannels.QUEUE`, redeclared).

**Other**
- `SERVER_OWNER = 1274047585098793034` (user ID, embedCog handbook text only)
- `MEAN_EMOJI_ID=1499771566475706553`, `NICE_EMOJI_ID=1499771565670137886` (reactionCog, custom emoji)
- `STATUS_ROLE_ID`, `ERROR_CHANNEL_ID` in `bot.py` — see above, duplicate other cogs' values rather than importing.

---

## 4. Cross-cog dependencies

(Excludes the `logConfig.py` shared-utility import pattern, which is used by nearly every logging/moderation cog for `LogChannels`/`MOD_ROLE_ID`/`MAIN_GUILD_ID`/helpers — that's noted in §1/§3, not repeated here.)

- **classCog ↔ rmpCog** (bidirectional, campus/): `rmpCog.py` does `from .classCog import _parse_course_query`; at runtime, `classCog`'s `_RMPButton` calls `bot.get_cog("RMP")` and `rmpCog`'s `ClassLookupView` calls `bot.get_cog("Class")` + `lookup_course()`.
- **appealServerCog → banCog** (moderation/): calls `bot.get_cog("Ban")` and reaches into `ban_cog._remove_tempban(...)` — a private-by-convention method accessed cross-cog; degrades gracefully (logs a warning) if BanCog isn't loaded.
- **banCog → warningsCog** (moderation/): `from .warningsCog import RULES` (rule-name dict for the `=ban` rule parameter).
- **warnAppealCog → warningsCog** (moderation/): `from .warningsCog import DB_PATH, RULES` — reuses warningsCog's SQLite path and rule dict directly rather than an API.
- **caseLogCog → warningsCog** (moderation/logging split): reads `~/terrierbot_data/warnings.db` directly by file path + schema (documented in-code as intentional since warningsCog exposes no public query function) — a data-layer coupling, not an import, but functionally the same dependency.
- **caseLogCog.record_case()** is called from banCog, kickCog, timeoutCog, hardmuteCog, appealServerCog (`from ..logging.caseLogCog import record_case`) — a one-way fan-in dependency from most moderation cogs into logging/caseLogCog.
- **messageLogCog / modLogCog ← purgeCog / scamImageCog / kickCog / banCog / timeoutCog**: not direct calls, but these cogs write into `logConfig`'s in-memory suppression/purge-attribution registries (`register_purge`, `suppress_message_log`, `suppress_mod_log`) which messageLogCog/modLogCog read — a shared-mutable-state coupling routed through logConfig rather than a direct cross-cog call.

**Shared-data (not shared-code) couplings worth knowing about:**
- `data/bu_courses_all.csv` read by both `searchCog.py` (orphaned/unloaded) and `classCog.py`.
- `terrierbot.shelve` is a single flat namespace shared by 9 cogs + bot.py, keyed by convention rather than enforced schema.

---

## 5. Recent changes

`git log --oneline -30`:

```
9b1b797 error catching
2e7d433 direction mbta
acd055d save my changes
d8678b9 update politics for kiddos
0b55419 help cog
5a3a812 mbtagay
74a87e1 bday remove override
fa47a34 birthday make pretty
4d8b0c5 birf
3114571 birthday cog
b360235 trivial
7729614 cute ifying help
b3af231 help cute
0864e09 uwu and ban
441242c better perms message :3
5abf1f3 notify for warns
1f7da1f warning and timeout anonymize
a98025c correct errowors
fdd41f5 hardmute and other updates
b1b3358 fix
34b988c mod handbook update
0cf6345 mo dcommand
9530e43 fix error
2206db3 update lockin
7aa9296 rules embed and quorum kill
448daf8 fix politics
08fb513 ban update
2ad6616 feedback route
2386ac7 rereouting
74300c3 rules update
```

Glosses for non-obvious messages (checked via `git show --stat`):
- **acd055d "save my changes"** — bot.py only; likely a WIP checkpoint commit.
- **5a3a812 "mbtagay"** — adds the `mbtgay`/`/mbtgay` Pride Train tracker to mbtaCog.py (touches README.md, bot.py, mbtaCog.py).
- **4d8b0c5 "birf"** — birthdayCog.py + bot.py changes (part of the birthday-feature build-out around this time).
- **b360235 "trivial"** — bot.py only, small/inconsequential change.
- **7729614 "cute ifying help" / b3af231 "help cute"** — cosmetic rewrite of helpCog.py's embed text/formatting.
- **0864e09 "uwu and ban"** — touches trollCog.py and banCog.py together (adds/adjusts uwu-mode and a ban-flow change in the same commit).
- **0cf6345 "mo dcommand"** — typo for "mod command"; modCommandsCog.py only.
- **a98025c "correct errowors"** — typo for "correct errors"; embedCog.py only.
- **9530e43 "fix error"** — bot.py + lockinCog.py.
- **2386ac7 "rereouting"** — typo for "rerouting"; moves/adjusts mod-queue routing across joinPoliticsCog, logConfig, appealServerCog, scamImageCog, snitchCog, warnAppealCog (consistent with the current shared `LogChannels.QUEUE` design).

General pattern: development is active and iterative on the same handful of areas — politics application flow, birthdays, help/embed cosmetics, ban/warning/mod-queue routing, and MBTA.

---

## 6. Known TODOs/FIXMEs

- **`cogs/campus/startCog.py:21`** — `GENERAL_CHANNEL_ID = 1396542256445391069  # TODO: confirm/replace channel id`. Only TODO/FIXME/XXX marker in the codebase. Note this ID is already duplicated across 4 other cogs (see §3) — resolving the TODO likely means consolidating all of them, not just this one.
- **No FIXME or XXX markers found anywhere.**
- **No commented-out code blocks found** — a heuristic grep for comment lines containing `await`/`def `/`self.`/`import` turned up only ordinary prose comments (e.g. explaining why a constant is duplicated, or why a query runs at import time), not dead code left in place.
- **Structural TODO-equivalents surfaced during this audit** (not marked in code, but worth listing since they're the kind of thing a planning pass would want to know):
  - `cogs/campus/searchCog.py` and `cogs/community/prideCog.py` exist but are never loaded (not in `cogList`/`defaultCogs`) — either intentionally shelved or accidentally dropped from the load list.
  - `cogs/campus/endCog.py` is in `cogList` but missing from `defaultCogs` — loadable manually but not auto-started; unclear if intentional (e.g. only meant to be loaded near end-of-semester) or an oversight.
  - `data/BU_R0032B_SR_CLASS_SCHD_DOWNLD.csv` is referenced by `classCog.py` but not present in the repo (handled gracefully via `.exists()` check).
  - `sheets_service_account.json` is gitignored but unreferenced by any code — likely vestigial.

---

## 7. Deployment-relevant files

- **`.github/workflows/deploy.yml`** — self-hosted runner, triggers on push to `main`. `git fetch --prune && git reset --hard origin/main`, installs `requirements.txt` only if it changed. Deploy strategy: if only `cogs/*Cog.py` files changed, hot-reloads each changed cog via `POST http://127.0.0.1:8080/reload/<cog>` (with `X-Reload-Secret` header); if anything else changed (bot.py, logConfig.py, requirements.txt, non-`*Cog.py` file, new file, etc.) it does a full `pm2 restart terrierbot --update-env` instead. A failed hot-reload also falls back to full restart. **Current and appears to match the deployed setup** (the reload endpoint, header name, and cog-naming convention in the workflow match `bot.py`'s `/reload/<cog_name>` route exactly).
- **`bot.py`'s Flask server** (`run_web_server`, started via `asyncio.to_thread` alongside the bot) — `GET /` health check (`{"latency": ...}`, 200 if `bot.is_ready()` else 503); `POST /reload/<cog_name>` (auth via `X-Reload-Secret` header checked against `RELOAD_SECRET` env var or `reload_secret.txt`, currently **neither is present in the working tree**, so the endpoint is effectively disabled — always 401 — unless the deployed server has one of those set outside the repo). Listens on `PORT` env var, default 8080 — matches the hardcoded `127.0.0.1:8080` in `deploy.yml`.
- **`ecosystem.config.cjs`** (PM2 config) — single app `terrierbot`, runs `scripts/pm2-run-terrierbot.sh` via bash, `autorestart: true`, `max_restarts: 100`, `restart_delay: 5000`, `exp_backoff_restart_delay: 100`. Env vars set here: `PYTHON_BIN=./ven/bin/python` (points at the local `ven/` virtualenv checked into `.gitignore`), `BOT_MAIN=./bot.py`, `ALERT_STATE_FILE=./data/pm2_restart_state.json`, `PM2_RESTART_WINDOW_SECONDS=300`, `PM2_RESTART_ALERT_THRESHOLD=5`. Consistent with the deploy workflow's `pm2 restart terrierbot`.
- **`scripts/pm2-run-terrierbot.sh`** — wraps the python process; on exit, classifies the exit code against `PM2_EXPECTED_EXIT_CODES` (default `0 130 143`), tracks a rolling window of "unexpected" exits in `ALERT_STATE_FILE` (JSON `{"timestamps":[...]}`), and if a `DISCORD_ALERT_WEBHOOK` env var is set, posts a webhook alert (escalating to "HIGH PRIORITY" if restarts exceed the threshold within the window). This is a second, independent crash-alerting path from `bot.py`'s own in-process `report_exception`/Discord-channel alerting — the two don't share state.
- **`.envrc`** — present (direnv), not inspected in detail; likely sets local dev env vars (e.g. `DISCORD_TOKEN`). Not part of the deploy path (deploy.yml doesn't source it).
- **Potentially stale/worth double-checking:** the hot-reload path in `deploy.yml` assumes the running process's Flask server already has `RELOAD_SECRET` set (otherwise every hot-reload attempt 401s and falls back to a full restart, which still works but defeats the purpose of the reload optimization) — since `reload_secret.txt` isn't in the repo and would have to be set via env var or a gitignored file directly on the server, this is invisible from the repo alone and should be verified against the actual deployed environment.
