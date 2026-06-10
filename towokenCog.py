from __future__ import annotations

import time

import discord
from discord import app_commands
from discord.ext import commands

from bot import TerrierBot, Context

TOWOKEN_THRESHOLD = 6
TOWOKEN_COOLDOWN_SECONDS = 10 * 60
TOWOKEN_EMOJI = "<:towoken:1418616280772247659>"
TOWOKEN_URL = "https://getstickbugged.lol/"
TOWOKEN_TEXT = (
    f"You have exceeded your Terrier Bot towoken limit {TOWOKEN_EMOJI}. "
    "Please purchase more towokens using the powoints you have earned."
)


async def setup(bot: TerrierBot):
    await bot.add_cog(TowokenCog(bot))


class TowokenCog(commands.Cog, name="Towoken", description="Silly towoken usage limiter response."):
    def __init__(self, bot: TerrierBot):
        self.bot = bot
        self._usage_counts: dict[int, int] = {}
        self._last_notice_at: dict[int, float] = {}
        print("Towoken Cog Ready")

    async def _maybe_send_towoken_notice(self, channel: discord.abc.Messageable, user_id: int) -> None:
        now = time.time()
        last_notice = self._last_notice_at.get(user_id, 0.0)
        if now - last_notice < TOWOKEN_COOLDOWN_SECONDS:
            return

        count = self._usage_counts.get(user_id, 0) + 1
        self._usage_counts[user_id] = count
        if count < TOWOKEN_THRESHOLD:
            return

        self._usage_counts[user_id] = 0
        self._last_notice_at[user_id] = now

        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Buy Towokens", url=TOWOKEN_URL))
        await channel.send(TOWOKEN_TEXT, view=view)

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: Context) -> None:
        if ctx.author.bot:
            return
        await self._maybe_send_towoken_notice(ctx.channel, ctx.author.id)

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command: app_commands.Command | app_commands.ContextMenu) -> None:
        _ = command
        if interaction.user.bot:
            return
        if interaction.channel is None:
            return
        await self._maybe_send_towoken_notice(interaction.channel, interaction.user.id)
