from __future__ import annotations

import re
import shelve
import time

import discord
from discord.ext import commands

from bot import TerrierBot
from ..logging.logConfig import MAIN_GUILD_ID

SHELVE_FILE = "terrierbot.shelve"
THREADS_KEY = "class_chat_threads"
MENTIONS_KEY = "class_mentions"
LAST_NOTIFIED_KEY = "last_notified"

FORUM_CHANNEL_ID = 1545063908048642058

CODE_PATTERN = re.compile(r"\b([A-Z]{2,4})\s?(\d{3})\b", re.IGNORECASE)

MENTION_THRESHOLD = 3
MENTION_WINDOW_SECONDS = 30 * 24 * 60 * 60  # 30 days
NOTIFY_COOLDOWN_SECONDS = 24 * 60 * 60  # 24h

# Department-code prefix -> forum tag name. Matched case-insensitively against
# the forum's actual available_tags, so a prefix with no matching tag is
# skipped instead of guessed at.
DEPARTMENT_TAG_NAMES: dict[str, str] = {
    "CH": "Chemistry",
    "CS": "Computer Science",
    "BI": "Biology",
    "PH": "Physics",
    "MA": "Math",
    "EC": "Economics",
    "PO": "Political Science",
    "SM": "Business",
    "QST": "Business",
    "COM": "Communication",
    "EK": "Engineering",
    "ME": "Engineering",
    "EE": "Engineering",
    "BE": "Engineering",
    "ENG": "Engineering",
}


async def setup(bot: TerrierBot):
    await bot.add_cog(ClassChatCog(bot))


class ClassChatCog(
    commands.Cog,
    name="ClassChat",
    description="Auto-detects BU class code mentions and connects members to (or creates) a class chat thread.",
):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot
        self.thread_cache: dict[str, int] = self._load(THREADS_KEY, {})
        self.mentions: dict[str, list[float]] = self._load(MENTIONS_KEY, {})
        self.last_notified: dict[tuple[str, int], float] = self._load(LAST_NOTIFIED_KEY, {})

    # ---------- storage helpers ----------

    @staticmethod
    def _load(key: str, default):
        with shelve.open(SHELVE_FILE) as sh:
            return sh.get(key, default)

    def _save(self, key: str, value) -> None:
        with shelve.open(SHELVE_FILE) as sh:
            sh[key] = value

    def _save_thread_cache(self) -> None:
        self._save(THREADS_KEY, self.thread_cache)

    def _save_mentions(self) -> None:
        self._save(MENTIONS_KEY, self.mentions)

    def _save_last_notified(self) -> None:
        self._save(LAST_NOTIFIED_KEY, self.last_notified)

    # ---------- listener ----------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if message.guild is None or message.guild.id != MAIN_GUILD_ID:
            return

        codes = self._extract_codes(message.content)
        if not codes:
            return

        forum = message.guild.get_channel(FORUM_CHANNEL_ID)
        if not isinstance(forum, discord.ForumChannel):
            return

        for code in codes:
            await self._handle_code(message, forum, code)

    @staticmethod
    def _extract_codes(content: str) -> list[str]:
        codes: list[str] = []
        for match in CODE_PATTERN.finditer(content):
            code = f"{match.group(1).upper()}{match.group(2)}"
            if code not in codes:
                codes.append(code)
        return codes

    # ---------- per-code handling ----------

    async def _handle_code(self, message: discord.Message, forum: discord.ForumChannel, code: str) -> None:
        thread = await self._resolve_cached_thread(forum, code)
        if thread is None:
            thread = self._find_active_thread_by_name(forum, code)
        if thread is None:
            thread = await self._find_archived_thread_by_name(forum, code)

        if thread is not None:
            self.thread_cache[code] = thread.id
            self._save_thread_cache()
            await self._maybe_notify(
                message,
                code,
                f"There's a class chat for {code} where you can connect with your classmates! → {thread.jump_url}",
            )
            return

        if not self._record_mention(code):
            return

        new_thread = await self._create_class_thread(forum, code)
        if new_thread is None:
            return

        self.thread_cache[code] = new_thread.id
        self._save_thread_cache()
        await self._maybe_notify(
            message,
            code,
            f"Seems like y'all are talking about {code} a lot, so I made a class chat for you: {new_thread.jump_url}",
        )

    async def _resolve_cached_thread(self, forum: discord.ForumChannel, code: str) -> discord.Thread | None:
        thread_id = self.thread_cache.get(code)
        if thread_id is None:
            return None

        thread = forum.get_thread(thread_id)
        if thread is not None:
            return thread

        try:
            fetched = await self.bot.fetch_channel(thread_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            fetched = None

        if isinstance(fetched, discord.Thread) and fetched.parent_id == forum.id:
            return fetched

        # Stale cache entry — the thread was deleted or is otherwise gone.
        del self.thread_cache[code]
        self._save_thread_cache()
        return None

    @staticmethod
    def _find_active_thread_by_name(forum: discord.ForumChannel, code: str) -> discord.Thread | None:
        for thread in forum.threads:
            if thread.name.strip().casefold() == code.casefold():
                return thread
        return None

    @staticmethod
    async def _find_archived_thread_by_name(forum: discord.ForumChannel, code: str) -> discord.Thread | None:
        async for thread in forum.archived_threads(limit=None):
            if thread.name.strip().casefold() == code.casefold():
                return thread
        return None

    # ---------- mention tracking / auto-create ----------

    def _record_mention(self, code: str) -> bool:
        """Records a mention timestamp for `code`, prunes entries older than the
        30-day window, and returns True once the code has hit the creation threshold."""
        now = time.time()
        cutoff = now - MENTION_WINDOW_SECONDS
        timestamps = [t for t in self.mentions.get(code, []) if t >= cutoff]
        timestamps.append(now)
        self.mentions[code] = timestamps
        self._save_mentions()
        return len(timestamps) >= MENTION_THRESHOLD

    async def _create_class_thread(self, forum: discord.ForumChannel, code: str) -> discord.Thread | None:
        content = await self._build_starter_content(code)
        applied_tags = self._match_tag(forum, code)

        try:
            result = await forum.create_thread(
                name=code,
                content=content,
                applied_tags=applied_tags,
                reason=f"Auto-created class chat for {code} (3+ mentions in 30 days)",
            )
        except (discord.Forbidden, discord.HTTPException):
            return None

        return result.thread

    async def _build_starter_content(self, code: str) -> str:
        class_cog = self.bot.get_cog("Class")
        if class_cog is not None:
            try:
                embed, _view, _error = await class_cog.lookup_course(code)
            except Exception:
                embed = None

            if embed is not None:
                title = embed.title or code
                description = next(
                    (field.value for field in embed.fields if field.name == "Description"),
                    None,
                )
                if description:
                    return f"**{title}**\n\n{description}"
                return f"**{title}**"

        return "This class kept coming up in the server, so here's a place to talk about it!"

    @staticmethod
    def _match_tag(forum: discord.ForumChannel, code: str) -> list[discord.ForumTag]:
        match = re.match(r"[A-Z]+", code)
        if not match:
            return []

        tag_name = DEPARTMENT_TAG_NAMES.get(match.group(0))
        if tag_name is None:
            return []

        for tag in forum.available_tags:
            if tag.name.casefold() == tag_name.casefold():
                return [tag]
        return []

    # ---------- throttled reply ----------

    async def _maybe_notify(self, message: discord.Message, code: str, text: str) -> None:
        key = (code, message.channel.id)
        now = time.time()
        last = self.last_notified.get(key)
        if last is not None and now - last < NOTIFY_COOLDOWN_SECONDS:
            return

        self.last_notified[key] = now
        self._save_last_notified()

        try:
            await message.channel.send(text)
        except (discord.Forbidden, discord.HTTPException):
            pass
