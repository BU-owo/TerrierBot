from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..logging.logConfig import LogChannels

SNITCH_CHANNEL_ID = LogChannels.QUEUE

# @here pings everyone currently online in whatever channel it's sent to —
# only ever fire it into the mod queue channel, never wherever
# SNITCH_CHANNEL_ID might resolve to if that constant ever changes.
_HERE_PING_SAFE_CHANNEL_ID = 1541936565151080519


async def setup(bot: commands.Bot):
    await bot.add_cog(SnitchCog(bot))


class SnitchCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="snitch", description="Silently alert mods without others knowing.")
    @app_commands.describe(context="What you want to report")
    async def snitch(self, interaction: discord.Interaction, context: str) -> None:
        await interaction.response.send_message("Report sent to mods.", ephemeral=True)

        channel = interaction.channel
        user = interaction.user

        embed = discord.Embed(
            title="🚨 New snitch report",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="Reporting channel",
            value=f"{channel.mention} ({channel.name})" if channel is not None else "Unknown",
            inline=False,
        )
        embed.add_field(
            name="Reporting user",
            value=f"{user.mention} — **{user.display_name}** (`{user.id}`)",
            inline=False,
        )
        embed.add_field(
            name="Context",
            value=context,
            inline=False,
        )

        snitch_channel = self.bot.get_channel(SNITCH_CHANNEL_ID)
        if snitch_channel is not None:
            can_ping_here = snitch_channel.id == _HERE_PING_SAFE_CHANNEL_ID
            content = "🚨 New snitch report @here" if can_ping_here else "🚨 New snitch report"
            try:
                await snitch_channel.send(
                    content=content,
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions(roles=False, everyone=can_ping_here, users=False),
                )
            except discord.HTTPException:
                pass
