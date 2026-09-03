from __future__ import annotations

import shelve
import time
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from bot import TerrierBot, Context
from ..logging.logConfig import MOD_ROLE_ID

_SHELVE_FILE = "terrierbot.shelve"
_SHELVE_KEY = "towoken_enabled"

TOWOKEN_THRESHOLD = 12
TOWOKEN_COOLDOWN_SECONDS = 10 * 60
TOWOKEN_EMOJI = "<:towoken:1418616280772247659>"
OWO_EMOJI = "<:towoken:1475665207882678383>"
TOWOKEN_URL = "https://sites.google.com/view/towokens/"
TOWOKEN_TEXT = (
    f"You have exceeded your Terrier Bot towoken limit {TOWOKEN_EMOJI}. "
    "Please purchase more towokens using the powoints earned by completing a variety of side quests, riddles, and puzzles.\n"
    f"Contact bridge trowoll OwO for more infowormation. {OWO_EMOJI} \n"
    "||/joke||" 
)



async def setup(bot: TerrierBot):
    await bot.add_cog(TowokenCog(bot))


class TowokenCog(commands.Cog, name="Towoken", description="Silly towoken usage limiter response."):
    def __init__(self, bot: TerrierBot):
        self.bot = bot
        self._usage_counts: dict[int, int] = {}
        self._last_notice_at: dict[int, float] = {}
        with shelve.open(_SHELVE_FILE) as sh:
            self.enabled: bool = sh.get(_SHELVE_KEY, True)
        print("Towoken Cog Ready")

    def _save_state(self) -> None:
        with shelve.open(_SHELVE_FILE) as sh:
            sh[_SHELVE_KEY] = self.enabled

    @staticmethod
    def _is_mod(user: discord.abc.User) -> bool:
        return isinstance(user, discord.Member) and any(r.id == MOD_ROLE_ID for r in user.roles)

    async def _maybe_send_towoken_notice(self, channel: discord.abc.Messageable, user_id: int) -> None:
        if not self.enabled:
            return

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
        if self._is_mod(ctx.author):
            return
        await self._maybe_send_towoken_notice(ctx.channel, ctx.author.id)

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command: app_commands.Command | app_commands.ContextMenu) -> None:
        _ = command
        if interaction.user.bot:
            return
        if interaction.channel is None:
            return
        if self._is_mod(interaction.user):
            return
        await self._maybe_send_towoken_notice(interaction.channel, interaction.user.id)

    # ── =towoken ─────────────────────────────────────────────────────────────

    @commands.hybrid_command(
        name="towoken", description="Enable or disable the towoken limit notice (mod only)."
    )
    @app_commands.describe(state="enable or disable")
    async def towoken(self, ctx: Context, state: Literal["enable", "disable"]):
        if not self._is_mod(ctx.author):
            await ctx.send("You don't have permission to use this command.", ephemeral=True)
            return

        self.enabled = state == "enable"
        self._save_state()
        await ctx.send(
            f"Towoken notice is now {'enabled' if self.enabled else 'disabled'}.", ephemeral=True
        )
