from __future__ import annotations

import asyncio
import json
import logging
import os

import discord
from discord.ext import commands, tasks
from google.oauth2 import service_account
from googleapiclient.discovery import build

from bot import TerrierBot
from .logConfig import LogChannels, LogColors, MOD_ROLE_ID, get_log_channel

# ── Google Sheets config ──────────────────────────────────────────────────────
# Read-only service account, credentials pre-provisioned on the host (not in
# the repo — see .gitignore). Sheet is the response sheet for the ban-appeal
# Google Form.
_CREDENTIALS_PATH = "/home/ubuntu/TerrierBot/sheets_service_account.json"
_SHEET_ID = "1k6U7okdgCwH9Le2sMu1DxEPhcyumQRIRLGZlsKpzjl0"
_SHEET_RANGE = "A:Z"
_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Exact header text for each column this cog cares about — matched against
# row 1 rather than fixed column indices, since the form can grow new fields
# (in any position) without breaking this.
_COL_TIMESTAMP = "Timestamp"
_COL_USERNAME = "Discord Username"
_COL_WHY_BANNED = "Why do you think you were banned?"
_COL_WHY_RECONSIDER = "Why should we reconsider the ban?"
_COL_RULES_AGREEMENT = "Do you understand and agree to follow the server rules if unbanned?"
_REQUIRED_COLUMNS = (_COL_TIMESTAMP, _COL_USERNAME, _COL_WHY_BANNED, _COL_WHY_RECONSIDER, _COL_RULES_AGREEMENT)

# ── Seen-row persistence ──────────────────────────────────────────────────────
# Same standalone-gitignored-JSON pattern as BanCog's tempbans.json — a
# lightweight de-dupe set keyed on the row's Timestamp column (unique per
# form submission) doesn't need a database.
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_SEEN_FILE = os.path.join(_DATA_DIR, "appeal_form_seen.json")


async def setup(bot: TerrierBot):
    await bot.add_cog(AppealFormCog(bot))


class AppealFormCog(
    commands.Cog,
    name="AppealForm",
    description="Polls the ban-appeal Google Form's response sheet and posts new submissions to mod-log.",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot
        self.seen: set[str] = set(self.load_seen())
        self._poll_appeal_form.start()

    def cog_unload(self) -> None:
        self._poll_appeal_form.cancel()

    # ── Seen-row persistence ────────────────────────────────────────────────

    @staticmethod
    def load_seen() -> list[str]:
        if not os.path.exists(_SEEN_FILE):
            os.makedirs(_DATA_DIR, exist_ok=True)
            with open(_SEEN_FILE, "w", encoding="utf-8") as f:
                json.dump([], f)
            return []
        with open(_SEEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_seen(self) -> None:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(self.seen), f, indent=2)

    # ── Sheet reading ────────────────────────────────────────────────────────

    @staticmethod
    def _fetch_rows() -> list[list[str]]:
        """Blocking Google API call (google-api-python-client has no asyncio
        support) — always run this via asyncio.to_thread from the polling
        loop so it doesn't stall the event loop."""
        credentials = service_account.Credentials.from_service_account_file(
            _CREDENTIALS_PATH, scopes=_SCOPES
        )
        service = build("sheets", "v4", credentials=credentials)
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=_SHEET_ID, range=_SHEET_RANGE)
            .execute()
        )
        return result.get("values", [])

    # ── Polling loop ─────────────────────────────────────────────────────────

    @tasks.loop(minutes=5)
    async def _poll_appeal_form(self) -> None:
        try:
            rows = await asyncio.to_thread(self._fetch_rows)
        except Exception:
            logging.exception("Failed to read the ban-appeal Google Sheet")
            return

        if not rows:
            return

        header = rows[0]
        try:
            col_index = {name: header.index(name) for name in _REQUIRED_COLUMNS}
        except ValueError:
            logging.error("Ban-appeal sheet header row is missing an expected column: %s", header)
            return

        def cell(row: list[str], name: str) -> str:
            index = col_index[name]
            return row[index] if index < len(row) else ""

        new_rows = [row for row in rows[1:] if cell(row, _COL_TIMESTAMP) and cell(row, _COL_TIMESTAMP) not in self.seen]
        if not new_rows:
            return

        log_channel = get_log_channel(self.bot, LogChannels.MOD)
        if log_channel is None:
            return

        for row in new_rows:
            timestamp = cell(row, _COL_TIMESTAMP)

            embed = discord.Embed(
                title="📨 Ban appeal received",
                description=(
                    f"**Discord username:** {cell(row, _COL_USERNAME) or '*Not provided*'}\n\n"
                    f"**Why they think they were banned:**\n{cell(row, _COL_WHY_BANNED) or '*No answer*'}\n\n"
                    f"**Why the ban should be reconsidered:**\n{cell(row, _COL_WHY_RECONSIDER) or '*No answer*'}\n\n"
                    f"**Agrees to follow server rules if unbanned:** {cell(row, _COL_RULES_AGREEMENT) or '*No answer*'}"
                ),
                color=LogColors.MOD,
                timestamp=discord.utils.utcnow(),
            )
            embed.set_footer(text=f"Submitted: {timestamp}")

            try:
                await log_channel.send(
                    content=f"<@&{MOD_ROLE_ID}>",
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions(roles=True, users=False, everyone=False),
                )
            except discord.HTTPException:
                logging.exception("Failed to post ban-appeal form submission to mod-log")
                continue  # don't mark as seen — retry next tick

            self.seen.add(timestamp)
            self.save_seen()

    @_poll_appeal_form.before_loop
    async def _before_poll_appeal_form(self) -> None:
        await self.bot.wait_until_ready()
