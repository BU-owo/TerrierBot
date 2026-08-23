from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot import Context, TerrierBot
from .logConfig import MOD_ROLE_ID, register_purge


async def setup(bot: TerrierBot):
    await bot.add_cog(PurgeCog(bot))


class PurgeCog(
    commands.Cog,
    name="Purge",
    description="Bulk-deletes recent messages in a channel (mod only).",
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

    @commands.hybrid_command(name="purge", description="Bulk-delete recent messages in this channel.")
    @app_commands.describe(amount="Number of messages to delete (1-100)")
    async def purge(self, ctx: Context, amount: commands.Range[int, 1, 100]):
        if not await self._require_mod(ctx):
            return
        if not isinstance(ctx.channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            await ctx.send("This command can only be used in a text channel.", ephemeral=True)
            return

        await ctx.defer(ephemeral=True)

        # Prefix invocations post a "=purge <amount>" message of their own —
        # exclude it from the amount-limited purge below so the count the mod
        # asked for matches actual content deleted, then clean it up separately.
        check = None
        if ctx.interaction is None:
            invoking_id = ctx.message.id
            check = lambda m: m.id != invoking_id  # noqa: E731

        try:
            deleted = await ctx.channel.purge(limit=amount, check=check, bulk=True)
        except discord.Forbidden:
            await ctx.send("I don't have permission to delete messages here.", ephemeral=True)
            return
        except discord.HTTPException as exc:
            await ctx.send(f"Failed to purge messages: {exc}", ephemeral=True)
            return

        if ctx.interaction is None:
            try:
                await ctx.message.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass

        if deleted:
            register_purge([m.id for m in deleted], ctx.author.id, ctx.channel.id)

        await ctx.send(f"🗑️ Purged {len(deleted)} message(s).", ephemeral=True)
