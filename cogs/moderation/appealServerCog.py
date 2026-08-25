from __future__ import annotations

import discord
from discord.ext import commands

from bot import Context, TerrierBot
from ..logging.logConfig import LogChannels, LogColors, MOD_ROLE_ID, get_log_channel

# Dedicated appeals server — TerrierBot is a member of both this and the main
# Terrier Hub server, so a banned user can still interact with the button
# (component interactions from a DM back to the bot are silently dropped once
# the user no longer shares a guild with it — see banCog.py's DM appeal flow).
APPEALS_GUILD_ID = 1541626494122598491
MAIN_GUILD_ID = 1396541818245484665

APPEAL_BUTTON_CUSTOM_ID = "open_ban_appeal"


async def setup(bot: TerrierBot):
    await bot.add_cog(AppealServerCog(bot))


class _AppealModal(discord.ui.Modal, title="Ban Appeal"):
    reason_input = discord.ui.TextInput(
        label="Why should we reconsider?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Defer + followup rather than a single send_message, since the
        # fetch_ban lookup + log-channel send below can outrun the 3s window.
        await interaction.response.defer(ephemeral=True, thinking=True)

        bot = interaction.client
        main_guild = bot.get_guild(MAIN_GUILD_ID)
        if main_guild is None:
            await interaction.followup.send(
                "Couldn't reach Terrier Hub right now — please try again later or contact a moderator another way.",
                ephemeral=True,
            )
            return

        try:
            ban_entry = await main_guild.fetch_ban(discord.Object(id=interaction.user.id))
        except discord.NotFound:
            await interaction.followup.send(
                "You don't appear to be banned from Terrier Hub.", ephemeral=True
            )
            return

        log_channel = get_log_channel(bot, LogChannels.MOD)
        if log_channel is not None:
            embed = discord.Embed(
                title="📨 Ban appeal received",
                description=(
                    f"**Appealing user:** {interaction.user} (`{interaction.user.id}`)\n"
                    f"**Original ban reason:** {ban_entry.reason or '*Unknown — could not be looked up*'}\n\n"
                    f"**Appeal:**\n{self.reason_input.value}"
                ),
                color=LogColors.MOD,
                timestamp=discord.utils.utcnow(),
            )
            try:
                await log_channel.send(
                    content=f"<@&{MOD_ROLE_ID}>",
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions(roles=True, users=False, everyone=False),
                )
            except discord.HTTPException:
                pass

        await interaction.followup.send(
            "Your appeal has been sent to the moderators.", ephemeral=True
        )


class _AppealButtonView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Appeal my ban",
        style=discord.ButtonStyle.primary,
        custom_id=APPEAL_BUTTON_CUSTOM_ID,
    )
    async def appeal_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.guild_id != APPEALS_GUILD_ID:
            await interaction.response.send_message(
                "This button can only be used in the appeals server.", ephemeral=True
            )
            return
        await interaction.response.send_modal(_AppealModal())


class AppealServerCog(
    commands.Cog,
    name="AppealServer",
    description="Ban-appeal button + modal flow for the dedicated appeals server. Owner only to set up.",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot
        # Fixed custom_id, single static view — registering it here (rather
        # than only when =postappealbutton is run) keeps the button working
        # across restarts without needing that command run again.
        self.bot.add_view(_AppealButtonView())

    @commands.command(name="postappealbutton")
    @commands.is_owner()
    async def postappealbutton(self, ctx: Context) -> None:
        """Post the ban-appeal button in this channel. Run once, manually. (Owner only)"""
        if ctx.guild is None or ctx.guild.id != APPEALS_GUILD_ID:
            await ctx.send("This command can only be run in the appeals server.")
            return

        embed = discord.Embed(
            title="Ban Appeals",
            description=(
                "If you were banned from Terrier Hub and want to appeal, click the button below."
            ),
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=embed, view=_AppealButtonView())
