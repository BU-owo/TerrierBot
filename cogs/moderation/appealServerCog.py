from __future__ import annotations

import logging
import re

import discord
from discord.ext import commands

from bot import Context, TerrierBot
from ..logging.caseLogCog import record_case
from ..logging.logConfig import LogChannels, LogColors, MOD_ROLE_ID, get_log_channel

# Dedicated appeals server — TerrierBot is a member of both this and the main
# Terrier Hub server, so a banned user can still interact with the button
# (component interactions from a DM back to the bot are silently dropped once
# the user no longer shares a guild with it — see banCog.py's DM appeal flow).
APPEALS_GUILD_ID = 1541626494122598491
MAIN_GUILD_ID = 1396541818245484665

APPEAL_BUTTON_CUSTOM_ID = "open_ban_appeal"


async def setup(bot: TerrierBot):
    await bot.add_cog(AppealServerCog(bot))


def _is_mod(user: discord.abc.User) -> bool:
    return isinstance(user, discord.Member) and any(r.id == MOD_ROLE_ID for r in user.roles)


class _AppealModal(discord.ui.Modal, title="Ban Appeal"):
    reason_input = discord.ui.TextInput(
        label="Why should we reconsider?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Defer + followup rather than a single send_message, since the
        # fetch_ban lookup + log-channel send below can outrun the 3s window.
        await interaction.response.defer(ephemeral=True, thinking=True)

        bot = interaction.client
        main_guild = bot.get_guild(MAIN_GUILD_ID)
        if main_guild is None:
            await interaction.followup.send(
                "Couldn't reach Terrier Hub right now — please try again later or contact a moderator another way.",
                ephemeral=True,
            )
            return

        try:
            ban_entry = await main_guild.fetch_ban(discord.Object(id=interaction.user.id))
        except discord.NotFound:
            await interaction.followup.send(
                "You don't appear to be banned from Terrier Hub.", ephemeral=True
            )
            return

        log_channel = get_log_channel(bot, LogChannels.MOD)
        if log_channel is not None:
            embed = discord.Embed(
                title="📨 Ban appeal received",
                description=(
                    f"**Appealing user:** {interaction.user} (`{interaction.user.id}`)\n"
                    f"**Original ban reason:** {ban_entry.reason or '*Unknown — could not be looked up*'}\n\n"
                    f"**Appeal:**\n{self.reason_input.value}"
                ),
                color=LogColors.MOD,
                timestamp=discord.utils.utcnow(),
            )
            try:
                await log_channel.send(
                    content=f"<@&{MOD_ROLE_ID}>",
                    embed=embed,
                    view=_build_decision_view(interaction.user.id),
                    allowed_mentions=discord.AllowedMentions(roles=True, users=False, everyone=False),
                )
            except discord.HTTPException:
                pass

        await interaction.followup.send(
            "Your appeal has been sent to the moderators.", ephemeral=True
        )


class _AppealButtonView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Appeal my ban",
        style=discord.ButtonStyle.primary,
        custom_id=APPEAL_BUTTON_CUSTOM_ID,
    )
    async def appeal_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.guild_id != APPEALS_GUILD_ID:
            await interaction.response.send_message(
                "This button can only be used in the appeals server.", ephemeral=True
            )
            return
        await interaction.response.send_modal(_AppealModal())


# ── Appeal decision (approve/deny) ───────────────────────────────────────────
# Same DynamicItem pattern as the original AppealButton (see git history at
# commit 9eeb27a / its introduction at 346d4db) — the custom_id encodes the
# appealing user's id, so a single fixed registration via
# bot.add_dynamic_items() in the cog's __init__ handles every appeal embed,
# including ones posted before a restart.

class _AppealDecisionModal(discord.ui.Modal):
    note_input = discord.ui.TextInput(
        label="Note (optional)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
    )

    def __init__(self, user_id: int, approve: bool, original_message: discord.Message):
        super().__init__(title="Approve Appeal" if approve else "Deny Appeal")
        self.user_id = user_id
        self.approve = approve
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        bot = interaction.client
        note = self.note_input.value.strip() or None
        main_guild: discord.Guild | None = None

        if self.approve:
            main_guild = bot.get_guild(MAIN_GUILD_ID)
            if main_guild is None:
                await interaction.followup.send(
                    "Couldn't reach Terrier Hub right now — please try again later.", ephemeral=True
                )
                return
            try:
                await main_guild.unban(
                    discord.Object(id=self.user_id),
                    reason=f"Appeal approved by {interaction.user} — {note or 'No note'}",
                )
            except discord.HTTPException as exc:
                await interaction.followup.send(
                    f"Failed to unban that user: {exc}", ephemeral=True
                )
                return

        # ── Update the original appeal embed so it can't be double-processed ──
        outcome_field = (
            f"✅ Approved by {interaction.user} — {note or 'No note'}"
            if self.approve
            else f"❌ Denied by {interaction.user} — {note or 'No note'}"
        )
        if self.original_message.embeds:
            embed = self.original_message.embeds[0]
            embed.add_field(name="Decision", value=outcome_field, inline=False)
        else:
            embed = discord.Embed(description=outcome_field, color=LogColors.MOD)
        try:
            await self.original_message.edit(embed=embed, view=None)
        except discord.HTTPException:
            pass

        # ── DM the appealing user with the outcome ──────────────────────────
        try:
            user = bot.get_user(self.user_id) or await bot.fetch_user(self.user_id)
            if self.approve:
                dm_text = (
                    "Your appeal for Terrier Hub was approved! You can rejoin here: "
                    "https://discord.gg/bostonuniversity"
                )
            else:
                dm_text = "Your appeal for Terrier Hub was reviewed and denied."
                if note:
                    dm_text += f"\n\n**Moderator note:** {note}"
            await user.send(dm_text)
        except (discord.Forbidden, discord.HTTPException):
            pass  # they may have left the appeals server or closed DMs

        if self.approve:
            # BanCog owns tempban.json and doesn't expose a public API for
            # this — reaching into its (single-underscore, not name-mangled)
            # _remove_tempban is the cleanest option available without adding
            # one. Degrades gracefully if BanCog isn't loaded.
            ban_cog = bot.get_cog("Ban")
            if ban_cog is not None and hasattr(ban_cog, "_remove_tempban") and main_guild is not None:
                try:
                    ban_cog._remove_tempban(guild_id=main_guild.id, user_id=self.user_id)
                except Exception:
                    logging.exception("Failed to clear tempban record for %s after appeal approval", self.user_id)
            else:
                logging.warning(
                    "BanCog not loaded — couldn't clear any tempban record for %s after appeal approval",
                    self.user_id,
                )

            try:
                record_case(
                    user_id=self.user_id,
                    moderator_id=interaction.user.id,
                    case_type="unban",
                    reason=f"Appeal approved — {note or 'No note'}",
                )
            except Exception:
                logging.exception("Failed to record case log entry for appeal-approved unban of %s", self.user_id)

        await interaction.followup.send(
            f"Appeal {'approved' if self.approve else 'denied'}.", ephemeral=True
        )


async def _handle_decision_click(interaction: discord.Interaction, user_id: int, *, approve: bool) -> None:
    if not _is_mod(interaction.user):
        await interaction.response.send_message(
            "You don't have permission to use this button.", ephemeral=True
        )
        return
    if interaction.message is None:
        await interaction.response.send_message(
            "Couldn't find the original appeal message.", ephemeral=True
        )
        return
    await interaction.response.send_modal(_AppealDecisionModal(user_id, approve, interaction.message))


class ApproveAppealButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"appeal_approve:(?P<user_id>\d+)",
):
    def __init__(self, user_id: int):
        super().__init__(
            discord.ui.Button(
                label="Approve",
                style=discord.ButtonStyle.success,
                custom_id=f"appeal_approve:{user_id}",
            )
        )
        self.user_id = user_id

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction, item: discord.ui.Item, match: re.Match[str], /
    ) -> "ApproveAppealButton":
        return cls(int(match["user_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await _handle_decision_click(interaction, self.user_id, approve=True)


class DenyAppealButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"appeal_deny:(?P<user_id>\d+)",
):
    def __init__(self, user_id: int):
        super().__init__(
            discord.ui.Button(
                label="Deny",
                style=discord.ButtonStyle.danger,
                custom_id=f"appeal_deny:{user_id}",
            )
        )
        self.user_id = user_id

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction, item: discord.ui.Item, match: re.Match[str], /
    ) -> "DenyAppealButton":
        return cls(int(match["user_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await _handle_decision_click(interaction, self.user_id, approve=False)


def _build_decision_view(user_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(ApproveAppealButton(user_id))
    view.add_item(DenyAppealButton(user_id))
    return view


class AppealServerCog(
    commands.Cog,
    name="AppealServer",
    description="Ban-appeal button + modal flow for the dedicated appeals server. Owner only to set up.",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot
        # Fixed custom_id, single static view — registering it here (rather
        # than only when =postappealbutton is run) keeps the button working
        # across restarts without needing that command run again.
        self.bot.add_view(_AppealButtonView())
        self.bot.add_dynamic_items(ApproveAppealButton, DenyAppealButton)

    @commands.command(name="postappealbutton")
    @commands.is_owner()
    async def postappealbutton(self, ctx: Context) -> None:
        """Post the ban-appeal button in this channel. Run once, manually. (Owner only)"""
        if ctx.guild is None or ctx.guild.id != APPEALS_GUILD_ID:
            await ctx.send("This command can only be run in the appeals server.")
            return

        embed = discord.Embed(
            title="Ban Appeals",
            description=(
                "If you were banned from Terrier Hub and want to appeal, click the button below."
            ),
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=embed, view=_AppealButtonView())
