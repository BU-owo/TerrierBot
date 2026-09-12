from __future__ import annotations

import json
import os
import time
from datetime import timedelta

import discord


class LogChannels:
    """Channel IDs for TerrierBot's logging layout. Import these instead of
    hardcoding IDs in individual cogs."""
    JOIN_LEAVE = 1441888109359796275
    MEMBER = 1441888363639603340
    SERVER = 1441888428735070400
    MOD = 1441889164898341098
    MESSAGE = 1441888579147141170
    # Consolidated "mod queue" — every flow that posts something for a mod to
    # review/act on (warn appeals, ban appeals, politics applications, snitch
    # reports, the scam-hash confirm prompt) posts the request here. Once a
    # mod decides, a permanent record of that decision goes to MOD above.
    QUEUE = 1541936565151080519
    # Plain-text, non-embed one-liner announcements ("X has been banned.")
    # posted alongside the richer MOD embed above whenever a ban happens —
    # a separate, lower-detail public channel.
    ANNOUNCE = 1470061524394709083
    # "OwO Doomer" — bot error/crash alerts (bot.py) and boost-role
    # announcements (roleboostCog) both post here.
    DOOMER = 1441925119202164886


# Mod role ID — several cogs previously redefined this constant locally with
# the same value; import it from here instead of re-declaring it.
MOD_ROLE_ID = 1402095379935395934


# Terrier Hub — the only guild these logging cogs should report activity
# for. TerrierBot is also a member of a separate appeals server (see
# appealServerCog.py), and every LogChannels.* channel above lives in this
# guild only — guild-scoped listeners must guard on this ID so activity
# from the appeals server doesn't get logged into Terrier Hub's channels.
MAIN_GUILD_ID = 1396541818245484665


class LogColors:
    """Standard embed colors per log category. Keep these consistent across
    every cog that posts to a log channel."""
    JOIN = discord.Color.green()
    LEAVE = discord.Color.red()
    MEMBER = discord.Color.blue()
    SERVER = discord.Color.gold()
    MOD = discord.Color.dark_red()
    MESSAGE = discord.Color.dark_grey()
    MOD_DELETE = discord.Color.orange()


def get_log_channel(bot: discord.Client, channel_id: int) -> discord.TextChannel | None:
    """Fetch a log channel by ID. Returns None (fail-silent) if the bot
    can't see it, so callers should always guard on this."""
    channel = bot.get_channel(channel_id)
    if isinstance(channel, discord.TextChannel):
        return channel
    return None


def format_duration(delta: timedelta) -> str:
    """Human-readable duration (e.g. "3 hours 15 minutes", "2 days"),
    granular enough to still be meaningful for spans under a day."""
    total_seconds = int(delta.total_seconds())
    if total_seconds <= 0:
        return "0 minutes"
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if not parts and seconds:
        parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
    return " ".join(parts) if parts else "less than a minute"


def user_line(user: discord.abc.User) -> str:
    """Mention + plain username as literal text, so the name stays legible
    even after the account leaves the server or is deleted and the client
    can no longer resolve the mention."""
    return f"{user.mention} — **{user}** (`{user.id}`)"


# ── Cross-cog deletion suppression ───────────────────────────────────────────
# Some cogs (e.g. scamImageCog) delete a message AND post their own richer
# log entry for it elsewhere (mod-log). Without this, MessageLogCog would
# also log the same deletion as a generic entry in #message-logs, duplicating
# it. Call suppress_message_log(message.id) immediately before you delete a
# message that's already being logged elsewhere.

_suppressed_message_ids: dict[int, float] = {}
_SUPPRESS_TTL_SECONDS = 30  # generous window to cover any delay before on_message_delete fires


def suppress_message_log(message_id: int) -> None:
    """Mark a message ID so MessageLogCog skips logging its deletion."""
    _suppressed_message_ids[message_id] = time.monotonic()


def is_suppressed(message_id: int) -> bool:
    """Check (and consume) a suppression flag for a message ID. Also
    opportunistically prunes stale entries so this dict can't grow unbounded."""
    now = time.monotonic()
    stale = [mid for mid, ts in _suppressed_message_ids.items() if now - ts > _SUPPRESS_TTL_SECONDS]
    for mid in stale:
        _suppressed_message_ids.pop(mid, None)

    ts = _suppressed_message_ids.pop(message_id, None)
    if ts is None:
        return False
    return (now - ts) <= _SUPPRESS_TTL_SECONDS


# ── Cross-cog mod-log suppression ────────────────────────────────────────────
# kickCog/timeoutCog/banCog each post their own (richer) embed to the mod-log
# channel right after performing an action, but that action — guild.kick(),
# member.timeout(), guild.ban()/unban() — also fires the matching gateway
# event that ModLogCog listens on, so without this it would post a second,
# duplicate, plainer entry for the same action. Call suppress_mod_log(...)
# right after the action call succeeds and before posting your own embed; the
# same pattern as suppress_message_log/is_suppressed above, just keyed on
# (user_id, action) instead of a message ID.

_suppressed_mod_log: dict[tuple[int, str], float] = {}
_MOD_LOG_SUPPRESS_TTL_SECONDS = 30  # generous window to cover audit-log propagation delay


def suppress_mod_log(user_id: int, action: str) -> None:
    """Mark a (user_id, action) pair so ModLogCog skips logging it. `action`
    is one of "kick", "timeout", "untimeout", "ban", "unban"."""
    _suppressed_mod_log[(user_id, action)] = time.monotonic()


def is_mod_log_suppressed(user_id: int, action: str) -> bool:
    """Check (and consume) a suppression flag for (user_id, action). Also
    opportunistically prunes stale entries so this dict can't grow unbounded."""
    now = time.monotonic()
    stale = [key for key, ts in _suppressed_mod_log.items() if now - ts > _MOD_LOG_SUPPRESS_TTL_SECONDS]
    for key in stale:
        _suppressed_mod_log.pop(key, None)

    ts = _suppressed_mod_log.pop((user_id, action), None)
    if ts is None:
        return False
    return (now - ts) <= _MOD_LOG_SUPPRESS_TTL_SECONDS


# ── Cross-cog purge attribution ──────────────────────────────────────────────
# PurgeCog's =purge bulk-deletes via TextChannel.purge(), which fires the same
# on_raw_bulk_message_delete event as any other bulk delete. Unlike
# suppress_message_log above, a purge should still show up in #message-logs —
# just attributed to the mod who ran it instead of logged as a generic,
# unattributed bulk delete. Call register_purge(...) right after the purge
# call succeeds, with the message IDs it actually deleted.

_purge_registry: dict[int, tuple[int, float]] = {}
_PURGE_TTL_SECONDS = 30  # generous window to cover any delay before on_raw_bulk_message_delete fires


def register_purge(message_ids: list[int], deleter_id: int, channel_id: int) -> None:
    """Record that `deleter_id` purged these message IDs from `channel_id`,
    so MessageLogCog can attribute the resulting bulk-delete log entry.
    `channel_id` isn't needed for the lookup (message IDs are already unique)
    but is accepted for a clearer call site."""
    _ = channel_id
    now = time.monotonic()
    for message_id in message_ids:
        _purge_registry[message_id] = (deleter_id, now)


def get_purger(message_id: int) -> int | None:
    """Check (and consume) purge attribution for a message ID — returns the
    deleter's user ID if it was part of a registered purge, else None. Also
    opportunistically prunes stale entries so this dict can't grow unbounded."""
    now = time.monotonic()
    stale = [mid for mid, (_, ts) in _purge_registry.items() if now - ts > _PURGE_TTL_SECONDS]
    for mid in stale:
        _purge_registry.pop(mid, None)

    entry = _purge_registry.pop(message_id, None)
    if entry is None:
        return None
    deleter_id, ts = entry
    if (now - ts) > _PURGE_TTL_SECONDS:
        return None
    return deleter_id


# ── Mod-queue stale-item reminder ────────────────────────────────────────────
# Any cog that posts an actionable item to LogChannels.QUEUE — something a mod
# must approve/deny/accept/reject (warn appeals, ban appeals, politics
# applications, and any future addition) — registers it here right after
# posting, and resolves it the moment a decision is made. Unlike the
# suppression registries above, this has to survive a restart (a mod could be
# sitting on a decision for most of the hour), so it's backed by a small JSON
# file rather than just an in-memory dict — same pattern as modvoteCog's
# modvotes.json. ModQueueReminderCog owns the periodic scan (see
# cogs/logging/modQueueReminderCog.py) and pings the mod role, once, for
# anything still unresolved an hour after it was registered.

_QUEUE_ITEMS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "mod_queue_reminders.json"
)
STALE_QUEUE_ITEM_SECONDS = 60 * 60  # 1 hour


def _load_queue_items() -> dict[str, dict]:
    if not os.path.exists(_QUEUE_ITEMS_FILE):
        return {}
    with open(_QUEUE_ITEMS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_queue_items(items: dict[str, dict]) -> None:
    os.makedirs(os.path.dirname(_QUEUE_ITEMS_FILE), exist_ok=True)
    with open(_QUEUE_ITEMS_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)


def register_queue_item(*, message_id: int, channel_id: int) -> None:
    """Call right after successfully posting an actionable item to the mod
    queue, with the id of the message that was posted (the one carrying the
    decision buttons)."""
    items = _load_queue_items()
    items[str(message_id)] = {
        "channel_id": channel_id,
        "posted_ts": int(time.time()),
        "reminded": False,
    }
    _save_queue_items(items)


def resolve_queue_item(message_id: int) -> None:
    """Call the moment a decision is made (approve/deny/accept/reject, or the
    item becomes moot, e.g. its underlying warning was nullified) — stops the
    stale-item reminder from ever firing for this item."""
    items = _load_queue_items()
    if items.pop(str(message_id), None) is not None:
        _save_queue_items(items)


def get_stale_queue_items(now_ts: int) -> list[tuple[int, int]]:
    """Returns (message_id, channel_id) for every registered item posted more
    than an hour ago that hasn't been resolved or already reminded about —
    and marks them reminded, so this only ever fires once per item."""
    items = _load_queue_items()
    stale: list[tuple[int, int]] = []
    changed = False
    for key, entry in items.items():
        if entry.get("reminded"):
            continue
        if now_ts - entry["posted_ts"] >= STALE_QUEUE_ITEM_SECONDS:
            stale.append((int(key), entry["channel_id"]))
            entry["reminded"] = True
            changed = True
    if changed:
        _save_queue_items(items)
    return stale
