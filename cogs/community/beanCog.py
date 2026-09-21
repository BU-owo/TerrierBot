import shelve

import discord
from discord import app_commands
from discord.ext import commands

from bot import Context, TerrierBot

BEAN_EMOJI = "🫘"
BEAN_COLOR = discord.Color(0x8B5A2B)


async def setup(bot: TerrierBot):
    await bot.add_cog(BeanCog(bot))


class BeanCog(
    commands.Cog,
    name="Bean",
    description="A joke ban. Nobody is actually banned, it's just for fun.",
):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot

        with shelve.open("terrierbot.shelve") as sh:
            # guild_id -> user_id -> times beaned
            self.bean_counts: dict[int, dict[int, int]] = sh.get("bean_counts", {})

        print("Bean Cog Ready")

    def _save_state(self) -> None:
        with shelve.open("terrierbot.shelve") as sh:
            sh["bean_counts"] = self.bean_counts

    @commands.hybrid_command(
        name="bean",
        description=f"{BEAN_EMOJI} Bean someone. This is a JOKE ban, nothing actually happens!",
    )
    @app_commands.describe(
        member="Who to bean (just for fun!)",
        rule="Make up a fake rule they broke",
    )
    @commands.guild_only()
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def bean(self, ctx: Context, member: discord.Member, *, rule: commands.Range[str, 1, 150]):
        if member.bot:
            await ctx.send(f"Bots can't be beaned. {BEAN_EMOJI}", ephemeral=True)
            return

        guild_counts = self.bean_counts.setdefault(ctx.guild.id, {})
        guild_counts[member.id] = guild_counts.get(member.id, 0) + 1
        times = guild_counts[member.id]
        self._save_state()

        embed = discord.Embed(
            title=f"{BEAN_EMOJI} Member beaned (JOKE)",
            description=(
                f"**User:** {member.name} (`{member.id}`)\n"
                f"**Rule:** {rule}\n"
                "**Reason:** bean\n"
                "**Duration:** Permanent (just kidding!)\n"
                f"**Times beaned:** {times}"
            ),
            color=BEAN_COLOR,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"{BEAN_EMOJI} This is a JOKE. Nobody was actually banned. Just for fun!")

        await ctx.send(
            f"{BEAN_EMOJI} {member.mention} has been beaned by {ctx.author.mention}! "
            "(This is just a joke, nothing actually happened.)",
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=[member, ctx.author], roles=False, everyone=False),
        )
