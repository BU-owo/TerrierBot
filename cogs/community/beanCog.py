import shelve
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from bot import Context, TerrierBot

BEAN_EMOJI_ID = 1551694453121753209
FALLBACK_EMOJI = "🫘"  # used if the bot can't see the custom emoji
# Committed in data/ instead of linking a Discord CDN URL, which expires.
BEAN_IMAGE_PATH = Path(__file__).resolve().parents[2] / "data" / "bean.png"
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

    @property
    def emoji(self) -> str:
        custom = self.bot.get_emoji(BEAN_EMOJI_ID)
        return str(custom) if custom is not None else FALLBACK_EMOJI

    @commands.hybrid_command(
        name="bean",
        description="Bean someone. This is a JOKE ban, nothing actually happens!",
    )
    @app_commands.describe(
        member="Who to bean (just for fun!)",
        rule="Make up a fake rule they broke",
    )
    @commands.guild_only()
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def bean(self, ctx: Context, member: discord.Member, *, rule: commands.Range[str, 1, 150]):
        if member.bot:
            await ctx.send(f"Bots can't be beaned. {self.emoji}", ephemeral=True)
            return

        guild_counts = self.bean_counts.setdefault(ctx.guild.id, {})
        guild_counts[member.id] = guild_counts.get(member.id, 0) + 1
        times = guild_counts[member.id]
        self._save_state()

        embed = discord.Embed(
            title=f"{self.emoji} Member beaned",
            description=(
                f"**User:** {member.name} (`{member.id}`)\n"
                f"**Rule:** {rule}\n"
                "**Reason:** bean\n"
                "**Duration:** Permanent\n"
                f"**Times beaned:** {times}"
            ),
            color=BEAN_COLOR,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_image(url=f"attachment://{BEAN_IMAGE_PATH.name}")
        embed.set_footer(text="JOKE.")

        await ctx.send(
            f"{self.emoji} {member.mention} has been beaned by {ctx.author.mention}!",
            embed=embed,
            file=discord.File(BEAN_IMAGE_PATH),
            allowed_mentions=discord.AllowedMentions(users=[member, ctx.author], roles=False, everyone=False),
        )
