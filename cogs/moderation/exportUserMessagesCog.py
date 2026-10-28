from __future__ import annotations

import csv
import io

import discord
from discord.ext import commands

from bot import Context, TerrierBot

_FIELDS = ["row", "message_id", "channel_id", "channel", "timestamp_utc", "content", "attachments", "jump_url", "delete"]


async def setup(bot: TerrierBot):
    await bot.add_cog(ExportUserMessagesCog(bot))


class ExportUserMessagesCog(
    commands.Cog,
    name="ExportUserMessages",
    description="DMs the owner a CSV of every message a user has sent in the server (owner only).",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot

    @staticmethod
    async def _channels(guild: discord.Guild) -> list:
        channels = [*guild.text_channels, *guild.voice_channels, *guild.threads]
        for channel in guild.text_channels:
            try:
                async for thread in channel.archived_threads(limit=None):
                    channels.append(thread)
            except (discord.Forbidden, discord.HTTPException):
                pass
        return channels

    @commands.command(name="exportusermessages", hidden=True)
    @commands.is_owner()
    @commands.guild_only()
    async def exportusermessages(self, ctx: Context, user_id: int):
        """Owner only. Silently DMs a CSV of all of a user's messages in this server."""
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        rows: list[dict] = []
        skipped: list[str] = []
        for channel in await self._channels(ctx.guild):
            try:
                async for m in channel.history(limit=None, oldest_first=True):
                    if m.author.id == user_id:
                        rows.append({
                            "message_id": m.id,
                            "channel_id": channel.id,
                            "channel": channel.name,
                            "timestamp_utc": m.created_at.isoformat(),
                            "content": m.content,
                            "attachments": " ".join(a.url for a in m.attachments),
                            "jump_url": m.jump_url,
                        })
            except discord.HTTPException:
                skipped.append(f"#{channel.name}")

        rows.sort(key=lambda r: r["timestamp_utc"])
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=_FIELDS)
        writer.writeheader()
        for i, row in enumerate(rows, start=1):
            writer.writerow({"row": i, **row, "delete": ""})

        # utf-8-sig so Excel opens emoji/non-ASCII text correctly
        file = discord.File(io.BytesIO(buffer.getvalue().encode("utf-8-sig")), filename=f"messages_{user_id}.csv")
        note = f"{len(rows)} messages from `{user_id}` in {ctx.guild.name}."
        if skipped:
            note += f" Couldn't read: {', '.join(skipped)}"
        try:
            await ctx.author.send(note[:2000], file=file)
        except discord.HTTPException:
            pass
