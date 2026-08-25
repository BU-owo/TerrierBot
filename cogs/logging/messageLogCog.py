from __future__ import annotations

import discord
from discord.ext import commands

from bot import TerrierBot
from .logConfig import LogChannels, LogColors, MAIN_GUILD_ID, get_log_channel, get_purger, is_suppressed

# How recent an audit log entry must be to count as "this deletion" — Discord
# only creates a message_delete audit entry when someone deletes another
# user's message (never for self-deletes), so a fresh match means a mod/bot
# did it.
_AUDIT_LOOKUP_WINDOW_SECONDS = 10

# Bulk-delete content preview limits — keep well under Discord's 4096-char
# embed description cap even in the worst case (long author names, every
# listed message hitting the per-line truncation).
_BULK_CONTENT_MAX_LEN = 150
_BULK_MAX_LISTED_MESSAGES = 15


async def setup(bot: TerrierBot):
    await bot.add_cog(MessageLogCog(bot))


class MessageLogCog(commands.Cog, name="MessageLog", description="Logs deleted messages."):
    def __init__(self, bot: TerrierBot):
        self.bot = bot

    async def _find_deleter(
        self, guild: discord.Guild, channel_id: int, author_id: int
    ) -> discord.Member | discord.User | None:
        """Best-effort lookup of who deleted a message via the audit log.
        Returns None if it was likely a self-delete, or the log can't be read."""
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.message_delete):
                if entry.target is None or entry.target.id != author_id:
                    continue
                if entry.extra.channel.id != channel_id:
                    continue
                age = (discord.utils.utcnow() - entry.created_at).total_seconds()
                if age > _AUDIT_LOOKUP_WINDOW_SECONDS:
                    continue
                return entry.user
        except (discord.Forbidden, discord.HTTPException):
            pass
        return None

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        # Use the raw event, not on_message_delete — the non-raw event only
        # fires when the message happens to still be in discord.py's internal
        # cache (bot-wide default cap of ~1000 messages), so deletions of
        # older/uncached messages were silently never logged.
        if payload.guild_id != MAIN_GUILD_ID:
            return
        if is_suppressed(payload.message_id):
            return  # already logged elsewhere (e.g. scam alert in mod-log)

        message = payload.cached_message
        if message is not None and message.author.bot:
            return

        channel = get_log_channel(self.bot, LogChannels.MESSAGE)
        if channel is None or channel.id == payload.channel_id:
            # Nothing to log to, or the deletion happened inside the log
            # channel itself — skip to avoid a feedback loop.
            return

        deleter: discord.Member | discord.User | None = None
        guild = self.bot.get_guild(payload.guild_id)

        if message is not None:
            content = message.content or "*(no text content)*"
            if len(content) > 900:
                content = content[:897] + "..."

            source_channel_mention = message.channel.mention

            if guild is not None:
                deleter = await self._find_deleter(guild, payload.channel_id, message.author.id)

            description_lines = [
                f"**Message deleted in {source_channel_mention}**",
                "",
                content,
            ]
            if message.attachments:
                description_lines.append(
                    "**Attachments:** " + ", ".join(a.filename for a in message.attachments)
                )
            if deleter is not None and deleter.id != message.author.id:
                description_lines.append(f"-# 🔨 Deleted by {deleter.mention}")

            embed = discord.Embed(
                description=f"{message.author.mention}\n" + "\n".join(description_lines),
                color=LogColors.MOD_DELETE if deleter is not None else LogColors.MESSAGE,
                timestamp=discord.utils.utcnow(),
            )
            embed.set_author(
                name=str(message.author),
                icon_url=message.author.display_avatar.url,
            )
            embed.set_footer(text=f"User ID: {message.author.id} • Message ID: {payload.message_id}")
        else:
            source_channel = self.bot.get_channel(payload.channel_id)
            location = source_channel.mention if source_channel else f"<#{payload.channel_id}>"
            embed = discord.Embed(
                description=(
                    f"**Message deleted in {location}**\n\n"
                    f"*(not seen by the bot before deletion — author/content unavailable)*"
                ),
                color=LogColors.MESSAGE,
                timestamp=discord.utils.utcnow(),
            )
            embed.set_footer(text=f"Message ID: {payload.message_id}")

        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        if payload.guild_id != MAIN_GUILD_ID:
            return

        cached_by_id = {m.id: m for m in payload.cached_messages}
        total = 0
        uncached_count = 0
        content_messages: list[discord.Message] = []
        for mid in payload.message_ids:
            if is_suppressed(mid):
                continue
            cached = cached_by_id.get(mid)
            if cached is not None and cached.author.bot:
                continue
            total += 1
            if cached is None:
                uncached_count += 1
            else:
                content_messages.append(cached)
        if total == 0:
            return

        # payload.message_ids is an unordered set, so cached messages are
        # collected in no particular order above — sort chronologically
        # (snowflake IDs are monotonic) before displaying them.
        content_messages.sort(key=lambda m: m.id)

        channel = get_log_channel(self.bot, LogChannels.MESSAGE)
        if channel is None:
            return

        source_channel = self.bot.get_channel(payload.channel_id)
        location = source_channel.mention if source_channel else f"<#{payload.channel_id}>"

        # If every message in this batch was purged by the same mod (=purge),
        # attribute it instead of logging a generic bulk delete. Falls back
        # to the generic line if attribution is missing or mixed (e.g. a
        # purge overlapping with an unrelated deletion in the same batch).
        purger_ids = {get_purger(mid) for mid in payload.message_ids}
        if len(purger_ids) == 1 and None not in purger_ids:
            (deleter_id,) = purger_ids
            description = f"{total} message(s) purged by <@{deleter_id}> in {location}"
        else:
            description = f"{total} message(s) deleted in {location}"
            if uncached_count:
                description += f" ({uncached_count} uncached)"

        content_lines: list[str] = []
        for message in content_messages[:_BULK_MAX_LISTED_MESSAGES]:
            content = message.content.replace("\n", " ") if message.content else "*(no text content)*"
            if len(content) > _BULK_CONTENT_MAX_LEN:
                content = content[: _BULK_CONTENT_MAX_LEN - 1].rstrip() + "…"
            content_lines.append(f"**{message.author}:** {content}")

        remaining_cached = len(content_messages) - len(content_lines)
        if remaining_cached > 0:
            content_lines.append(f"...and {remaining_cached} more")

        if uncached_count:
            content_lines.append(f"+ {uncached_count} uncached message(s) — content unavailable")

        if content_lines:
            description += "\n\n" + "\n".join(content_lines)

        embed = discord.Embed(
            title="🗑️ Bulk message delete",
            description=description,
            color=LogColors.MESSAGE,
            timestamp=discord.utils.utcnow(),
        )
        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass
