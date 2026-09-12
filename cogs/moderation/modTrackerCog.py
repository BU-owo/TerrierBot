from __future__ import annotations

import logging
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

    def _build_report(self) -> list[str]:
        case_data = self._query_case_actions()
        warn_data = self._query_warn_actions()

        all_mod_ids = set(case_data) | set(warn_data) | {int(k) for k in self.message_counts}

        if not all_mod_ids:
            return ["No mod activity found yet — no case log, warning, or message data."]

        lines: list[str] = []
        for mod_id in sorted(all_mod_ids):
            user = self.bot.get_user(mod_id)
            display = f"{user}" if user else f"User ID {mod_id}"

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

            action_summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items())) or "no logged actions"
            last_summary = f"{last[0]} at {last[1]}" if last else "none"

            msg_entry = self.message_counts.get(str(mod_id), {"category": 0, "rest": 0})

            lines.append(
                f"**{display}** (`{mod_id}`)\n"
                f"Actions: {action_summary}\n"
                f"Most recent action: {last_summary}\n"
                f"Messages — tracked category: {msg_entry.get('category', 0)}, "
                f"rest of server: {msg_entry.get('rest', 0)}\n"
            )
        return lines

    # ── Command ──────────────────────────────────────────────────────────

    @commands.command(name="modtracker")
    @commands.is_owner()
    async def modtracker(self, ctx: Context):
        """Owner only. DMs a report of mod action and message activity."""
        lines = self._build_report()

        header = (
            f"**Mod Activity Report** — generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
            f"Action counts are retroactive (from casedb.sqlite3 / warnings.db). "
            f"Message counts only cover activity since this tracker went live.\n\n"
        )

        chunks: list[str] = []
        current = header
        for line in lines:
            if len(current) + len(line) > 1900:
                chunks.append(current)
                current = ""
            current += line + "\n"
        if current:
            chunks.append(current)

        # Delete the invoking message first regardless of DM outcome — it
        # should never sit visible in-channel either way.
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

        try:
            for chunk in chunks:
                await ctx.author.send(chunk)
        except (discord.Forbidden, discord.HTTPException):
            # No ephemeral option exists for a prefix-only command, and this
            # command must not surface anything in-channel — so a failed DM
            # (e.g. DMs closed) just logs server-side instead.
            logging.warning("modtracker: failed to DM report to %s (%d)", ctx.author, ctx.author.id)
