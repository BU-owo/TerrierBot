from __future__ import annotations

import asyncio
import csv
import io
import logging
import os
import random
import shelve
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

from bot import TerrierBot
from ..logging.logConfig import MAIN_GUILD_ID

EASTERN = ZoneInfo("America/New_York")

# Thanksgiving week 2026: Tue 11/24 through Fri 11/27 at noon ET. Outside this
# window the nudges do nothing. The form itself has no limit or timer.
EVENT_START = datetime(2026, 11, 24, 0, 0, tzinfo=EASTERN)
EVENT_END = datetime(2026, 11, 27, 12, 0, tzinfo=EASTERN)

# Fallback for nudges until /thankyou has posted the Discord form somewhere.
FORM_URL = "https://forms.gle/9XaRheMvQqjWujHp6"

# "Very active" = this many messages within this many seconds.
ACTIVE_MESSAGE_COUNT = 10
ACTIVE_WINDOW_SECONDS = 10 * 60
# Don't nudge the same channel more often than this.
CHANNEL_COOLDOWN_SECONDS = 5 * 60

# Mod / logs category — never nudge there.
EXCLUDED_CATEGORY_IDS = frozenset({1441884565873496177})

SHELVE_FILE = "terrierbot.shelve"
# {str(user_id): "YYYY-MM-DD"} — the ET date each member was last nudged.
NUDGED_KEY = "thankful_nudged"
# list[dict] — every form submission (see ThankfulModal.on_submit).
SUBMISSIONS_KEY = "thankful_submissions"
# str — jump URL of the most recent /thankyou embed, used by the nudges.
EMBED_URL_KEY = "thankful_embed_url"

# ── Google Sheets (optional) ──────────────────────────────────────────────────
# Each submission is appended to the response sheet of the old Google Form so
# everything lives in one place. Turns on automatically once the service
# account key exists and the sheet is shared with it as Editor; until then
# submissions are only kept in the shelve (export with /thankfulexport).
SHEETS_CREDS_FILE = "sheets_service_account.json"  # gitignored
SHEET_ID = "1R7EhJO9IJS74jBakCgquh32AOTNqxIWl82pU2VTGwV0"
SHEET_RANGE = "'Form Responses 1'!A:D"
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

CSV_HEADER = [
    "Timestamp",
    "Their Name (make it so that I can figure out who they are please!)",
    "Tell them why you are thankful for them <3",
    'Your Sign Off / Name (leave blank for "Anonymous")',
]

THANKFUL_COLOR = discord.Color.from_rgb(230, 126, 34)

EMBED_TITLE = "Who are YOU thankful for? 🦃"
EMBED_DESCRIPTION = (
    "**Happy Thanksgiving Week!** To celebrate the day of thankfulness, I invite you to "
    "participate in this exercise to reflect on what others have done for you.\n\n"
    "Has someone helped you with something, answered your questions, spent time with you, "
    "been your friend, encouraged you, been a positive presence, supported you, or anything "
    "else? **Please acknowledge them!**\n\n"
    "These will be shared with the individuals via Discord the day after Thanksgiving <3"
)

SUBMITTED_MESSAGE = (
    "## THANK YOU for being thankful! 🧡\n"
    "Is there anyone else who's made your semester better? There's **no limit** and **no timer**, "
    "so thank as many people as you want! 🦃🍂🥧"
)

# (message, weight) — {name} is replaced with the member's mention. Higher
# weight = picked more often; "I am so thankful..." is the favorite.
NUDGES: list[tuple[str, int]] = [
    ("Wow, {name}, you're talking a lot in the server, but have you expressed your gratitude toward others?", 1),
    ("Holy yap {name}, can you yap your thanks instead?", 1),
    ("I am so thankful that you are active in chat, {name}! Who are you thankful for?", 4),
    ("You {name}, have you done your thank you messages yet?", 1),
    ("Lots to discuss right now {name}, but let's do a quick thank you first!", 1),
    ("Hey {name}! Express your gratitude by sending a message here!", 1),
]
NUDGE_FOOTER = "🦃🧡🍂🥧💛"


async def setup(bot: TerrierBot):
    # Persistent view so the button on old /thankyou embeds survives restarts.
    bot.add_view(ThankfulView())
    await bot.add_cog(ThankfulCog(bot))


# ── Google Sheets helpers ─────────────────────────────────────────────────────

_sheets_service: Any = None
_sheets_unavailable_logged = False


def _append_to_sheet_blocking(row: list[str]) -> bool:
    """Blocking Sheets API call — run via asyncio.to_thread. Returns True if
    the row was appended. Never raises."""
    global _sheets_service, _sheets_unavailable_logged
    try:
        if _sheets_service is None:
            if not os.path.exists(SHEETS_CREDS_FILE):
                if not _sheets_unavailable_logged:
                    logging.warning("thankfulCog: %s not found; submissions saved locally only", SHEETS_CREDS_FILE)
                    _sheets_unavailable_logged = True
                return False
            # Imported lazily so the cog still loads without the Google libs.
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            credentials = service_account.Credentials.from_service_account_file(  # pyright: ignore[reportUnknownMemberType]
                SHEETS_CREDS_FILE, scopes=SHEETS_SCOPES
            )
            _sheets_service = build("sheets", "v4", credentials=credentials, cache_discovery=False)

        _sheets_service.spreadsheets().values().append(
            spreadsheetId=SHEET_ID,
            range=SHEET_RANGE,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()
        return True
    except Exception:
        logging.exception("thankfulCog: failed to append submission to Google Sheet")
        return False


def _submission_row(sub: dict[str, Any]) -> list[str]:
    return [sub["ts"], sub["name"], sub["message"], sub["sign_off"]]


# ── Form UI ───────────────────────────────────────────────────────────────────


class ThankfulModal(discord.ui.Modal, title="Who are YOU thankful for? 🦃"):
    their_name = discord.ui.TextInput(
        label="Their Name",
        placeholder="Make it so we can figure out who they are!",
        max_length=100,
        required=True,
    )
    message = discord.ui.TextInput(
        label="Tell them why you are thankful for them <3",
        style=discord.TextStyle.paragraph,
        placeholder="They helped me with..., they're always..., I'm grateful that...",
        max_length=2000,
        required=True,
    )
    sign_off = discord.ui.TextInput(
        label="Your Sign Off / Name",
        placeholder='Leave blank for "Anonymous"',
        max_length=100,
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        sub: dict[str, Any] = {
            "ts": datetime.now(EASTERN).strftime("%m/%d/%Y %H:%M:%S"),
            "name": self.their_name.value.strip(),
            "message": self.message.value.strip(),
            "sign_off": self.sign_off.value.strip() or "Anonymous",
            "user_id": interaction.user.id,
            "synced": False,
        }
        with shelve.open(SHELVE_FILE) as sh:
            subs: list[dict[str, Any]] = sh.get(SUBMISSIONS_KEY, [])
            subs.append(sub)
            sh[SUBMISSIONS_KEY] = subs

        await interaction.response.send_message(SUBMITTED_MESSAGE, view=ThankfulView(), ephemeral=True)

        if await asyncio.to_thread(_append_to_sheet_blocking, _submission_row(sub)):
            with shelve.open(SHELVE_FILE) as sh:
                subs = sh.get(SUBMISSIONS_KEY, [])
                # Re-find it by content in case the list changed meanwhile.
                for s in subs:
                    if s["user_id"] == sub["user_id"] and s["ts"] == sub["ts"] and s["message"] == sub["message"]:
                        s["synced"] = True
                        sh[SUBMISSIONS_KEY] = subs
                        break

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        logging.exception("thankfulCog: modal submit failed", exc_info=error)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "Something went wrong saving that — please try again!", ephemeral=True
            )


class ThankfulView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Write a Thank You",
        emoji="💌",
        style=discord.ButtonStyle.primary,
        custom_id="thankfulcog:write",
    )
    async def write_button(
        self, interaction: discord.Interaction, button: discord.ui.Button  # type: ignore[type-arg]
    ) -> None:
        await interaction.response.send_modal(ThankfulModal())


# ── Cog ───────────────────────────────────────────────────────────────────────


class ThankfulCog(
    commands.Cog,
    name="Thankful",
    description="Thanksgiving week: a Discord thank-you form (/thankyou) plus nudges for very active chatters.",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot
        self.recent: defaultdict[int, deque[float]] = defaultdict(deque)
        self.channel_last_nudge: dict[int, float] = {}
        with shelve.open(SHELVE_FILE) as sh:
            self.nudged: dict[str, str] = sh.get(NUDGED_KEY, {})
            self.embed_url: str | None = sh.get(EMBED_URL_KEY)

    def _save(self) -> None:
        with shelve.open(SHELVE_FILE) as sh:
            sh[NUDGED_KEY] = self.nudged

    @app_commands.command(name="thankyou", description="Post the Thanksgiving thank-you form in this channel.")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def thankyou(self, interaction: discord.Interaction) -> None:
        channel = interaction.channel
        if not isinstance(channel, discord.abc.Messageable):
            await interaction.response.send_message("I can't post here.", ephemeral=True)
            return

        embed = discord.Embed(title=EMBED_TITLE, description=EMBED_DESCRIPTION, color=THANKFUL_COLOR)
        embed.set_footer(text=NUDGE_FOOTER)
        try:
            msg = await channel.send(embed=embed, view=ThankfulView())
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Couldn't post the form: {e}", ephemeral=True)
            return

        self.embed_url = msg.jump_url
        with shelve.open(SHELVE_FILE) as sh:
            sh[EMBED_URL_KEY] = msg.jump_url
        await interaction.response.send_message("Posted the thank-you form ✅", ephemeral=True)

    @app_commands.command(name="thankfulexport", description="Download every thank-you form submission as a CSV.")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def thankfulexport(self, interaction: discord.Interaction) -> None:
        with shelve.open(SHELVE_FILE) as sh:
            subs: list[dict[str, Any]] = sh.get(SUBMISSIONS_KEY, [])
        if not subs:
            await interaction.response.send_message("No thank-you submissions yet.", ephemeral=True)
            return

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(CSV_HEADER)
        writer.writerows(_submission_row(s) for s in subs)
        file = discord.File(io.BytesIO(buf.getvalue().encode("utf-8-sig")), filename="thankful_submissions.csv")

        unsynced = sum(1 for s in subs if not s.get("synced"))
        note = f"{len(subs)} submission(s)."
        if unsynced:
            note += f" {unsynced} of them aren't in the Google Sheet yet."
        await interaction.response.send_message(note, file=file, ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.guild.id != MAIN_GUILD_ID:
            return
        if message.author.bot or message.webhook_id is not None:
            return
        now_et = datetime.now(EASTERN)
        if not (EVENT_START <= now_et < EVENT_END):
            return
        if getattr(message.channel, "category_id", None) in EXCLUDED_CATEGORY_IDS:
            return

        uid = message.author.id
        today = now_et.strftime("%Y-%m-%d")
        if self.nudged.get(str(uid)) == today:
            return

        now = time.monotonic()
        stamps = self.recent[uid]
        stamps.append(now)
        while stamps and now - stamps[0] > ACTIVE_WINDOW_SECONDS:
            stamps.popleft()
        if len(stamps) < ACTIVE_MESSAGE_COUNT:
            return

        channel_id = message.channel.id
        if now - self.channel_last_nudge.get(channel_id, -CHANNEL_COOLDOWN_SECONDS) < CHANNEL_COOLDOWN_SECONDS:
            return

        texts, weights = zip(*NUDGES)
        text = random.choices(texts, weights=weights)[0].format(name=message.author.mention)
        link = self.embed_url or FORM_URL
        try:
            await message.reply(
                f"{text}\n## [Write a Thank You Message]({link})\n{NUDGE_FOOTER}",
                mention_author=False,
                allowed_mentions=discord.AllowedMentions(users=[message.author], everyone=False, roles=False),
            )
        except discord.HTTPException:
            return

        self.channel_last_nudge[channel_id] = now
        self.recent.pop(uid, None)
        self.nudged[str(uid)] = today
        self._save()
