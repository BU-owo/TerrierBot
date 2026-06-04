import random

import discord
from discord import app_commands
from discord.ext import commands

from bot import Context, TerrierBot

PRIDE_CHANNEL_ID = 1396542256445391069
PRIDE_INTERVAL = 500  # trigger every N server messages

PRIDE_MESSAGE = (
    "# Happy Pride! Pick a name color for the month of June by going to <id:customize>!\n"
    "<:Frainbow:1511023562658418939> <:Fpride:1511023471461793823> "
    "<:Fally:1511023628542545990> <:Ftrans:1511024293734121702> "
    "<:Ftransfem:1511025526532341942> <:Ftransmasc:1511025574049480896> "
    "<:Fnb:1511024179950915835> <:Fgenderqueer:1511024073596207334> "
    "<:Fgenderfluid:1511023987021582346> <:Fagender:1511023704895914175> "
    "<:Fintersex:1511024134250037260> <:Flesbian:1511023313970008227> "
    "<:Fgayman:1511025487563194548> <:Fbi:1511023871283691550> "
    "<:Fpan:1511023401412591726> <:Face:1511023821174345779> "
    "<:Faro:1511023768456396820> <:Faroace:1511025608313016522> "
    "<:Fdemi:1511023917760778352> <:Fpolyam:1511035210815373413>"
)


async def setup(bot: TerrierBot):
    await bot.add_cog(PrideCog(bot))


class PrideCog(commands.Cog, name="Pride", description="Send Pride celebration messages automatically and on command."):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot

        # Start counter at a random offset so the first trigger isn't always
        # exactly 300 messages after every restart.
        self.message_count: int = random.randint(0, PRIDE_INTERVAL - 1)

        print("Pride Cog Ready")

    async def _get_pride_channel(self) -> discord.TextChannel | None:
        channel = self.bot.get_channel(PRIDE_CHANNEL_ID)
        if isinstance(channel, discord.TextChannel):
            return channel

        try:
            fetched_channel = await self.bot.fetch_channel(PRIDE_CHANNEL_ID)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            return None

        if isinstance(fetched_channel, discord.TextChannel):
            return fetched_channel
        return None

    async def _send_pride_message(self) -> bool:
        channel = await self._get_pride_channel()
        if channel is None:
            return False

        try:
            await channel.send(
                PRIDE_MESSAGE,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return True
        except (discord.Forbidden, discord.HTTPException):
            return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.guild is None:
            return

        self.message_count += 1

        if self.message_count >= PRIDE_INTERVAL:
            self.message_count = 0
            await self._send_pride_message()

    @commands.command(name="pride")
    async def pride(self, ctx: Context):
        """Send the Pride message to the configured Pride channel."""
        sent = await self._send_pride_message()
        if sent:
            _ = await ctx.send("Posted the Pride message.")
            return
        _ = await ctx.send("I could not post the Pride message. Please check channel access.")

    @app_commands.command(name="pride", description="Send the Pride message.")
    async def pride_slash(self, interaction: discord.Interaction):
        sent = await self._send_pride_message()
        if sent:
            await interaction.response.send_message("Posted the Pride message.", ephemeral=True)
            return
        await interaction.response.send_message(
            "I could not post the Pride message. Please check channel access.",
            ephemeral=True,
        )
