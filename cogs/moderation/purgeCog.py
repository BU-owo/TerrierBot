from __future__ import annotations

import io
import re

import discord
from discord import app_commands
from discord.ext import commands

from bot import Context, TerrierBot
from ..logging.logConfig import (
    JUNIOR_MOD_ROLE_ID,
    LogChannels,
    LogColors,
    MAIN_GUILD_ID,
    MOD_ROLE_ID,
    get_log_channel,
    register_purge,
)

# Matches a full Discord message link, e.g.
# https://discord.com/channels/{guild}/{channel}/{message}
# (also accepts the ptb./canary. and legacy discordapp.com variants).
_MESSAGE_LINK_RE = re.compile(
    r"^https?://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)$"
)

# Safety cap for =purgeafter — never delete more than this many messages in
# one call, even if the target message is far back in channel history.
PURGE_AFTER_CAP = 200

# Safety cap for =purgeuser — how far back through channel history to search
# for that user's messages before giving up, even if `amount` wasn't reached.
PURGEUSER_SCAN_LIMIT = 500

# Transcript files stay well under Discord's upload cap; a purge that somehow
# exceeds this is split across several files so nothing is ever truncated.
_TRANSCRIPT_CHUNK_BYTES = 7_000_000
_DISCORD_MAX_FILES_PER_MESSAGE = 10


def _format_message(message: discord.Message) -> str:
    stamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [f"[{stamp}] {message.author} (user {message.author.id}) | message {message.id}"]
    if message.reference is not None and message.reference.message_id is not None:
        lines.append(f"  (reply to message {message.reference.message_id})")
    if message.content:
        lines.extend("  " + line for line in message.content.split("\n"))
    else:
        lines.append("  (no text content)")
    for attachment in message.attachments:
        lines.append(f"  [attachment] {attachment.filename}: {attachment.url}")
    for embed in message.embeds:
        parts = [part for part in (embed.title, embed.description, embed.url) if part]
        lines.append("  [embed] " + " - ".join(parts) if parts else "  [embed]")
    for sticker in message.stickers:
        lines.append(f"  [sticker] {sticker.name}")
    return "\n".join(lines)


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
            r.id in (MOD_ROLE_ID, JUNIOR_MOD_ROLE_ID) for r in ctx.author.roles
        ):
            await ctx.send("Oops! You can't run that... mods only!", ephemeral=True)
            return False
        return True

    async def _log_purge(self, ctx: Context, deleted: list[discord.Message], command: str, detail: str | None = None) -> None:
        """Post the complete, untruncated contents of a purge to #message-logs
        as attached text transcripts, using the messages the purge itself
        returned (full content even if they were never in the bot's cache)."""
        if ctx.guild is None or ctx.guild.id != MAIN_GUILD_ID:
            return
        log_channel = get_log_channel(self.bot, LogChannels.MESSAGE)
        if log_channel is None:
            return

        messages = sorted(deleted, key=lambda m: m.id)
        now = discord.utils.utcnow()
        header = (
            f"Purge by {ctx.author} (user {ctx.author.id})\n"
            f"Command: {command}\n"
            f"Channel: #{ctx.channel.name} ({ctx.channel.id})\n"
            f"Time: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"Messages deleted: {len(messages)}"
        )
        if detail:
            header += f"\n{detail}"

        chunks: list[str] = []
        current = [header]
        size = len(header.encode())
        for block in (_format_message(m) for m in messages):
            block_size = len(block.encode()) + 2
            if size + block_size > _TRANSCRIPT_CHUNK_BYTES and len(current) > 1:
                chunks.append("\n\n".join(current))
                current, size = [], 0
            current.append(block)
            size += block_size
        chunks.append("\n\n".join(current))

        stamp = now.strftime("%Y%m%d-%H%M%S")
        files = [
            discord.File(
                io.BytesIO(chunk.encode("utf-8")),
                filename=f"purge-{stamp}.txt" if len(chunks) == 1 else f"purge-{stamp}-part{i}.txt",
            )
            for i, chunk in enumerate(chunks, start=1)
        ]

        description = (
            f"{len(messages)} message(s) purged by {ctx.author.mention} in {ctx.channel.mention} (`{command}`)"
        )
        if detail:
            description += f"\n{detail}"
        description += f"\n\nFull transcript attached ({len(files)} file(s)) — nothing truncated."
        embed = discord.Embed(
            title="🗑️ Purge transcript",
            description=description,
            color=LogColors.MOD_DELETE,
            timestamp=now,
        )
        embed.set_footer(text=f"Purged by user ID: {ctx.author.id}")

        try:
            for start in range(0, len(files), _DISCORD_MAX_FILES_PER_MESSAGE):
                batch = files[start : start + _DISCORD_MAX_FILES_PER_MESSAGE]
                await log_channel.send(
                    embed=embed if start == 0 else None,
                    files=batch,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        except discord.HTTPException:
            pass

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
            await self._log_purge(ctx, deleted, f"purge {amount}")

        confirmation = await ctx.send(f"🗑️ Purged {len(deleted)} message(s).", ephemeral=True)
        # ephemeral is a no-op on a prefix invocation (=purge, not /purge) —
        # it posts as a normal visible message, so clean it up after a delay
        # instead of leaving it sitting in the channel forever.
        if ctx.interaction is None:
            await confirmation.delete(delay=60)

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
            await self._log_purge(ctx, deleted, "purgeafter", f"After message: {target_message.jump_url}")

        lines = [f"🗑️ Purged {len(deleted)} message(s) after {target_message.jump_url}."]
        if partial:
            lines.append(
                f"⚠️ More than {PURGE_AFTER_CAP} messages were posted after the target — only the "
                f"{PURGE_AFTER_CAP} closest to now were deleted; older messages were left untouched."
            )
        if contradiction_note:
            lines.append(contradiction_note)
        await ctx.send("\n".join(lines), ephemeral=True)

    @commands.hybrid_command(
        name="purgeuser",
        description="Delete a specific member's most recent messages in this channel.",
    )
    @app_commands.describe(
        user="Whose messages to delete",
        amount="How many of their messages to delete (1-100)",
    )
    async def purgeuser(self, ctx: Context, user: discord.Member, amount: commands.Range[int, 1, 100]):
        if not await self._require_mod(ctx):
            return
        if not isinstance(ctx.channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            await ctx.send("This command can only be used in a text channel.", ephemeral=True)
            return

        await ctx.defer(ephemeral=True)

        # Prefix invocations post a "=purgeuser <user> <amount>" message of
        # their own — exclude it, same as =purge does with its own invoking
        # message. `matched` bounds how many of the user's messages we let
        # through the check to exactly `amount`, since `purge`'s own `limit`
        # caps how many messages are *scanned*, not how many are deleted.
        invoking_id = ctx.message.id if ctx.interaction is None else None
        matched = 0

        def check(message: discord.Message) -> bool:
            nonlocal matched
            if message.id == invoking_id or message.author.id != user.id:
                return False
            if matched >= amount:
                return False
            matched += 1
            return True

        try:
            deleted = await ctx.channel.purge(limit=PURGEUSER_SCAN_LIMIT, check=check, bulk=True)
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
            await self._log_purge(ctx, deleted, f"purgeuser {amount}", f"Target user: {user} (user {user.id})")

        note = ""
        if len(deleted) < amount:
            note = f" (only found {len(deleted)} within the last {PURGEUSER_SCAN_LIMIT} messages scanned)"
        await ctx.send(f"🗑️ Purged {len(deleted)} message(s) from {user.mention}.{note}", ephemeral=True)
