from __future__ import annotations

import math
import shelve
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from bot import Context, TerrierBot

TARGET_UNIX_TS = 1781182800
TARGET_CHANNEL_ID = 1435336927795744858
SHELVE_KEY_LAST_ANNOUNCED_HOUR = "doomsday_last_announced_hour"


async def setup(bot: TerrierBot):
    await bot.add_cog(DoomsdayCog(bot))


class DoomsdayCog(commands.Cog, name="Doomsday", description="Hourly registration countdown announcements."):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot
        self.countdown_task.start()
        print("Doomsday Cog Ready")

    def cog_unload(self):
        self.countdown_task.cancel()

    def _target_dt(self) -> datetime:
        return datetime.fromtimestamp(TARGET_UNIX_TS, tz=timezone.utc)

    def _hours_remaining(self, now: datetime) -> int:
        remaining_seconds = (self._target_dt() - now).total_seconds()
        if remaining_seconds <= 0:
            return 0
        return math.ceil(remaining_seconds / 3600)

    def _format_remaining(self, now: datetime) -> str:
        remaining_seconds = int((self._target_dt() - now).total_seconds())
        if remaining_seconds <= 0:
            return "0h 0m"

        total_minutes = math.ceil(remaining_seconds / 60)
        days = total_minutes // (24 * 60)
        rem_after_days = total_minutes % (24 * 60)
        hours = rem_after_days // 60
        minutes = rem_after_days % 60

        parts: list[str] = []
        if days > 0:
            parts.append(f"{days}d")
        parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        return " ".join(parts)

    def _current_countdown_hour(self, now: datetime) -> int:
        target_hour = int(self._target_dt().timestamp() // 3600)
        current_hour = int(now.timestamp() // 3600)
        return target_hour - current_hour

    async def _send_countdown_if_due(self) -> None:
        now = datetime.now(timezone.utc)
        countdown_hour = self._current_countdown_hour(now)

        with shelve.open("terrierbot.shelve") as sh:
            last_announced_hour = sh.get(SHELVE_KEY_LAST_ANNOUNCED_HOUR)

        if last_announced_hour == countdown_hour:
            return

        channel = self.bot.get_channel(TARGET_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            return

        if countdown_hour <= 0:
            msg = f"🚨🔥 REGISTRATION TIME IS NOW!!! 🔥🚨 <t:{TARGET_UNIX_TS}:f>"
            await channel.send(msg)
            with shelve.open("terrierbot.shelve") as sh:
                sh[SHELVE_KEY_LAST_ANNOUNCED_HOUR] = countdown_hour
            self.countdown_task.cancel()
            return

        hours_left = self._hours_remaining(now)
        remaining = self._format_remaining(now)
        msg = (
            f"⏳💥 T minus {hours_left} hours ({remaining}) until registration on "
            f"<t:{TARGET_UNIX_TS}:f> 💥⏳"
        )
        await channel.send(msg)

        with shelve.open("terrierbot.shelve") as sh:
            sh[SHELVE_KEY_LAST_ANNOUNCED_HOUR] = countdown_hour

    @tasks.loop(minutes=5)
    async def countdown_task(self):
        await self._send_countdown_if_due()

    @countdown_task.before_loop
    async def before_countdown_task(self):
        await self.bot.wait_until_ready()

    @commands.command(name="doomsday")
    async def doomsday(self, ctx: Context):
        """Show current registration countdown status."""
        now = datetime.now(timezone.utc)
        hours_left = self._hours_remaining(now)
        remaining = self._format_remaining(now)

        if hours_left <= 0:
            _ = await ctx.send(f"🚨🔥 REGISTRATION TIME IS NOW!!! 🔥🚨 <t:{TARGET_UNIX_TS}:f>")
            return

        _ = await ctx.send(
            f"⏳💥 T minus {hours_left} hours ({remaining}) until registration on <t:{TARGET_UNIX_TS}:f> 💥⏳"
        )