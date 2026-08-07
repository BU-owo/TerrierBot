import discord
from discord import app_commands
from discord.ext import commands
import nonexistentthing

from bot import TerrierBot, Context


async def setup(bot: TerrierBot):
    await bot.add_cog(BoostCog(bot))


class BoostCog(
    commands.Cog,
    name="Boost",
    description="Board of Trustees perks and server boost announcements.",
):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot
        print("Boost Cog Ready")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return

        if message.type == discord.MessageType.premium_guild_subscription:
            await message.channel.send(
                f"""🎉 **Congratulations, {message.author.mention}!**

You have officially joined the **Board of Trustees** by boosting the server.

**Board of Trustees Benefits:**

• Custom name color (holographic, solid, or gradient)  
• Custom PNG or emoji next to your name (rule-compliant)  
• One custom server emote added (rule-compliant)

*Please message a moderator to claim your trustee benefits. Thank you for supporting the server!*
"""
            )

    BOOST_TEXT = """# **Join the Board of Trustees**
Support the server by boosting it and become a member of the **Board of Trustees**.
**Trustee Benefits:**
• Custom name color (holographic, solid, or gradient)
• Custom PNG or emoji next to your name (rule-compliant)
• One custom server emote added (rule-compliant)
*Boost the server and message a moderator to claim your trustee benefits. Thank you for your support!*"""

    @commands.command()
    async def boost(self, ctx: Context):
        """See the perks of joining the Board of Trustees!"""
        _ = await ctx.send(self.BOOST_TEXT)

    @app_commands.command(
        name="boost",
        description="See the perks of joining the Board of Trustees!",
    )
    async def boost_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(self.BOOST_TEXT)


        