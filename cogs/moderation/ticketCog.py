from __future__ import annotations
import asyncio
import logging

import discord
from discord.ext import commands

from cogs.logging.logConfig import MOD_ROLE_ID

log = logging.getLogger(__name__)

# Category that TicketTool creates mod-application ticket channels under.
# Every channel created in this category is a mod application (confirmed).
MOD_APP_CATEGORY_ID = 1528788382434726029

# TicketTool sometimes finishes wiring up the applicant's permission overwrite
# a moment after the channel itself is created, so we retry briefly instead
# of giving up on the first empty scan.
OVERWRITE_SCAN_ATTEMPTS = 5
OVERWRITE_SCAN_DELAY_SECONDS = 2

WELCOME_MESSAGE = (
    "Thank you {mention} for your application. Please answer the following questions:\n\n"
    "**What kind of role do you envision having?**\n"
    "**What can the server improve on & how will you support that goal?**\n"
    "**Why do you want to be a mod?**\n"
    "**What experience / assets would you bring to the team?**\n\n"
    "Please take your time. We will review your application and get back to you in the next few weeks.\n\n"
    "- Terrier Hub Moderation Team"
)


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketCog(bot))


class TicketCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _find_applicant(self, channel: discord.TextChannel) -> discord.Member | None:
        candidates: list[discord.Member] = []
        for target, overwrite in channel.overwrites.items():
            if not isinstance(target, discord.Member):
                continue
            if target.bot:
                continue
            if any(r.id == MOD_ROLE_ID for r in target.roles):
                continue
            if overwrite.view_channel:
                candidates.append(target)

        if len(candidates) == 1:
            return candidates[0]
        if candidates:
            log.warning(
                "ticketCog: found %d applicant candidates in #%s, using the first one",
                len(candidates), channel.name,
            )
            return candidates[0]
        return None

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        if not isinstance(channel, discord.TextChannel):
            return
        if channel.category_id != MOD_APP_CATEGORY_ID:
            return

        applicant: discord.Member | None = None
        for attempt in range(OVERWRITE_SCAN_ATTEMPTS):
            applicant = self._find_applicant(channel)
            if applicant:
                break
            await asyncio.sleep(OVERWRITE_SCAN_DELAY_SECONDS)

        if applicant is None:
            log.warning(
                "ticketCog: could not identify applicant for new ticket #%s (id=%d)",
                channel.name, channel.id,
            )
            return

        try:
            await channel.edit(
                name=f"{applicant.name}-mod",
                reason="Mod application ticket — renamed to applicant-mod",
            )
        except discord.HTTPException:
            log.warning("ticketCog: failed to rename #%s to %s-mod", channel.name, applicant.name)

        try:
            await channel.send(
                WELCOME_MESSAGE.format(mention=applicant.mention),
                allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
            )
        except discord.HTTPException:
            log.warning("ticketCog: failed to send welcome message in #%s", channel.name)