from __future__ import annotations

import csv
import io
import shelve
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot import Context, TerrierBot
from ..logging.logConfig import MAIN_GUILD_ID, MOD_ROLE_ID

EASTERN = ZoneInfo("America/New_York")
SHELVE_FILE = "terrierbot.shelve"
# {str(user_id): {"days": {"YYYY-MM-DD": count}, "last": unix_ts}} — keyed by
# str(user_id) so deleteUserDataCog can drop a user's entry outright.
ACTIVITY_KEY = "member_activity"
ACTIVITY_SINCE_KEY = "member_activity_since"
WINDOW_DAYS = 30

_FIELDS = [
    "username", "global_name", "server_nickname", "user_id", "bot", "roles",
    "joined_server_et", "account_created_et", "boosting_since_et",
    "messages_7d", "messages_30d", "last_message_et", "activity_level",
]


def _day(ts: float | datetime) -> str:
    dt = ts if isinstance(ts, datetime) else datetime.fromtimestamp(ts, tz=EASTERN)
    return dt.astimezone(EASTERN).strftime("%Y-%m-%d")


def _fmt(dt: datetime | None) -> str:
    return dt.astimezone(EASTERN).strftime("%Y-%m-%d %H:%M") if dt else ""


def _activity_level(messages_30d: int) -> str:
    if messages_30d >= 200:
        return "Very active"
    if messages_30d >= 50:
        return "Active"
    if messages_30d >= 10:
        return "Moderate"
    if messages_30d >= 1:
        return "Low"
    return "Inactive"


async def setup(bot: TerrierBot):
    await bot.add_cog(ExportAllCog(bot))


class ExportAllCog(
    commands.Cog,
    name="ExportAll",
    description="Tracks per-member message activity and exports every member to a CSV in DMs (mod only).",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot
        with shelve.open(SHELVE_FILE) as sh:
            self.activity: dict[str, dict] = sh.get(ACTIVITY_KEY, {})
            self.since: float = sh.get(ACTIVITY_SINCE_KEY) or time.time()
            sh[ACTIVITY_SINCE_KEY] = self.since
        self._dirty = False
        self._save_loop.start()

    async def cog_unload(self) -> None:
        self._save_loop.cancel()
        self._save()

    # ---------- persistence ----------

    def _prune(self) -> None:
        cutoff = _day(time.time() - (WINDOW_DAYS + 1) * 86400)
        for uid in list(self.activity):
            entry = self.activity[uid]
            entry["days"] = {d: n for d, n in entry.get("days", {}).items() if d >= cutoff}

    def _save(self) -> None:
        if not self._dirty:
            return
        self._prune()
        with shelve.open(SHELVE_FILE) as sh:
            sh[ACTIVITY_KEY] = self.activity
        self._dirty = False

    @tasks.loop(minutes=5)
    async def _save_loop(self) -> None:
        self._save()

    # ---------- live tracking ----------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.guild.id != MAIN_GUILD_ID:
            return
        if message.author.bot or message.webhook_id is not None:
            return
        ts = message.created_at.timestamp()
        entry = self.activity.setdefault(str(message.author.id), {"days": {}, "last": 0})
        day = _day(ts)
        entry["days"][day] = entry["days"].get(day, 0) + 1
        entry["last"] = max(entry.get("last", 0), ts)
        self._dirty = True

    # ---------- history backfill ----------

    async def _scan_history(self, guild: discord.Guild, days: int) -> tuple[int, list[str]]:
        """Recount the last `days` days from channel history, replacing the
        tracked counts for those days. Returns (messages counted, unreadable channels)."""
        after = discord.utils.utcnow() - timedelta(days=days)
        channels: list = [*guild.text_channels, *guild.voice_channels, *guild.threads]
        seen = {c.id for c in channels}
        for parent in [*guild.text_channels, *guild.forums]:
            try:
                async for thread in parent.archived_threads(limit=None):
                    if thread.archive_timestamp < after:
                        break  # newest-archived first; the rest are older
                    if thread.id not in seen:
                        seen.add(thread.id)
                        channels.append(thread)
            except discord.HTTPException:
                pass

        counts: dict[str, dict[str, int]] = {}
        last: dict[str, float] = {}
        total = 0
        skipped: list[str] = []
        for channel in channels:
            try:
                async for m in channel.history(after=after, limit=None):
                    if m.author.bot or m.webhook_id is not None:
                        continue
                    uid = str(m.author.id)
                    ts = m.created_at.timestamp()
                    day = _day(ts)
                    user_days = counts.setdefault(uid, {})
                    user_days[day] = user_days.get(day, 0) + 1
                    last[uid] = max(last.get(uid, 0), ts)
                    total += 1
            except discord.HTTPException:
                skipped.append(f"#{channel.name}")

        # Scanned days replace tracked ones wholesale so nothing is double-counted.
        scanned_days = {_day(after + timedelta(days=i)) for i in range(days + 1)}
        for uid in set(self.activity) | set(counts):
            entry = self.activity.setdefault(uid, {"days": {}, "last": 0})
            entry["days"] = {d: n for d, n in entry["days"].items() if d not in scanned_days}
            entry["days"].update(counts.get(uid, {}))
            entry["last"] = max(entry.get("last", 0), last.get(uid, 0))
        self.since = min(self.since, after.timestamp())
        with shelve.open(SHELVE_FILE) as sh:
            sh[ACTIVITY_SINCE_KEY] = self.since
        self._dirty = True
        self._save()
        return total, skipped

    # ---------- export ----------

    def _counts(self, user_id: int) -> tuple[int, int, float]:
        entry = self.activity.get(str(user_id))
        if not entry:
            return 0, 0, 0
        now = time.time()
        cut7 = _day(now - 6 * 86400)
        cut30 = _day(now - (WINDOW_DAYS - 1) * 86400)
        days = entry.get("days", {})
        m7 = sum(n for d, n in days.items() if d >= cut7)
        m30 = sum(n for d, n in days.items() if d >= cut30)
        return m7, m30, entry.get("last", 0)

    @commands.hybrid_command(
        name="exportall",
        description="DM yourself a CSV of every member: names, roles, join date, and activity (mod only).",
    )
    @app_commands.describe(
        days="Optional: rescan this many days of message history first for accurate activity (1-30)",
    )
    @commands.guild_only()
    async def exportall(self, ctx: Context, days: app_commands.Range[int, 0, 30] = 0):
        """Mod only. DMs a CSV of all members with names, roles, join date and activity level.

        Usage: =exportall [days] — pass days (1-30) to rescan that much history first.
        """
        assert ctx.guild is not None
        if not isinstance(ctx.author, discord.Member) or not any(r.id == MOD_ROLE_ID for r in ctx.author.roles):
            await ctx.send("Oops! You can't run that... mods only!", ephemeral=True)
            return

        await ctx.defer(ephemeral=True)
        guild = ctx.guild
        if not guild.chunked:
            await guild.chunk()

        scan_note = ""
        if days > 0 and guild.id == MAIN_GUILD_ID:
            total, skipped = await self._scan_history(guild, days)
            scan_note = f" Rescanned {days}d of history ({total} messages)."
            if skipped:
                scan_note += f" Couldn't read {len(skipped)} channel(s)."

        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=_FIELDS)
        writer.writeheader()
        members = sorted(guild.members, key=lambda m: m.joined_at or discord.utils.utcnow())
        for m in members:
            m7, m30, last_ts = self._counts(m.id)
            roles = [r.name for r in reversed(m.roles) if not r.is_default()]  # highest first
            writer.writerow({
                "username": m.name,
                "global_name": m.global_name or "",
                "server_nickname": m.nick or "",
                "user_id": m.id,
                "bot": "yes" if m.bot else "",
                "roles": "; ".join(roles),
                "joined_server_et": _fmt(m.joined_at),
                "account_created_et": _fmt(m.created_at),
                "boosting_since_et": _fmt(m.premium_since),
                "messages_7d": "" if m.bot else m7,
                "messages_30d": "" if m.bot else m30,
                "last_message_et": _fmt(datetime.fromtimestamp(last_ts, tz=EASTERN)) if last_ts else "",
                "activity_level": "Bot" if m.bot else _activity_level(m30),
            })

        tracked_days = (time.time() - self.since) / 86400
        note = f"{len(members)} members in {guild.name}.{scan_note}"
        if tracked_days < WINDOW_DAYS:
            note += (
                f"\n-# Activity only covers the last {tracked_days:.1f} days (tracking started "
                f"<t:{int(self.since)}:R>). Run `=exportall 30` to backfill from history."
            )

        filename = f"members-{datetime.now(EASTERN):%Y-%m-%d}.csv"
        # utf-8-sig so Excel opens emoji/non-ASCII names correctly
        file = discord.File(io.BytesIO(buffer.getvalue().encode("utf-8-sig")), filename=filename)
        try:
            await ctx.author.send(note[:2000], file=file)
        except discord.Forbidden:
            await ctx.send("I couldn't DM you. Open your DMs for this server and try again.", ephemeral=True)
            return
        await ctx.send("Sent to your DMs.", ephemeral=True)
