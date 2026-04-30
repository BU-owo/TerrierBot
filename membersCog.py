import csv
import io
import discord
from discord.ext import commands
from bot import TerrierBot, Context

async def setup(bot: TerrierBot):
    await bot.add_cog(MembersCog(bot))

class MembersCog(commands.Cog, name="Members", description="Member exports and manual-prune reporting tools."):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot
        self.prune_role_id = 1474070492548956170
        print("Members Cog Ready")

    @commands.command()
    @commands.is_owner()
    @commands.guild_only()
    async def exportmembers(self, ctx: Context):
        """Export all server members to a CSV file."""
        assert ctx.guild is not None

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Username", "Global Display Name", "Server Nickname", "Roles", "Joined At"])

        async for member in ctx.guild.fetch_members(limit=None):
            roles = [r.name for r in member.roles if r.name != "@everyone"]
            joined = member.joined_at.strftime("%Y-%m-%d %H:%M:%S") if member.joined_at else ""
            writer.writerow([
                member.name,
                member.global_name or "",
                member.nick or "",
                ", ".join(roles),
                joined,
            ])

        output.seek(0)
        file = discord.File(fp=io.BytesIO(output.getvalue().encode()), filename="members.csv")
        await ctx.send("Here are the server members:", file=file)

    @commands.command()
    @commands.is_owner()
    @commands.guild_only()
    async def exportprunecandidates(self, ctx: Context):
        """Export members with no roles or only role ID 1474070492548956170."""
        assert ctx.guild is not None

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Username",
            "Global Display Name",
            "Server Nickname",
            "Roles",
            "Joined At",
            "Member ID",
        ])

        candidate_count = 0
        async for member in ctx.guild.fetch_members(limit=None):
            if member.bot:
                continue

            extra_roles = [role for role in member.roles if role != ctx.guild.default_role]
            has_no_extra_roles = len(extra_roles) == 0
            has_only_prune_role = len(extra_roles) == 1 and extra_roles[0].id == self.prune_role_id

            if not (has_no_extra_roles or has_only_prune_role):
                continue

            joined = member.joined_at.strftime("%Y-%m-%d %H:%M:%S") if member.joined_at else ""
            writer.writerow([
                member.name,
                member.global_name or "",
                member.nick or "",
                ", ".join(role.name for role in extra_roles),
                joined,
                member.id,
            ])
            candidate_count += 1

        output.seek(0)
        file = discord.File(
            fp=io.BytesIO(output.getvalue().encode()),
            filename="prune_candidates_role_filter_only.csv",
        )
        await ctx.send(
            f"Found {candidate_count} prune candidates using role filter only.",
            file=file,
        )
