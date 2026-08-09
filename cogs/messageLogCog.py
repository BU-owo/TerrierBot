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
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if is_suppressed(message.id):
            return  # already logged elsewhere (e.g. scam alert in mod-log)

        channel = get_log_channel(self.bot, LogChannels.MESSAGE)
        if channel is None or channel.id == message.channel.id:
            # Nothing to log to, or the deletion happened inside the log
            # channel itself — skip to avoid a feedback loop.
            return

        content = message.content or "*(no text content)*"
        if len(content) > 900:
            content = content[:897] + "..."

        lines = [
            f"{message.author.mention} (`{message.author.id}`) in {message.channel.mention}",
            content,
        ]
        if message.attachments:
            lines.append("**Attachments:** " + ", ".join(a.filename for a in message.attachments))

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
    async def on_bulk_message_delete(self, messages: list[discord.Message]):
        if not messages or messages[0].guild is None:
            return

        non_bot = [m for m in messages if not m.author.bot and not is_suppressed(m.id)]
        if not non_bot:
            return

        channel = get_log_channel(self.bot, LogChannels.MESSAGE)
        if channel is None:
            return

        embed = discord.Embed(
            title="🗑️ Bulk message delete",
            description=f"{len(non_bot)} message(s) deleted in {messages[0].channel.mention}",
            color=LogColors.MESSAGE,
            timestamp=discord.utils.utcnow(),
        )
        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass
