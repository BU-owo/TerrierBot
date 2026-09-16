from __future__ import annotations

import re

import discord
from discord import app_commands
from discord.ext import commands

from bot import Context, TerrierBot
from ..logging.logConfig import (
    LogChannels,
    LogColors,
    MAIN_GUILD_ID,
    MAX_SNAPSHOTS_PER_MESSAGE,
    MOD_ROLE_ID,
    MessageEditRecord,
    edit_history_fields,
    get_edit_history,
    get_log_channel,
    record_edit,
    user_line,
)

# Per-revision content preview cap for this cog's own embed — logConfig's
# edit_history_fields() defaults to the same value, passed explicitly here
# so the two stay obviously in sync.
_CONTENT_FIELD_MAX_LEN = 400

# Matches a full Discord message link, same pattern purgeCog uses.
_MESSAGE_LINK_RE = re.compile(
    r"^https?://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)$"
)


async def setup(bot: TerrierBot):
    await bot.add_cog(ViewEditsCog(bot))


class ViewEditsCog(
    commands.Cog,
    name="ViewEdits",
    description="Silently tracks message edit history and lets mods look it up on demand.",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot

    # ── Silent tracking ──────────────────────────────────────────────────────
    # The actual store lives in logConfig.py (record_edit/get_edit_history) so
    # MessageLogCog can show a deleted message's full edit chain too, not just
    # its own /=viewedits lookup.

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        if payload.guild_id != MAIN_GUILD_ID:
            return
        if "content" not in payload.data:
            # Not a content edit — e.g. Discord attaching a link-preview embed
            # after the fact fires this event too, but nothing was actually edited.
            return

        message = payload.message
        if message.author.bot:
            return

        if payload.cached_message is not None:
            before_content = payload.cached_message.content or "*(no text content)*"
        else:
            before_content = "*(original content unknown — not cached before this edit)*"

        record_edit(
            payload.message_id,
            channel_id=payload.channel_id,
            author_id=message.author.id,
            author_display=str(message.author),
            before_content=before_content,
            new_content=message.content or "*(no text content)*",
            created_at=message.created_at,
            edited_at=message.edited_at or discord.utils.utcnow(),
        )

    # ── Lookup command ───────────────────────────────────────────────────────

    @staticmethod
    async def _require_mod(ctx: Context) -> bool:
        if not isinstance(ctx.author, discord.Member) or not any(
            r.id == MOD_ROLE_ID for r in ctx.author.roles
        ):
            await ctx.send("Oops! You can't run that... mods only!", ephemeral=True)
            return False
        return True

    @staticmethod
    def _parse_message_id(target: str) -> int | None:
        target = target.strip().strip("<>")
        match = _MESSAGE_LINK_RE.match(target)
        if match:
            return int(match.group(3))
        if target.isdigit():
            return int(target)
        return None

    def _build_embed(
        self,
        guild: discord.Guild | None,
        message_id: int,
        record: MessageEditRecord,
        *,
        requested_by: discord.abc.User,
    ) -> discord.Embed:
        member = guild.get_member(record.author_id) if guild is not None else None
        author_line = user_line(member) if member is not None else f"**{record.author_display}** (`{record.author_id}`)"

        description = f"{author_line}\n**Channel:** <#{record.channel_id}>"
        if guild is not None:
            jump_url = f"https://discord.com/channels/{guild.id}/{record.channel_id}/{message_id}"
            description += f"\n[Jump to message]({jump_url})"
        if record.truncated:
            description += f"\n-# ⚠️ Only the {MAX_SNAPSHOTS_PER_MESSAGE} most recent revisions are shown — earlier history aged out."

        embed = discord.Embed(
            title="📝 Edit history",
            description=description,
            color=LogColors.EDIT,
            timestamp=discord.utils.utcnow(),
        )

        for name, value in edit_history_fields(record, max_len=_CONTENT_FIELD_MAX_LEN):
            embed.add_field(name=name, value=value, inline=False)

        embed.set_footer(text=f"Message ID: {message_id} • Looked up by {requested_by}")
        return embed

    @commands.hybrid_command(
        name="viewedits",
        description="View a message's edit history (mod only).",
    )
    @app_commands.describe(
        message="Message link or ID to view edit history for (reply to a message instead when using =viewedits)"
    )
    async def viewedits(self, ctx: Context, message: str | None = None):
        if not await self._require_mod(ctx):
            return

        target_message_id: int | None = None
        if ctx.interaction is None and ctx.message.reference is not None:
            target_message_id = ctx.message.reference.message_id

        if target_message_id is None and message is not None:
            target_message_id = self._parse_message_id(message)

        if target_message_id is None:
            await ctx.send(
                "Tell me which message to check — reply to it with `=viewedits`, "
                "or pass its message ID or link: `=viewedits <id_or_link>`.",
                ephemeral=True,
            )
            return

        record = get_edit_history(target_message_id)
        if record is None:
            await ctx.send(
                "No edit history recorded for that message — it either hasn't been edited, "
                "predates this bot session, or aged out of tracking.",
                ephemeral=True,
            )
            return

        embed = self._build_embed(ctx.guild, target_message_id, record, requested_by=ctx.author)

        if ctx.interaction is not None:
            await ctx.send(embed=embed, ephemeral=True)
        else:
            try:
                await ctx.message.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass

        log_channel = get_log_channel(self.bot, LogChannels.MESSAGE)
        if log_channel is not None:
            try:
                await log_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                pass
