from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from bot import Context, TerrierBot
from .logConfig import LogColors, MOD_ROLE_ID, format_duration

# Same on-disk location pattern as warningsCog's warnings.db — outside the
# PM2-watched project directory so a deploy/redeploy never touches case data.
DB_DIR = os.path.expanduser("~/terrierbot_data")
DB_PATH = os.path.join(DB_DIR, "casedb.sqlite3")

# warningsCog.py's DB, read directly below. It doesn't expose a public
# function for fetching a user's warning history (its queries live inline in
# the `warninfo` command), so rather than add one there this reads the file
# it already writes, read-only, using the schema it defines.
_WARNINGS_DB_PATH = os.path.join(DB_DIR, "warnings.db")

_PAGE_SIZE = 15

CASE_LABELS = {
    "kick": ("👢", "Kick"),
    "timeout": ("🔇", "Timeout"),
    "untimeout": ("🔊", "Timeout cleared"),
    "ban": ("🔨", "Ban"),
    "unban": ("🔓", "Unban"),
    "warn": ("⚠️", "Warn"),
}
_UNKNOWN_CASE_EMOJI = "•"
_REASON_MAX_LEN = 60

_MENTION_RE = re.compile(r"^<@!?(\d+)>$")


def _init_db() -> None:
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            case_type TEXT NOT NULL,
            reason TEXT,
            duration_seconds INTEGER,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


# Run at import time (not in the Cog's __init__) so record_case() works for
# callers even if CaseLogCog itself hasn't been added as a cog yet.
_init_db()


def record_case(
    user_id: int,
    moderator_id: int,
    case_type: str,
    reason: str | None,
    duration_seconds: int | None = None,
) -> None:
    """Insert one moderation case. Importable by other cogs (kick/timeout/ban)
    to log an action without depending on CaseLogCog being loaded."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO cases (user_id, moderator_id, case_type, reason, duration_seconds, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            user_id,
            moderator_id,
            case_type,
            reason,
            duration_seconds,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def _fetch_cases(user_id: int) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT case_type, moderator_id, reason, duration_seconds, created_at "
        "FROM cases WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()

    entries = []
    for case_type, moderator_id, reason, duration_seconds, created_at in rows:
        entries.append(
            {
                "type": case_type,
                "moderator_id": moderator_id,
                "reason": reason or "No reason provided",
                "duration_seconds": duration_seconds,
                "timestamp": datetime.fromisoformat(created_at),
            }
        )
    return entries


def _fetch_warnings(user_id: int) -> list[dict]:
    if not os.path.exists(_WARNINGS_DB_PATH):
        return []
    conn = sqlite3.connect(_WARNINGS_DB_PATH)
    rows = conn.execute(
        "SELECT moderator_id, rule, reason, warned_at FROM warnings WHERE user_id = ? ORDER BY warned_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()

    entries = []
    for moderator_id, rule, reason, warned_at in rows:
        entries.append(
            {
                "type": "warn",
                "moderator_id": moderator_id,
                "reason": f"Rule {rule}: {reason}",
                "duration_seconds": None,
                "timestamp": datetime.fromisoformat(warned_at),
            }
        )
    return entries


def _parse_user_id(raw: str) -> int | None:
    raw = raw.strip()
    match = _MENTION_RE.match(raw)
    if match:
        raw = match.group(1)
    return int(raw) if raw.isdigit() else None


def _resolve_target(guild: discord.Guild, raw: str) -> tuple[int, discord.Member | None] | None:
    """Resolve a mention, raw ID, or username to (user_id, member-or-None)."""
    user_id = _parse_user_id(raw)
    if user_id is not None:
        return user_id, guild.get_member(user_id)

    needle = raw.strip().lower()
    if not needle:
        return None
    for member in guild.members:
        if member.name.lower() == needle or member.display_name.lower() == needle:
            return member.id, member
    for member in guild.members:
        if needle in member.name.lower() or needle in member.display_name.lower():
            return member.id, member
    return None


def _format_entry(entry: dict) -> str:
    emoji, type_text = CASE_LABELS.get(entry["type"], (_UNKNOWN_CASE_EMOJI, entry["type"].title()))
    ts = int(entry["timestamp"].timestamp())

    reason = entry["reason"]
    if len(reason) > _REASON_MAX_LEN:
        reason = reason[: _REASON_MAX_LEN - 1].rstrip() + "…"

    duration_suffix = ""
    if entry["duration_seconds"]:
        duration_suffix = f" ({format_duration(timedelta(seconds=entry['duration_seconds']))})"

    return (
        f"{emoji} **{type_text}** — <t:{ts}:R> by <@{entry['moderator_id']}> — "
        f"{reason}{duration_suffix}"
    )


async def setup(bot: TerrierBot):
    await bot.add_cog(CaseLogCog(bot))


class _ModLogsView(discord.ui.View):
    def __init__(self, entries: list[dict], target_line: str) -> None:
        super().__init__(timeout=120)
        self.entries = entries
        self.target_line = target_line
        self.page = 0
        self._rebuild()

    def _total_pages(self) -> int:
        return max(1, (len(self.entries) + _PAGE_SIZE - 1) // _PAGE_SIZE)

    def _rebuild(self) -> None:
        self.clear_items()
        total_pages = self._total_pages()

        prev_btn = discord.ui.Button(
            label="◀ Prev", style=discord.ButtonStyle.secondary, disabled=(self.page == 0)
        )
        prev_btn.callback = self._on_prev
        self.add_item(prev_btn)

        self.add_item(
            discord.ui.Button(
                label=f"Page {self.page + 1} / {total_pages}",
                style=discord.ButtonStyle.secondary,
                disabled=True,
            )
        )

        next_btn = discord.ui.Button(
            label="Next ▶",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page >= total_pages - 1),
        )
        next_btn.callback = self._on_next
        self.add_item(next_btn)

    def build_embed(self) -> discord.Embed:
        total = len(self.entries)
        start = self.page * _PAGE_SIZE
        end = min(start + _PAGE_SIZE, total)
        page_entries = self.entries[start:end]

        if page_entries:
            lines = "\n".join(_format_entry(entry) for entry in page_entries)
            description = f"{self.target_line}\n\n{lines}"
        else:
            description = f"{self.target_line}\n\nNo warns, kicks, timeouts, or bans on record."

        embed = discord.Embed(
            title="📋 Moderation case log",
            description=description,
            color=LogColors.MOD,
        )
        embed.set_footer(
            text=f"{total} total entr{'y' if total == 1 else 'ies'} — showing {start + 1}-{end}"
            if total
            else "0 entries"
        )
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member) or not any(
            r.id == MOD_ROLE_ID for r in interaction.user.roles
        ):
            await interaction.response.send_message(
                "You don't have permission to use this.", ephemeral=True
            )
            return False
        return True

    async def _on_prev(self, interaction: discord.Interaction) -> None:
        self.page = max(0, self.page - 1)
        self._rebuild()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _on_next(self, interaction: discord.Interaction) -> None:
        self.page = min(self._total_pages() - 1, self.page + 1)
        self._rebuild()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class CaseLogCog(
    commands.Cog,
    name="CaseLog",
    description="Shared moderation case log for kicks/timeouts/bans/warnings, viewable with =modlogs.",
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

    @commands.hybrid_command(
        name="modlogs", description="View a member's full moderation case history."
    )
    @app_commands.describe(member_or_id="Member mention, user ID, or username")
    async def modlogs(self, ctx: Context, *, member_or_id: str):
        if not await self._require_mod(ctx):
            return
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        resolved = _resolve_target(guild, member_or_id)
        if resolved is None:
            await ctx.send(f"Couldn't find a member matching `{member_or_id}`.", ephemeral=True)
            return
        user_id, member = resolved

        target_display = member.mention if member else f"<@{user_id}>"
        target_line = f"{target_display} (`{user_id}`)"

        entries = sorted(
            _fetch_cases(user_id) + _fetch_warnings(user_id),
            key=lambda e: e["timestamp"],
            reverse=True,
        )

        view = _ModLogsView(entries, target_line)
        await ctx.send(
            embed=view.build_embed(),
            view=view if len(entries) > _PAGE_SIZE else None,
        )
