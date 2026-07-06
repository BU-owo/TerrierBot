import discord
from discord import app_commands
from discord.ext import commands

# Eligible ping roles: id -> (display name, description shown in the picker)
PINGROLES = {
    1405219077693243434: ("Eventee", "ping for server events, BU events, or other fun happenings"),
    1412441490591842354: ("Foodee", "ping when you see free or cheap food to alert everyone else to it"),
    1416190981102895136: ("HungryLonger", "ping to find someone to eat with"),
    1422358773657243678: ("FitnessFriend", "ping to find someone to exercise with, whether working out, running, etc"),
    1425108753086287903: ("StudyBuddy", "ping this when you are studying and don't want to be alone"),
    1458528619482710047: ("MC", "ping this to invite others to play Minecraft"),
    1475971319366549534: ("Val", "ping this to invite others to play Valorant"),
    1503410327352508587: ("SummerLocal", "ping to hang out with people over the summer"),
}


class PingRoleCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Build the dropdown choices once: label shows "Name — description"
    def _role_choices() -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=f"{name} ({desc})", value=str(role_id))
            for role_id, (name, desc) in PINGROLES.items()
        ][:25]  # Discord caps choices at 25

    @app_commands.command(name="pingrole", description="Ping one of the community roles with a message")
    @app_commands.describe(
        role="Choose which role to ping",
        message="The message to include with your ping",
    )
    @app_commands.choices(role=_role_choices())
    @app_commands.checks.cooldown(1, 30, key=lambda i: i.user.id)
    async def pingrole(
        self,
        interaction: discord.Interaction,
        role: app_commands.Choice[str],
        message: str,
    ):
        role_id = int(role.value)
        guild_role = interaction.guild.get_role(role_id)

        if guild_role is None:
            await interaction.response.send_message(
                "That role couldn't be found in this server. It may have been deleted or renamed.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"{interaction.user.mention} has pinged {guild_role.mention}: *{message}*"
        )

    @pingrole.error
    async def pingrole_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"Slow down! You can use /pingrole again in {error.retry_after:.0f}s.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "Something went wrong running that command.", ephemeral=True
            )
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(PingRoleCog(bot))
