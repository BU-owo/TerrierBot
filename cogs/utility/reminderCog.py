from __future__ import annotations

import logging
import re
import shelve
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

from bot import Context, TerrierBot

log = logging.getLogger(__name__)

SHELVE_FILE = "terrierbot.shelve"
SHELVE_KEY = "reminders"
EASTERN = ZoneInfo("America/New_York")  # handles EST/EDT automatically

MAX_PER_USER = 25
MAX_MESSAGE_LEN = 500
MAX_AHEAD = timedelta(days=3650)  # ~10 years
MIN_AHEAD_SECONDS = 5
TOO_FAR_MSG = "Dude... Terrier Hub will not survive that long"

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}

UNIT_SECONDS = {
    "w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1,
}

WHEN_HELP = (
    "**How to say when** (all dates/times are Eastern Time, EST/EDT):\n"
    "• **In X amount of time:** `30m`, `2h`, `1d 3h`, `in 2 hours 15 minutes`, `1 week`\n"
    "• **At a date/time:** `3pm` (next 3 PM), `tomorrow 9:30am`, `10/15 6pm`, "
    "`oct 15 6pm`, `2026-10-15 18:00`\n"
    "With `=reminder`, put the time in quotes if it has spaces: "
    "`=reminder \"tomorrow 9am\" submit the form`"
)

_RELATIVE_TOKEN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(weeks?|w|days?|d|hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)(?![a-z])"
)
_TIME = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b|\b(\d{1,2}):(\d{2})\b")


class ReminderParseError(ValueError):
    pass


def _parse_relative(text: str) -> timedelta | None:
    cleaned = re.sub(r"^in\s+", "", text).replace(",", " ").replace(" and ", " ").strip()
    if not cleaned:
        return None
    pos = 0
    total = 0.0
    for match in _RELATIVE_TOKEN.finditer(cleaned):
        if cleaned[pos:match.start()].strip():
            return None
        total += float(match.group(1)) * UNIT_SECONDS[match.group(2)[0]]
        pos = match.end()
    if pos == 0 or cleaned[pos:].strip():
        return None
    return timedelta(seconds=total)


def _parse_absolute(text: str, now: datetime) -> datetime:
    cleaned = re.sub(r"\b(est|edt|et|eastern)\b", " ", text)
    cleaned = re.sub(r"\b(at|on|of)\b", " ", cleaned).replace(",", " ")

    times = list(_TIME.finditer(cleaned))
    if not times:
        raise ReminderParseError("I couldn't find a time of day in that (like `3pm` or `15:30`).")
    tm = times[-1]
    if tm.group(3):
        hour, minute, meridiem = int(tm.group(1)), int(tm.group(2) or 0), tm.group(3)
        if not (1 <= hour <= 12):
            raise ReminderParseError("With am/pm, the hour has to be 1-12.")
        hour = hour % 12 + (12 if meridiem == "pm" else 0)
    else:
        hour, minute = int(tm.group(4)), int(tm.group(5))
    if hour > 23 or minute > 59:
        raise ReminderParseError("That isn't a valid time of day.")

    date_text = " ".join((cleaned[:tm.start()] + " " + cleaned[tm.end():]).split())

    explicit_year = True
    if date_text in ("", "today"):
        target = now.date()
        explicit_year = False
    elif date_text == "tomorrow":
        target = (now + timedelta(days=1)).date()
        explicit_year = False
    else:
        target = None
        m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", date_text)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            m = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2}|\d{4}))?", date_text)
            if m:
                mo, d = int(m.group(1)), int(m.group(2))
                y = int(m.group(3)) if m.group(3) else None
            else:
                m = re.fullmatch(r"([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+(\d{4}))?", date_text)
                if not m or m.group(1) not in MONTHS:
                    raise ReminderParseError(f"I couldn't understand the date \"{date_text}\".")
                mo, d = MONTHS[m.group(1)], int(m.group(2))
                y = int(m.group(3)) if m.group(3) else None
        if y is not None and y < 100:
            y += 2000
        explicit_year = y is not None
        try:
            target = datetime(y or now.year, mo, d, tzinfo=EASTERN).date()
        except ValueError:
            raise ReminderParseError("That date doesn't exist.") from None

    result = datetime(target.year, target.month, target.day, hour, minute, tzinfo=EASTERN)
    if result <= now:
        if date_text == "":
            result += timedelta(days=1)
        elif not explicit_year and date_text not in ("today", "tomorrow"):
            result = result.replace(year=result.year + 1)
        else:
            raise ReminderParseError("That time is already in the past.")
    return result


def parse_when(raw: str, now: datetime | None = None) -> datetime:
    """Turn user input into an aware datetime. Raises ReminderParseError."""
    now = (now or datetime.now(EASTERN)).astimezone(EASTERN)
    text = raw.strip().lower()
    if not text:
        raise ReminderParseError("Tell me when!")

    try:
        delta = _parse_relative(text)
        due = now + delta if delta is not None else _parse_absolute(text, now)
    except OverflowError:
        raise ReminderParseError(TOO_FAR_MSG) from None

    if (due - now).total_seconds() < MIN_AHEAD_SECONDS:
        raise ReminderParseError("That's too soon — pick at least a few seconds from now.")
    if due - now > MAX_AHEAD:
        raise ReminderParseError(TOO_FAR_MSG)
    return due


class ReminderCog(commands.Cog, name="Reminder", description="Set reminders that ping you in-channel and DM you."):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot
        self.reminders: list[dict] = []
        with shelve.open(SHELVE_FILE) as sh:
            self.reminders = sh.get(SHELVE_KEY, [])
        self.check_reminders.start()

    def cog_unload(self) -> None:
        self.check_reminders.cancel()

    def _save(self) -> None:
        with shelve.open(SHELVE_FILE) as sh:
            sh[SHELVE_KEY] = self.reminders

    # ---------- background task ----------

    @tasks.loop(seconds=15)
    async def check_reminders(self) -> None:
        now = time.time()
        due = [r for r in self.reminders if r["due"] <= now]
        if not due:
            return
        # Drop (and persist) first so a crash mid-send can't re-fire everything.
        self.reminders = [r for r in self.reminders if r["due"] > now]
        self._save()
        for reminder in due:
            try:
                await self._fire(reminder, now)
            except Exception:
                log.exception("reminderCog: failed to deliver reminder %s", reminder.get("id"))

    @check_reminders.before_loop
    async def before_check_reminders(self) -> None:
        await self.bot.wait_until_ready()

    async def _fire(self, reminder: dict, now: float) -> None:
        user_id: int = reminder["user_id"]
        created = int(reminder["created"])
        late = now - reminder["due"] > 120
        body = (
            f"⏰ **Reminder:** {reminder['message']}\n"
            f"-# Set <t:{created}:R>" + (" · delivered late (the bot was offline)" if late else "")
        )

        user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
        channel = self.bot.get_channel(reminder["channel_id"])
        in_dm = isinstance(channel, discord.DMChannel)

        if channel is not None and not in_dm and isinstance(channel, discord.abc.Messageable):
            try:
                await channel.send(
                    f"{user.mention} {body}",
                    allowed_mentions=discord.AllowedMentions(users=[user], everyone=False, roles=False),
                )
            except (discord.Forbidden, discord.HTTPException):
                log.warning("reminderCog: couldn't post reminder in channel %s", reminder["channel_id"])

        try:
            await user.send(body, allowed_mentions=discord.AllowedMentions.none())
        except (discord.Forbidden, discord.HTTPException):
            log.info("reminderCog: couldn't DM user %s", user_id)

    # ---------- commands ----------

    @commands.hybrid_command(
        name="reminder",
        description="Set a reminder (ET): e.g. when: 2h30m or tomorrow 9am",
    )
    @discord.app_commands.describe(
        when="In X time (30m, 2h, 1d 3h) or a date/time in Eastern (3pm, tomorrow 9am, 10/15 6pm)",
        message="What should I remind you about?",
    )
    async def reminder(self, ctx: Context, when: str, *, message: str) -> None:
        """Set a reminder. I'll ping you here and DM you when it's time.

        Examples: `/reminder 2h call mom` · `/reminder "tomorrow 9am" submit form`
        All dates/times are Eastern Time (EST/EDT).
        """
        message = message.strip()
        if not message:
            await ctx.send("What should I remind you about?", ephemeral=True)
            return
        if len(message) > MAX_MESSAGE_LEN:
            await ctx.send(f"Keep it under {MAX_MESSAGE_LEN} characters.", ephemeral=True)
            return
        if sum(1 for r in self.reminders if r["user_id"] == ctx.author.id) >= MAX_PER_USER:
            await ctx.send(f"You already have {MAX_PER_USER} reminders — wait for some to go off.", ephemeral=True)
            return

        try:
            due = parse_when(when)
        except ReminderParseError as exc:
            await ctx.send(f"❌ {exc}\n\n{WHEN_HELP}", ephemeral=True)
            return

        reminder_id = max((r["id"] for r in self.reminders), default=0) + 1
        due_ts = int(due.timestamp())
        self.reminders.append({
            "id": reminder_id,
            "user_id": ctx.author.id,
            "channel_id": ctx.channel.id,
            "message": message,
            "due": due_ts,
            "created": int(time.time()),
        })
        self._save()

        await ctx.send(
            f"⏰ Reminder set for **{due.strftime('%a, %b %d at %I:%M %p %Z').replace(' 0', ' ')}** (<t:{due_ts}:R>).\n"
            f"-# Pings you here + DMs you · `/reminderview` · `/remindercancel`",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.hybrid_command(name="reminderview", description="View your upcoming reminders.")
    async def reminderview(self, ctx: Context) -> None:
        """View your upcoming reminders (only you can see the list)."""
        mine = sorted((r for r in self.reminders if r["user_id"] == ctx.author.id), key=lambda r: r["due"])
        if not mine:
            await ctx.send(
                "You have no upcoming reminders. Set one with `/reminder`.\n\n" + WHEN_HELP,
                ephemeral=True,
            )
            return

        lines = []
        for r in mine:
            text = r["message"] if len(r["message"]) <= 100 else r["message"][:97] + "..."
            lines.append(f"<t:{r['due']}:F> (<t:{r['due']}:R>) in <#{r['channel_id']}>\n> {text}")

        embed = discord.Embed(
            title="⏰ Your reminders",
            description="\n\n".join(lines)[:4000],
            color=discord.Color.red(),
        )
        embed.set_footer(text="Times shown in your local timezone")
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="remindercancel", description="Pick one of your reminders to cancel.")
    async def remindercancel(self, ctx: Context) -> None:
        """Pick one of your upcoming reminders from a dropdown to cancel it."""
        mine = sorted((r for r in self.reminders if r["user_id"] == ctx.author.id), key=lambda r: r["due"])
        if not mine:
            await ctx.send("You have no upcoming reminders to cancel.", ephemeral=True)
            return
        await ctx.send("Which reminder do you want to cancel?", view=CancelView(self, ctx.author.id, mine[:25]), ephemeral=True)


class CancelSelect(discord.ui.Select):
    def __init__(self, cog: ReminderCog, reminders: list[dict]):
        self.cog = cog
        options = []
        for r in reminders:
            when = datetime.fromtimestamp(r["due"], EASTERN).strftime("%b %d, %I:%M %p %Z").replace(" 0", " ")
            text = r["message"] if len(r["message"]) <= 80 else r["message"][:77] + "..."
            options.append(discord.SelectOption(label=text, description=when, value=str(r["id"])))
        super().__init__(placeholder="Choose a reminder to cancel", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        rid = int(self.values[0])
        match = next((r for r in self.cog.reminders if r["id"] == rid and r["user_id"] == interaction.user.id), None)
        if match is None:
            await interaction.response.edit_message(content="That reminder already went off or was cancelled.", view=None)
            return
        self.cog.reminders.remove(match)
        self.cog._save()
        await interaction.response.edit_message(content=f"🗑️ Cancelled: {match['message'][:200]}", view=None)


class CancelView(discord.ui.View):
    def __init__(self, cog: ReminderCog, user_id: int, reminders: list[dict]):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.add_item(CancelSelect(cog, reminders))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id


async def setup(bot: TerrierBot):
    await bot.add_cog(ReminderCog(bot))
