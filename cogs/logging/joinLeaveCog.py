from __future__ import annotations

import discord
from discord.ext import commands

from bot import TerrierBot
from .logConfig import LogChannels, LogColors, format_duration, get_log_channel, user_line


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
        lines = [
            user_line(member),
            f"**Account created:** <t:{int(member.created_at.timestamp())}:F> (<t:{int(member.created_at.timestamp())}:R>)",
            f"**Member count:** {member.guild.member_count}",
        ]
        if account_age.days < 7:
            lines.append(f"⚠️ **New account:** {account_age.days} day(s) old")

        embed = discord.Embed(
            title="📥 Member joined",
            description="\n".join(lines),
            color=LogColors.JOIN,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        channel = get_log_channel(self.bot, LogChannels.JOIN_LEAVE)
        if channel is None:
            return

        lines = [f"{member} (`{member.id}`)"]

        if member.joined_at is not None:
            time_in_server = discord.utils.utcnow() - member.joined_at
            lines.append(f"**Time in server:** {format_duration(time_in_server)}")

        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        if roles:
            joined_roles = ", ".join(roles)
            lines.append(
                "**Roles:** " + (joined_roles if len(joined_roles) <= 1024 else f"{len(roles)} role(s)")
            )
        lines.append(f"**Member count:** {member.guild.member_count}")

        embed = discord.Embed(
            title="📤 Member left",
            description="\n".join(lines),
            color=LogColors.LEAVE,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass
