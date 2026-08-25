from __future__ import annotations

import discord
from discord.ext import commands

from bot import TerrierBot
from .logConfig import LogChannels, LogColors, get_log_channel


async def setup(bot: TerrierBot):
    await bot.add_cog(ServerLogCog(bot))


class ServerLogCog(commands.Cog, name="ServerLog", description="Logs channel, role, and emoji changes."):
    def __init__(self, bot: TerrierBot):
        self.bot = bot

    async def _send(self, embed: discord.Embed) -> None:
        channel = get_log_channel(self.bot, LogChannels.SERVER)
        if channel is None:
            return
        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        before_ids = {role.id for role in before.roles}
        after_ids = {role.id for role in after.roles}
        added_roles = [role for role in after.roles if role.id not in before_ids and role.name != "@everyone"]
        removed_roles = [role for role in before.roles if role.id not in after_ids and role.name != "@everyone"]
        if not added_roles and not removed_roles:
            return

        lines: list[str] = []
        if added_roles:
            lines.append("**Added:** " + ", ".join(role.mention for role in added_roles))
        if removed_roles:
            lines.append("**Removed:** " + ", ".join(role.mention for role in removed_roles))

        embed = discord.Embed(
            title="🎭 Member roles updated",
            description=f"{after.mention} (`{after.id}`)\n" + "\n".join(lines),
            color=LogColors.MEMBER,
            timestamp=discord.utils.utcnow(),
        )

        channel = get_log_channel(self.bot, LogChannels.MEMBER)
        if channel is None:
            return
        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    # ── Channels ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        embed = discord.Embed(
            title="➕ Channel created",
            description=f"{channel.mention} (`{channel.name}`, {channel.type})",
            color=LogColors.SERVER,
            timestamp=discord.utils.utcnow(),
        )
        await self._send(embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        embed = discord.Embed(
            title="➖ Channel deleted",
            description=f"`#{channel.name}` ({channel.type})",
            color=LogColors.SERVER,
            timestamp=discord.utils.utcnow(),
        )
        await self._send(embed)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        if before.name != after.name:
            embed = discord.Embed(
                title="✏️ Channel renamed",
                description=f"{after.mention}\n**Before:** `{before.name}`\n**After:** `{after.name}`",
                color=LogColors.SERVER,
                timestamp=discord.utils.utcnow(),
            )
            await self._send(embed)

        if before.overwrites != after.overwrites:
            await self._log_permission_update(before, after)

    @staticmethod
    def _overwrite_key(target: discord.Role | discord.Member) -> tuple[str, int]:
        return ("role", target.id) if isinstance(target, discord.Role) else ("member", target.id)

    @staticmethod
    def _fmt_perm_value(value: bool | None) -> str:
        if value is True:
            return "✅"
        if value is False:
            return "❌"
        return "⬜"  # inherited/unset

    def _fmt_overwrite(self, overwrite: discord.PermissionOverwrite) -> str:
        parts = [f"`{perm}` {self._fmt_perm_value(value)}" for perm, value in overwrite if value is not None]
        return ", ".join(parts) if parts else "*(no explicit perms)*"

    def _fmt_overwrite_diff(
        self, before_ow: discord.PermissionOverwrite, after_ow: discord.PermissionOverwrite
    ) -> str:
        before_vals = dict(before_ow)
        after_vals = dict(after_ow)
        changed = [
            f"`{perm}` {self._fmt_perm_value(before_vals[perm])}→{self._fmt_perm_value(after_vals[perm])}"
            for perm in before_vals
            if before_vals[perm] != after_vals[perm]
        ]
        return ", ".join(changed)

    async def _log_permission_update(
        self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
    ) -> None:
        before_map = {self._overwrite_key(t): (t, ow) for t, ow in before.overwrites.items()}
        after_map = {self._overwrite_key(t): (t, ow) for t, ow in after.overwrites.items()}

        lines: list[str] = []
        for key in before_map.keys() | after_map.keys():
            before_entry = before_map.get(key)
            after_entry = after_map.get(key)

            if before_entry is None and after_entry is not None:
                target, ow = after_entry
                lines.append(f"➕ **{target.mention}:** {self._fmt_overwrite(ow)}")
            elif after_entry is None and before_entry is not None:
                target, _ = before_entry
                lines.append(f"➖ **{target.mention}:** overrides removed")
            else:
                target, before_ow = before_entry  # type: ignore[misc]
                _, after_ow = after_entry  # type: ignore[misc]
                if before_ow == after_ow:
                    continue
                diff = self._fmt_overwrite_diff(before_ow, after_ow)
                if diff:
                    lines.append(f"✏️ **{target.mention}:** {diff}")

        if not lines:
            return

        description = f"{after.mention}\n" + "\n".join(lines)
        if len(description) > 4000:
            description = description[:3997] + "..."

        embed = discord.Embed(
            title="🔒 Channel permissions updated",
            description=description,
            color=LogColors.SERVER,
            timestamp=discord.utils.utcnow(),
        )
        await self._send(embed)

    # ── Roles ─────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        embed = discord.Embed(
            title="➕ Role created",
            description=f"{role.mention} (`{role.name}`)",
            color=LogColors.SERVER,
            timestamp=discord.utils.utcnow(),
        )
        await self._send(embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        embed = discord.Embed(
            title="➖ Role deleted",
            description=f"`@{role.name}` ({role.id})",
            color=LogColors.SERVER,
            timestamp=discord.utils.utcnow(),
        )
        await self._send(embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        changes: list[str] = []
        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` → `{after.name}`")
        if before.color != after.color:
            changes.append(f"**Color:** `{before.color}` → `{after.color}`")
        if before.permissions != after.permissions:
            changes.append("**Permissions changed**")
        if not changes:
            return

        embed = discord.Embed(
            title="✏️ Role updated",
            description=f"{after.mention}\n" + "\n".join(changes),
            color=LogColors.SERVER,
            timestamp=discord.utils.utcnow(),
        )
        await self._send(embed)

    # ── Emoji ─────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_emojis_update(
        self, guild: discord.Guild, before: list[discord.Emoji], after: list[discord.Emoji]
    ):
        before_ids = {e.id for e in before}
        after_ids = {e.id for e in after}
        added = [e for e in after if e.id not in before_ids]
        removed = [e for e in before if e.id not in after_ids]
        if not added and not removed:
            return

        lines = [f"➕ {e} `:{e.name}:`" for e in added] + [f"➖ `:{e.name}:`" for e in removed]
        embed = discord.Embed(
            title="😀 Emoji updated",
            description="\n".join(lines),
            color=LogColors.SERVER,
            timestamp=discord.utils.utcnow(),
        )
        await self._send(embed)
