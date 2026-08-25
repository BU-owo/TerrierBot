from __future__ import annotations

import re
import sqlite3
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from bot import Context, TerrierBot
from .warningsCog import DB_PATH, RULES
from ..logging.logConfig import LogChannels, MOD_ROLE_ID, user_line


def _is_mod(user: discord.abc.User) -> bool:
    return isinstance(user, discord.Member) and any(r.id == MOD_ROLE_ID for r in user.roles)


async def setup(bot: TerrierBot):
    await bot.add_cog(WarnAppealCog(bot))


class _WarnAppealTextModal(discord.ui.Modal, title="Appeal Warning"):
    appeal_input = discord.ui.TextInput(
        label="Why should this warning be reconsidered?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000,
    )

    def __init__(self, warning: tuple[int, int, str, str, int]):
        super().__init__()
        self.warning = warning

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        warn_id, rule, reason, warned_at, moderator_id = self.warning
        bot = interaction.client

        log_channel = bot.get_channel(LogChannels.QUEUE)
        if log_channel is None:
            await interaction.followup.send(
                "Couldn't deliver your appeal right now — please contact a moderator another way.",
                ephemeral=True,
            )
            return

        date_str = datetime.fromisoformat(warned_at).strftime("%Y-%m-%d")
        rule_name = RULES.get(rule, "Unknown rule")

        embed = discord.Embed(
            title="⚖️ Warning appeal received",
            description=(
                f"**Appellant:** {user_line(interaction.user)}\n\n"
                f"**Warning #{warn_id}** — Rule {rule}: {rule_name} ({date_str})\n"
                f"**Reason:** {reason}\n"
                f"**Issued by:** <@{moderator_id}>\n\n"
                f"**Appeal:**\n{self.appeal_input.value}"
            ),
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )

        try:
            await log_channel.send(
                embed=embed,
                view=_build_decision_view(warn_id, interaction.user.id),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            await interaction.followup.send(
                "Something went wrong sending your appeal — please try again later or contact a moderator another way.",
                ephemeral=True,
            )
            return

        await interaction.followup.send("Your appeal has been sent to the moderators.", ephemeral=True)


class _WarnSelect(discord.ui.Select):
    def __init__(self, warnings: list[tuple[int, int, str, str, int]]):
        self._by_id = {w[0]: w for w in warnings}
        options = []
        for warn_id, rule, reason, warned_at, _moderator_id in warnings:
            date_str = datetime.fromisoformat(warned_at).strftime("%Y-%m-%d")
            rule_name = RULES.get(rule, "Unknown rule")
            options.append(
                discord.SelectOption(
                    label=f"#{warn_id} — Rule {rule}: {rule_name} ({date_str})"[:100],
                    description=reason[:100],
                    value=str(warn_id),
                )
            )
        super().__init__(placeholder="Select a warning to appeal...", options=options[:25])

    async def callback(self, interaction: discord.Interaction) -> None:
        warning = self._by_id[int(self.values[0])]
        await interaction.response.send_modal(_WarnAppealTextModal(warning))


class _WarnSelectView(discord.ui.View):
    def __init__(self, warnings: list[tuple[int, int, str, str, int]]):
        super().__init__(timeout=180)
        self.add_item(_WarnSelect(warnings))


class _WarnAppealResponseModal(discord.ui.Modal):
    message_input = discord.ui.TextInput(
        label="Response message",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000,
    )

    def __init__(self, warn_id: int, appellant_id: int, *, approve: bool, original_message: discord.Message):
        super().__init__(title="Accept Appeal" if approve else "Reject Appeal")
        self.warn_id = warn_id
        self.appellant_id = appellant_id
        self.approve = approve
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        mod_message = self.message_input.value.strip()

        if self.approve:
            # Same removal path =warnremove uses, but tagged so caseLogCog
            # can show this was removed via appeal rather than manually.
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "UPDATE warnings SET active = 0, removed_via = 'appeal' WHERE id = ?", (self.warn_id,)
            )
            conn.commit()
            conn.close()

        outcome_field = (
            f"✅ Accepted by {interaction.user}\n{mod_message}"
            if self.approve
            else f"❌ Rejected by {interaction.user}\n{mod_message}"
        )
        if self.original_message.embeds:
            embed = self.original_message.embeds[0]
            embed.add_field(name="Decision", value=outcome_field, inline=False)
        else:
            embed = discord.Embed(description=outcome_field, color=discord.Color.orange())
        try:
            await self.original_message.edit(embed=embed, view=None)
        except discord.HTTPException:
            pass

        # Permanent record of the decision in mod-log — a new message, not an
        # edit, and with no buttons (the message above is where decisions
        # happen). Best-effort: never blocks the rest of this flow.
        try:
            mod_log_channel = interaction.client.get_channel(LogChannels.MOD)
            if mod_log_channel is not None:
                await mod_log_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

        dm_failed = False
        try:
            bot = interaction.client
            user = bot.get_user(self.appellant_id) or await bot.fetch_user(self.appellant_id)
            if self.approve:
                dm_text = (
                    "Your warning appeal was accepted — the warning has been removed.\n\n"
                    f"**Moderator's message:** {mod_message}"
                )
            else:
                dm_text = (
                    "Your warning appeal was reviewed and denied. The warning stays on record.\n\n"
                    f"**Moderator's message:** {mod_message}"
                )
            await user.send(dm_text)
        except discord.Forbidden:
            dm_failed = True

        note = " Couldn't DM the user — they may have DMs closed." if dm_failed else ""
        await interaction.followup.send(
            f"Appeal {'accepted' if self.approve else 'rejected'}.{note}", ephemeral=True
        )


# ── Appeal decision (accept/reject) ──────────────────────────────────────────
# Same DynamicItem pattern as appealServerCog.py's ApproveAppealButton /
# DenyAppealButton — the custom_id encodes both the warning id and the
# appellant's user id, so a single fixed registration via
# bot.add_dynamic_items() in the cog's __init__ handles every appeal embed,
# including ones posted before a restart.

async def _handle_decision_click(
    interaction: discord.Interaction, warn_id: int, appellant_id: int, *, approve: bool
) -> None:
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
    await interaction.response.send_modal(
        _WarnAppealResponseModal(
            warn_id, appellant_id, approve=approve, original_message=interaction.message
        )
    )


class AcceptWarnAppealButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"warnappeal_accept:(?P<warn_id>\d+):(?P<appellant_id>\d+)",
):
    def __init__(self, warn_id: int, appellant_id: int):
        super().__init__(
            discord.ui.Button(
                label="Accept",
                style=discord.ButtonStyle.success,
                custom_id=f"warnappeal_accept:{warn_id}:{appellant_id}",
            )
        )
        self.warn_id = warn_id
        self.appellant_id = appellant_id

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction, item: discord.ui.Item, match: re.Match[str], /
    ) -> "AcceptWarnAppealButton":
        return cls(int(match["warn_id"]), int(match["appellant_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await _handle_decision_click(interaction, self.warn_id, self.appellant_id, approve=True)


class RejectWarnAppealButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"warnappeal_reject:(?P<warn_id>\d+):(?P<appellant_id>\d+)",
):
    def __init__(self, warn_id: int, appellant_id: int):
        super().__init__(
            discord.ui.Button(
                label="Reject",
                style=discord.ButtonStyle.danger,
                custom_id=f"warnappeal_reject:{warn_id}:{appellant_id}",
            )
        )
        self.warn_id = warn_id
        self.appellant_id = appellant_id

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction, item: discord.ui.Item, match: re.Match[str], /
    ) -> "RejectWarnAppealButton":
        return cls(int(match["warn_id"]), int(match["appellant_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await _handle_decision_click(interaction, self.warn_id, self.appellant_id, approve=False)


def _build_decision_view(warn_id: int, appellant_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(AcceptWarnAppealButton(warn_id, appellant_id))
    view.add_item(RejectWarnAppealButton(warn_id, appellant_id))
    return view


class WarnAppealCog(
    commands.Cog,
    name="WarnAppeal",
    description="Warning appeal flow: pick a warning, submit an appeal, mods accept/reject with a response.",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot
        self.bot.add_dynamic_items(AcceptWarnAppealButton, RejectWarnAppealButton)

    @app_commands.command(name="warnappeal", description="Appeal one of your active warnings")
    async def warnappeal(self, interaction: discord.Interaction) -> None:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT id, rule, reason, warned_at, moderator_id FROM warnings "
            "WHERE user_id = ? AND active = 1 ORDER BY warned_at DESC",
            (interaction.user.id,),
        ).fetchall()
        conn.close()

        if not rows:
            await interaction.response.send_message("You have no warnings to appeal.", ephemeral=True)
            return

        await interaction.response.send_message(
            "Select the warning you'd like to appeal:",
            view=_WarnSelectView(rows),
            ephemeral=True,
        )
