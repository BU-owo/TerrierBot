from __future__ import annotations

import logging
import shelve

import discord
from discord import app_commands
from discord.ext import commands

from bot import TerrierBot
from ..logging.caseLogCog import record_case
from ..logging.logConfig import LogChannels, LogColors, MOD_ROLE_ID, get_log_channel, user_line

UNSERIOUS_CATEGORY_ID = 1402023982185713835

# Same shelve file BanCog/LockinCog/HardmuteCog use for their own persistence,
# just a different key — no reason to stand up a second file for one more set.
SHELVE_FILE = "terrierbot.shelve"
SHELVE_KEY = "unserious_enabled"


def _is_mod(interaction: discord.Interaction) -> bool:
    return isinstance(interaction.user, discord.Member) and any(
        r.id == MOD_ROLE_ID for r in interaction.user.roles
    )


async def setup(bot: TerrierBot):
    await bot.add_cog(UnseriousCog(bot))


class UnseriousCog(
    commands.Cog,
    name="Unserious",
    description="Toggles a member's access to the Serious category via a per-member permission overwrite.",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot
        self.enabled_ids: set[int] = self._load_enabled()

    # ── Storage helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _load_enabled() -> set[int]:
        with shelve.open(SHELVE_FILE) as sh:
            return sh.get(SHELVE_KEY, set())

    def _save_enabled(self) -> None:
        with shelve.open(SHELVE_FILE) as sh:
            sh[SHELVE_KEY] = self.enabled_ids

    # ── Shared helpers ───────────────────────────────────────────────────────

    async def _log_action(
        self, *, title: str, member: discord.Member, moderator: discord.abc.User
    ) -> None:
        log_channel = get_log_channel(self.bot, LogChannels.MOD)
        if log_channel is None:
            return
        embed = discord.Embed(
            title=title,
            description=(
                f"**Target:** {user_line(member)}\n"
                f"**Moderator:** {user_line(moderator)}"
            ),
            color=LogColors.MOD,
            timestamp=discord.utils.utcnow(),
        )
        try:
            await log_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    async def _unserious_user_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        guild = interaction.guild
        if guild is None:
            return []

        # `user` can be autocompleted before `mode` is chosen (Discord doesn't
        # enforce fill order), so mode may still be unset here — fall back to
        # the broader "enable" candidate list rather than assuming disable.
        mode = interaction.namespace.mode

        if mode is None or mode == "enable":
            candidates = guild.members
        else:
            candidates = [
                member for uid in self.enabled_ids if (member := guild.get_member(uid)) is not None
            ]

        current_lower = current.lower()
        matches = [m for m in candidates if current_lower in m.display_name.lower()]
        # Prefix matches first (most likely what the searcher means), then
        # alphabetical — otherwise a common search term fills all 25 slots
        # with whatever order guild.members happens to be cached in before
        # the person being searched for is ever reached.
        matches.sort(key=lambda m: (not m.display_name.lower().startswith(current_lower), m.display_name.lower()))
        return [
            app_commands.Choice(name=member.display_name, value=str(member.id))
            for member in matches[:25]
        ]

    @app_commands.command(name="unserious", description="Toggle a user's access to the Serious category (mod only)")
    @app_commands.describe(mode="enable or disable", user="The user to toggle Unserious mode for")
    @app_commands.choices(mode=[
        app_commands.Choice(name="enable", value="enable"),
        app_commands.Choice(name="disable", value="disable"),
    ])
    @app_commands.autocomplete(user=_unserious_user_autocomplete)
    @app_commands.check(_is_mod)
    async def unserious(self, interaction: discord.Interaction, mode: app_commands.Choice[str], user: str):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        category = guild.get_channel(UNSERIOUS_CATEGORY_ID)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                "Unserious category not found in this server.", ephemeral=True
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
                "Could not find that user in this server.", ephemeral=True
            )
            return

        try:
            if mode.value == "enable":
                if member.id in self.enabled_ids:
                    await interaction.response.send_message(
                        f"Unserious mode is already enabled for {member.mention}.", ephemeral=True
                    )
                    return

                await category.set_permissions(
                    member,
                    view_channel=False,
                    reason=f"Unserious mode enabled by {interaction.user} ({interaction.user.id})",
                )
                self.enabled_ids.add(member.id)
                self._save_enabled()

                await self._log_action(
                    title="😐 Unserious mode enabled", member=member, moderator=interaction.user
                )
                try:
                    record_case(
                        user_id=member.id,
                        moderator_id=interaction.user.id,
                        case_type="unserious",
                        reason="Removed from Serious",
                    )
                except Exception:
                    logging.exception(
                        "Failed to record case log entry for unserious-enable of %s", member.id
                    )

                await interaction.response.send_message(
                    f"Unserious mode enabled for {member.mention}.", ephemeral=True
                )
            else:
                if member.id not in self.enabled_ids:
                    await interaction.response.send_message(
                        f"Unserious mode isn't enabled for {member.mention}.", ephemeral=True
                    )
                    return

                await category.set_permissions(
                    member,
                    overwrite=None,
                    reason=f"Unserious mode disabled by {interaction.user} ({interaction.user.id})",
                )
                self.enabled_ids.discard(member.id)
                self._save_enabled()

                await self._log_action(
                    title="🙂 Unserious mode disabled", member=member, moderator=interaction.user
                )
                try:
                    record_case(
                        user_id=member.id,
                        moderator_id=interaction.user.id,
                        case_type="unserious",
                        reason="Restored to Serious",
                    )
                except Exception:
                    logging.exception(
                        "Failed to record case log entry for unserious-disable of %s", member.id
                    )

                await interaction.response.send_message(
                    f"Unserious mode disabled for {member.mention}.", ephemeral=True
                )
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to modify that category's permissions.", ephemeral=True
            )

    @unserious.error
    async def unserious_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "You don't have permission to use this command.", ephemeral=True
            )
        else:
            raise error
