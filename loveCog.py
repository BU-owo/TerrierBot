import discord
from discord.ext import commands
from bot import TerrierBot, Context

async def setup(bot : TerrierBot):
    await bot.add_cog(LoveCog(bot))

class LoveCog(commands.Cog, name="Love", description="Spread the Terrier love."):
    def __init__(self, bot : TerrierBot):
        self.bot : TerrierBot = bot
        
        print("Love Cog Ready")        

    @commands.Cog.listener()
    async def on_message(self, message : discord.Message):
        if message.author == self.bot.user:
            return
        # you can do stuff here when someone sends a message

    @commands.command()
    # @commands.is_owner()
    async def love(self, ctx : Context):
        """Send some Terrier love! (Coming soon)"""
        _ = await ctx.send(":heart: Terrier Love — Coming Soon! :heart:")
        # you can do stuff here when someone executes the command "test"