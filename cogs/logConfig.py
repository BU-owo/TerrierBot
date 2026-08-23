from __future__ import annotations

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


# Mod role ID — several cogs previously redefined this constant locally with
# the same value; import it from here instead of re-declaring it.
MOD_ROLE_ID = 1402095379935395934


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
