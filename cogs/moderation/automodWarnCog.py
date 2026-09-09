from __future__ import annotations

import logging

import discord
from discord.ext import commands

from bot import TerrierBot
from ..logging.logConfig import MAIN_GUILD_ID

log = logging.getLogger(__name__)

# AutoMod rules whose block-message triggers should also generate an
# automatic Rule 2 warning. Matched by name prefix rather than rule ID so the
# mods can add "Slurs Part 4", etc. without touching this cog.
SLUR_RULE_NAME_PREFIX = "Slurs Part"
SLUR_WARN_RULE = 2

# Reason ends up in a Discord embed field (1024-char cap) alongside
# boilerplate text, so the blocked content itself has to stay well under that.
_CONTENT_PREVIEW_LIMIT = 300


def _alert_jump_link(execution: discord.AutoModAction, rule: discord.AutoModRule) -> str | None:
    """Best-effort link to view the blocked message in context. A blocked
    message is never actually sent, so there's normally nothing in the
    channel to link to — message_id is only populated when the trigger was
    an edit to an existing (already-sent) message. Otherwise, fall back to
    the rule's own AutoMod alert-channel post, if the rule has one
    configured; Discord's alert message quotes the full blocked content."""
    if execution.message_id is not None and execution.channel_id is not None:
        return f"https://discord.com/channels/{execution.guild_id}/{execution.channel_id}/{execution.message_id}"

    if execution.alert_system_message_id is not None:
        alert_channel_id = next(
            (a.channel_id for a in rule.actions if a.type is discord.AutoModRuleActionType.send_alert_message),
            None,
        )
        if alert_channel_id is not None:
            return f"https://discord.com/channels/{execution.guild_id}/{alert_channel_id}/{execution.alert_system_message_id}"

    return None


def _format_warn_reason(execution: discord.AutoModAction, rule: discord.AutoModRule) -> str:
    lines = [
        "Automated warning: TerrierBot's AutoMod slur filter blocked a message from you.",
    ]

    content = execution.content.strip()
    if content:
        preview = content if len(content) <= _CONTENT_PREVIEW_LIMIT else content[:_CONTENT_PREVIEW_LIMIT] + "…"
        lines.append(f'Blocked message: "{preview}"')

    link = _alert_jump_link(execution, rule)
    if link:
        lines.append(f"Context: {link}")

    lines.append("If you believe this is a mistake, you can appeal with /warnappeal.")
    return "\n".join(lines)


async def setup(bot: TerrierBot):
    await bot.add_cog(AutomodWarnCog(bot))


class AutomodWarnCog(
    commands.Cog,
    name="AutomodWarn",
    description="Turns AutoMod slur-filter blocks into automatic Rule 2 warnings.",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_automod_action(self, execution: discord.AutoModAction) -> None:
        if execution.guild_id != MAIN_GUILD_ID:
            return
        if execution.action.type is not discord.AutoModRuleActionType.block_message:
            return

        try:
            rule = await execution.fetch_rule()
        except (discord.Forbidden, discord.HTTPException):
            log.warning("automodWarnCog: couldn't fetch AutoMod rule %s", execution.rule_id)
            return

        if not rule.name.startswith(SLUR_RULE_NAME_PREFIX):
            return

        guild = self.bot.get_guild(execution.guild_id)
        if guild is None:
            return

        member = guild.get_member(execution.user_id)
        if member is None:
            try:
                member = await guild.fetch_member(execution.user_id)
            except discord.HTTPException:
                log.warning(
                    "automodWarnCog: couldn't resolve member %s to issue an auto-warning",
                    execution.user_id,
                )
                return

        warnings_cog = self.bot.get_cog("WarningsCog")
        if warnings_cog is None:
            log.warning("automodWarnCog: WarningsCog isn't loaded, can't issue automatic warning")
            return

        moderator = self.bot.user
        if moderator is None:
            return

        await warnings_cog.issue_warning(
            user=member,
            moderator=moderator,
            rule=SLUR_WARN_RULE,
            reason=_format_warn_reason(execution, rule),
        )

        channel = execution.channel
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.send(
                    f"{member.mention} has been warned for a Rule {SLUR_WARN_RULE} violation.",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                pass
