from __future__ import annotations

import discord
from discord.ext import commands

from bot import TerrierBot
from .logConfig import LogChannels, LogColors, get_log_channel, is_suppressed


async def setup(bot: TerrierBot):
    await bot.add_cog(MessageLogCog(bot))


class MessageLogCog(commands.Cog, name="MessageLog", description="Logs deleted messages."):
    def __init__(self, bot: TerrierBot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        # Use the raw event, not on_message_delete — the non-raw event only
        # fires when the message happens to still be in discord.py's internal
        # cache (bot-wide default cap of ~1000 messages), so deletions of
        # older/uncached messages were silently never logged.
        if payload.guild_id is None:
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

        if message is not None:
            content = message.content or "*(no text content)*"
            if len(content) > 900:
                content = content[:897] + "..."
            lines = [
                f"{message.author.mention} (`{message.author.id}`) in {message.channel.mention}",
                content,
            ]
            if message.attachments:
                lines.append("**Attachments:** " + ", ".join(a.filename for a in message.attachments))
        else:
            source_channel = self.bot.get_channel(payload.channel_id)
            location = source_channel.mention if source_channel else f"<#{payload.channel_id}>"
            lines = [
                f"Uncached message deleted in {location}",
                f"*(not seen by the bot before deletion — author/content unavailable, ID `{payload.message_id}`)*",
            ]

        embed = discord.Embed(
            title="🗑️ Message deleted",
            description="\n".join(lines),
            color=LogColors.MESSAGE,
            timestamp=discord.utils.utcnow(),
        )

        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        if payload.guild_id is None:
            return

        cached_by_id = {m.id: m for m in payload.cached_messages}
        total = 0
        uncached_count = 0
        for mid in payload.message_ids:
            if is_suppressed(mid):
                continue
            cached = cached_by_id.get(mid)
            if cached is not None and cached.author.bot:
                continue
            total += 1
            if cached is None:
                uncached_count += 1
        if total == 0:
            return

        channel = get_log_channel(self.bot, LogChannels.MESSAGE)
        if channel is None:
            return

        source_channel = self.bot.get_channel(payload.channel_id)
        location = source_channel.mention if source_channel else f"<#{payload.channel_id}>"

        description = f"{total} message(s) deleted in {location}"
        if uncached_count:
            description += f" ({uncached_count} uncached)"

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
