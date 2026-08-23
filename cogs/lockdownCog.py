from __future__ import annotations

from dataclasses import dataclass

import discord
from discord.ext import commands

from bot import Context, TerrierBot
from .logConfig import LogChannels, LogColors, MOD_ROLE_ID, get_log_channel, user_line


@dataclass
class _LockdownSnapshot:
    guild_id: int
    existed_before: bool
    allow: discord.Permissions
    deny: discord.Permissions


# channel_id -> snapshot of the @everyone overwrite from just before lockdown.
# In-memory only — a bot restart while a channel is locked drops these, so
# =unlock will fall through to "not locked" and the prior exact overwrite
# state can no longer be auto-restored; a mod would need to manually review
# and fix permissions on that channel in that edge case.
_lockdown_snapshots: dict[int, _LockdownSnapshot] = {}


async def setup(bot: TerrierBot):
    await bot.add_cog(LockdownCog(bot))


class LockdownCog(
    commands.Cog,
    name="Lockdown",
    description="Locks/unlocks a single channel by denying @everyone send permissions.",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot

    @staticmethod
    async def _require_mod(ctx: Context) -> bool:
        if not isinstance(ctx.author, discord.Member) or not any(
            r.id == MOD_ROLE_ID for r in ctx.author.roles
        ):
            await ctx.send("You don't have permission to use this command.", ephemeral=True)
            return False
        return True

    async def _log_action(
        self, channel: discord.TextChannel, moderator: discord.abc.User, *, locked: bool
    ) -> None:
        log_channel = get_log_channel(self.bot, LogChannels.MOD)
        if log_channel is None:
            return
        embed = discord.Embed(
            title="🔒 Channel locked" if locked else "🔓 Channel unlocked",
            description=(
                f"**Channel:** {channel.mention}\n"
                f"**Moderator:** {user_line(moderator)}"
            ),
            color=LogColors.MOD,
            timestamp=discord.utils.utcnow(),
        )
        try:
            await log_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    @commands.hybrid_command(
        name="lockdown", description="Lock this channel — prevents @everyone from sending messages."
    )
    async def lockdown(self, ctx: Context):
        if not await self._require_mod(ctx):
            return

        channel = ctx.channel
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("This command can only be used in a text channel.", ephemeral=True)
            return

        if channel.id in _lockdown_snapshots:
            await ctx.send("This channel is already locked.", ephemeral=True)
            return

        everyone = channel.guild.default_role
        existing = channel.overwrites.get(everyone)
        existed_before = existing is not None
        current = existing if existing is not None else discord.PermissionOverwrite()
        allow, deny = current.pair()

        # Snapshot the full prior overwrite (every permission field, not just
        # the four we're about to touch) so =unlock can restore it exactly.
        _lockdown_snapshots[channel.id] = _LockdownSnapshot(
            guild_id=channel.guild.id,
            existed_before=existed_before,
            allow=allow,
            deny=deny,
        )

        new_overwrite = discord.PermissionOverwrite.from_pair(allow, deny)
        new_overwrite.send_messages = False
        new_overwrite.create_public_threads = False
        new_overwrite.create_private_threads = False
        new_overwrite.send_messages_in_threads = False

        try:
            await channel.set_permissions(
                everyone, overwrite=new_overwrite, reason=f"Lockdown by {ctx.author} ({ctx.author.id})"
            )
        except discord.HTTPException:
            del _lockdown_snapshots[channel.id]
            await ctx.send("Failed to lock this channel — check my permissions.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🔒 Channel locked",
            description=f"This channel has been locked by {ctx.author.mention}. Only moderators can send messages here.",
            color=LogColors.MOD,
            timestamp=discord.utils.utcnow(),
        )
        await ctx.send(embed=embed)
        await self._log_action(channel, ctx.author, locked=True)

    @commands.hybrid_command(
        name="unlock", description="Restore this channel's normal send-message permissions."
    )
    async def unlock(self, ctx: Context):
        if not await self._require_mod(ctx):
            return

        channel = ctx.channel
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("This command can only be used in a text channel.", ephemeral=True)
            return

        snapshot = _lockdown_snapshots.get(channel.id)
        if snapshot is None:
            await ctx.send("This channel isn't locked (per my tracking).", ephemeral=True)
            return

        everyone = channel.guild.default_role
        try:
            if snapshot.existed_before:
                restored = discord.PermissionOverwrite.from_pair(snapshot.allow, snapshot.deny)
                await channel.set_permissions(
                    everyone, overwrite=restored, reason=f"Unlock by {ctx.author} ({ctx.author.id})"
                )
            else:
                await channel.set_permissions(
                    everyone, overwrite=None, reason=f"Unlock by {ctx.author} ({ctx.author.id})"
                )
        except discord.HTTPException:
            await ctx.send(
                "Failed to unlock this channel — check my permissions. Lockdown state was kept, try again.",
                ephemeral=True,
            )
            return

        del _lockdown_snapshots[channel.id]

        embed = discord.Embed(
            title="🔓 Channel unlocked",
            description=f"This channel has been unlocked by {ctx.author.mention}.",
            color=LogColors.MOD,
            timestamp=discord.utils.utcnow(),
        )
        await ctx.send(embed=embed)
        await self._log_action(channel, ctx.author, locked=False)
