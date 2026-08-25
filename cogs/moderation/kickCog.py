from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot import Context, TerrierBot
from ..logging.caseLogCog import record_case
from ..logging.logConfig import LogChannels, LogColors, MOD_ROLE_ID, get_log_channel, suppress_mod_log, user_line


async def setup(bot: TerrierBot):
    await bot.add_cog(KickCog(bot))


class KickCog(
    commands.Cog,
    name="Kick",
    description="Kicks a member, with a best-effort DM notice beforehand.",
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

    async def _log_kick(
        self,
        *,
        target: discord.Member,
        moderator: discord.abc.User,
        reason: str,
        dm_delivered: bool,
    ) -> None:
        log_channel = get_log_channel(self.bot, LogChannels.MOD)
        if log_channel is None:
            return
        embed = discord.Embed(
            title="👢 Member kicked",
            description=(
                f"**Target:** {target.mention} (`{target.id}`)\n"
                f"**Moderator:** {user_line(moderator)}\n"
                f"**Reason:** {reason}\n"
                f"**DM delivered:** {'✅ Yes' if dm_delivered else '❌ No'}"
            ),
            color=LogColors.MOD,
            timestamp=discord.utils.utcnow(),
        )
        try:
            await log_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    # ── =kick ────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="kick", description="Kick a member from the server.")
    @app_commands.describe(member="The member to kick", reason="Reason for the kick")
    async def kick(self, ctx: Context, member: discord.Member, *, reason: str | None = None):
        if not await self._require_mod(ctx):
            return
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        if member.id == guild.owner_id:
            await ctx.send("I can't kick the server owner.", ephemeral=True)
            return
        if any(r.id == MOD_ROLE_ID for r in member.roles):
            await ctx.send("Mods can't be kicked via this command.", ephemeral=True)
            return
        bot_member = guild.me
        if bot_member.top_role <= member.top_role:
            await ctx.send(
                "I can't kick that member — their top role is at or above my own.", ephemeral=True
            )
            return

        # All checks passed — defer now. The DM send + guild.kick() below are
        # two sequential network calls, which combined can outrun Discord's
        # 3-second interaction ack window and make ctx.send() below fail with
        # a 404 Unknown interaction even though the kick itself went through.
        await ctx.defer(ephemeral=True)

        reason_text = reason or "No reason provided"

        # DM must be attempted before the kick — the bot may lose the ability
        # to DM them afterward if they don't share another guild with it.
        dm_delivered = True
        dm_embed = discord.Embed(
            title="You have been kicked",
            description=(
                f"You were kicked from **{guild.name}**.\n\n"
                f"**Reason:** {reason_text}\n\n"
                "You're welcome to rejoin with a new invite if you're given one."
            ),
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )
        try:
            await member.send(embed=dm_embed)
        except (discord.Forbidden, discord.HTTPException):
            dm_delivered = False

        try:
            await guild.kick(
                member, reason=f"{reason_text} — by {ctx.author} ({ctx.author.id})"
            )
        except discord.Forbidden:
            await ctx.send("I don't have permission to kick that member.", ephemeral=True)
            return
        except discord.HTTPException as exc:
            await ctx.send(f"Failed to kick that member: {exc}", ephemeral=True)
            return

        # The kick above triggers on_member_remove; suppress ModLogCog's
        # duplicate before posting our own (richer) embed for it below.
        suppress_mod_log(member.id, "kick")

        dm_note = "" if dm_delivered else " (DM could not be delivered)"
        await ctx.send(
            f"Kicked {member} (`{member.id}`).{dm_note} Reason: {reason_text}",
            ephemeral=True,
        )

        await self._log_kick(
            target=member,
            moderator=ctx.author,
            reason=reason_text,
            dm_delivered=dm_delivered,
        )

        try:
            record_case(
                user_id=member.id,
                moderator_id=ctx.author.id,
                case_type="kick",
                reason=reason_text,
            )
        except Exception:
            logging.exception("Failed to record case log entry for kick of %s", member.id)
