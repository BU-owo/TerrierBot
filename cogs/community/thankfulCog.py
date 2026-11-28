from __future__ import annotations

import asyncio
import csv
import io
import logging
import os
import re
import random
import shelve
import time
import xml.etree.ElementTree as ET
import zipfile
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

# The form is closed: /thankyou is gone and the button on old embeds says so.
CLOSED_MESSAGE = (
    "Terrier Hub Thanksgiving is over! If you have more thanks to give, "
    "you should reach out to the person directly!"
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

# ── Releasing the thank-yous (/reviewreleasethankyous, /releasethankyous) ─────
# Cleaned-up spreadsheet of submissions. Columns are found by header name, so
# order and extra columns don't matter: "User ID", "Message", "From".
RELEASE_XLSX = "data/2026 Who are you thankful for_ (Responses) (1).xlsx"
# {str(user_id): "ISO timestamp"} — recipients already DMed, so a re-run
# (after a crash or fixing a failed row) never sends anyone a duplicate.
RELEASED_KEY = "thankful_released"
DM_CHAR_LIMIT = 2000
# Pause between recipients to stay well clear of Discord's DM rate limits.
RELEASE_DELAY_SECONDS = 1.5

RELEASE_HEADER = (
    "## You are appreciated! ❤️\n"
    "The Terrier Hub Discord Server has done an exercise in thankfulness where folks write a "
    "message saying why they are thankful to someone! Here are the messages for you, <@{user_id}>!"
)
RELEASE_FOOTER = "### Happy Thanksgiving!"


async def setup(bot: TerrierBot):
    # Persistent view so the button on old /thankyou embeds still answers (with
    # CLOSED_MESSAGE) after restarts.
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

        # Only reachable from a form opened before it closed; still saved.
        await interaction.response.send_message(CLOSED_MESSAGE, ephemeral=True)

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
        await interaction.response.send_message(CLOSED_MESSAGE, ephemeral=True)


# ── Release helpers ───────────────────────────────────────────────────────────

_XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _read_xlsx(path: str) -> list[dict[str, str]]:
    """Rows of the first sheet as {header: value}, using only the stdlib (an
    .xlsx is a zip of XML). The first row is the header row."""
    with zipfile.ZipFile(path) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{_XLSX_NS}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{_XLSX_NS}t")))
        sheet = sorted(n for n in z.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))[0]
        root = ET.fromstring(z.read(sheet))

    grid: list[dict[str, str]] = []
    for row in root.iter(f"{_XLSX_NS}row"):
        cells: dict[str, str] = {"_row": row.get("r", "?")}
        for c in row.iter(f"{_XLSX_NS}c"):
            col = re.match(r"[A-Z]+", c.get("r", "")).group()  # type: ignore[union-attr]
            kind = c.get("t")
            v = c.find(f"{_XLSX_NS}v")
            if kind == "s" and v is not None and v.text is not None:
                cells[col] = shared[int(v.text)]
            elif kind == "inlineStr":
                cells[col] = "".join(t.text or "" for t in c.iter(f"{_XLSX_NS}t"))
            else:
                cells[col] = (v.text or "") if v is not None else ""
        grid.append(cells)
    if not grid:
        return []

    header = {col: name.strip() for col, name in grid[0].items() if col != "_row"}
    return [{"_row": r["_row"], **{header[c]: v for c, v in r.items() if c in header}} for r in grid[1:]]


class ThankYouNote:
    __slots__ = ("message", "sender", "row")

    def __init__(self, message: str, sender: str, row: str):
        self.message = message
        self.sender = sender
        self.row = row


def load_thankyous() -> tuple[dict[int, list[ThankYouNote]], list[str]]:
    """Notes grouped by recipient ID (sheet order kept), plus warnings about
    rows that were skipped."""
    rows = _read_xlsx(RELEASE_XLSX)
    grouped: dict[int, list[ThankYouNote]] = {}
    warnings: list[str] = []
    for r in rows:
        uid = (r.get("User ID") or "").strip()
        message = (r.get("Message") or "").strip()
        sender = (r.get("From") or "").strip() or "Anonymous"
        if not uid and not message:
            continue  # blank row
        if not re.fullmatch(r"\d{17,20}", uid):
            what = f"`{uid}`" if uid else "no User ID"
            warnings.append(f"Row {r['_row']}: skipped, {what} (to {r.get('Name', '?')!r})")
            continue
        if not message:
            warnings.append(f"Row {r['_row']}: skipped, empty message")
            continue
        grouped.setdefault(int(uid), []).append(ThankYouNote(message, sender, r["_row"]))
    return grouped, warnings


def _escape(text: str) -> str:
    """Neutralise markdown (*, _, ~, |, `, leading #/-/>) and @everyone/<@id>
    pings so whatever people typed shows up exactly as written."""
    return discord.utils.escape_mentions(discord.utils.escape_markdown(text))


def _quote_note(note: ThankYouNote) -> list[str]:
    """One note as block-quote lines: `> line`, signed ` -From` on the last line.

    Every line gets its own `> ` instead of one `>>> `: a `>>> ` quote runs to the
    end of the message, so a second note would render as literal `>>>` text,
    and per-line quotes still look right when a long DM is split in two."""
    lines: list[str] = []
    for raw in note.message.splitlines():
        line = raw.strip()
        if not line and (not lines or not lines[-1]):
            continue  # collapse runs of blank lines
        lines.append(_escape(line))
    while lines and not lines[-1]:
        lines.pop()
    lines[-1] += f" -{_escape(note.sender)}"
    # A bare ">" ends the quote, so blank lines get a zero-width space.
    return [f"> {line}" if line else "> ​" for line in lines]


def _split_long_line(line: str, limit: int) -> list[str]:
    """Hard-wrap a single quote line that alone exceeds the limit."""
    pieces: list[str] = []
    while len(line) > limit:
        cut = line.rfind(" ", 0, limit)
        if cut <= 2:
            cut = limit
        pieces.append(line[:cut])
        line = "> " + line[cut:].lstrip()
    pieces.append(line)
    return pieces


def render_thankyou_dms(user_id: int, notes: list[ThankYouNote]) -> list[str]:
    """The DM text for one recipient, split into messages of at most 2000 chars
    (only ever between lines, never mid-word unless a line is huge)."""
    parts: list[list[str]] = [RELEASE_HEADER.format(user_id=user_id).split("\n")]
    parts += [_quote_note(n) for n in notes]
    parts.append([RELEASE_FOOTER])

    messages: list[str] = []
    current = ""

    def add(text: str, sep: str) -> None:
        nonlocal current
        if current and len(current) + len(sep) + len(text) <= DM_CHAR_LIMIT:
            current += sep + text
        else:
            if current:
                messages.append(current)
            current = text

    for part in parts:
        block = "\n".join(part)
        if len(block) <= DM_CHAR_LIMIT:
            add(block, "\n\n")
            continue
        # A single note too long for one DM: add it line by line.
        first = True
        for line in part:
            for piece in _split_long_line(line, DM_CHAR_LIMIT):
                add(piece, "\n\n" if first else "\n")
                first = False
    if current:
        messages.append(current)
    return messages


def _load_released() -> dict[str, str]:
    with shelve.open(SHELVE_FILE) as sh:
        return dict(sh.get(RELEASED_KEY, {}))


def _mark_released(user_id: int) -> None:
    with shelve.open(SHELVE_FILE) as sh:
        released: dict[str, str] = sh.get(RELEASED_KEY, {})
        released[str(user_id)] = datetime.now(EASTERN).isoformat(timespec="seconds")
        sh[RELEASED_KEY] = released


class ConfirmReleaseView(discord.ui.View):
    def __init__(self, invoker_id: int):
        super().__init__(timeout=120)
        self.invoker_id = invoker_id
        self.confirmed: bool | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.invoker_id

    @discord.ui.button(label="Send the DMs", style=discord.ButtonStyle.danger, emoji="💌")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[type-arg]
        self.confirmed = True
        await interaction.response.edit_message(content="Sending… I'll post a summary here when done.", view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[type-arg]
        self.confirmed = False
        await interaction.response.edit_message(content="Cancelled — nothing was sent.", view=None)
        self.stop()


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
        self._release_lock = asyncio.Lock()
        with shelve.open(SHELVE_FILE) as sh:
            self.nudged: dict[str, str] = sh.get(NUDGED_KEY, {})

    def _save(self) -> None:
        with shelve.open(SHELVE_FILE) as sh:
            sh[NUDGED_KEY] = self.nudged

    async def _resolve_user(self, user_id: int) -> discord.User | None:
        user = self.bot.get_user(user_id)
        if user is not None:
            return user
        try:
            return await self.bot.fetch_user(user_id)
        except discord.HTTPException:
            return None

    def _load_or_error(self) -> tuple[dict[int, list[ThankYouNote]], list[str]] | str:
        try:
            return load_thankyous()
        except FileNotFoundError:
            return f"Couldn't find `{RELEASE_XLSX}`."
        except Exception as e:
            logging.exception("thankfulCog: failed to read %s", RELEASE_XLSX)
            return f"Couldn't read `{RELEASE_XLSX}`: {e}"

    @app_commands.command(
        name="reviewreleasethankyous",
        description="Preview every thank-you DM and who it goes to (nothing is sent).",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def reviewreleasethankyous(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        loaded = self._load_or_error()
        if isinstance(loaded, str):
            await interaction.followup.send(loaded, ephemeral=True)
            return
        grouped, warnings = loaded
        released = _load_released()
        guild = interaction.guild

        out = io.StringIO()
        problems: list[str] = list(warnings)
        total_dms = 0
        for uid, notes in grouped.items():
            dms = render_thankyou_dms(uid, notes)
            total_dms += len(dms)
            user = await self._resolve_user(uid)
            label = f"@{user.name}" if user else "UNKNOWN USER"
            flags: list[str] = []
            if user is None:
                flags.append("no Discord account with this ID")
            elif user.bot:
                flags.append("is a bot, can't be DMed")
            elif guild is not None and guild.get_member(uid) is None:
                flags.append("not in this server, DM will likely fail")
            if str(uid) in released:
                flags.append(f"ALREADY SENT {released[str(uid)]}, will be skipped")
            if flags:
                problems.append(f"{label} ({uid}): " + "; ".join(flags))

            out.write(f"{'=' * 72}\nTO: {label} ({uid}) | {len(notes)} note(s) from rows "
                      f"{', '.join(n.row for n in notes)} | {len(dms)} DM(s)\n")
            if flags:
                out.write("!! " + "; ".join(flags) + "\n")
            out.write(f"{'=' * 72}\n")
            for i, dm in enumerate(dms, 1):
                if len(dms) > 1:
                    out.write(f"--- DM {i}/{len(dms)} ({len(dm)} chars) ---\n")
                out.write(dm + "\n\n")

        notes_total = sum(len(n) for n in grouped.values())
        summary = (
            f"**{len(grouped)}** recipients, **{notes_total}** notes, **{total_dms}** DMs total. "
            f"{len(released)} already sent.\nFull preview of every DM is attached."
        )
        if problems:
            listing = "\n".join(f"• {_escape(p)}" for p in problems)
            summary += f"\n\n**Heads up:**\n{listing}"
        if len(summary) > DM_CHAR_LIMIT:
            summary = summary[: DM_CHAR_LIMIT - 30] + "\n… (see the file)"
            out.write("\n\nHEADS UP\n" + "\n".join(problems) + "\n")
        file = discord.File(io.BytesIO(out.getvalue().encode("utf-8-sig")), filename="thankyou_preview.txt")
        await interaction.followup.send(summary, file=file, ephemeral=True)

    @app_commands.command(
        name="releasethankyous",
        description="DM every thank-you recipient their messages. Asks for confirmation first.",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def releasethankyous(self, interaction: discord.Interaction) -> None:
        if self._release_lock.locked():
            await interaction.response.send_message("A release is already running.", ephemeral=True)
            return
        loaded = self._load_or_error()
        if isinstance(loaded, str):
            await interaction.response.send_message(loaded, ephemeral=True)
            return
        grouped, warnings = loaded
        released = _load_released()
        pending = {uid: notes for uid, notes in grouped.items() if str(uid) not in released}
        if not pending:
            await interaction.response.send_message(
                f"Everyone in the sheet ({len(grouped)}) has already been sent their thank-yous.", ephemeral=True
            )
            return

        view = ConfirmReleaseView(interaction.user.id)
        skipped = f" {len(warnings)} sheet row(s) will be skipped." if warnings else ""
        await interaction.response.send_message(
            f"This DMs **{len(pending)}** people ({len(grouped) - len(pending)} already sent).{skipped}\n"
            "Run `/reviewreleasethankyous` first if you haven't. Send now?",
            view=view,
            ephemeral=True,
        )
        await view.wait()
        if not view.confirmed:
            if view.confirmed is None:
                await interaction.edit_original_response(content="Timed out — nothing was sent.", view=None)
            return

        async with self._release_lock:
            sent: list[str] = []
            failed: list[str] = []
            for uid, notes in pending.items():
                if str(uid) in _load_released():
                    continue
                user = await self._resolve_user(uid)
                if user is None:
                    failed.append(f"{uid}: no account with this ID")
                    continue
                if user.bot:
                    failed.append(f"@{user.name}: is a bot")
                    continue
                dms = render_thankyou_dms(uid, notes)
                delivered = 0
                try:
                    for dm in dms:
                        await user.send(dm, allowed_mentions=discord.AllowedMentions.none())
                        delivered += 1
                except discord.Forbidden:
                    failed.append(f"@{user.name}: DMs closed or blocked the bot")
                except discord.HTTPException as e:
                    failed.append(f"@{user.name}: {e}")
                if delivered:
                    # Even a partial send counts, so a re-run never repeats DM 1.
                    _mark_released(uid)
                    sent.append(f"@{user.name}" + (f" (only {delivered}/{len(dms)} DMs)" if delivered < len(dms) else ""))
                await asyncio.sleep(RELEASE_DELAY_SECONDS)

        report = f"✅ Sent to **{len(sent)}** people."
        if failed:
            report += f"\n❌ **{len(failed)}** failed (fix and re-run to retry just those):\n" + "\n".join(
                f"• {_escape(f)}" for f in failed
            )
        partial = [s for s in sent if "only" in s]
        if partial:
            report += "\n⚠️ Partially sent (won't be retried):\n" + "\n".join(f"• {_escape(p)}" for p in partial)
        await interaction.followup.send(report[:DM_CHAR_LIMIT], ephemeral=True)

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
        try:
            await message.reply(
                f"{text}\n{NUDGE_FOOTER}",
                view=ThankfulView(),
                mention_author=False,
                allowed_mentions=discord.AllowedMentions(users=[message.author], everyone=False, roles=False),
            )
        except discord.HTTPException:
            return

        self.channel_last_nudge[channel_id] = now
        self.recent.pop(uid, None)
        self.nudged[str(uid)] = today
        self._save()
