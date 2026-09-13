from __future__ import annotations

import logging
import re

import discord
from discord.ext import commands

from bot import Context, TerrierBot
from ..logging.caseLogCog import record_case
from ..logging.logConfig import LogChannels, get_log_channel, register_queue_item, resolve_queue_item
from cogs.logging.logConfig import MOD_ROLE_ID

log = logging.getLogger(__name__)

POLITICS_CHANNEL_ID = 1477468981194391675
RULES_CHANNEL_ID = 1396542143803424768
MOD_REVIEW_CHANNEL_ID = LogChannels.QUEUE
POLITICS_ROLE_ID = 1477468718127775824

MIN_TENURE_DAYS = 7

AGREEMENT_TEXT = (
    "Politics Channel Agreement:\n\n"
    "1. I agree to be respectful and civil towards your fellow Terrier Hub members by assuming "
    "good intentions, not accusing others, and not personally attacking others.\n"
    "2. I understand that adherence to radical ideologies that call for harm against others is "
    "unwelcome in this channel.\n"
    "3. I understand that general rules of Terrier Hub apply to this channel as well.\n"
    "4. I understand that breaches in rules 1 and 2 are punishable by moderators of this channel, "
    "with potential forms of punishment being warnings and mutes. Obtaining three warnings equals "
    "expulsion from this channel.\n"
    "5. I understand that I may leave the channel on my own discretion, using the command "
    "`/leavepolitics`."
)

AGREE_VALUE = "agree"
DISAGREE_VALUE = "disagree"

APPROVE_TEMPLATE = re.compile(r"joinpoliticscog:approve:(?P<user_id>[0-9]+)")
DENY_TEMPLATE = re.compile(r"joinpoliticscog:deny:(?P<user_id>[0-9]+)")


def _is_mod(member: discord.Member) -> bool:
    return any(r.id == MOD_ROLE_ID for r in member.roles)


async def setup(bot: TerrierBot):
    bot.add_dynamic_items(PoliticsApproveButton, PoliticsDenyButton)
    bot.add_view(PoliticsApplicationStartView())
    await bot.add_cog(JoinPoliticsCog(bot))


async def _post_application_for_review(applicant: discord.Member) -> None:
    embed = discord.Embed(
        title="Politics Channel Application",
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Applicant", value=applicant.mention, inline=False)
    embed.add_field(name="Politics Channel Agreement", value="I agree", inline=False)
    embed.set_footer(text=f"Applicant ID: {applicant.id}")

    view = discord.ui.View(timeout=None)
    view.add_item(PoliticsApproveButton(applicant.id))
    view.add_item(PoliticsDenyButton(applicant.id))

    channel = applicant.guild.get_channel(MOD_REVIEW_CHANNEL_ID) if applicant.guild else None
    if not isinstance(channel, discord.TextChannel):
        log.error("joinPoliticsCog: mod review channel %d not found or is not a TextChannel", MOD_REVIEW_CHANNEL_ID)
        return

    try:
        queue_message = await channel.send(
            content=applicant.mention,
            embed=embed,
            view=view,
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )
    except discord.HTTPException:
        log.exception("joinPoliticsCog: failed to post application review message")
        return

    register_queue_item(message_id=queue_message.id, channel_id=channel.id)


# ── Application modal (native radio-button questions) ───────────────────────

class PoliticsApplicationModal(discord.ui.Modal, title="Politics Channel Application"):
    agreement_text = discord.ui.TextDisplay(AGREEMENT_TEXT)
    agreement_field = discord.ui.Label(
        text="Politics Channel Agreement",
        component=discord.ui.RadioGroup(
            options=[
                discord.RadioGroupOption(label="I agree", value=AGREE_VALUE),
                discord.RadioGroupOption(label="I do not agree", value=DISAGREE_VALUE),
            ],
        ),
    )

    def __init__(self, applicant: discord.Member) -> None:
        super().__init__()
        self.applicant = applicant

    async def on_submit(self, interaction: discord.Interaction) -> None:
        agreement_radio = self.agreement_field.component
        assert isinstance(agreement_radio, discord.ui.RadioGroup)

        if agreement_radio.value != AGREE_VALUE:
            await interaction.response.send_message(
                "You must agree to the Politics Channel Agreement to submit an application. "
                "Feel free to start over any time.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Thank you for your submission. The moderators will promptly review your application.",
            ephemeral=True,
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

        if member.joined_at is not None:
            tenure = discord.utils.utcnow() - member.joined_at
            if tenure.days < MIN_TENURE_DAYS:
                await interaction.response.send_message(
                    f"You need to be a member of the server for at least {MIN_TENURE_DAYS} days "
                    "before applying for #politics.",
                    ephemeral=True,
                )
                return

        await interaction.response.send_modal(PoliticsApplicationModal(member))


# ── Approve / Deny buttons (dynamic, survive restarts) ─────────────────────

async def _handle_decision(interaction: discord.Interaction, applicant_id: int, *, approved: bool) -> None:
    reviewer = interaction.user
    if not isinstance(reviewer, discord.Member) or not _is_mod(reviewer):
        await interaction.response.send_message("You don't have permission to review applications.", ephemeral=True)
        return

    message = interaction.message
    # Idempotency guard: the buttons are removed (view=None) as the very
    # first thing once a decision is made, below. If they're already gone,
    # this is a duplicate click — e.g. a mod clicking again because the
    # first click was slow to visibly respond — racing in before Discord's
    # client re-rendered the message. Bail out instead of reprocessing.
    if message is not None and not message.components:
        await interaction.response.send_message(
            "This application has already been handled.", ephemeral=True
        )
        return

    if message is not None:
        resolve_queue_item(message.id)

    embed = message.embeds[0] if message and message.embeds else None
    if embed is not None:
        decision = "Approved" if approved else "Denied"
        embed.color = discord.Color.green() if approved else discord.Color.red()
        embed.set_footer(text=f"{decision} by {reviewer.display_name}")

    # Respond immediately — remove the buttons and update the embed right
    # away, before the slower role-add/DM calls below, so a mod always sees
    # the click register instantly instead of wondering if it landed. This
    # delay (both network calls ran before any response was sent) is what
    # let a second click race in and send the acceptance DM twice.
    try:
        await interaction.response.edit_message(embed=embed, view=None)
    except discord.HTTPException:
        pass

    try:
        record_case(
            user_id=applicant_id,
            moderator_id=reviewer.id,
            case_type="politics_approve" if approved else "politics_deny",
            reason=None,
        )
    except Exception:
        log.exception(
            "joinPoliticsCog: failed to record case log entry for politics decision on %d", applicant_id
        )

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
            "Please consult the moderators for any questions.\n\n"
            f"{AGREEMENT_TEXT}"
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

    # Permanent record of the decision in mod-log — a new message, not an
    # edit, and with no buttons (the message above, in the mod queue, is
    # where decisions happen). Best-effort: never blocks the rest of this flow.
    if embed is not None:
        mod_log_channel = get_log_channel(interaction.client, LogChannels.MOD)
        if mod_log_channel is not None:
            try:
                await mod_log_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                pass

    try:
        await interaction.followup.send(
            f"Application {'approved' if approved else 'denied'}.", ephemeral=True
        )
    except discord.HTTPException:
        pass


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
                f"Please submit a ticket in <#{RULES_CHANNEL_ID}> if you have any questions."
            ),
            color=discord.Color.blurple(),
        )

        await ctx.send(embed=embed, view=PoliticsApplicationStartView())