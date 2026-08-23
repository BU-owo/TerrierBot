from __future__ import annotations

import logging
import re
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from bot import Context, TerrierBot
from .caseLogCog import record_case
from .logConfig import (
    LogChannels,
    LogColors,
    MOD_ROLE_ID,
    format_duration,
    get_log_channel,
    suppress_mod_log,
    user_line,
)

_DURATION_RE = re.compile(r"^(\d+)\s*([smhd])$", re.IGNORECASE)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_MAX_TIMEOUT_SECONDS = 28 * 86400  # Discord's hard cap on timeout duration
_DURATION_FORMAT_HELP = "Use a number + unit: `30m`, `2h`, `1d`, `45s` (s/m/h/d)."


def _parse_duration_seconds(duration_str: str) -> int | None:
    """Parse a single number+unit duration string into seconds. Returns None
    if it's empty, malformed, or resolves to zero/negative."""
    match = _DURATION_RE.match(duration_str.strip().lower().replace(" ", ""))
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    seconds = amount * _UNIT_SECONDS[unit]
    return seconds if seconds > 0 else None


async def setup(bot: TerrierBot):
    await bot.add_cog(TimeoutCog(bot))


class TimeoutCog(
    commands.Cog,
    name="Timeout",
    description="Manually time out a member, or clear an active timeout early.",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot

    # ── Shared helpers ───────────────────────────────────────────────────────

    @staticmethod
    async def _require_mod(ctx: Context) -> bool:
        if not isinstance(ctx.author, discord.Member) or not any(
            r.id == MOD_ROLE_ID for r in ctx.author.roles
        ):
            await ctx.send("You don't have permission to use this command.", ephemeral=True)
            return False
        return True

    async def _log_action(
        self,
        *,
        title: str,
        target: discord.Member,
        moderator: discord.abc.User,
        reason: str,
        extra_lines: list[str] | None = None,
    ) -> None:
        log_channel = get_log_channel(self.bot, LogChannels.MOD)
        if log_channel is None:
            return
        lines = [
            f"**Target:** {user_line(target)}",
            f"**Moderator:** {user_line(moderator)}",
            *(extra_lines or []),
            f"**Reason:** {reason}",
        ]
        embed = discord.Embed(
            title=title,
            description="\n".join(lines),
            color=LogColors.MOD,
            timestamp=discord.utils.utcnow(),
        )
        try:
            await log_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    # ── =timeout ─────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="timeout", description="Time out a member for a set duration.")
    @app_commands.describe(
        member="The member to time out",
        duration="e.g. 30m, 2h, 1d, 45s",
        reason="Reason for the timeout",
    )
    async def timeout(
        self, ctx: Context, member: discord.Member, duration: str, *, reason: str | None = None
    ):
        if not await self._require_mod(ctx):
            return
        if ctx.guild is None:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        seconds = _parse_duration_seconds(duration)
        if seconds is None:
            await ctx.send(
                f"Couldn't parse `{duration}` as a duration. {_DURATION_FORMAT_HELP}",
                ephemeral=True,
            )
            return

        clamped = seconds > _MAX_TIMEOUT_SECONDS
        if clamped:
            seconds = _MAX_TIMEOUT_SECONDS

        guild = ctx.guild
        bot_member = guild.me

        if member.id == guild.owner_id:
            await ctx.send("I can't time out the server owner.", ephemeral=True)
            return
        if any(r.id == MOD_ROLE_ID for r in member.roles):
            await ctx.send("Mods can't be timed out via this command.", ephemeral=True)
            return
        if bot_member.top_role <= member.top_role:
            await ctx.send(
                "I can't time out that member — their top role is at or above my own.",
                ephemeral=True,
            )
            return

        reason_text = reason or "No reason provided"
        duration_display = format_duration(timedelta(seconds=seconds))
        clamp_note = " (clamped to Discord's 28-day max)" if clamped else ""

        try:
            await member.timeout(
                timedelta(seconds=seconds),
                reason=f"{reason_text} — by {ctx.author} ({ctx.author.id})",
            )
        except discord.Forbidden:
            await ctx.send("I don't have permission to time out that member.", ephemeral=True)
            return
        except discord.HTTPException as exc:
            await ctx.send(f"Failed to time out that member: {exc}", ephemeral=True)
            return

        # The timeout above triggers on_member_update; suppress ModLogCog's
        # duplicate before posting our own (richer) embed for it below.
        suppress_mod_log(member.id, "timeout")

        await ctx.send(
            f"Timed out {member.mention} for {duration_display}{clamp_note}. Reason: {reason_text}",
            ephemeral=True,
        )

        embed = discord.Embed(
            title="🔇 Member timed out",
            description=(
                f"**Member:** {member.mention} — **{member}**\n"
                f"**Duration:** {duration_display}{clamp_note}\n"
                f"**Reason:** {reason_text}"
            ),
            color=LogColors.MOD,
            timestamp=discord.utils.utcnow(),
        )
        if isinstance(ctx.channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            try:
                await ctx.channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                pass

        await self._log_action(
            title="🔇 Member timed out",
            target=member,
            moderator=ctx.author,
            reason=reason_text,
            extra_lines=[f"**Duration:** {duration_display}{clamp_note}"],
        )

        try:
            record_case(
                user_id=member.id,
                moderator_id=ctx.author.id,
                case_type="timeout",
                reason=reason_text,
                duration_seconds=seconds,
            )
        except Exception:
            logging.exception("Failed to record case log entry for timeout of %s", member.id)

    # ── =untimeout ───────────────────────────────────────────────────────────

    @commands.hybrid_command(name="untimeout", description="Clear a member's active timeout.")
    @app_commands.describe(member="The member to clear the timeout for", reason="Reason")
    async def untimeout(self, ctx: Context, member: discord.Member, *, reason: str | None = None):
        if not await self._require_mod(ctx):
            return
        if ctx.guild is None:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        now = discord.utils.utcnow()
        if member.timed_out_until is None or member.timed_out_until <= now:
            await ctx.send(f"{member.mention} isn't currently timed out.", ephemeral=True)
            return

        reason_text = reason or "No reason provided"

        try:
            await member.timeout(None, reason=f"{reason_text} — by {ctx.author} ({ctx.author.id})")
        except discord.Forbidden:
            await ctx.send("I don't have permission to clear that member's timeout.", ephemeral=True)
            return
        except discord.HTTPException as exc:
            await ctx.send(f"Failed to clear that member's timeout: {exc}", ephemeral=True)
            return

        # The timeout clear above triggers on_member_update; suppress
        # ModLogCog's duplicate before posting our own embed for it below.
        suppress_mod_log(member.id, "untimeout")

        await ctx.send(f"Cleared {member.mention}'s timeout. Reason: {reason_text}", ephemeral=True)

        embed = discord.Embed(
            title="🔊 Timeout cleared",
            description=(
                f"**Member:** {member.mention} — **{member}**\n"
                f"**Reason:** {reason_text}"
            ),
            color=LogColors.MOD,
            timestamp=discord.utils.utcnow(),
        )
        if isinstance(ctx.channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            try:
                await ctx.channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                pass

        await self._log_action(
            title="🔊 Timeout cleared",
            target=member,
            moderator=ctx.author,
            reason=reason_text,
        )

        try:
            record_case(
                user_id=member.id,
                moderator_id=ctx.author.id,
                case_type="untimeout",
                reason=reason_text,
            )
        except Exception:
            logging.exception("Failed to record case log entry for untimeout of %s", member.id)
