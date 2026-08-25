from __future__ import annotations

import discord
from discord.ext import commands

from bot import TerrierBot
from .logConfig import LogChannels, LogColors, get_log_channel


async def setup(bot: TerrierBot):
    await bot.add_cog(MemberLogCog(bot))


class MemberLogCog(commands.Cog, name="MemberLog", description="Logs nickname, username, and avatar changes."):
    def __init__(self, bot: TerrierBot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.nick == after.nick:
            return

        channel = get_log_channel(self.bot, LogChannels.MEMBER)
        if channel is None:
            return

        embed = discord.Embed(
            title="✏️ Nickname changed",
            description=(
                f"{after.mention} (`{after.id}`)\n"
                f"**Before:** {before.nick or '*(none)*'}\n"
                f"**After:** {after.nick or '*(none)*'}"
            ),
            color=LogColors.MEMBER,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=after.display_avatar.url)

        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        # on_user_update fires globally (not guild-scoped) — only log for
        # guilds this bot actually shares with the user.
        if after.bot:
            return
        if before.name == after.name and before.display_avatar.key == after.display_avatar.key:
            return

        for guild in self.bot.guilds:
            member = guild.get_member(after.id)
            if member is None:
                continue

            channel = get_log_channel(self.bot, LogChannels.MEMBER)
            if channel is None:
                continue

            lines = [f"{after.mention} (`{after.id}`)"]
            if before.name != after.name:
                lines.append(f"**Username before:** {before.name}\n**Username after:** {after.name}")
            if before.display_avatar.key != after.display_avatar.key:
                lines.append("**Avatar changed** (old → new below)")

            embed = discord.Embed(
                title="🪪 Username/avatar changed",
                description="\n".join(lines),
                color=LogColors.MEMBER,
                timestamp=discord.utils.utcnow(),
            )

            if before.display_avatar.key != after.display_avatar.key:
                embed.set_thumbnail(url=before.display_avatar.with_size(128).url)
                embed.set_image(url=after.display_avatar.with_size(128).url)

            try:
                await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                pass
