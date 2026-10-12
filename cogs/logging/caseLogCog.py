from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from bot import Context, TerrierBot
from .logConfig import LogColors, MOD_ROLE_ID, format_duration, resolve_user

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
# Discord's embed description cap. Pages are packed by length against this
# (not just by _PAGE_SIZE) so reasons are always shown in full instead of
# being cut short or making the send fail.
_DESCRIPTION_LIMIT = 4096


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
                # Kicks/timeouts/bans aren't warnings and are never appealed —
                # present here so _format_entry can treat every entry type
                # uniformly.
                "active": True,
                "appealed": False,
            }
        )
    return entries


def _fetch_warnings(user_id: int) -> list[dict]:
    if not os.path.exists(_WARNINGS_DB_PATH):
        return []
    conn = sqlite3.connect(_WARNINGS_DB_PATH)
    rows = conn.execute(
        "SELECT moderator_id, rule, reason, warned_at, active, removed_via FROM warnings "
        "WHERE user_id = ? ORDER BY warned_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()

    entries = []
    for moderator_id, rule, reason, warned_at, active, removed_via in rows:
        entries.append(
            {
                "type": "warn",
                "moderator_id": moderator_id,
                "reason": f"Rule {rule}: {reason}",
                "duration_seconds": None,
                "timestamp": datetime.fromisoformat(warned_at),
                "active": bool(active),
                "appealed": removed_via == "appeal",
            }
        )
    return entries


def _moderator_label(entry: dict) -> str:
    # "moderator_name" is filled in by modlogs before the entries are paged;
    # without it (unresolvable account) fall back to the bare mention.
    mention = f"<@{entry['moderator_id']}>"
    name = entry.get("moderator_name")
    return f"{mention} (**{name}**)" if name else mention


def _format_entry(entry: dict) -> str:
    emoji, type_text = CASE_LABELS.get(entry["type"], (_UNKNOWN_CASE_EMOJI, entry["type"].title()))
    ts = int(entry["timestamp"].timestamp())

    reason = entry["reason"]

    duration_suffix = ""
    if entry["duration_seconds"]:
        duration_suffix = f" ({format_duration(timedelta(seconds=entry['duration_seconds']))})"

    if entry["appealed"]:
        # Zero-width mark + space in place of the emoji — invisible, but
        # occupies the same column position as a real emoji would.
        marker = "‎ "
        return (
            f"*{marker}**{type_text}** — <t:{ts}:R> by {_moderator_label(entry)} — "
            f"{reason}{duration_suffix} — Appealed*"
        )

    return (
        f"{emoji} **{type_text}** — <t:{ts}:R> by {_moderator_label(entry)} — "
        f"{reason}{duration_suffix}"
    )


async def setup(bot: TerrierBot):
    await bot.add_cog(CaseLogCog(bot))


def _split_long(text: str, limit: int) -> list[str]:
    """Split one over-long entry into chunks of at most `limit` chars,
    preferring line then word boundaries, so nothing is ever dropped."""
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = text.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip()
    chunks.append(text)
    return chunks


def paginate_lines(
    header: str, lines: list[str], *, sep: str = "\n", max_per_page: int = _PAGE_SIZE
) -> list[tuple[str, int, int]]:
    """Pack `lines` under `header` into embed descriptions that each fit
    Discord's cap. Returns (description, first_line_no, last_line_no) per
    page, 1-indexed. A single line too long for one page continues onto the
    next rather than being truncated."""
    budget = _DESCRIPTION_LIMIT - len(header) - 2  # "\n\n" after the header
    pages: list[tuple[str, int, int]] = []
    current: list[str] = []
    current_len = 0
    first = last = 0

    def flush() -> None:
        pages.append((f"{header}\n\n" + sep.join(current), first, last))

    for idx, line in enumerate(lines, start=1):
        for piece in _split_long(line, budget):
            added = len(piece) + (len(sep) if current else 0)
            if current and (current_len + added > budget or len(current) >= max_per_page):
                flush()
                current, current_len = [], 0
                added = len(piece)
            if not current:
                first = idx
            current.append(piece)
            current_len += added
            last = idx
    if current:
        flush()
    return pages


class PagedEmbedView(discord.ui.View):
    """Prev/Next pager over pre-built pages from paginate_lines(). Shared by
    =modlogs and warningsCog's =warninfo / /mywarns. Paging is restricted to
    `owner_id` when given, otherwise to mods."""

    def __init__(
        self,
        pages: list[tuple[str, int, int]],
        *,
        title: str,
        color: discord.Color | int,
        total: int,
        empty_text: str,
        owner_id: int | None = None,
    ) -> None:
        super().__init__(timeout=120)
        self.pages = pages
        self.title = title
        self.color = color
        self.total = total
        self.empty_text = empty_text
        self.owner_id = owner_id
        self.page = 0
        self._rebuild()

    def _total_pages(self) -> int:
        return max(1, len(self.pages))

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
        total = self.total
        if self.pages:
            description, start, end = self.pages[self.page]
            footer = f"{total} total entr{'y' if total == 1 else 'ies'} — showing {start}-{end}"
        else:
            description, footer = self.empty_text, "0 entries"

        embed = discord.Embed(title=self.title, description=description, color=self.color)
        embed.set_footer(text=footer)
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.owner_id is not None:
            if interaction.user.id == self.owner_id:
                return True
        elif isinstance(interaction.user, discord.Member) and any(
            r.id == MOD_ROLE_ID for r in interaction.user.roles
        ):
            return True
        await interaction.response.send_message(
            "You don't have permission to use this.", ephemeral=True
        )
        return False

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
            await ctx.send("Oops! You can't run that... mods only!", ephemeral=True)
            return False
        return True

    @commands.hybrid_command(
        name="modlogs", description="View a member's full moderation case history."
    )
    @app_commands.describe(member="Member to look up (works even if they've left the server)")
    async def modlogs(self, ctx: Context, member: discord.User):
        if not await self._require_mod(ctx):
            return

        user_id = member.id
        target_line = f"{member.mention} — **{member}** (`{user_id}`)"

        entries = sorted(
            _fetch_cases(user_id) + _fetch_warnings(user_id),
            key=lambda e: e["timestamp"],
            reverse=True,
        )

        moderator_names: dict[int, str | None] = {}
        for entry in entries:
            mod_id = entry["moderator_id"]
            if mod_id not in moderator_names:
                mod = await resolve_user(self.bot, mod_id)
                moderator_names[mod_id] = str(mod) if mod is not None else None
            entry["moderator_name"] = moderator_names[mod_id]

        view = PagedEmbedView(
            paginate_lines(target_line, [_format_entry(entry) for entry in entries]),
            title="📋 Moderation case log",
            color=LogColors.MOD,
            total=len(entries),
            empty_text=f"{target_line}\n\nNo warns, kicks, timeouts, or bans on record.",
        )
        await ctx.send(
            embed=view.build_embed(),
            view=view if len(view.pages) > 1 else None,
        )
