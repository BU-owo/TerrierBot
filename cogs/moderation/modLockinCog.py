from __future__ import annotations

import re
import shelve
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot import TerrierBot
from ..logging.logConfig import LogChannels, LogColors, MAIN_GUILD_ID, MOD_ROLE_ID, get_log_channel, user_line

# Same "mod-work" category modTrackerCog tracks message activity against —
# a locked-in mod can still talk freely in here (case queues, mod chat,
# tickets) without getting the public callout treatment.
MOD_CATEGORY_ID = 1441884565873496177

SHELVE_FILE = "terrierbot.shelve"
SHELVE_KEY = "modlockins"

MIN_SECONDS = 60            # 1 minute
MAX_SECONDS = 2 * 60 * 60   # 2 hours

# matches combos like "1h30m", "45m", "2h" — no days, since the cap is 2h
DURATION_PATTERN = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?$", re.IGNORECASE)

NAG_TEMPLATE = (
    "I said I would be locked in until {time}, but I'm still trying to message chat. "
    "Please verbally abuse me!"
)


def parse_duration(duration_str: str) -> int | None:
    """Parse a duration string ("1h30m", "45m", "2h") into seconds. Returns
    None if invalid or empty."""
    duration_str = duration_str.strip().lower().replace(" ", "")
    if not duration_str:
        return None

    match = DURATION_PATTERN.match(duration_str)
    if not match or not any(match.groups()):
        return None

    hours, minutes = (int(g) if g else 0 for g in match.groups())
    total_seconds = hours * 3600 + minutes * 60

    if total_seconds <= 0:
        return None
    return total_seconds


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes or not parts:
        parts.append(f"{minutes}m")
    return " ".join(parts)


def _is_mod(interaction: discord.Interaction) -> bool:
    return isinstance(interaction.user, discord.Member) and any(
        r.id == MOD_ROLE_ID for r in interaction.user.roles
    )


async def setup(bot: TerrierBot):
    await bot.add_cog(ModLockinCog(bot))


class ModLockinCog(
    commands.Cog,
    name="ModLockin",
    description=(
        "Lets a mod self-lock-in — every message they send outside the mod category gets "
        "deleted and reposted as a public callout until time's up or they cancel it."
    ),
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot
        self.lockins: dict[str, dict[str, int]] = self._load()
        self.check_lockins.start()

    def cog_unload(self):
        self.check_lockins.cancel()

    # ── Storage helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _load() -> dict[str, dict[str, int]]:
        with shelve.open(SHELVE_FILE) as sh:
            return sh.get(SHELVE_KEY, {})

    def _save(self) -> None:
        with shelve.open(SHELVE_FILE) as sh:
            sh[SHELVE_KEY] = self.lockins

    # ── Shared helpers ───────────────────────────────────────────────────────

    async def _log(
        self, *, title: str, member: discord.abc.User, extra: str | None = None
    ) -> None:
        channel = get_log_channel(self.bot, LogChannels.MOD)
        if channel is None:
            return
        description = user_line(member)
        if extra:
            description += f"\n{extra}"
        embed = discord.Embed(
            title=title, description=description, color=LogColors.MOD, timestamp=discord.utils.utcnow()
        )
        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    async def _repost_as_nag(self, channel: discord.abc.Messageable, member: discord.abc.User, content: str) -> None:
        # Reuses TrollCog's actual webhook-impersonation plumbing (name lookup/
        # creation, thread handling, length guard, fallback on missing perms) —
        # "exactly how the troll cog works" rather than a second copy of it.
        troll_cog = self.bot.get_cog("TrollCog")
        if troll_cog is not None:
            await troll_cog._send_as(channel, member, content)
            return
        try:
            await channel.send(f"**{member.display_name}:** {content}")
        except (discord.Forbidden, discord.HTTPException):
            pass

    # ── Commands ─────────────────────────────────────────────────────────────
    # Slash-only, like TrollCog's own /troll toggle — a hybrid =modlockinstop
    # would risk getting caught by the interception below before the command
    # even runs, since prefix invocations are regular messages.

    @app_commands.command(
        name="modlockin",
        description="Lock yourself in — messages outside the mod category get deleted and reposted publicly (mod only).",
    )
    @app_commands.describe(duration="How long, e.g. 30m, 1h, 2h (max 2h)")
    @app_commands.check(_is_mod)
    async def modlockin(self, interaction: discord.Interaction, duration: str):
        user_id = str(interaction.user.id)

        if user_id in self.lockins:
            end_ts = self.lockins[user_id]["end_timestamp"]
            await interaction.response.send_message(
                f"You're already locked in — ends <t:{end_ts}:t> (<t:{end_ts}:R>). "
                f"Use `/modlockinstop` to end it early.",
                ephemeral=True,
            )
            return

        seconds = parse_duration(duration)
        if seconds is None:
            await interaction.response.send_message(
                "Couldn't understand that duration — try something like `30m`, `1h`, or `2h`.", ephemeral=True
            )
            return
        if seconds < MIN_SECONDS:
            await interaction.response.send_message("Minimum lock-in is 1 minute.", ephemeral=True)
            return
        if seconds > MAX_SECONDS:
            await interaction.response.send_message("Maximum lock-in is 2 hours.", ephemeral=True)
            return

        end_ts = int(time.time() + seconds)
        self.lockins[user_id] = {"guild_id": interaction.guild.id, "end_timestamp": end_ts}
        self._save()

        await self._log(
            title="🔒 Mod lock-in started",
            member=interaction.user,
            extra=f"**Duration:** {format_duration(seconds)}\n**Ends:** <t:{end_ts}:F> (<t:{end_ts}:R>)",
        )

        await interaction.response.send_message(
            f"Locked in until <t:{end_ts}:t> (<t:{end_ts}:R>). Any message you send outside the mod-work "
            f"category gets deleted and reposted with a public callout. Use `/modlockinstop` to end it early.",
            ephemeral=True,
        )

    @app_commands.command(name="modlockinstop", description="End your own mod lock-in early.")
    @app_commands.check(_is_mod)
    async def modlockinstop(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        entry = self.lockins.pop(user_id, None)
        if entry is None:
            await interaction.response.send_message("You don't have an active mod lock-in.", ephemeral=True)
            return
        self._save()

        await self._log(title="🔓 Mod lock-in ended early", member=interaction.user)
        await interaction.response.send_message("Mod lock-in ended — you can talk normally again.", ephemeral=True)

    # ── Interception ─────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        if message.guild.id != MAIN_GUILD_ID:
            return
        if message.webhook_id is not None:
            return

        entry = self.lockins.get(str(message.author.id))
        if entry is None:
            return

        if message.channel.category_id == MOD_CATEGORY_ID:
            return  # mod-work category is exempt

        end_ts = entry["end_timestamp"]
        nag = NAG_TEMPLATE.format(time=f"<t:{end_ts}:t>")

        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        await self._repost_as_nag(message.channel, message.author, nag)

    # ── Auto-expiry ──────────────────────────────────────────────────────────

    @tasks.loop(seconds=30)
    async def check_lockins(self):
        now = time.time()
        expired_ids = [uid for uid, entry in self.lockins.items() if entry["end_timestamp"] <= now]
        if not expired_ids:
            return

        for user_id in expired_ids:
            entry = self.lockins.pop(user_id)
            guild = self.bot.get_guild(entry["guild_id"])
            member = guild.get_member(int(user_id)) if guild is not None else None
            if member is None:
                continue

            await self._log(title="🔓 Mod lock-in ended", member=member)
            try:
                await member.send("Your mod lock-in is over — you can talk normally again. 🔓")
            except discord.HTTPException:
                pass

        self._save()

    @check_lockins.before_loop
    async def before_check_lockins(self):
        await self.bot.wait_until_ready()
