from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot import TerrierBot
from ..logging.caseLogCog import record_case
from ..logging.logConfig import LogChannels, LogColors, MOD_ROLE_ID, get_log_channel, user_line

POLITICS_ROLE_ID = 1477468718127775824
POLITICS_MOD_ROLE_ID = 1548747637166055425


def _is_mod(interaction: discord.Interaction) -> bool:
    return isinstance(interaction.user, discord.Member) and any(
        r.id in (MOD_ROLE_ID, POLITICS_MOD_ROLE_ID) for r in interaction.user.roles
    )


async def setup(bot: TerrierBot):
    await bot.add_cog(KickPoliticsCog(bot))


class KickPoliticsCog(
    commands.Cog,
    name="KickPolitics",
    description="Removes the Politics role from a member. Mod (or Politics Mod) only.",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot

    async def _politics_user_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        guild = interaction.guild
        if guild is None:
            return []

        candidates = [m for m in guild.members if any(r.id == POLITICS_ROLE_ID for r in m.roles)]

        current_lower = current.lower()
        matches = [m for m in candidates if current_lower in m.display_name.lower()]
        # Prefix matches first, then alphabetical — see unseriousCog's
        # autocomplete for why (a common search term shouldn't fill all 25
        # slots before reaching the person being searched for).
        matches.sort(key=lambda m: (not m.display_name.lower().startswith(current_lower), m.display_name.lower()))
        return [
            app_commands.Choice(name=member.display_name, value=str(member.id))
            for member in matches[:25]
        ]

    async def _log_kick_politics(self, *, target: discord.Member, moderator: discord.abc.User) -> None:
        log_channel = get_log_channel(self.bot, LogChannels.MOD)
        if log_channel is None:
            return
        embed = discord.Embed(
            title="🏛️ Politics role removed",
            description=(
                f"**Target:** {user_line(target)}\n"
                f"**Moderator:** {user_line(moderator)}"
            ),
            color=LogColors.MOD,
            timestamp=discord.utils.utcnow(),
        )
        try:
            await log_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    @app_commands.command(name="kickpolitics", description="Remove the Politics role from a member (mod only)")
    @app_commands.describe(user="The member to remove from #politics")
    @app_commands.autocomplete(user=_politics_user_autocomplete)
    @app_commands.check(_is_mod)
    async def kickpolitics(self, interaction: discord.Interaction, user: str):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        role = guild.get_role(POLITICS_ROLE_ID)
        if role is None:
            await interaction.response.send_message(
                "Couldn't find the Politics role — ping an owner.", ephemeral=True
            )
            return

        try:
            member = guild.get_member(int(user))
            if member is None:
                member = await guild.fetch_member(int(user))
        except (ValueError, discord.NotFound, discord.HTTPException):
            member = None

        if member is None:
            await interaction.response.send_message(
                "Could not find that member in this server.", ephemeral=True
            )
            return

        if role not in member.roles:
            await interaction.response.send_message(
                f"{member.mention} isn't in #politics.", ephemeral=True
            )
            return

        try:
            await member.remove_roles(
                role, reason=f"Removed from #politics by {interaction.user} ({interaction.user.id})"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to remove that role.", ephemeral=True
            )
            return
        except discord.HTTPException as exc:
            await interaction.response.send_message(f"Failed to remove the role: {exc}", ephemeral=True)
            return

        await interaction.response.send_message(
            f"Removed {member.mention} from #politics.", ephemeral=True
        )

        await self._log_kick_politics(target=member, moderator=interaction.user)

        try:
            record_case(
                user_id=member.id,
                moderator_id=interaction.user.id,
                case_type="politics_kick",
                reason=None,
            )
        except Exception:
            logging.exception("Failed to record case log entry for politics_kick of %s", member.id)

    @kickpolitics.error
    async def kickpolitics_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "You don't have permission to use this command.", ephemeral=True
            )
        else:
            raise error
