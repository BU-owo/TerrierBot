from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from bot import Context, TerrierBot
from ..logging.logConfig import LogChannels, LogColors, MAIN_GUILD_ID, MOD_ROLE_ID, get_log_channel, user_line

# How many tracked messages (each with its own edit chain) to keep in memory
# at once — bounds memory use on a busy server. Oldest-tracked message is
# evicted first once this is exceeded; a freshly-edited message is bumped
# back to "newest" so actively-discussed messages survive longest.
MAX_TRACKED_MESSAGES = 2000

# How many revisions of a single message to keep. Past this, the oldest
# revisions are dropped (keeping the most recent chain) — mostly a guard
# against a message getting edited dozens of times.
MAX_SNAPSHOTS_PER_MESSAGE = 12

# Per-revision content preview cap for the embed — keeps the total embed
# comfortably under Discord's 6000-char combined-embed limit even with
# MAX_SNAPSHOTS_PER_MESSAGE fields all populated.
_CONTENT_FIELD_MAX_LEN = 400

# Matches a full Discord message link, same pattern purgeCog uses.
_MESSAGE_LINK_RE = re.compile(
    r"^https?://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)$"
)


async def setup(bot: TerrierBot):
    await bot.add_cog(ViewEditsCog(bot))


@dataclass
class EditSnapshot:
    content: str
    at: datetime


@dataclass
class MessageEditRecord:
    channel_id: int
    author_id: int
    author_display: str
    snapshots: list[EditSnapshot] = field(default_factory=list)
    truncated: bool = False


class ViewEditsCog(
    commands.Cog,
    name="ViewEdits",
    description="Silently tracks message edit history and lets mods look it up on demand.",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot
        # In-memory only, same tradeoff messageLogCog makes with its cached
        # deletes — edit history doesn't survive a restart, and that's fine
        # for a mod lookup tool.
        self._edit_history: OrderedDict[int, MessageEditRecord] = OrderedDict()

    # ── Silent tracking ──────────────────────────────────────────────────────

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

        record = self._edit_history.get(payload.message_id)
        if record is None:
            if payload.cached_message is not None:
                before_content = payload.cached_message.content or "*(no text content)*"
            else:
                before_content = "*(original content unknown — not cached before this edit)*"
            record = MessageEditRecord(
                channel_id=payload.channel_id,
                author_id=message.author.id,
                author_display=str(message.author),
                snapshots=[EditSnapshot(content=before_content, at=message.created_at)],
            )
            self._edit_history[payload.message_id] = record
        else:
            self._edit_history.move_to_end(payload.message_id)

        record.snapshots.append(
            EditSnapshot(
                content=message.content or "*(no text content)*",
                at=message.edited_at or discord.utils.utcnow(),
            )
        )
        if len(record.snapshots) > MAX_SNAPSHOTS_PER_MESSAGE:
            record.snapshots = record.snapshots[-MAX_SNAPSHOTS_PER_MESSAGE:]
            record.truncated = True

        while len(self._edit_history) > MAX_TRACKED_MESSAGES:
            self._edit_history.popitem(last=False)

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

        total = len(record.snapshots)
        for i, snap in enumerate(record.snapshots, start=1):
            content = snap.content
            if len(content) > _CONTENT_FIELD_MAX_LEN:
                content = content[: _CONTENT_FIELD_MAX_LEN - 1].rstrip() + "…"
            label = f"Revision {i}/{total}"
            if i == total:
                label += " — current"
            elif i == 1 and not record.truncated:
                label += " — original"
            embed.add_field(name=f"{label} • <t:{int(snap.at.timestamp())}:f>", value=content, inline=False)

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

        record = self._edit_history.get(target_message_id)
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
