from __future__ import annotations
import discord
from discord.ext import commands

BOMO_ID = 1040114538898526257

class BomoCog(commands.Cog):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.id == BOMO_ID:
            await message.add_reaction("😡")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BomoCog(bot))
