from __future__ import annotations

import re

import discord
from discord import app_commands
from discord.ext import commands

from bot import Context, TerrierBot
from ..logging.logConfig import MOD_ROLE_ID, register_purge

# Matches a full Discord message link, e.g.
# https://discord.com/channels/{guild}/{channel}/{message}
# (also accepts the ptb./canary. and legacy discordapp.com variants).
_MESSAGE_LINK_RE = re.compile(
    r"^https?://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)$"
)

# Safety cap for =purgeafter — never delete more than this many messages in
# one call, even if the target message is far back in channel history.
PURGE_AFTER_CAP = 200


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
            await ctx.send("Oops! You can't run that... mods only!", ephemeral=True)
            return False
        return True

    @staticmethod
    def _parse_target(target: str) -> tuple[int | None, int | None]:
        """Parse a =purgeafter target argument into (channel_id, message_id).
        channel_id is None when it can't be determined (a bare message ID) —
        callers fall back to trying the current channel in that case.
        Returns (None, None) if target isn't a usable ID or link."""
        target = target.strip().strip("<>")
        match = _MESSAGE_LINK_RE.match(target)
        if match:
            _guild_id, channel_id, message_id = match.groups()
            return int(channel_id), int(message_id)
        if target.isdigit():
            return None, int(target)
        return None, None

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
        check = lambda m: True  # noqa: E731
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

    @commands.hybrid_command(
        name="purgeafter",
        description="Delete every message posted after a target message in this channel (up to 200).",
    )
    @app_commands.describe(
        target="Message ID or message link to purge after (reply to a message instead when using =purgeafter)"
    )
    async def purgeafter(self, ctx: Context, target: str | None = None):
        if not await self._require_mod(ctx):
            return
        if not isinstance(ctx.channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            await ctx.send("This command can only be used in a text channel.", ephemeral=True)
            return

        # Prefix replies take priority over an explicit target argument — a
        # slash invocation has no reply concept, so target is required there.
        reply_channel_id: int | None = None
        reply_message_id: int | None = None
        contradiction_note: str | None = None
        if ctx.interaction is None and ctx.message.reference is not None:
            reply_channel_id = ctx.message.reference.channel_id
            reply_message_id = ctx.message.reference.message_id
            if target is not None:
                contradiction_note = (
                    "You replied to a message and also passed a target — used the reply, ignored the argument."
                )

        if reply_message_id is None and target is None:
            await ctx.send(
                "Tell me which message to purge after — reply to it with `=purgeafter`, "
                "or pass its message ID or link: `=purgeafter <id_or_link>`.",
                ephemeral=True,
            )
            return

        if reply_message_id is not None:
            target_channel_id, target_message_id = reply_channel_id, reply_message_id
        else:
            assert target is not None
            target_channel_id, target_message_id = self._parse_target(target)
            if target_message_id is None:
                await ctx.send(
                    "That doesn't look like a message ID or a Discord message link. "
                    "Reply to the message with `=purgeafter`, or pass its ID or link.",
                    ephemeral=True,
                )
                return

        if target_channel_id is not None and target_channel_id != ctx.channel.id:
            await ctx.send(
                "That message isn't in this channel — `=purgeafter` only purges within the current channel.",
                ephemeral=True,
            )
            return

        await ctx.defer(ephemeral=True)

        try:
            target_message = await ctx.channel.fetch_message(target_message_id)
        except discord.NotFound:
            await ctx.send("Couldn't find that message in this channel.", ephemeral=True)
            return
        except discord.Forbidden:
            await ctx.send("I don't have permission to read message history here.", ephemeral=True)
            return
        except discord.HTTPException as exc:
            await ctx.send(f"Failed to fetch that message: {exc}", ephemeral=True)
            return

        try:
            deleted = await ctx.channel.purge(
                after=target_message, limit=PURGE_AFTER_CAP, oldest_first=False, bulk=True
            )
        except discord.Forbidden:
            await ctx.send("I don't have permission to delete messages here.", ephemeral=True)
            return
        except discord.HTTPException as exc:
            await ctx.send(f"Failed to purge messages: {exc}", ephemeral=True)
            return

        # oldest_first=False above deleted the 200 messages closest to now first;
        # anything still sitting after the target means the cap left messages behind.
        partial = False
        try:
            async for _ in ctx.channel.history(after=target_message, limit=1):
                partial = True
                break
        except (discord.Forbidden, discord.HTTPException):
            pass

        if ctx.interaction is None:
            try:
                await ctx.message.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass

        if deleted:
            register_purge([m.id for m in deleted], ctx.author.id, ctx.channel.id)

        lines = [f"🗑️ Purged {len(deleted)} message(s) after {target_message.jump_url}."]
        if partial:
            lines.append(
                f"⚠️ More than {PURGE_AFTER_CAP} messages were posted after the target — only the "
                f"{PURGE_AFTER_CAP} closest to now were deleted; older messages were left untouched."
            )
        if contradiction_note:
            lines.append(contradiction_note)
        await ctx.send("\n".join(lines), ephemeral=True)
