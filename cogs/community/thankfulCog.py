from __future__ import annotations

import random
import shelve
import time
from collections import defaultdict, deque
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

from bot import TerrierBot
from ..logging.logConfig import MAIN_GUILD_ID

EASTERN = ZoneInfo("America/New_York")

# Thanksgiving week 2026: Tue 11/24 through Fri 11/27 at noon ET. Outside this
# window the cog does nothing, so it's safe to leave loaded afterwards.
EVENT_START = datetime(2026, 11, 24, 0, 0, tzinfo=EASTERN)
EVENT_END = datetime(2026, 11, 27, 12, 0, tzinfo=EASTERN)

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
    await bot.add_cog(ThankfulCog(bot))


class ThankfulCog(
    commands.Cog,
    name="Thankful",
    description="Thanksgiving week: nudges very active chatters to fill out the thank-you form.",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot
        self.recent: defaultdict[int, deque[float]] = defaultdict(deque)
        self.channel_last_nudge: dict[int, float] = {}
        with shelve.open(SHELVE_FILE) as sh:
            self.nudged: dict[str, str] = sh.get(NUDGED_KEY, {})

    def _save(self) -> None:
        with shelve.open(SHELVE_FILE) as sh:
            sh[NUDGED_KEY] = self.nudged

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
                f"{text}\n## [Write a Thank You Message]({FORM_URL})\n{NUDGE_FOOTER}",
                mention_author=False,
                allowed_mentions=discord.AllowedMentions(users=[message.author], everyone=False, roles=False),
            )
        except discord.HTTPException:
            return

        self.channel_last_nudge[channel_id] = now
        self.recent.pop(uid, None)
        self.nudged[str(uid)] = today
        self._save()
