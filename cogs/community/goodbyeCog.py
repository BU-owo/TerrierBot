import discord
from discord import app_commands
from discord.ext import commands
from bot import TerrierBot, Context

async def setup(bot : TerrierBot):
    await bot.add_cog(GoodbyeCog(bot))

class GoodbyeCog(commands.Cog, name="Goodbye", description="Farewell commands."):
    def __init__(self, bot : TerrierBot):
        self.bot : TerrierBot = bot
        print("Goodbye Cog Ready")

    @commands.Cog.listener()
    async def on_message(self, message : discord.Message):
        if message.author == self.bot.user:
            return
        # you can do stuff here when someone sends a message

    @commands.command()
    # @commands.is_owner()
    async def goodbye(self, ctx : Context):
        """Say goodbye and have TerrierBot see you off!"""
        _ = await ctx.send(f"Goodbye {ctx.author.display_name}! I am TerrierBot!")
        # you can do stuff here when someone executes the command "test"

    @app_commands.command(name="goodbye", description="Say bye and have TerrierBot see you off!")
    async def goodbye_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Goodbye {interaction.user.display_name}! I am TerrierBot!")




