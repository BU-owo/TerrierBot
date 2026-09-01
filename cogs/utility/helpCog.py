import discord
from discord.ext import commands
from bot import TerrierBot, Context


async def setup(bot: TerrierBot):
    await bot.add_cog(HelpCog(bot))


class HelpCog(commands.Cog, name="Help", description="Shows the categorized TerrierBot commands overview."):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot

    @commands.command(name="help")
    async def help_command(self, ctx: Context):
        """Show categorized TerrierBot commands."""
        embed = discord.Embed(
            title="🐾 TerrierBot Commands 🐾",
            description="Use the `=` prefix or `/` slash commands where available!",
            color=discord.Color.red(),
        )

        embed.add_field(
            name="──── ⋆⁺₊✧🐾✧₊⁺⋆ ────\n✧ Moderation ✧",
            value=(
                "🐕 `/mywarns` — see your active warnings\n"
                "📝 `/warnappeal` — appeal one of your warnings\n"
                "🤫 `/snitch` — send an anonymous, silent alert to the mods"
            ),
            inline=False,
        )

        embed.add_field(
            name="──── ⋆⁺₊✧🐾✧₊⁺⋆ ────\n✧ Tools ✧",
            value=(
                "📚 `=class` / `/class` — look up a BU course from the Bulletin\n"
                "⭐ `=rmp` / `/rmp` — look up a professor on RateMyProfessors\n"
                "🐾 `=club` / `/club` — search for BU clubs on Terrier Central\n"
                "🚋 `=mbta` / `/mbta` — check how far Green Line trains are from a station (leave blank for the BU stops)\n"
                "🌈 `=mbtgay` / `/mbtgay` — track down the MBTA Pride Train (car #3706), if it's out riding today\n"
                "📣 `/pingrole` — ping one of our community roles — events, food, gaming, and more — with a message\n"
                "🔒 `=lockin` / `/lockin` — lock yourself out of the server for a set time to focus (can't be undone early)\n"
                "⏳ `=lockinleft` / `/lockinleft` — check how much time is left on your lock-in\n"
                "🥰 `=uwu` / `/uwu` — uwu-ify your own message"
            ),
            inline=False,
        )

        embed.add_field(
            name="──── ⋆⁺₊✧🐾✧₊⁺⋆ ────\n✧ Birthdays ✧",
            value=(
                "🎉 `=birthday set` / `/birthday set` `<month> <day>` — save (or update) your birthday"
            ),
            inline=False,
        )

        embed.set_footer(text="⋆⁺₊✧ ✧₊⁺⋆ — woof! — ⋆⁺₊✧ ✧₊⁺⋆")

        await ctx.send(embed=embed)
