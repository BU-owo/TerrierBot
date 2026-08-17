from __future__ import annotations

import logging
import re

import discord
from discord.ext import commands

from bot import Context, TerrierBot

log = logging.getLogger(__name__)

MOD_ROLE_ID = 1402095379935395934
POLITICS_CHANNEL_ID = 1477468981194391675
RULES_CHANNEL_ID = 1396542143803424768
MOD_REVIEW_CHANNEL_ID = 1401924438341062798
INCOMING_STUDENT_ROLE_ID = 1435381901077647412
POLITICS_ROLE_ID = 1477468718127775824

MIN_TENURE_DAYS = 7

CONDUCT_TEXT = (
    "I agree to not use charged/loaded language like \"evil\" to describe things or groups, "
    "and to not stereotype or generalize a group of people.\n\n"
    "I agree to remain respectful and civil towards your fellow Terrier Hub members by assuming "
    "good intentions, not accusing others, and not personally attacking others."
)
PUNISHMENTS_TEXT = (
    "I understand that participating in #politics is a privilege, and violating any rules will "
    "result in 3 immediate warnings and removal from the channel."
)

AGREE_VALUE = "agree"
DISAGREE_VALUE = "disagree"
UNDERSTAND_VALUE = "understand"
NOT_UNDERSTAND_VALUE = "not_understand"

RADIO_SELECTED = "🔘"
RADIO_UNSELECTED = "⚪"

APPROVE_TEMPLATE = re.compile(r"joinpoliticscog:approve:(?P<user_id>[0-9]+)")
DENY_TEMPLATE = re.compile(r"joinpoliticscog:deny:(?P<user_id>[0-9]+)")


def _is_mod(member: discord.Member) -> bool:
    return any(r.id == MOD_ROLE_ID for r in member.roles)


async def setup(bot: TerrierBot):
    bot.add_dynamic_items(PoliticsApproveButton, PoliticsDenyButton)
    bot.add_view(PoliticsApplicationStartView())
    await bot.add_cog(JoinPoliticsCog(bot))


def _build_application_form_embed() -> discord.Embed:
    embed = discord.Embed(
        description="# Politics Channel Application\nAnswer both questions below, then submit.",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Politics Channel Conduct Code", value=CONDUCT_TEXT, inline=False)
    embed.add_field(name="Punishments", value=PUNISHMENTS_TEXT, inline=False)
    return embed


async def _post_application_for_review(applicant: discord.Member) -> None:
    embed = discord.Embed(
        title="Politics Channel Application",
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Applicant", value=applicant.mention, inline=False)
    embed.add_field(name="Politics Channel Conduct Code", value="I agree", inline=False)
    embed.add_field(name="Punishments", value="I understand", inline=False)
    embed.set_footer(text=f"Applicant ID: {applicant.id}")

    view = discord.ui.View(timeout=None)
    view.add_item(PoliticsApproveButton(applicant.id))
    view.add_item(PoliticsDenyButton(applicant.id))

    channel = applicant.guild.get_channel(MOD_REVIEW_CHANNEL_ID) if applicant.guild else None
    if not isinstance(channel, discord.TextChannel):
        log.error("joinPoliticsCog: mod review channel %d not found or is not a TextChannel", MOD_REVIEW_CHANNEL_ID)
        return

    try:
        await channel.send(
            content=f"{applicant.mention} <@&{MOD_ROLE_ID}>",
            embed=embed,
            view=view,
            allowed_mentions=discord.AllowedMentions(users=True, roles=True, everyone=False),
        )
    except discord.HTTPException:
        log.exception("joinPoliticsCog: failed to post application review message")


# ── Application form (radio-style buttons) ──────────────────────────────────

class ApplicationFormView(discord.ui.View):
    def __init__(self, applicant: discord.Member) -> None:
        super().__init__(timeout=300)
        self.applicant = applicant
        self.conduct_answer: str | None = None
        self.punishments_answer: str | None = None

        self.agree_button = discord.ui.Button(
            label=f"{RADIO_UNSELECTED} I agree", style=discord.ButtonStyle.secondary, row=0
        )
        self.disagree_button = discord.ui.Button(
            label=f"{RADIO_UNSELECTED} I do not agree", style=discord.ButtonStyle.secondary, row=0
        )
        self.understand_button = discord.ui.Button(
            label=f"{RADIO_UNSELECTED} I understand", style=discord.ButtonStyle.secondary, row=1
        )
        self.not_understand_button = discord.ui.Button(
            label=f"{RADIO_UNSELECTED} I do not understand", style=discord.ButtonStyle.secondary, row=1
        )
        self.submit_button = discord.ui.Button(
            label="Submit Application", style=discord.ButtonStyle.success, row=2, disabled=True
        )

        self.agree_button.callback = self._answer_callback("conduct", AGREE_VALUE)
        self.disagree_button.callback = self._answer_callback("conduct", DISAGREE_VALUE)
        self.understand_button.callback = self._answer_callback("punishments", UNDERSTAND_VALUE)
        self.not_understand_button.callback = self._answer_callback("punishments", NOT_UNDERSTAND_VALUE)
        self.submit_button.callback = self._submit

        for item in (
            self.agree_button,
            self.disagree_button,
            self.understand_button,
            self.not_understand_button,
            self.submit_button,
        ):
            self.add_item(item)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.applicant.id:
            await interaction.response.send_message("This isn't your application to fill out.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True  # type: ignore[attr-defined]

    def _answer_callback(self, question: str, value: str):
        async def _callback(interaction: discord.Interaction) -> None:
            if question == "conduct":
                self.conduct_answer = value
                self.agree_button.style = (
                    discord.ButtonStyle.primary if value == AGREE_VALUE else discord.ButtonStyle.secondary
                )
                self.agree_button.label = f"{RADIO_SELECTED if value == AGREE_VALUE else RADIO_UNSELECTED} I agree"
                self.disagree_button.style = (
                    discord.ButtonStyle.primary if value == DISAGREE_VALUE else discord.ButtonStyle.secondary
                )
                self.disagree_button.label = (
                    f"{RADIO_SELECTED if value == DISAGREE_VALUE else RADIO_UNSELECTED} I do not agree"
                )
            else:
                self.punishments_answer = value
                self.understand_button.style = (
                    discord.ButtonStyle.primary if value == UNDERSTAND_VALUE else discord.ButtonStyle.secondary
                )
                self.understand_button.label = (
                    f"{RADIO_SELECTED if value == UNDERSTAND_VALUE else RADIO_UNSELECTED} I understand"
                )
                self.not_understand_button.style = (
                    discord.ButtonStyle.primary if value == NOT_UNDERSTAND_VALUE else discord.ButtonStyle.secondary
                )
                self.not_understand_button.label = (
                    f"{RADIO_SELECTED if value == NOT_UNDERSTAND_VALUE else RADIO_UNSELECTED} I do not understand"
                )

            self.submit_button.disabled = not (self.conduct_answer and self.punishments_answer)
            await interaction.response.edit_message(view=self)

        return _callback

    async def _submit(self, interaction: discord.Interaction) -> None:
        for item in self.children:
            item.disabled = True  # type: ignore[attr-defined]
        self.stop()

        if self.conduct_answer != AGREE_VALUE or self.punishments_answer != UNDERSTAND_VALUE:
            await interaction.response.edit_message(
                content=(
                    "You must agree to the Conduct Code and acknowledge the Punishments policy to "
                    "submit an application. Feel free to start over any time."
                ),
                view=self,
            )
            return

        await interaction.response.edit_message(
            content="Thank you for your submission. The moderators will promptly review your application.",
            view=self,
        )
        await _post_application_for_review(self.applicant)


# ── "Start Application" button ─────────────────────────────────────────────

class PoliticsApplicationStartView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Start Application",
        style=discord.ButtonStyle.primary,
        custom_id="joinpoliticscog:start_application",
    )
    async def start_application(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("This can only be used in the server.", ephemeral=True)
            return

        if any(r.id == POLITICS_ROLE_ID for r in member.roles):
            await interaction.response.send_message("You're already in #politics.", ephemeral=True)
            return

        if any(r.id == INCOMING_STUDENT_ROLE_ID for r in member.roles):
            await interaction.response.send_message(
                "Incoming students can apply for #politics access starting September 1, 2026. "
                "Check back then!",
                ephemeral=True,
            )
            return

        if member.joined_at is not None:
            tenure = discord.utils.utcnow() - member.joined_at
            if tenure.days < MIN_TENURE_DAYS:
                await interaction.response.send_message(
                    f"You need to be a member of the server for at least {MIN_TENURE_DAYS} days "
                    "before applying for #politics.",
                    ephemeral=True,
                )
                return

        await interaction.response.send_message(
            embed=_build_application_form_embed(),
            view=ApplicationFormView(member),
            ephemeral=True,
        )


# ── Approve / Deny buttons (dynamic, survive restarts) ─────────────────────

async def _handle_decision(interaction: discord.Interaction, applicant_id: int, *, approved: bool) -> None:
    reviewer = interaction.user
    if not isinstance(reviewer, discord.Member) or not _is_mod(reviewer):
        await interaction.response.send_message("You don't have permission to review applications.", ephemeral=True)
        return

    guild = interaction.guild
    if guild is None:
        return
    applicant = guild.get_member(applicant_id)

    if approved and applicant is not None:
        role = guild.get_role(POLITICS_ROLE_ID)
        if role is not None:
            try:
                await applicant.add_roles(role, reason=f"Politics application approved by {reviewer}")
            except (discord.Forbidden, discord.HTTPException):
                log.exception("joinPoliticsCog: failed to add politics role to %d", applicant_id)

    mention = applicant.mention if applicant is not None else f"<@{applicant_id}>"
    if approved:
        dm_text = (
            f"{mention} has been accepted to the #politics channel of Terrier Hub.\n\n"
            "Please consult the moderators for any questions. If you would like to be removed "
            "from the channel, please run /leavepolitics"
        )
    else:
        dm_text = (
            f"{mention} has been denied access to the #politics channel of Terrier Hub.\n\n"
            "Please consult the moderators with any questions by submitting a ticket in #rules."
        )

    if applicant is not None:
        try:
            await applicant.send(dm_text)
        except discord.Forbidden:
            log.warning("joinPoliticsCog: could not DM applicant %d (DMs closed)", applicant_id)
    else:
        log.warning("joinPoliticsCog: applicant %d not found in guild, skipping DM", applicant_id)

    embed = interaction.message.embeds[0] if interaction.message and interaction.message.embeds else None
    if embed is not None:
        decision = "Approved" if approved else "Denied"
        embed.color = discord.Color.green() if approved else discord.Color.red()
        embed.set_footer(text=f"{decision} by {reviewer.display_name}")

    await interaction.response.edit_message(embed=embed, view=None)


class PoliticsApproveButton(discord.ui.DynamicItem[discord.ui.Button], template=APPROVE_TEMPLATE.pattern):
    def __init__(self, user_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label="Approve",
                style=discord.ButtonStyle.success,
                custom_id=f"joinpoliticscog:approve:{user_id}",
            )
        )
        self.user_id = user_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Item, match: re.Match[str], /) -> "PoliticsApproveButton":
        return cls(int(match["user_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await _handle_decision(interaction, self.user_id, approved=True)


class PoliticsDenyButton(discord.ui.DynamicItem[discord.ui.Button], template=DENY_TEMPLATE.pattern):
    def __init__(self, user_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label="Deny",
                style=discord.ButtonStyle.danger,
                custom_id=f"joinpoliticscog:deny:{user_id}",
            )
        )
        self.user_id = user_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Item, match: re.Match[str], /) -> "PoliticsDenyButton":
        return cls(int(match["user_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await _handle_decision(interaction, self.user_id, approved=False)


# ── Setup command ───────────────────────────────────────────────────────────

class JoinPoliticsCog(commands.Cog, name="JoinPolitics", description="Politics channel application flow."):
    def __init__(self, bot: TerrierBot) -> None:
        self.bot: TerrierBot = bot

    @commands.hybrid_command(name="joinpolitics", description="Post the #politics application. Mod only.")
    async def joinpolitics(self, ctx: Context) -> None:
        """Post the Politics Channel Application embed in this channel. Mod only."""
        author = ctx.author
        if not isinstance(author, discord.Member) or not _is_mod(author):
            await ctx.send("You don't have permission to use this command.", ephemeral=True)
            return

        embed = discord.Embed(
            description=(
                "# Politics Channel Application\n"
                f"To gain access to <#{POLITICS_CHANNEL_ID}>, you must complete the application "
                f"and agree to the rules in <#{RULES_CHANNEL_ID}>. A history of civil behavior in "
                "the server is required for acceptance.\n\n"
                "Incoming students may apply for access on September 1, 2026 :)\n\n"
                f"Please submit a ticket in <#{RULES_CHANNEL_ID}> if you have any questions."
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Politics Channel Conduct Code", value=CONDUCT_TEXT, inline=False)
        embed.add_field(name="Punishments", value=PUNISHMENTS_TEXT, inline=False)

        await ctx.send(embed=embed, view=PoliticsApplicationStartView())
