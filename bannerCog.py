import random
import shelve
from datetime import datetime, timedelta, timezone
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands, tasks
from bot import TerrierBot, Context

BANNER_CHANNELS = [1402962052812898404, 1403922809012355172]
SHELVE_KEY = "banner_last_sent"
INTERVAL_DAYS = 7
SHELVE_PATH = str(Path(__file__).resolve().parent / "terrierbot.shelve")

BANNER_MESSAGE = (
    "## **Your photo or gif can be our server banner!**\n"
    "Submit it to <#1403922809012355172> and it might get added!!! 🐾"
)


async def setup(bot: TerrierBot):
    await bot.add_cog(BannerCog(bot))


class BannerCog(commands.Cog, name="Banner"):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot
        self.weekly_banner.start()
        print("Banner Cog Ready")

    def cog_unload(self):
        self.weekly_banner.cancel()

    @tasks.loop(hours=1)
    async def weekly_banner(self):
        now = datetime.now(timezone.utc)
        with shelve.open(SHELVE_PATH) as sh:
            last_sent_raw = sh.get(SHELVE_KEY)

        last_sent: datetime | None = None
        if isinstance(last_sent_raw, (int, float)):
            last_sent = datetime.fromtimestamp(last_sent_raw, tz=timezone.utc)
        elif isinstance(last_sent_raw, datetime):
            last_sent = (
                last_sent_raw.replace(tzinfo=timezone.utc)
                if last_sent_raw.tzinfo is None
                else last_sent_raw.astimezone(timezone.utc)
            )

        if last_sent is not None and now - last_sent < timedelta(days=INTERVAL_DAYS):
            return

        channel_id = random.choice(BANNER_CHANNELS)
        channel = self.bot.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            await channel.send(BANNER_MESSAGE)
            with shelve.open(SHELVE_PATH) as sh:
                sh[SHELVE_KEY] = now.timestamp()

    @weekly_banner.before_loop
    async def before_weekly_banner(self):
        await self.bot.wait_until_ready()

    @commands.command()
    async def banner(self, ctx: Context):
        """Want your photo or gif to be the server banner? Find out how!"""
        await ctx.send(BANNER_MESSAGE)

    @app_commands.command(name="banner", description="Want your photo or gif to be the server banner? Find out how!")
    async def banner_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(BANNER_MESSAGE)
