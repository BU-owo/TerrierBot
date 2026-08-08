from __future__ import annotations

import discord
from discord.ext import commands

from bot import TerrierBot
from .logConfig import LogChannels, LogColors, get_log_channel


async def setup(bot: TerrierBot):
    await bot.add_cog(JoinLeaveCog(bot))


class JoinLeaveCog(commands.Cog, name="JoinLeave", description="Logs member joins and leaves."):
    def __init__(self, bot: TerrierBot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel = get_log_channel(self.bot, LogChannels.JOIN_LEAVE)
        if channel is None:
            return

        account_age = discord.utils.utcnow() - member.created_at
        embed = discord.Embed(
            title="📥 Member joined",
            color=LogColors.JOIN,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
        embed.add_field(
            name="Account created",
            value=f"<t:{int(member.created_at.timestamp())}:R>",
            inline=True,
        )
        if account_age.days < 7:
            embed.add_field(name="⚠️ New account", value=f"{account_age.days} day(s) old", inline=True)
        embed.add_field(name="Member count", value=str(member.guild.member_count), inline=True)

        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        channel = get_log_channel(self.bot, LogChannels.JOIN_LEAVE)
        if channel is None:
            return

        embed = discord.Embed(
            title="📤 Member left",
            color=LogColors.LEAVE,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)

        if member.joined_at is not None:
            time_in_server = discord.utils.utcnow() - member.joined_at
            embed.add_field(name="Time in server", value=f"{time_in_server.days} day(s)", inline=True)

        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        if roles:
            joined_roles = ", ".join(roles)
            embed.add_field(
                name="Roles",
                value=joined_roles if len(joined_roles) <= 1024 else f"{len(roles)} role(s)",
                inline=False,
            )
        embed.add_field(name="Member count", value=str(member.guild.member_count), inline=True)

        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass
