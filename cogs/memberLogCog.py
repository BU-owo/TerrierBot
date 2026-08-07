from __future__ import annotations

import discord
from discord.ext import commands

from bot import TerrierBot
from logConfig import LogChannels, LogColors, get_log_channel


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
            color=LogColors.MEMBER,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=after.display_avatar.url)
        embed.add_field(name="User", value=f"{after.mention} ({after.id})", inline=False)
        embed.add_field(name="Before", value=before.nick or "*(none)*", inline=True)
        embed.add_field(name="After", value=after.nick or "*(none)*", inline=True)

        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        # on_user_update fires globally (not guild-scoped) — only log for
        # guilds this bot actually shares with the user.
        if before.name == after.name and before.display_avatar.key == after.display_avatar.key:
            return

        for guild in self.bot.guilds:
            member = guild.get_member(after.id)
            if member is None:
                continue

            channel = get_log_channel(self.bot, LogChannels.MEMBER)
            if channel is None:
                continue

            embed = discord.Embed(
                title="🪪 Username/avatar changed",
                color=LogColors.MEMBER,
                timestamp=discord.utils.utcnow(),
            )
            embed.add_field(name="User", value=f"{after.mention} ({after.id})", inline=False)

            if before.name != after.name:
                embed.add_field(name="Username before", value=before.name, inline=True)
                embed.add_field(name="Username after", value=after.name, inline=True)

            if before.display_avatar.key != after.display_avatar.key:
                embed.set_thumbnail(url=before.display_avatar.url)
                embed.set_image(url=after.display_avatar.url)
                embed.add_field(name="Avatar", value="Changed — old (thumbnail) → new (below)", inline=False)

            try:
                await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                pass
