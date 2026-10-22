from __future__ import annotations

import logging
import time
from datetime import timedelta

import discord
from discord.ext import commands

from bot import TerrierBot
from ..logging.caseLogCog import record_case
from ..logging.logConfig import (
    JUNIOR_MOD_ROLE_ID,
    LogChannels,
    LogColors,
    MAIN_GUILD_ID,
    MOD_ROLE_ID,
    format_duration,
    get_log_channel,
    suppress_message_log,
    suppress_mod_log,
    user_line,
)

log = logging.getLogger(__name__)

# Community ping roles members can @mention directly (replaces the old
# /pingrole command). Rate-limited per member across all of these roles:
# pinging any of them again within PING_COOLDOWN of their last ping (even a
# different role) gets the message deleted and the member timed out for
# PENALTY_TIMEOUT. Role IDs carried over from pingroleCog.
PING_ROLES: dict[int, str] = {
    1405219077693243434: "Eventee",
    1412441490591842354: "Foodee",
    1416190981102895136: "HungryLonger",
    1422358773657243678: "FitnessFriend",
    1425108753086287903: "StudyBuddy",
    1458528619482710047: "MC",
    1475971319366549534: "Val",
}

PING_COOLDOWN = timedelta(minutes=30)
PENALTY_TIMEOUT = timedelta(minutes=30)

# Mods and Support (Junior Mod) can ping these roles as often as they like.
_EXEMPT_ROLE_IDS = {MOD_ROLE_ID, JUNIOR_MOD_ROLE_ID}

_CONTENT_PREVIEW_LIMIT = 500


class RolePingCog(
    commands.Cog,
    name="RolePing",
    description="Rate-limits direct @pings of the community ping roles (once per 30 min per member).",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot
        # member id -> monotonic time of their last allowed ping of any
        # ping role. In-memory only: a restart just forgets recent pings,
        # which is fine for a 30-minute window.
        self._last_ping: dict[int, float] = {}

    def _prune(self, now: float) -> None:
        cutoff = now - PING_COOLDOWN.total_seconds()
        for key in [k for k, ts in self._last_ping.items() if ts < cutoff]:
            del self._last_ping[key]

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.webhook_id is not None:
            return
        if message.guild is None or message.guild.id != MAIN_GUILD_ID:
            return
        if not isinstance(message.author, discord.Member):
            return

        pinged = [r for r in message.role_mentions if r.id in PING_ROLES]
        if not pinged:
            return
        if any(r.id in _EXEMPT_ROLE_IDS for r in message.author.roles):
            return

        now = time.monotonic()
        self._prune(now)
        # Pinging several ping roles in one message counts as a single ping.
        if message.author.id not in self._last_ping:
            self._last_ping[message.author.id] = now
            return

        await self._punish(message, pinged)

    async def _punish(self, message: discord.Message, roles: list[discord.Role]) -> None:
        member = message.author
        role_names = ", ".join(f"@{r.name}" for r in roles)
        reason_text = f"Pinged {role_names} within {format_duration(PING_COOLDOWN)} of a previous ping-role ping"

        suppress_message_log(message.id)
        try:
            await message.delete()
        except discord.NotFound:
            pass
        except discord.HTTPException:
            log.exception("Failed to delete repeat role ping %s", message.id)

        timed_out = False
        try:
            await member.timeout(PENALTY_TIMEOUT, reason=f"{reason_text} — automatic (RolePing)")
            timed_out = True
        except discord.HTTPException:
            # Forbidden if the member's top role is at/above the bot's.
            log.exception("Failed to time out %s for repeat role ping", member.id)

        if timed_out:
            # Our own embed below replaces ModLogCog's generic timeout entry.
            suppress_mod_log(member.id, "timeout")
            try:
                record_case(
                    user_id=member.id,
                    moderator_id=self.bot.user.id,
                    case_type="timeout",
                    reason=reason_text,
                    duration_seconds=int(PENALTY_TIMEOUT.total_seconds()),
                )
            except Exception:
                log.exception("Failed to record case log entry for role-ping timeout of %s", member.id)

            try:
                await member.send(
                    f"You were timed out in **{message.guild.name}** for {format_duration(PENALTY_TIMEOUT)} "
                    f"for pinging {role_names} within {format_duration(PING_COOLDOWN)} of your last ping-role ping. "
                    "You can only ping one of the community ping roles once every 30 minutes."
                )
            except discord.HTTPException:
                pass

        log_channel = get_log_channel(self.bot, LogChannels.MOD)
        if log_channel is None:
            return
        content = message.content
        if len(content) > _CONTENT_PREVIEW_LIMIT:
            content = content[:_CONTENT_PREVIEW_LIMIT] + "…"
        outcome = (
            f"**Timeout:** {format_duration(PENALTY_TIMEOUT)}"
            if timed_out
            else "**Timeout:** ⚠️ failed — check the bot's role position/permissions"
        )
        embed = discord.Embed(
            title="📣 Repeat role ping — message deleted",
            description=(
                f"**Member:** {user_line(member)}\n"
                f"**Channel:** {message.channel.mention}\n"
                f"**Role(s):** {role_names}\n"
                f"{outcome}\n"
                f"**Moderator:** automatic (RolePing)"
            ),
            color=LogColors.MOD,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Message", value=content or "*no text*", inline=False)
        try:
            await log_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass


async def setup(bot: TerrierBot):
    await bot.add_cog(RolePingCog(bot))
