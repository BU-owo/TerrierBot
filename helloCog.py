import discord
from discord.ext import commands
from bot import TerrierBot, Context

async def setup(bot : TerrierBot):
    await bot.add_cog(HelloCog(bot))

class HelloCog(commands.Cog, name="Hello"):
    def __init__(self, bot : TerrierBot):
        self.bot : TerrierBot = bot

        print("Hello Cog Ready")        

    @commands.Cog.listener()
    async def on_message(self, message : discord.Message):
        if message.author == self.bot.user:
            return
        # you can do stuff here when someone sends a message

    @commands.command()
    # @commands.is_owner()
    async def hello(self, ctx : Context):
        _ = await ctx.send(f"Hello {ctx.author.display_name}! I am TerrierBot!")
        # you can do stuff here when someone executes the command "test"