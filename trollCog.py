import re
import random
import discord
from discord import app_commands
from discord.ext import commands

TROLL_ROLE_ID = 1529519978976379061

EMOTICONS = [
    "fwendo", "Huoh", "._.", ";-;", ";_;", "（；ω；）", "ÙωÙ", "UwU",
    "（人◕ω◕）", "（●´ω｀●）", "（✿ ♡‿♡）", "（◠‿◠✿）", "^-^", "^_^",
    "＞_＜", "＞_＞", ":P", ":3", ";3", "x3", ":D", "xD", "XDDD",
    "（＾ｖ＾）", "ㅇㅅㅇ", "（• o •）", "ʕ•̫͡•ʔ", "ʕʘ‿ʘʔ", "（　'◟ '）",
]

WORD_REPLACEMENTS = [
    (r"\byou\b", "uu"),
    (r"\bhave\b", "haz"),
    (r"\bhas\b", "haz"),
    (r"\bno\b", "nu"),
]


def owo_ify(text: str) -> str:
    if not text:
        text = ""

    result = text.lower()

    for pattern, repl in WORD_REPLACEMENTS:
        result = re.sub(pattern, repl, result)

    result = result.replace("=", " da")

    result = re.sub(r"[rl]", "w", result)

    if result:
        first_char = result[0]
        stutter = f"{first_char}-{first_char}-{first_char}-"
        result = stutter + result
    else:
        result = "w-w-w-..."

    result = f"{result} {random.choice(EMOTICONS)}"

    return result


class TrollCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="troll", description="Toggle owo-troll mode on a user (mod only)")
    @app_commands.describe(user="The user to toggle troll mode for", mode="enable or disable")
    @app_commands.choices(mode=[
        app_commands.Choice(name="enable", value="enable"),
        app_commands.Choice(name="disable", value="disable"),
    ])
    @app_commands.checks.has_permissions(manage_roles=True)
    async def troll(self, interaction: discord.Interaction, user: discord.Member, mode: app_commands.Choice[str]):
        role = interaction.guild.get_role(TROLL_ROLE_ID)
        if role is None:
            await interaction.response.send_message(
                "Troll role not found in this server.", ephemeral=True
            )
            return

        try:
            if mode.value == "enable":
                await user.add_roles(role, reason=f"Troll mode enabled by {interaction.user}")
                await interaction.response.send_message(
                    f"Troll mode enabled for {user.mention}.", ephemeral=True
                )
            else:
                await user.remove_roles(role, reason=f"Troll mode disabled by {interaction.user}")
                await interaction.response.send_message(
                    f"Troll mode disabled for {user.mention}.", ephemeral=True
                )
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to modify that user's roles.", ephemeral=True
            )

    @troll.error
    async def troll_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "You don't have permission to use this command.", ephemeral=True
            )
        else:
            raise error

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.guild is None:
            return

        role_ids = {r.id for r in message.author.roles}
        if TROLL_ROLE_ID not in role_ids:
            return

        original_content = message.content
        if not original_content:
            return

        transformed = owo_ify(original_content)

        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        try:
            await message.channel.send(f"**{message.author.display_name} says:** {transformed}")
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(TrollCog(bot))
