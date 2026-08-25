from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from ..logging.logConfig import MOD_ROLE_ID

SNITCH_CHANNEL_ID = 1401924438341062798


async def setup(bot: commands.Bot):
    await bot.add_cog(SnitchCog(bot))


class SnitchCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="snitch", description="Send an anonymous-to-others report to the mods.")
    @app_commands.describe(context="What you want to report (optional)")
    async def snitch(self, interaction: discord.Interaction, context: str | None = None) -> None:
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
            value=context if context else "No context provided",
            inline=False,
        )

        snitch_channel = self.bot.get_channel(SNITCH_CHANNEL_ID)
        if snitch_channel is not None:
            try:
                await snitch_channel.send(
                    content=f"🚨 New snitch report <@&{MOD_ROLE_ID}>",
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions(roles=True, everyone=False, users=False),
                )
            except discord.HTTPException:
                pass
