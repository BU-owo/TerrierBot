import discord
from discord.ext import commands
from bot import TerrierBot, Context

async def setup(bot : TerrierBot):
    await bot.add_cog(TestCog(bot))

class TestCog(commands.Cog, name="Test"):
    def __init__(self, bot : TerrierBot):
        self.bot : TerrierBot = bot

        print("Test Cog Ready")        

    @commands.Cog.listener()
    async def on_message(self, message : discord.Message):
        if message.author == self.bot.user:
            return 
        # you can do stuff here when someone sends a message

    @commands.command()
    # @commands.is_owner()
    async def test(self, ctx : Context):
        _ = await ctx.send("This is a test cog by so selene featuring owo")
        # you can do stuff here when someone executes the command "test"
