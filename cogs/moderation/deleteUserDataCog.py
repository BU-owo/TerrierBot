from __future__ import annotations

import json
import os
import shelve
import sqlite3

import discord
from discord.ext import commands

from bot import Context, TerrierBot
from ..logging.logConfig import LogChannels, LogColors, get_log_channel

SHELVE_FILE = "terrierbot.shelve"

# Same external-data-dir convention as caseLogCog/warningsCog/modTrackerCog
# (see repo_overview.md §2) — both DBs live outside the repo.
_EXTERNAL_DATA_DIR = os.path.join(os.path.expanduser("~"), "terrierbot_data")
_CASE_DB = os.path.join(_EXTERNAL_DATA_DIR, "casedb.sqlite3")
_WARNINGS_DB = os.path.join(_EXTERNAL_DATA_DIR, "warnings.db")

# Repo-root data/ folder — banCog.py is the same three-folders-up path.
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
_TEMPBANS_FILE = os.path.join(_DATA_DIR, "tempbans.json")
_MODVOTES_FILE = os.path.join(_DATA_DIR, "modvotes.json")
_SOFTPINGS_FILE = os.path.join(_DATA_DIR, "softpings.json")


async def setup(bot: TerrierBot):
    await bot.add_cog(DeleteUserDataCog(bot))


class _ConfirmDeleteView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=30)
        self.owner_id = owner_id
        self.confirmed: bool | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This isn't your confirmation to click.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True  # type: ignore[attr-defined]

    @discord.ui.button(label="Delete everything", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.confirmed = True
        for child in self.children:
            child.disabled = True  # type: ignore[attr-defined]
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.confirmed = False
        for child in self.children:
            child.disabled = True  # type: ignore[attr-defined]
        await interaction.response.edit_message(content="Cancelled — nothing was deleted.", view=self)
        self.stop()


class DeleteUserDataCog(
    commands.Cog,
    name="DeleteUserData",
    description="Owner-only: permanently erases every stored record of a specific user across all of TerrierBot's data stores.",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot

    # ── Per-store scan/purge — each returns lines describing what it found.
    # With apply=False nothing is written; with apply=True the change is saved.

    def _handle_shelve(self, user_id: int, *, apply: bool) -> list[str]:
        uid_s = str(user_id)
        lines: list[str] = []
        with shelve.open(SHELVE_FILE) as sh:
            # {str(user_id): {...}} maps — drop the key outright.
            for key in ("birthdays", "lockins", "hardmutes", "modtracker_message_counts"):
                data = sh.get(key)
                if isinstance(data, dict) and uid_s in data:
                    lines.append(f"shelve[{key}]: 1 entry")
                    if apply:
                        del data[uid_s]
                        sh[key] = data

            # roleboost_assignments is {int(user_id): role_id}
            data = sh.get("roleboost_assignments")
            if isinstance(data, dict) and user_id in data:
                lines.append("shelve[roleboost_assignments]: 1 entry")
                if apply:
                    del data[user_id]
                    sh["roleboost_assignments"] = data

            # unserious_enabled is a set[int]
            data = sh.get("unserious_enabled")
            if isinstance(data, set) and user_id in data:
                lines.append("shelve[unserious_enabled]: membership")
                if apply:
                    data.discard(user_id)
                    sh["unserious_enabled"] = data

            # birthday_current_holders is a list[int]
            data = sh.get("birthday_current_holders")
            if isinstance(data, list) and user_id in data:
                lines.append("shelve[birthday_current_holders]: membership")
                if apply:
                    sh["birthday_current_holders"] = [u for u in data if u != user_id]

            # birthday_announced_today is {"date": ..., "user_ids": [int, ...]}
            data = sh.get("birthday_announced_today")
            if isinstance(data, dict) and user_id in data.get("user_ids", []):
                lines.append("shelve[birthday_announced_today]: membership")
                if apply:
                    data["user_ids"] = [u for u in data["user_ids"] if u != user_id]
                    sh["birthday_announced_today"] = data

            # positivity_recent_selected_by_guild is {int(guild_id): [int(user_id), ...]}
            data = sh.get("positivity_recent_selected_by_guild")
            if isinstance(data, dict):
                touched = False
                for guild_id, recent in data.items():
                    if isinstance(recent, list) and user_id in recent:
                        touched = True
                        if apply:
                            data[guild_id] = [u for u in recent if u != user_id]
                if touched:
                    lines.append("shelve[positivity_recent_selected_by_guild]: membership")
                    if apply:
                        sh["positivity_recent_selected_by_guild"] = data

            # starboard_* — nested {int(guild_id): {int(msg_id or user_id): ...}}
            authors = sh.get("starboard_message_authors")
            counts = sh.get("starboard_message_star_counts")
            posted = sh.get("starboard_posted_messages")
            totals = sh.get("starboard_user_star_totals")
            starboard_touched = 0

            if isinstance(authors, dict):
                for guild_id, guild_authors in authors.items():
                    if not isinstance(guild_authors, dict):
                        continue
                    dead_msg_ids = [mid for mid, aid in guild_authors.items() if aid == user_id]
                    for mid in dead_msg_ids:
                        starboard_touched += 1
                        if apply:
                            del guild_authors[mid]
                            if isinstance(counts, dict):
                                counts.get(guild_id, {}).pop(mid, None)
                            if isinstance(posted, dict):
                                posted.get(guild_id, {}).pop(mid, None)

            if isinstance(totals, dict):
                for guild_id, guild_totals in totals.items():
                    if isinstance(guild_totals, dict) and user_id in guild_totals:
                        starboard_touched += 1
                        if apply:
                            del guild_totals[user_id]

            if starboard_touched:
                lines.append(f"shelve[starboard_*]: {starboard_touched} entrie(s) (authored messages + star total)")
                if apply:
                    sh["starboard_message_authors"] = authors
                    sh["starboard_message_star_counts"] = counts
                    sh["starboard_posted_messages"] = posted
                    sh["starboard_user_star_totals"] = totals

        return lines

    def _handle_sqlite(self, db_path: str, table: str, user_id: int, *, apply: bool) -> list[str]:
        if not os.path.exists(db_path):
            return []
        conn = sqlite3.connect(db_path)
        try:
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE user_id = ? OR moderator_id = ?", (user_id, user_id)
            ).fetchone()[0]
            if count and apply:
                conn.execute(f"DELETE FROM {table} WHERE user_id = ? OR moderator_id = ?", (user_id, user_id))
                conn.commit()
        finally:
            conn.close()
        return [f"{os.path.basename(db_path)}[{table}]: {count} row(s)"] if count else []

    def _handle_tempbans(self, user_id: int, *, apply: bool) -> list[str]:
        if not os.path.exists(_TEMPBANS_FILE):
            return []
        with open(_TEMPBANS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        dead_keys = [k for k, v in data.items() if v.get("user_id") == user_id]
        if not dead_keys:
            return []
        if apply:
            for k in dead_keys:
                del data[k]
            with open(_TEMPBANS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        return [f"tempbans.json: {len(dead_keys)} entry(s)"]

    def _handle_modvotes(self, user_id: int, *, apply: bool) -> list[str]:
        if not os.path.exists(_MODVOTES_FILE):
            return []
        with open(_MODVOTES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        votes = data.get("votes", {})
        uid_s = str(user_id)
        touched = 0
        for vote in votes.values():
            if uid_s in vote.get("votes", {}):
                touched += 1
                if apply:
                    del vote["votes"][uid_s]
        if not touched:
            return []
        if apply:
            with open(_MODVOTES_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        return [f"modvotes.json: {touched} cast vote(s)"]

    def _handle_softpings(self, user_id: int, *, apply: bool) -> list[str]:
        if not os.path.exists(_SOFTPINGS_FILE):
            return []
        with open(_SOFTPINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        touched = 0
        for entry in data.values():
            members = entry.get("members", [])
            if user_id in members:
                touched += 1
                if apply:
                    entry["members"] = [m for m in members if m != user_id]
        if not touched:
            return []
        if apply:
            with open(_SOFTPINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        return [f"softpings.json: membership in {touched} list(s)"]

    def _run(self, user_id: int, *, apply: bool) -> list[str]:
        lines: list[str] = []
        lines += self._handle_shelve(user_id, apply=apply)
        lines += self._handle_sqlite(_CASE_DB, "cases", user_id, apply=apply)
        lines += self._handle_sqlite(_WARNINGS_DB, "warnings", user_id, apply=apply)
        lines += self._handle_tempbans(user_id, apply=apply)
        lines += self._handle_modvotes(user_id, apply=apply)
        lines += self._handle_softpings(user_id, apply=apply)
        return lines

    # ── Command ──────────────────────────────────────────────────────────

    @commands.command(name="deletealluserdata")
    @commands.is_owner()
    async def deletealluserdata(self, ctx: Context, user_id: int):
        """Owner only. Permanently erases every stored record of a user."""
        preview = self._run(user_id, apply=False)

        if not preview:
            await ctx.send(f"No stored data found for user ID `{user_id}` in any known data store.")
            return

        embed = discord.Embed(
            title="⚠️ Confirm permanent data deletion",
            description=f"About to permanently delete all stored data for `{user_id}`:\n\n"
            + "\n".join(f"• {line}" for line in preview)
            + "\n\n**This can't be undone.**",
            color=discord.Color.red(),
        )
        view = _ConfirmDeleteView(ctx.author.id)
        await ctx.send(embed=embed, view=view)
        await view.wait()

        if not view.confirmed:
            return

        deleted = self._run(user_id, apply=True)

        result_embed = discord.Embed(
            title="🗑️ User data deleted",
            description=f"**Target:** `{user_id}`\n**Deleted by:** {ctx.author.mention} (`{ctx.author.id}`)\n\n"
            + "\n".join(f"• {line}" for line in deleted),
            color=LogColors.MOD,
            timestamp=discord.utils.utcnow(),
        )
        await ctx.send(embed=result_embed)

        log_channel = get_log_channel(self.bot, LogChannels.MOD)
        if log_channel is not None:
            try:
                await log_channel.send(embed=result_embed, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                pass
