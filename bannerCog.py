import random
import shelve
from datetime import datetime, timedelta
import discord
from discord.ext import commands, tasks
from bot import TerrierBot, Context

BANNER_CHANNELS = [1402962052812898404, 1403922809012355172]
SHELVE_KEY = "banner_last_sent"
INTERVAL_DAYS = 7

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
        with shelve.open("terrierbot.shelve") as sh:
            last_sent: datetime | None = sh.get(SHELVE_KEY)

        if last_sent is not None and datetime.utcnow() - last_sent < timedelta(days=INTERVAL_DAYS):
            return

        channel_id = random.choice(BANNER_CHANNELS)
        channel = self.bot.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            await channel.send(BANNER_MESSAGE)
            with shelve.open("terrierbot.shelve") as sh:
                sh[SHELVE_KEY] = datetime.utcnow()

    @weekly_banner.before_loop
    async def before_weekly_banner(self):
        await self.bot.wait_until_ready()

    @commands.command()
    async def banner(self, ctx: Context):
        """Want your photo or gif to be the server banner? Find out how!"""
        await ctx.send(BANNER_MESSAGE)
