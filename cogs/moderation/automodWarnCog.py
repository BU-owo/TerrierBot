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
            reason=(
                f'Automated warning: TerrierBot\'s AutoMod slur filter ("{rule.name}") blocked '
                "a message from you. If you believe this is a mistake, you can appeal with /warnappeal."
            ),
        )
