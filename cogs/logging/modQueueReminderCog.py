from __future__ import annotations

import logging
import time

import discord
from discord.ext import commands, tasks

from bot import TerrierBot
from .logConfig import MOD_ROLE_ID, get_stale_queue_items

log = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 5 * 60


async def setup(bot: TerrierBot):
    await bot.add_cog(ModQueueReminderCog(bot))


class ModQueueReminderCog(
    commands.Cog,
    name="ModQueueReminder",
    description="Pings the mod role, once, for actionable mod-queue items left undecided for over an hour.",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot
        self.check_stale_items.start()

    def cog_unload(self) -> None:
        self.check_stale_items.cancel()

    @tasks.loop(seconds=CHECK_INTERVAL_SECONDS)
    async def check_stale_items(self) -> None:
        for message_id, channel_id in get_stale_queue_items(int(time.time())):
            channel = self.bot.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                continue
            try:
                message = await channel.fetch_message(message_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                continue
            try:
                await message.reply(
                    f"<@&{MOD_ROLE_ID}> this has been waiting on a decision for over an hour.",
                    allowed_mentions=discord.AllowedMentions(roles=True, users=False, everyone=False),
                )
            except discord.HTTPException:
                log.warning("modQueueReminderCog: failed to send stale-item reminder for message %d", message_id)

    @check_stale_items.before_loop
    async def before_check_stale_items(self) -> None:
        await self.bot.wait_until_ready()
