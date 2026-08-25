from __future__ import annotations

import json
import logging
import os
import time
import uuid

import discord
from discord import app_commands
from discord.ext import commands, tasks

from ..logging.logConfig import LogChannels

log = logging.getLogger(__name__)

MOD_ROLE_ID = 1402095379935395934
MODVOTE_RESULTS_CHANNEL_ID = LogChannels.MOD

MAX_OPTIONS = 10  # buttons must stay under Discord's 25-component cap
CHECK_INTERVAL_SECONDS = 45

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_VOTES_FILE = os.path.join(_DATA_DIR, "modvotes.json")


def _has_mod_role(user: discord.abc.User | discord.Member) -> bool:
    if not isinstance(user, discord.Member):
        return False
    return any(r.id == MOD_ROLE_ID for r in user.roles)


# ── Group ─────────────────────────────────────────────────────────────────────

class ModVoteGroup(app_commands.Group):
    """All /modvote subcommands are mod-role-only; enforced once here."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not _has_mod_role(interaction.user):
            await interaction.response.send_message(
                "You don't have permission to use this command.", ephemeral=True
            )
            return False
        return True


# ── Voting view ───────────────────────────────────────────────────────────────

class ModVoteOptionButton(discord.ui.Button):
    def __init__(self, cog: "ModVoteCog", vote_id: str, option_index: int, label: str):
        super().__init__(
            label=label[:80],
            style=discord.ButtonStyle.primary,
            custom_id=f"modvote:{vote_id}:opt:{option_index}",
        )
        self.cog = cog
        self.vote_id = vote_id
        self.option_index = option_index

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.cog.handle_vote_click(interaction, self.vote_id, self.option_index)


class ModVoteView(discord.ui.View):
    def __init__(self, cog: "ModVoteCog", vote_id: str, options: list[str]):
        super().__init__(timeout=None)
        for i, opt in enumerate(options):
            self.add_item(ModVoteOptionButton(cog, vote_id, i, opt))


# ── Cog ───────────────────────────────────────────────────────────────────────

class ModVoteCog(commands.Cog, name="ModVote", description="Anonymous mod votes on disciplining a member."):

    modvote = ModVoteGroup(name="modvote", description="Start and manage anonymous mod votes.")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data: dict = {"votes": {}, "sticky_by_channel": {}}
        self._load()

        # Re-register persistent views for votes that were still open at last shutdown.
        for vote_id, vote in self.data["votes"].items():
            if vote.get("closed") or not vote.get("message_id"):
                continue
            view = ModVoteView(self, vote_id, vote["options"])
            self.bot.add_view(view, message_id=vote["message_id"])

        self.check_expired.start()

    def cog_unload(self) -> None:
        self.check_expired.cancel()

    # ── Persistence ────────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not os.path.exists(_VOTES_FILE):
            os.makedirs(_DATA_DIR, exist_ok=True)
            self._save()
            return
        with open(_VOTES_FILE, "r", encoding="utf-8") as f:
            self.data = json.load(f)
        self.data.setdefault("votes", {})
        self.data.setdefault("sticky_by_channel", {})

    def _save(self) -> None:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_VOTES_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _compute_counts(self, vote: dict) -> list[int]:
        counts = [0] * len(vote["options"])
        for option_index in vote["votes"].values():
            if 0 <= option_index < len(counts):
                counts[option_index] += 1
        return counts

    def _target_display(self, vote: dict) -> str:
        guild = self.bot.get_guild(vote["guild_id"])
        member = guild.get_member(vote["target_id"]) if guild else None
        if member is not None:
            return f"{member.display_name} ({member.id})"
        return f"Unknown Member ({vote['target_id']})"

    def _build_open_vote_embed(self, vote: dict) -> discord.Embed:
        # While a vote is open, only the total count is ever shown — never a
        # per-option breakdown. The breakdown is revealed once, in the
        # results embed posted to the results channel when the vote closes.
        option_lines = "\n".join(f"• {opt}" for opt in vote["options"])
        total = len(vote["votes"])

        embed = discord.Embed(
            title="🗳️ Mod Vote",
            description=f"Target: {self._target_display(vote)}",
            color=discord.Color.orange(),
        )
        embed.add_field(name="Options", value=option_lines or "—", inline=False)
        embed.add_field(name="Votes cast", value=f"{total} votes cast so far", inline=True)
        embed.add_field(name="Quorum required", value=str(vote["quorum"]), inline=True)
        embed.add_field(name="Closes", value=f"<t:{vote['close_ts']}:R>", inline=True)
        embed.set_footer(text=f"Vote ID: {vote['vote_id']}")
        return embed

    def _build_closed_sticky_embed(self, vote: dict) -> discord.Embed:
        # No counts here either — just a pointer to the results embed.
        embed = discord.Embed(
            title="🗳️ Mod Vote (Closed)",
            description=f"Target: {self._target_display(vote)}",
            color=discord.Color.dark_grey(),
        )
        embed.add_field(
            name="Status",
            value="Voting closed — see the results posted below.",
            inline=False,
        )
        embed.set_footer(text=f"Vote ID: {vote['vote_id']}")
        return embed

    # ── Vote lifecycle ────────────────────────────────────────────────────────

    async def _close_vote(self, vote_id: str) -> None:
        vote = self.data["votes"].get(vote_id)
        if vote is None or vote["closed"]:
            return

        vote["closed"] = True
        vote["closed_ts"] = int(time.time())

        channel = self.bot.get_channel(vote["channel_id"])
        if channel is not None and vote.get("message_id"):
            try:
                msg = await channel.fetch_message(vote["message_id"])
            except (discord.NotFound, discord.HTTPException):
                msg = None
            if msg is not None:
                try:
                    await msg.edit(embed=self._build_closed_sticky_embed(vote), view=None)
                except discord.HTTPException:
                    pass

        ch_key = str(vote["channel_id"])
        if self.data["sticky_by_channel"].get(ch_key) == vote_id:
            del self.data["sticky_by_channel"][ch_key]

        self._save()
        await self._post_results(vote)

    def _build_results_embed(self, vote: dict) -> discord.Embed:
        options = vote["options"]
        counts = self._compute_counts(vote)
        total = sum(counts)
        quorum = vote["quorum"]
        quorum_met = total >= quorum

        option_lines = "\n".join(
            f"**{opt}** — {counts[i]} vote(s)" for i, opt in enumerate(options)
        )

        embed = discord.Embed(
            title="🗳️ Mod Vote Results",
            description=f"Target: {self._target_display(vote)}",
            color=discord.Color.green() if quorum_met else discord.Color.dark_grey(),
        )
        embed.add_field(name="Options", value=option_lines or "—", inline=False)
        embed.add_field(name="Total votes", value=str(total), inline=True)
        embed.add_field(
            name="Quorum", value=f"{total}/{quorum} ({'met' if quorum_met else 'not met'})", inline=True
        )

        if quorum_met:
            max_count = max(counts) if counts else 0
            leaders = [options[i] for i, c in enumerate(counts) if c == max_count]
            if max_count == 0:
                outcome = "No votes were cast for any option."
            elif len(leaders) > 1:
                outcome = "Tied — no clear outcome, mod judgment required."
            else:
                outcome = f"**{leaders[0]}**"
        else:
            outcome = "Quorum not reached — result does not count."
        embed.add_field(name="Outcome", value=outcome, inline=False)
        embed.set_footer(text=f"Vote ID: {vote['vote_id']}")
        return embed

    async def _post_results(self, vote: dict) -> None:
        embed = self._build_results_embed(vote)

        # Mod-logs is for record-keeping, not where mods actually read results —
        # always post there, but also post the same results back in the channel
        # the vote was run in so mods see them without hunting through logs.
        log_channel = self.bot.get_channel(MODVOTE_RESULTS_CHANNEL_ID)
        if log_channel is not None:
            try:
                await log_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                log.warning("modvoteCog: failed to post results for vote %s", vote["vote_id"])
        else:
            log.warning("modvoteCog: results channel %s not found/visible", MODVOTE_RESULTS_CHANNEL_ID)

        if vote["channel_id"] != MODVOTE_RESULTS_CHANNEL_ID:
            origin_channel = self.bot.get_channel(vote["channel_id"])
            if origin_channel is not None:
                try:
                    await origin_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
                except discord.HTTPException:
                    log.warning(
                        "modvoteCog: failed to post results in origin channel for vote %s", vote["vote_id"]
                    )

    @tasks.loop(seconds=CHECK_INTERVAL_SECONDS)
    async def check_expired(self) -> None:
        now = int(time.time())
        expired = [
            vote_id for vote_id, vote in self.data["votes"].items()
            if not vote["closed"] and vote["close_ts"] <= now
        ]
        for vote_id in expired:
            await self._close_vote(vote_id)

    @check_expired.before_loop
    async def before_check_expired(self) -> None:
        await self.bot.wait_until_ready()

    # ── Button callbacks ──────────────────────────────────────────────────────

    async def handle_vote_click(self, interaction: discord.Interaction, vote_id: str, option_index: int) -> None:
        if not _has_mod_role(interaction.user):
            await interaction.response.send_message("You don't have permission to vote.", ephemeral=True)
            return

        vote = self.data["votes"].get(vote_id)
        if vote is None or vote["closed"] or not (0 <= option_index < len(vote["options"])):
            await interaction.response.send_message("This vote has closed.", ephemeral=True)
            return

        vote["votes"][str(interaction.user.id)] = option_index
        self._save()

        try:
            await interaction.response.edit_message(embed=self._build_open_vote_embed(vote))
        except discord.HTTPException:
            pass

        option_label = vote["options"][option_index]
        try:
            await interaction.followup.send(f"Your vote has been recorded: {option_label}.", ephemeral=True)
        except discord.HTTPException:
            pass

    # ── /modvote start ────────────────────────────────────────────────────────

    @modvote.command(name="start", description="Start an anonymous mod vote on disciplining a member.")
    @app_commands.describe(
        target="The member the vote concerns",
        options="Comma-separated choices, e.g. \"Warn, Timeout, No action\"",
        duration_minutes="How long the vote stays open, in minutes",
        quorum="Minimum number of votes required for the result to count",
    )
    async def modvote_start(
        self,
        interaction: discord.Interaction,
        target: discord.Member,
        options: str,
        duration_minutes: int,
        quorum: int,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        if interaction.guild is None or not isinstance(interaction.channel, discord.abc.Messageable):
            await interaction.followup.send("This command can only be used in a server text channel.", ephemeral=True)
            return

        parsed_options = [o.strip() for o in options.split(",")]
        parsed_options = [o for o in parsed_options if o]
        if len(parsed_options) < 2:
            await interaction.followup.send("Provide at least two comma-separated options.", ephemeral=True)
            return
        if len(parsed_options) > MAX_OPTIONS:
            await interaction.followup.send(f"Too many options — max {MAX_OPTIONS}.", ephemeral=True)
            return
        if duration_minutes < 1:
            await interaction.followup.send("Duration must be at least 1 minute.", ephemeral=True)
            return
        if quorum < 1:
            await interaction.followup.send("Quorum must be at least 1.", ephemeral=True)
            return

        channel = interaction.channel
        ch_key = str(channel.id)
        existing_vote_id = self.data["sticky_by_channel"].get(ch_key)
        if existing_vote_id is not None:
            existing = self.data["votes"].get(existing_vote_id)
            if existing is not None and not existing["closed"]:
                await interaction.followup.send(
                    "There's already an active modvote in this channel — close it before starting another.",
                    ephemeral=True,
                )
                return
            # Stale entry (vote closed but map wasn't cleared) — safe to drop.
            del self.data["sticky_by_channel"][ch_key]

        vote_id = uuid.uuid4().hex
        close_ts = int(time.time()) + duration_minutes * 60

        vote = {
            "vote_id": vote_id,
            "guild_id": interaction.guild.id,
            "channel_id": channel.id,
            "message_id": None,
            "target_id": target.id,
            "options": parsed_options,
            "votes": {},
            "quorum": quorum,
            "close_ts": close_ts,
            "created_by": interaction.user.id,
            "closed": False,
            "closed_ts": None,
        }
        self.data["votes"][vote_id] = vote

        view = ModVoteView(self, vote_id, parsed_options)
        try:
            msg = await channel.send(
                embed=self._build_open_vote_embed(vote),
                view=view,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            del self.data["votes"][vote_id]
            await interaction.followup.send("Failed to post the vote message.", ephemeral=True)
            return

        vote["message_id"] = msg.id
        self.bot.add_view(view, message_id=msg.id)

        self.data["sticky_by_channel"][ch_key] = vote_id
        self._save()

        await interaction.followup.send(
            f"Started modvote `{vote_id}` in {channel.mention}, closing <t:{close_ts}:R>.", ephemeral=True
        )

    # ── /modvote close ────────────────────────────────────────────────────────

    async def _open_vote_id_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        choices: list[app_commands.Choice[str]] = []
        for vote_id, vote in self.data["votes"].items():
            if vote["closed"]:
                continue
            label = f"{vote_id} — target {vote['target_id']}"[:100]
            if current.lower() in vote_id.lower():
                choices.append(app_commands.Choice(name=label, value=vote_id))
        return choices[:25]

    @modvote.command(name="close", description="Manually close an open mod vote early.")
    @app_commands.describe(vote_id="The vote to close — leave blank to close this channel's active vote.")
    @app_commands.autocomplete(vote_id=_open_vote_id_autocomplete)
    async def modvote_close(self, interaction: discord.Interaction, vote_id: str | None = None) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        if vote_id is None:
            if interaction.channel is None:
                await interaction.followup.send("Specify a vote_id.", ephemeral=True)
                return
            vote_id = self.data["sticky_by_channel"].get(str(interaction.channel.id))
            if vote_id is None:
                await interaction.followup.send(
                    "No active modvote in this channel — specify a vote_id.", ephemeral=True
                )
                return

        vote = self.data["votes"].get(vote_id)
        if vote is None:
            await interaction.followup.send("Unknown vote_id.", ephemeral=True)
            return
        if vote["closed"]:
            await interaction.followup.send("That vote is already closed.", ephemeral=True)
            return

        await self._close_vote(vote_id)
        await interaction.followup.send(f"Closed vote `{vote_id}` and posted results.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ModVoteCog(bot))
