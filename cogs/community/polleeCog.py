from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot import TerrierBot
from ..logging.logConfig import JUNIOR_MOD_ROLE_ID

POLLEE_PING_ROLE_ID = 1404504161680228542
POLLEE_ALLOWED_ROLE_ID = 1403879675679215827


def _is_allowed(interaction: discord.Interaction) -> bool:
    return isinstance(interaction.user, discord.Member) and any(
        r.id in (POLLEE_ALLOWED_ROLE_ID, JUNIOR_MOD_ROLE_ID) for r in interaction.user.roles
    )


async def setup(bot: TerrierBot):
    await bot.add_cog(PolleeCog(bot))


class PolleeCog(
    commands.Cog,
    name="Pollee",
    description="Pings the Pollee role with a message. Restricted to a specific role.",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot

    @app_commands.command(name="pollee", description="Ping the Pollee role with a message")
    @app_commands.describe(message="The message to include with the ping")
    @app_commands.check(_is_allowed)
    async def pollee(self, interaction: discord.Interaction, message: str):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        role = guild.get_role(POLLEE_PING_ROLE_ID)
        if role is None:
            await interaction.response.send_message(
                "Couldn't find the Pollee role — ping a mod.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"{role.mention}: {message}",
            allowed_mentions=discord.AllowedMentions(roles=True, users=False, everyone=False),
        )
