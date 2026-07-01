import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot import Context, TerrierBot

FEEDBACK_CHANNEL_ID = 1401924438341062798
FEEDBACK_ROLE_ID = 1402095379935395934


async def setup(bot: TerrierBot):
    # Register the persistent view so button interactions survive restarts
    bot.add_view(FeedbackView(bot))
    await bot.add_cog(FeedbackCog(bot))


class FeedbackModal(discord.ui.Modal, title="Anonymous Feedback"):
    feedback_input = discord.ui.TextInput(
        label="Your feedback",
        style=discord.TextStyle.paragraph,
        placeholder="Share your thoughts anonymously...",
        max_length=1000,
        required=True,
    )

    def __init__(self, bot: TerrierBot) -> None:
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Respond ephemerally first — this acknowledges the interaction
        await interaction.response.send_message(
            "Your feedback has been submitted anonymously. Thank you!",
            ephemeral=True,
        )

        # Build the embed from the submitted text only.
        # No user identity, ID, username, or any metadata is included here
        # or logged anywhere — submissions are fully anonymous.
        text = self.feedback_input.value
        # Defensively truncate to Discord's embed description limit (4096 chars),
        # even though the TextInput is already capped at 1000.
        if len(text) > 4096:
            text = text[:4093] + "..."

        embed = discord.Embed(
            title="Anonymous Feedback",
            description=text,
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )

        channel = self.bot.get_channel(FEEDBACK_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            logging.error(
                "feedbackCog: feedback channel %d not found or is not a TextChannel",
                FEEDBACK_CHANNEL_ID,
            )
            return

        try:
            await channel.send(
                content=f"<@&{FEEDBACK_ROLE_ID}>",
                embed=embed,
            )
        except discord.HTTPException as e:
            logging.error("feedbackCog: failed to send feedback embed: %s", e)


class FeedbackView(discord.ui.View):
    def __init__(self, bot: TerrierBot) -> None:
        # timeout=None makes this a persistent view
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Submit Feedback",
        emoji="📝",
        style=discord.ButtonStyle.primary,
        # custom_id is required for persistent views
        custom_id="feedbackcog:submit",
    )
    async def submit_button(
        self, interaction: discord.Interaction, button: discord.ui.Button  # type: ignore[type-arg]
    ) -> None:
        await interaction.response.send_modal(FeedbackModal(self.bot))


class FeedbackCog(commands.Cog, name="Feedback", description="Anonymous feedback submission."):

    def __init__(self, bot: TerrierBot) -> None:
        self.bot: TerrierBot = bot
        logging.info("Feedback Cog Ready")

    # Slash command: /feedbacksetup
    # Also available as a prefix command: =feedbacksetup
    # Requires Manage Server permission.

    @app_commands.command(
        name="feedbacksetup",
        description="Post the anonymous feedback prompt in this channel. Requires Manage Server.",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def feedbacksetup_slash(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Submit Anonymous Feedback",
            description=(
                    "**Your identity is never recorded.** No username, ID, or metadata is logged."
                    " Only the text you write is forwarded to the moderation team.\n\n"
            ),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, view=FeedbackView(self.bot))

    @commands.command(name="feedbacksetup")
    @commands.has_permissions(manage_guild=True)
    async def feedbacksetup_prefix(self, ctx: Context) -> None:
        """Post the anonymous feedback prompt in this channel. Requires Manage Server."""
        embed = discord.Embed(
            title="Submit Anonymous Feedback",
            description=(
                    "**Your identity is never recorded.** No username, ID, or metadata is logged."
                    " Only the text you write is forwarded to the moderation team.\n\n"
            ),
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=embed, view=FeedbackView(self.bot))
