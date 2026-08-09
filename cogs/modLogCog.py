from __future__ import annotations

import asyncio
from datetime import timedelta

import discord
from discord.ext import commands

from bot import TerrierBot
from .logConfig import LogChannels, LogColors, get_log_channel

# How long to wait before checking the audit log, so the entry has time to
# propagate, and how old an entry is allowed to be to still count as a match.
_AUDIT_LOOKUP_DELAY = 1.0
_AUDIT_MATCH_WINDOW = timedelta(seconds=15)


async def setup(bot: TerrierBot):
    await bot.add_cog(ModLogCog(bot))


class ModLogCog(
    commands.Cog,
    name="ModLog",
    description="Logs kicks, bans, and timeouts (with moderator + reason from the audit log).",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot

    async def _send(self, embed: discord.Embed) -> None:
        channel = get_log_channel(self.bot, LogChannels.MOD)
        if channel is None:
            return
        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    async def _find_audit_entry(
        self,
        guild: discord.Guild,
        action: discord.AuditLogAction,
        target_id: int,
        *,
        changed_attr: str | None = None,
    ) -> discord.AuditLogEntry | None:
        """Best-effort lookup of the audit log entry for a moderation action
        that just happened. Returns None if it can't be found (missing
        permission, propagation delay, etc.) — callers must handle that."""
        await asyncio.sleep(_AUDIT_LOOKUP_DELAY)
        try:
            async for entry in guild.audit_logs(action=action, limit=10):
                if entry.target is None or entry.target.id != target_id:
                    continue
                if discord.utils.utcnow() - entry.created_at > _AUDIT_MATCH_WINDOW:
                    continue
                if changed_attr is not None and not hasattr(entry.after, changed_attr):
                    continue
                return entry
        except discord.Forbidden:
            pass
        except discord.HTTPException:
            pass
        return None

    @staticmethod
    def _mod_reason_lines(entry: discord.AuditLogEntry | None) -> str:
        moderator = entry.user.mention if entry and entry.user else "*Unknown*"
        reason = entry.reason if entry and entry.reason else "*No reason provided*"
        return f"**Moderator:** {moderator}\n**Reason:** {reason}"

    # ── Kicks ─────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        entry = await self._find_audit_entry(member.guild, discord.AuditLogAction.kick, member.id)
        if entry is None:
            return  # not a kick (plain leave) — JoinLeaveCog already covers that

        embed = discord.Embed(
            title="👢 Member kicked",
            description=(
                f"{member.mention} (`{member.id}`)\n" + self._mod_reason_lines(entry)
            ),
            color=LogColors.MOD,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await self._send(embed)

    # ── Bans / unbans ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        entry = await self._find_audit_entry(guild, discord.AuditLogAction.ban, user.id)

        embed = discord.Embed(
            title="🔨 Member banned",
            description=f"{user.mention} (`{user.id}`)\n" + self._mod_reason_lines(entry),
            color=LogColors.MOD,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        await self._send(embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        entry = await self._find_audit_entry(guild, discord.AuditLogAction.unban, user.id)

        embed = discord.Embed(
            title="🔓 Member unbanned",
            description=f"{user.mention} (`{user.id}`)\n" + self._mod_reason_lines(entry),
            color=LogColors.MOD,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        await self._send(embed)

    # ── Timeouts ─────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.timed_out_until == after.timed_out_until:
            return

        now = discord.utils.utcnow()
        was_active = before.timed_out_until is not None and before.timed_out_until > now
        is_active = after.timed_out_until is not None and after.timed_out_until > now

        entry = await self._find_audit_entry(
            after.guild, discord.AuditLogAction.member_update, after.id, changed_attr="timed_out_until"
        )

        if is_active:
            title = "🔇 Member timed out" if not was_active else "🔇 Timeout updated"
            until = after.timed_out_until
            description = (
                f"{after.mention} (`{after.id}`)\n"
                f"**Until:** <t:{int(until.timestamp())}:F> (<t:{int(until.timestamp())}:R>)\n"
                + self._mod_reason_lines(entry)
            )
        elif was_active:
            title = "🔊 Timeout removed"
            description = f"{after.mention} (`{after.id}`)\n" + self._mod_reason_lines(entry)
        else:
            return  # e.g. transitioning between two already-expired timestamps

        embed = discord.Embed(
            title=title,
            description=description,
            color=LogColors.MOD,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=after.display_avatar.url)
        await self._send(embed)
