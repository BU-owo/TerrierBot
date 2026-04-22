import csv
import io
import discord
from discord.ext import commands
from bot import TerrierBot, Context

async def setup(bot: TerrierBot):
    await bot.add_cog(MembersCog(bot))

class MembersCog(commands.Cog, name="Members"):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot
        print("Members Cog Ready")

    @commands.command()
    @commands.is_owner()
    @commands.guild_only()
    async def exportmembers(self, ctx: Context):
        """Export all server members to a CSV file."""
        assert ctx.guild is not None

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Username", "Nickname", "Roles", "Joined At"])

        async for member in ctx.guild.fetch_members(limit=None):
            roles = [r.name for r in member.roles if r.name != "@everyone"]
            joined = member.joined_at.strftime("%Y-%m-%d %H:%M:%S") if member.joined_at else ""
            writer.writerow([
                str(member),
                member.nick or "",
                ", ".join(roles),
                joined,
            ])

        output.seek(0)
        file = discord.File(fp=io.BytesIO(output.getvalue().encode()), filename="members.csv")
        await ctx.send("Here are the server members:", file=file)
