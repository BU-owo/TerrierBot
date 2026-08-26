from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands, tasks
import re
import shelve
import time
from typing import Any

from ..logging.logConfig import LogChannels, LogColors, MAIN_GUILD_ID, get_log_channel

LOCKIN_ROLE_ID = 1410344839718895716
SHELVE_FILE = "terrierbot.shelve"
SHELVE_KEY = "lockins"

MIN_SECONDS = 5 * 60          # 5 minutes
MAX_SECONDS = 7 * 24 * 60 * 60  # 7 days

# matches combos like "1d2h30m", "90m", "2h", "1d"
DURATION_PATTERN = re.compile(
    r"^(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?$", re.IGNORECASE
)


def parse_duration(duration_str: str) -> int | None:
    """Parse a duration string into seconds. Returns None if invalid or empty."""
    duration_str = duration_str.strip().lower().replace(" ", "")
    if not duration_str:
        return None

    match = DURATION_PATTERN.match(duration_str)
    if not match or not any(match.groups()):
        return None

    days, hours, minutes = (int(g) if g else 0 for g in match.groups())
    total_seconds = days * 86400 + hours * 3600 + minutes * 60

    if total_seconds <= 0:
        return None

    return total_seconds


def format_duration(seconds: int) -> str:
    """Turn a seconds count into a human-readable string like '1d 2h 5m'."""
    seconds = max(0, int(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    return " ".join(parts)


class LockinCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.lockins: dict[str, dict[str, Any]] = self._load_lockins()
        self.check_lockins.start()

    def cog_unload(self):
        self.check_lockins.cancel()

    # ---------- storage helpers ----------

    def _load_lockins(self) -> dict[str, dict[str, Any]]:
        with shelve.open(SHELVE_FILE) as sh:
            return sh.get(SHELVE_KEY, {})

    def _save_lockins(self):
        with shelve.open(SHELVE_FILE) as sh:
            sh[SHELVE_KEY] = self.lockins

    # ---------- member-log ----------

    async def _log_lockin_start(self, member: discord.Member, *, seconds: int, end_ts: int) -> None:
        if member.guild.id != MAIN_GUILD_ID:
            return

        channel = get_log_channel(self.bot, LogChannels.MEMBER)
        if channel is None:
            return

        embed = discord.Embed(
            title="🔒 Lock-in started",
            description=(
                f"{member.mention} (`{member.id}`)\n"
                f"**Duration:** {format_duration(seconds)}\n"
                f"**Ends:** <t:{end_ts}:F> (<t:{end_ts}:R>)"
            ),
            color=LogColors.MEMBER,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    # ---------- background task ----------

    @tasks.loop(seconds=60)
    async def check_lockins(self):
        now = time.time()
        expired_ids = [
            user_id for user_id, entry in self.lockins.items()
            if entry["end_timestamp"] <= now
        ]

        for user_id in expired_ids:
            entry = self.lockins.pop(user_id)
            guild = self.bot.get_guild(entry["guild_id"])
            if guild is None:
                continue

            member = guild.get_member(int(user_id))
            if member is None:
                try:
                    member = await guild.fetch_member(int(user_id))
                except discord.NotFound:
                    continue

            role = guild.get_role(entry["role_id"])
            if role and role in member.roles:
                try:
                    await member.remove_roles(role, reason="Lock-in period ended")
                except discord.HTTPException:
                    pass

            # Restore whatever roles were stashed when the lock-in started.
            # A saved role ID that no longer resolves (deleted since then) is
            # skipped rather than erroring.
            saved_role_ids = entry.get("saved_role_ids", [])
            roles_to_restore = [
                r for rid in saved_role_ids if (r := guild.get_role(rid)) is not None
            ]
            if roles_to_restore:
                try:
                    await member.add_roles(*roles_to_restore, reason="Lock-in period ended — restoring roles")
                except discord.HTTPException:
                    pass

            try:
                await member.send("your lock-in is over — welcome back 🔓")
            except discord.HTTPException:
                pass  # DMs closed, no big deal

        if expired_ids:
            self._save_lockins()

    @check_lockins.before_loop
    async def before_check_lockins(self):
        await self.bot.wait_until_ready()

    # ---------- commands ----------

    @commands.hybrid_command(
        name="lockin",
        description="Lock yourself out of server access for a set time to focus. Cannot be undone early."
    )
    @app_commands.describe(duration="e.g. 30m, 2h, 1d, 1d2h30m")
    async def lockin(self, ctx: commands.Context, duration: str):
        user_id = str(ctx.author.id)

        if user_id in self.lockins:
            end_ts = int(self.lockins[user_id]["end_timestamp"])
            await ctx.reply(
                f"you're already locked in — ends <t:{end_ts}:R> (<t:{end_ts}:F>). "
                f"can't stack or extend it, gotta ride it out.",
                ephemeral=True
            )
            return

        seconds = parse_duration(duration)
        if seconds is None:
            await ctx.reply(
                "couldn't parse that duration. try something like `30m`, `2h`, `1d`, or `1d2h30m`.",
                ephemeral=True
            )
            return

        if seconds < MIN_SECONDS:
            await ctx.reply("minimum lock-in is 5 minutes.", ephemeral=True)
            return
        if seconds > MAX_SECONDS:
            await ctx.reply("maximum lock-in is 7 days.", ephemeral=True)
            return

        role = ctx.guild.get_role(LOCKIN_ROLE_ID)
        if role is None:
            await ctx.reply("lock-in role not found on this server — ping a mod.", ephemeral=True)
            return

        # All checks passed — defer now. The role-strip, role-add, shelve
        # write, and member-log send below are several sequential network
        # calls, which combined can outrun Discord's 3-second interaction ack
        # window and make the final reply below fail with a 404 Unknown
        # interaction even though the lock-in itself went through.
        await ctx.defer(ephemeral=True)

        end_ts = int(time.time() + seconds)

        # Stash the member's current roles (minus @everyone, which can't be
        # assigned/removed directly) so they can be restored when the
        # lock-in ends, then strip them — otherwise other roles' channel
        # access would defeat the point of locking out server access.
        current_roles = [r for r in ctx.author.roles if not r.is_default()]
        saved_role_ids = [r.id for r in current_roles]

        try:
            if current_roles:
                await ctx.author.remove_roles(
                    *current_roles, reason="Lock-in requested — roles stashed until lock-in ends"
                )
            await ctx.author.add_roles(role, reason="Lock-in requested")
        except discord.HTTPException:
            await ctx.send("couldn't assign the role — ping a mod.", ephemeral=True)
            return

        self.lockins[user_id] = {
            "guild_id": ctx.guild.id,
            "role_id": LOCKIN_ROLE_ID,
            "end_timestamp": end_ts,
            "saved_role_ids": saved_role_ids,
        }
        self._save_lockins()

        await self._log_lockin_start(ctx.author, seconds=seconds, end_ts=end_ts)

        await ctx.send(
            f"locked in for {format_duration(seconds)}. ends <t:{end_ts}:F> (<t:{end_ts}:R>). "
            f"no take-backs, good luck 🔒",
            ephemeral=True
        )

    @commands.hybrid_command(
        name="lockinleft",
        description="Check how much time is left on your current lock-in."
    )
    async def lockinleft(self, ctx: commands.Context):
        user_id = str(ctx.author.id)
        entry = self.lockins.get(user_id)

        if entry is None:
            await ctx.reply("you're not locked in right now.", ephemeral=True)
            return

        end_ts = int(entry["end_timestamp"])
        remaining = end_ts - time.time()

        await ctx.reply(
            f"{format_duration(remaining)} left — ends <t:{end_ts}:R> (<t:{end_ts}:F>).",
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(LockinCog(bot))