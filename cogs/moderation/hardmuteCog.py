from __future__ import annotations

import logging
import shelve
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from bot import Context, TerrierBot
from ..logging.caseLogCog import record_case
from ..logging.logConfig import LogChannels, LogColors, MOD_ROLE_ID, get_log_channel, user_line

# The role that confines a hardmuted member to a single channel. That
# channel's own permission overwrites are what actually grant/deny access —
# this cog only ever adds/removes the role, it never touches channel
# overwrites directly.
HARDMUTE_ROLE_ID = 1441111071715758171
HARDMUTE_CHANNEL_ID = 1498345257455194242

# Same shelve file BanCog/LockinCog use for their own persistence, just a
# different key — no reason to stand up a second file for one more dict.
SHELVE_FILE = "terrierbot.shelve"
SHELVE_KEY = "hardmutes"


async def setup(bot: TerrierBot):
    await bot.add_cog(HardmuteCog(bot))


class HardmuteCog(
    commands.Cog,
    name="Hardmute",
    description="Strips a member's roles and confines them to one channel, indefinitely, until unmuted.",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot
        self.hardmutes: dict[str, dict[str, Any]] = self._load_hardmutes()

    # ── Storage helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _load_hardmutes() -> dict[str, dict[str, Any]]:
        with shelve.open(SHELVE_FILE) as sh:
            return sh.get(SHELVE_KEY, {})

    def _save_hardmutes(self) -> None:
        with shelve.open(SHELVE_FILE) as sh:
            sh[SHELVE_KEY] = self.hardmutes

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

    # ── =hardmute ────────────────────────────────────────────────────────────

    @commands.hybrid_command(
        name="hardmute", description="Strip a member's roles and confine them to one channel."
    )
    @app_commands.describe(member="The member to hardmute")
    async def hardmute(self, ctx: Context, member: discord.Member):
        if not await self._require_mod(ctx):
            return
        guild = ctx.guild
        if guild is None:
            await ctx.send("this command can only be used in a server.", ephemeral=True)
            return

        user_id = str(member.id)
        if user_id in self.hardmutes:
            await ctx.send(f"{member.mention} is already hardmuted.", ephemeral=True)
            return

        if member.id == guild.owner_id:
            await ctx.send("can't hardmute the server owner.", ephemeral=True)
            return
        if any(r.id == MOD_ROLE_ID for r in member.roles):
            await ctx.send("mods can't be hardmuted via this command.", ephemeral=True)
            return
        bot_member = guild.me
        if bot_member.top_role <= member.top_role:
            await ctx.send(
                "can't hardmute that member — their top role is at or above my own.", ephemeral=True
            )
            return

        role = guild.get_role(HARDMUTE_ROLE_ID)
        if role is None:
            await ctx.send("hardmute role not found on this server — ping a mod.", ephemeral=True)
            return

        # All checks passed — defer now. The role-strip, role-add, shelve
        # write, and mod-log send below are several sequential network calls,
        # which combined can outrun Discord's 3-second interaction ack window
        # and make the final reply below fail with a 404 Unknown interaction
        # even though the hardmute itself went through.
        await ctx.defer(ephemeral=True)

        # Stash the member's current roles (minus @everyone, which can't be
        # assigned/removed directly) so =unmute can restore them later, then
        # strip them — otherwise a role granting access elsewhere would
        # defeat the point of confining them to one channel.
        current_roles = [r for r in member.roles if not r.is_default()]
        saved_role_ids = [r.id for r in current_roles]

        try:
            if current_roles:
                await member.remove_roles(
                    *current_roles,
                    reason=f"Hardmuted by {ctx.author} ({ctx.author.id}) — roles stashed",
                )
            await member.add_roles(role, reason=f"Hardmuted by {ctx.author} ({ctx.author.id})")
        except discord.HTTPException:
            await ctx.send("couldn't assign the hardmute role — check my permissions.", ephemeral=True)
            return

        self.hardmutes[user_id] = {
            "guild_id": guild.id,
            "saved_role_ids": saved_role_ids,
        }
        self._save_hardmutes()

        await self._log_action(title="🔇 Member hardmuted", member=member, moderator=ctx.author)

        try:
            record_case(
                user_id=member.id,
                moderator_id=ctx.author.id,
                case_type="hardmute",
                reason=None,
            )
        except Exception:
            logging.exception("Failed to record case log entry for hardmute of %s", member.id)

        await ctx.send(
            f"🔇 hardmuted {member.mention} — they're confined to <#{HARDMUTE_CHANNEL_ID}> until `=unmute`.",
            ephemeral=True,
        )

    # ── =unmute ──────────────────────────────────────────────────────────────

    @commands.hybrid_command(
        name="unmute", description="Remove a hardmute and restore the member's roles."
    )
    @app_commands.describe(member="The member to unmute")
    async def unmute(self, ctx: Context, member: discord.Member):
        if not await self._require_mod(ctx):
            return
        guild = ctx.guild
        if guild is None:
            await ctx.send("this command can only be used in a server.", ephemeral=True)
            return

        user_id = str(member.id)
        entry = self.hardmutes.get(user_id)
        if entry is None:
            await ctx.send(f"{member.mention} isn't hardmuted.", ephemeral=True)
            return

        # All checks passed — defer now, same reasoning as =hardmute above.
        await ctx.defer(ephemeral=True)

        role = guild.get_role(HARDMUTE_ROLE_ID)
        if role is not None and role in member.roles:
            try:
                await member.remove_roles(role, reason=f"Unmuted by {ctx.author} ({ctx.author.id})")
            except discord.HTTPException:
                pass

        # Restore whatever roles were stashed when the hardmute started. A
        # saved role ID that no longer resolves (deleted since then) is
        # skipped rather than erroring.
        saved_role_ids = entry.get("saved_role_ids", [])
        roles_to_restore = [
            r for rid in saved_role_ids if (r := guild.get_role(rid)) is not None
        ]
        restore_failed = False
        if roles_to_restore:
            try:
                await member.add_roles(
                    *roles_to_restore,
                    reason=f"Unmuted by {ctx.author} ({ctx.author.id}) — restoring roles",
                )
            except discord.HTTPException:
                restore_failed = True

        del self.hardmutes[user_id]
        self._save_hardmutes()

        await self._log_action(title="🔊 Member unmuted", member=member, moderator=ctx.author)

        try:
            record_case(
                user_id=member.id,
                moderator_id=ctx.author.id,
                case_type="unmute",
                reason=None,
            )
        except Exception:
            logging.exception("Failed to record case log entry for unmute of %s", member.id)

        if restore_failed:
            await ctx.send(
                f"🔊 unmuted {member.mention}, but couldn't restore all their roles — check my permissions.",
                ephemeral=True,
            )
        else:
            await ctx.send(f"🔊 unmuted {member.mention} — roles restored.", ephemeral=True)
