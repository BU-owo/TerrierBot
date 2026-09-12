from __future__ import annotations

import os
import shelve
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

import discord
from discord.ext import commands

from bot import Context, TerrierBot
from ..logging.logConfig import MOD_ROLE_ID

# ── Config ────────────────────────────────────────────────────────────────
# Category to split message counts against — messages here vs. everywhere
# else in the server. Change if the mod-work category ever moves.
TRACKED_CATEGORY_ID = 1441884565873496177

# Same external-data-dir convention as caseLogCog/warningsCog (see
# repo_overview.md §2) — both DBs live outside the repo in ~/terrierbot_data/.
_DATA_DIR = os.path.join(os.path.expanduser("~"), "terrierbot_data")
_CASE_DB = os.path.join(_DATA_DIR, "casedb.sqlite3")
_WARNINGS_DB = os.path.join(_DATA_DIR, "warnings.db")

# Own shelve key for live message-count tracking. Prefixed to avoid colliding
# with the shared terrierbot.shelve namespace (see repo_overview.md §2).
SHELVE_FILE = "terrierbot.shelve"
SHELVE_KEY = "modtracker_message_counts"


async def setup(bot: TerrierBot):
    await bot.add_cog(ModTrackerCog(bot))


class ModTrackerCog(
    commands.Cog,
    name="ModTracker",
    description="Owner-only: DMs a report of mod action counts and message activity.",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot
        # {user_id_str: {"category": int, "rest": int}}
        self.message_counts: dict[str, dict[str, int]] = self._load_counts()

    # ── Persistence ──────────────────────────────────────────────────────

    @staticmethod
    def _load_counts() -> dict[str, dict[str, int]]:
        with shelve.open(SHELVE_FILE) as sh:
            return sh.get(SHELVE_KEY, {})

    def _save_counts(self) -> None:
        with shelve.open(SHELVE_FILE) as sh:
            sh[SHELVE_KEY] = self.message_counts

    # ── Live message tracking (forward-only, see note in chat) ─────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        if not isinstance(message.author, discord.Member):
            return
        if not any(r.id == MOD_ROLE_ID for r in message.author.roles):
            return

        key = str(message.author.id)
        bucket = "category" if (
            message.channel.category_id == TRACKED_CATEGORY_ID
        ) else "rest"

        entry = self.message_counts.setdefault(key, {"category": 0, "rest": 0})
        entry[bucket] += 1
        self._save_counts()

    # ── Data gathering ───────────────────────────────────────────────────

    @staticmethod
    def _query_case_actions() -> dict[int, dict[str, object]]:
        """Returns {moderator_id: {"counts": {case_type: n}, "last": (type, iso_ts)}}"""
        result: dict[int, dict[str, object]] = {}
        if not os.path.exists(_CASE_DB):
            return result

        conn = sqlite3.connect(_CASE_DB)
        try:
            rows = conn.execute(
                "SELECT moderator_id, case_type, created_at FROM cases ORDER BY created_at ASC"
            ).fetchall()
        finally:
            conn.close()

        for moderator_id, case_type, created_at in rows:
            entry = result.setdefault(moderator_id, {"counts": defaultdict(int), "last": None})
            entry["counts"][case_type] += 1
            entry["last"] = (case_type, created_at)  # rows are ascending, so last write wins
        return result

    @staticmethod
    def _query_warn_actions() -> dict[int, dict[str, object]]:
        result: dict[int, dict[str, object]] = {}
        if not os.path.exists(_WARNINGS_DB):
            return result

        conn = sqlite3.connect(_WARNINGS_DB)
        try:
            rows = conn.execute(
                "SELECT moderator_id, warned_at FROM warnings ORDER BY warned_at ASC"
            ).fetchall()
        finally:
            conn.close()

        for moderator_id, warned_at in rows:
            entry = result.setdefault(moderator_id, {"counts": defaultdict(int), "last": None})
            entry["counts"]["warn"] += 1
            entry["last"] = ("warn", warned_at)
        return result

    def _build_report_embeds(self) -> list[discord.Embed]:
        case_data = self._query_case_actions()
        warn_data = self._query_warn_actions()

        all_mod_ids = set(case_data) | set(warn_data) | {int(k) for k in self.message_counts}

        embed = discord.Embed(
            title="Mod Activity Report",
            description=(
                "Action counts are retroactive. Message counts only cover "
                "activity since this tracker went live."
            ),
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )

        if not all_mod_ids:
            embed.description += "\n\nNo mod activity found yet."
            return [embed]

        # Rank by total logged actions, most active first.
        rows: list[tuple[int, str, str, str]] = []
        for mod_id in all_mod_ids:
            counts: defaultdict[str, int] = defaultdict(int)
            last: tuple[str, str] | None = None
            for source in (case_data.get(mod_id), warn_data.get(mod_id)):
                if source is None:
                    continue
                for k, v in source["counts"].items():
                    counts[k] += v
                if source["last"] is not None:
                    if last is None or source["last"][1] > last[1]:
                        last = source["last"]

            total = sum(counts.values())
            action_summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items())) or "no logged actions"

            last_summary = "none"
            if last is not None:
                action_type, raw_ts = last
                try:
                    unix_ts = int(datetime.fromisoformat(raw_ts).timestamp())
                    last_summary = f"{action_type} <t:{unix_ts}:R>"
                except ValueError:
                    last_summary = f"{action_type} at {raw_ts}"

            msg_entry = self.message_counts.get(str(mod_id), {"category": 0, "rest": 0})
            msg_total = msg_entry.get("category", 0) + msg_entry.get("rest", 0)
            msg_summary = (
                f"{msg_entry.get('category', 0)} in category, {msg_entry.get('rest', 0)} elsewhere"
                if msg_total
                else "none tracked yet"
            )

            user = self.bot.get_user(mod_id)
            display = f"{user}" if user else f"User ID {mod_id}"

            field_value = f"{action_summary}\nLast: {last_summary}\nMessages: {msg_summary}"
            rows.append((total, display, str(mod_id), field_value))

        rows.sort(key=lambda r: r[0], reverse=True)

        embeds = [embed]
        current = embed
        field_count = 0
        for _total, display, mod_id, field_value in rows:
            if field_count >= 25:
                current = discord.Embed(color=discord.Color.blurple())
                embeds.append(current)
                field_count = 0
            current.add_field(name=f"{display} ({mod_id})", value=field_value, inline=False)
            field_count += 1

        return embeds

    # ── Command ──────────────────────────────────────────────────────────

    @commands.command(name="modtracker")
    @commands.is_owner()
    async def modtracker(self, ctx: Context):
        """Owner only. DMs a report of mod action and message activity."""
        embeds = self._build_report_embeds()

        # Delete the invoking message first regardless of DM outcome — it
        # should never sit visible in-channel either way.
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

        try:
            # Discord allows up to 10 embeds per message.
            for i in range(0, len(embeds), 10):
                await ctx.author.send(embeds=embeds[i : i + 10])
        except (discord.Forbidden, discord.HTTPException):
            # No ephemeral option exists for a prefix-only command, and this
            # command must not surface anything in-channel — so a failed DM
            # just fails silently.
            pass