from __future__ import annotations

import gzip
import io
import re
from collections import Counter
from datetime import timedelta
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

from bot import Context, TerrierBot

EASTERN = ZoneInfo("America/New_York")

# Stay under Discord's upload limit with some headroom; larger exports get gzipped.
GZIP_THRESHOLD_BYTES = 9 * 1024 * 1024

# clean_content resolves user/role/channel mentions to names, but custom emoji and
# message links still carry raw IDs, so collapse those to keep IDs out of the export.
_CUSTOM_EMOJI_RE = re.compile(r"<a?:(\w+):\d+>")
_MESSAGE_LINK_RE = re.compile(
    r"https?://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/channels/\d+/\d+(?:/\d+)?"
)


async def setup(bot: TerrierBot):
    await bot.add_cog(ExportCog(bot))


class ExportCog(
    commands.Cog,
    name="Export",
    description="Exports recent channel history to a text file in DMs (mod only).",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot

    @staticmethod
    def _clean(message: discord.Message) -> str:
        text = message.clean_content.replace("\r\n", "\n").replace("\n", " ⏎ ").strip()
        text = _CUSTOM_EMOJI_RE.sub(r":\1:", text)
        return _MESSAGE_LINK_RE.sub("[message link]", text)

    @commands.hybrid_command(
        name="exporthistory",
        description="DM yourself a text export of recent messages in a channel (mod only).",
    )
    @app_commands.describe(
        channel="Channel to export",
        days="How many days back to export (1-30, default 7)",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def exporthistory(
        self,
        ctx: Context,
        channel: discord.TextChannel,
        days: app_commands.Range[int, 1, 30] = 7,
    ):
        # Manage Messages alone doesn't imply the mod can read the target channel.
        perms = channel.permissions_for(ctx.author)
        if not (perms.view_channel and perms.read_message_history):
            await ctx.send("You can't read that channel, so I can't export it.", ephemeral=True)
            return

        await ctx.defer(ephemeral=True)

        after = discord.utils.utcnow() - timedelta(days=days)
        names: dict[int, str] = {}  # author id -> display name (ids never written out)
        authors_by_message: dict[int, int] = {}  # message id -> author id
        posters: Counter[int] = Counter()
        pairs: Counter[tuple[int, int]] = Counter()
        lines: list[str] = []

        try:
            async for message in channel.history(after=after, limit=None, oldest_first=True):
                author = message.author
                names[author.id] = author.display_name
                authors_by_message[message.id] = author.id

                text = self._clean(message)
                attachments = len(message.attachments)
                if author.bot or (not text and not attachments):
                    continue

                reply_to = ""
                ref = message.reference
                if ref is not None and ref.message_id is not None:
                    target_id = authors_by_message.get(ref.message_id)
                    if target_id is None and isinstance(ref.resolved, discord.Message):
                        target_id = ref.resolved.author.id
                        names.setdefault(target_id, ref.resolved.author.display_name)
                    if target_id is None:
                        reply_to = " (reply to unknown)"
                    else:
                        reply_to = f" (reply to {names[target_id]})"
                        if target_id != author.id:
                            pairs[tuple(sorted((author.id, target_id)))] += 1

                stamp = message.created_at.astimezone(EASTERN).strftime("%m/%d %H:%M")
                line = f"[{stamp}] {author.display_name}{reply_to}: {text}"
                if attachments:
                    line += f" [+{attachments} attachment]"
                lines.append(line)
                posters[author.id] += 1
        except discord.Forbidden:
            await ctx.send(f"I don't have permission to read history in {channel.mention}.", ephemeral=True)
            return

        header = [
            f"Channel: #{channel.name}",
            f"Days: {days}",
            f"Messages: {len(lines)}",
            "",
            "Top posters:",
            *(f"  {names[uid]}: {n}" for uid, n in posters.most_common(10)),
            "",
            "Top reply pairs:",
            *(f"  {names[a]} <-> {names[b]}: {n}" for (a, b), n in pairs.most_common(10)),
            "",
            "-" * 40,
            "",
        ]
        data = ("\n".join(header + lines) + "\n").encode("utf-8")
        filename = f"{channel.name}-last-{days}d.txt"
        if len(data) > GZIP_THRESHOLD_BYTES:
            data = gzip.compress(data)
            filename += ".gz"

        try:
            await ctx.author.send(file=discord.File(io.BytesIO(data), filename=filename))
        except discord.Forbidden:
            await ctx.send(
                "I couldn't DM you. Open your DMs for this server and try again.",
                ephemeral=True,
            )
            return

        await ctx.send("Sent to your DMs.", ephemeral=True)
