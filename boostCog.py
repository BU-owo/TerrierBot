import discord
from discord.ext import commands
from bot import TerrierBot, Context

async def setup(bot : TerrierBot):
    await bot.add_cog(BoostCog(bot))

class BoostCog(commands.Cog, name="Boost"):
    def __init__(self, bot : TerrierBot):
        self.bot : TerrierBot = bot
        print("Boost Cog Ready")        

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return
        # you can do stuff here when someone sends a message
        if message.type in (
            discord.MessageType.premium_guild_subscription,
            discord.MessageType.premium_guild_subscription_tier_1,
            discord.MessageType.premium_guild_subscription_tier_2,
            discord.MessageType.premium_guild_subscription_tier_3,
        ):
            await message.channel.send(
                f"""🎉 **Thank you for boosting, {message.author.mention}!**

            **Booster perks:**
            • Custom name color (holographic, solid, or gradient)  
            • Custom PNG or emoji next to your name (rule-compliant)  
            • One server emote added (rule-compliant)

            *Message a mod to claim your rewards!*
            """
            )
