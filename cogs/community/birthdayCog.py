from __future__ import annotations

import io
import json
import logging
import shelve
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot import Context, TerrierBot
from ..logging.logConfig import MAIN_GUILD_ID, MOD_ROLE_ID

log = logging.getLogger(__name__)

BIRTHDAY_ROLE_ID = 1404879458992914484
BIRTHDAY_ANNOUNCE_CHANNEL_ID = 1396542256445391069
EASTERN = ZoneInfo("America/New_York")
BIRTHDAY_GIF_URL = "https://media1.tenor.com/m/Hq-zbjBKsRYAAAAC/happy-birthday-cute.gif"
SHELVE_FILE = "terrierbot.shelve"
# One-time (repeatable, no-op after first success) import of birthdays collected
# by the old birthday bot before it was replaced by this cog.
SEED_FILE = Path("data/birthday_migration.json")

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
# Feb allows 29 even though no year is stored — see MONTH_DAYS below.
MONTH_DAYS = {1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}
MONTH_CHOICES = [app_commands.Choice(name=name, value=str(i)) for i, name in enumerate(MONTH_NAMES, start=1)]


def parse_month(raw: str) -> int | None:
    raw = raw.strip()
    if raw.isdigit():
        value = int(raw)
        return value if 1 <= value <= 12 else None
    lowered = raw.lower()
    for i, name in enumerate(MONTH_NAMES, start=1):
        if name.lower() == lowered:
            return i
    return None


def day_of_year(month: int, day: int) -> int:
    # 2024 is a leap year, so this accepts Feb 29 the same way MONTH_DAYS does.
    return date(2024, month, day).timetuple().tm_yday


def format_birthday(month: int, day: int) -> str:
    return f"{MONTH_NAMES[month - 1]} {day}"


class BirthdayCog(commands.Cog, name="Birthday", description="Birthday roles, announcements, and self-service birthday tracking."):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot
        self.birthdays: dict[str, dict[str, int]] = {}
        # {"date": iso_date_str, "user_ids": [user_id, ...]} — tracks who has
        # already been assigned/announced today, per-user rather than a single
        # whole-day flag, so a birthday added mid-day still gets picked up on
        # the next tick instead of waiting until the following year.
        self.announced_today: dict[str, Any] = {"date": None, "user_ids": []}
        self.last_removed_date: str | None = None
        self.current_holders: list[int] = []

        self._load_state()
        self._migrate_seed()

        self.birthday_task.start()

    def cog_unload(self) -> None:
        self.birthday_task.cancel()

    # ---------- storage ----------

    def _load_state(self) -> None:
        with shelve.open(SHELVE_FILE) as sh:
            self.birthdays = sh.get("birthdays", {})
            self.announced_today = sh.get("birthday_announced_today", {"date": None, "user_ids": []})
            self.last_removed_date = sh.get("birthday_last_removed_date")
            self.current_holders = sh.get("birthday_current_holders", [])

    def _save_birthdays(self) -> None:
        with shelve.open(SHELVE_FILE) as sh:
            sh["birthdays"] = self.birthdays

    def _save_task_state(self) -> None:
        with shelve.open(SHELVE_FILE) as sh:
            sh["birthday_announced_today"] = self.announced_today
            sh["birthday_last_removed_date"] = self.last_removed_date
            sh["birthday_current_holders"] = self.current_holders

    def _migrate_seed(self) -> None:
        if not SEED_FILE.exists():
            return
        try:
            with open(SEED_FILE, "r", encoding="utf-8") as f:
                seed = json.load(f)
        except (OSError, json.JSONDecodeError):
            log.exception("birthdayCog: failed to read seed file %s", SEED_FILE)
            return

        imported = 0
        for user_id, entry in seed.items():
            if user_id in self.birthdays:
                continue
            month = entry.get("month")
            day = entry.get("day")
            if not isinstance(month, int) or not isinstance(day, int):
                continue
            if month not in MONTH_DAYS or not (1 <= day <= MONTH_DAYS[month]):
                continue
            self.birthdays[user_id] = {"month": month, "day": day}
            imported += 1

        if imported:
            self._save_birthdays()
            log.info("birthdayCog: imported %d birthday(s) from seed file", imported)

    @staticmethod
    def _is_mod(user: discord.abc.User) -> bool:
        return isinstance(user, discord.Member) and any(r.id == MOD_ROLE_ID for r in user.roles)

    # ---------- background task ----------

    @tasks.loop(minutes=5)
    async def birthday_task(self) -> None:
        now = datetime.now(EASTERN)
        today_str = now.date().isoformat()

        if self.announced_today.get("date") != today_str:
            self.announced_today = {"date": today_str, "user_ids": []}
            self._save_task_state()

        await self._assign_todays_birthdays(now)

        if (now.hour, now.minute) >= (23, 59) and today_str != self.last_removed_date:
            await self._remove_expired_holders(today_str)

    @birthday_task.before_loop
    async def before_birthday_task(self) -> None:
        await self.bot.wait_until_ready()

    @staticmethod
    def _join_mentions(mentions: list[str]) -> str:
        if len(mentions) == 1:
            return mentions[0]
        if len(mentions) == 2:
            return f"{mentions[0]} and {mentions[1]}"
        return f"{', '.join(mentions[:-1])}, and {mentions[-1]}"

    async def _assign_todays_birthdays(self, now: datetime) -> None:
        guild = self.bot.get_guild(MAIN_GUILD_ID)
        if guild is None:
            return

        role = guild.get_role(BIRTHDAY_ROLE_ID)
        channel = self.bot.get_channel(BIRTHDAY_ANNOUNCE_CHANNEL_ID)
        announced_ids: list[int] = self.announced_today["user_ids"]

        members_today: list[discord.Member] = []
        for user_id_str, entry in self.birthdays.items():
            if entry.get("month") != now.month or entry.get("day") != now.day:
                continue

            user_id = int(user_id_str)
            if user_id in announced_ids:
                continue

            member = guild.get_member(user_id)
            if member is None:
                continue

            members_today.append(member)


        if not members_today:
            return

        if role is not None:
            for member in members_today:
                try:
                    await member.add_roles(role, reason="Birthday today")
                except (discord.Forbidden, discord.HTTPException):
                    log.warning("birthdayCog: couldn't add birthday role to %s", member.id)
        if isinstance(channel, discord.TextChannel):
            mentions = [member.mention for member in members_today]
            if len(members_today) == 1:
                intro = f"# {mentions[0]} is a birthday terrier today! Please wish them a happy birthday!"
            else:
                intro = f"# {self._join_mentions(mentions)} are birthday terriers today! Please wish them a happy birthday!"

            content = f"{intro}\n\n*Add your birthday with the command /birthday set month date*\n\n{BIRTHDAY_GIF_URL}"

            try:
                await channel.send(
                    content=content,
                    allowed_mentions=discord.AllowedMentions(users=True, everyone=False, roles=False),
                )
            except discord.HTTPException:
                log.exception(
                    "birthdayCog: failed to post birthday announcement for %s",
                    [member.id for member in members_today],
                )

        for member in members_today:
            announced_ids.append(member.id)
            if member.id not in self.current_holders:
                self.current_holders.append(member.id)

        self._save_task_state()

    async def _remove_expired_holders(self, today_str: str) -> None:
        guild = self.bot.get_guild(MAIN_GUILD_ID)
        role = guild.get_role(BIRTHDAY_ROLE_ID) if guild is not None else None

        if guild is not None and role is not None:
            for user_id in self.current_holders:
                member = guild.get_member(user_id)
                if member is None or role not in member.roles:
                    continue
                try:
                    await member.remove_roles(role, reason="Birthday over")
                except (discord.Forbidden, discord.HTTPException):
                    log.warning("birthdayCog: couldn't remove birthday role from %s", user_id)

        self.current_holders = []
        self.last_removed_date = today_str
        self._save_task_state()

    # ---------- shared command logic ----------

    async def _set_birthday(
        self, ctx: Context, target: discord.abc.User, month_raw: str, day: int, *, ephemeral: bool = True
    ) -> bool:
        month = parse_month(month_raw)
        if month is None:
            await ctx.send(f"\"{month_raw}\" isn't a real month — use a name like `March` or a number 1-12.", ephemeral=ephemeral)
            return False

        max_day = MONTH_DAYS[month]
        if not (1 <= day <= max_day):
            await ctx.send(f"Come on... {MONTH_NAMES[month - 1]} only has {max_day} days.", ephemeral=ephemeral)
            return False

        self.birthdays[str(target.id)] = {"month": month, "day": day}
        self._save_birthdays()
        return True

    # ---------- commands ----------

    @commands.hybrid_group(name="birthday", description="View or manage your birthday.")
    async def birthday(self, ctx: Context) -> None:
        if ctx.invoked_subcommand is not None:
            return

        entry = self.birthdays.get(str(ctx.author.id))
        if entry is None:
            await ctx.send("You haven't set your birthday yet. Run `=birthday set`.")
            return
        await ctx.send(f"Your birthday is {format_birthday(entry['month'], entry['day'])}! 🎂")

    @birthday.command(name="set", description="Set your birthday.")
    @app_commands.describe(month="Your birth month", day="Your birth day")
    @app_commands.choices(month=MONTH_CHOICES)
    async def birthday_set(self, ctx: Context, month: str, day: app_commands.Range[int, 1, 31]) -> None:
        if await self._set_birthday(ctx, ctx.author, month, day):
            entry = self.birthdays[str(ctx.author.id)]
            await ctx.send(f"Thank you! Your birthday is set to {format_birthday(entry['month'], entry['day'])}. 🎂", ephemeral=True)

    @birthday.command(name="get", description="Look up a saved birthday.")
    @app_commands.describe(user="Whose birthday to check (leave blank for your own)")
    async def birthday_get(self, ctx: Context, user: discord.Member | None = None) -> None:
        target = user or ctx.author
        entry = self.birthdays.get(str(target.id))
        if entry is None:
            possessive = "You have" if target.id == ctx.author.id else f"{target.display_name} has"
            await ctx.send(f"{possessive} no birthday on file.")
            return

        possessive = "Your" if target.id == ctx.author.id else f"{target.display_name}'s"
        await ctx.send(f"{possessive} birthday is {format_birthday(entry['month'], entry['day'])}.")

    @birthday.command(name="remove", description="Remove a saved birthday.")
    @app_commands.describe(user="Whose birthday to remove (mods only — leave blank to remove your own)")
    async def birthday_remove(self, ctx: Context, user: discord.Member | None = None) -> None:
        is_self = user is None or user.id == ctx.author.id
        if not is_self and not self._is_mod(ctx.author):
            await ctx.send("Oops! You can't run that... mods only!", ephemeral=True)
            return

        target = ctx.author if is_self else user
        removed = self.birthdays.pop(str(target.id), None)
        if removed is None:
            possessive = "You don't" if is_self else f"{target.display_name} doesn't"
            await ctx.send(f"{possessive} have a birthday here!", ephemeral=True)
            return

        self._save_birthdays()
        if is_self:
            await ctx.send(
                "Your birthday has been removed and won't recur. "
                "If you're wearing the birthday role today, it'll still come off at the end of the day as usual.",
                ephemeral=True,
            )
        else:
            await ctx.send(
                f"{target.display_name}'s birthday has been removed and won't recur. "
                "If they're wearing the birthday role today, it'll still come off at the end of the day as usual."
            )

    @birthday.command(name="nearest", description="Show birthdays coming up in the next couple weeks.")
    async def birthday_nearest(self, ctx: Context) -> None:
        guild = self.bot.get_guild(MAIN_GUILD_ID)
        if guild is None:
            await ctx.send("Couldn't find the main server.", ephemeral=True)
            return

        now = datetime.now(EASTERN)
        today_doy = day_of_year(now.month, now.day)

        upcoming: list[tuple[int, discord.Member, dict[str, int]]] = []
        for user_id_str, entry in self.birthdays.items():
            member = guild.get_member(int(user_id_str))
            if member is None:
                continue
            entry_doy = day_of_year(entry["month"], entry["day"])
            # Signed day offset from today, wrapped to (-183, 183] so a birthday
            # just before year-end still sorts correctly relative to early January.
            offset = (entry_doy - today_doy) % 366
            if offset > 183:
                offset -= 366
            if abs(offset) <= 14:
                upcoming.append((offset, member, entry))

        if not upcoming:
            await ctx.send("No birthdays in the next two weeks. 🥲")
            return

        upcoming.sort(key=lambda item: item[0])
        lines = [
            f"**{format_birthday(entry['month'], entry['day'])}** — {member.display_name}"
            for _, member, entry in upcoming
        ]
        embed = discord.Embed(
            title="🎂 Upcoming Birthdays",
            description="\n".join(lines),
            color=discord.Color.pink(),
        )
        await ctx.send(embed=embed)

    @birthday.command(name="export", description="Export all saved birthdays to a text file. (Mod only)")
    async def birthday_export(self, ctx: Context) -> None:
        if not self._is_mod(ctx.author):
            await ctx.send("Oops! You can't run that... mods only!", ephemeral=True)
            return

        guild = self.bot.get_guild(MAIN_GUILD_ID)
        rows = sorted(self.birthdays.items(), key=lambda kv: (kv[1]["month"], kv[1]["day"]))

        lines = []
        for user_id_str, entry in rows:
            member = guild.get_member(int(user_id_str)) if guild is not None else None
            name = member.display_name if member is not None else "unknown - left server"
            lines.append(f"{entry['month']:02d}-{entry['day']:02d}: {user_id_str} ({name})")

        content = "\n".join(lines) if lines else "No birthdays on file."
        buffer = io.BytesIO(content.encode("utf-8"))
        await ctx.send(file=discord.File(buffer, filename="birthdays_export.txt"), ephemeral=True)

    @birthday.command(name="override", description="Set another member's birthday. (Mod only)")
    @app_commands.describe(user="Member to set the birthday for", month="Birth month", day="Birth day")
    @app_commands.choices(month=MONTH_CHOICES)
    async def birthday_override(
        self, ctx: Context, user: discord.Member, month: str, day: app_commands.Range[int, 1, 31]
    ) -> None:
        if not self._is_mod(ctx.author):
            await ctx.send("Oops! You can't run that... mods only!", ephemeral=True)
            return

        if await self._set_birthday(ctx, user, month, day, ephemeral=False):
            entry = self.birthdays[str(user.id)]
            await ctx.send(
                f"Set {user.display_name}'s birthday to {format_birthday(entry['month'], entry['day'])}."
            )


async def setup(bot: TerrierBot) -> None:
    await bot.add_cog(BirthdayCog(bot))
