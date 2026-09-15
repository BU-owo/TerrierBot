from __future__ import annotations

import json
import logging
import os
import re
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot import Context, TerrierBot
from .warningsCog import RULES
from ..logging.caseLogCog import record_case
from ..logging.logConfig import (
    LogChannels,
    LogColors,
    MOD_ROLE_ID,
    format_duration,
    get_log_channel,
    suppress_mod_log,
    user_line,
)

_MENTION_RE = re.compile(r"^<@!?(\d+)>$")

# Rule 8 (scams / unapproved self-promo) bans purge the target's recent
# messages server-wide via Discord's native delete_message_seconds — scam
# links/pings tend to be spammed across multiple channels right before the
# ban, so a scoped purge catches those without a manual mod sweep. This is
# just the default for that one rule — =ban's own `delete_history` param lets
# a mod pick any window up to Discord's hard cap (below) for any ban.
_RULE_8_PURGE_SECONDS = 4 * 60 * 60
_MAX_DELETE_HISTORY_SECONDS = 7 * 24 * 60 * 60  # Discord's own cap on delete_message_seconds



def _parse_user_id(raw: str) -> int | None:
    """Accept a raw snowflake or a mention like <@123> / <@!123>."""
    raw = raw.strip()
    match = _MENTION_RE.match(raw)
    if match:
        raw = match.group(1)
    return int(raw) if raw.isdigit() else None


# ── Temp-ban duration parsing ────────────────────────────────────────────────
# Same shorthand as timeoutCog.py (30m, 2h, 1d, 45s). timeoutCog's parser is
# name-mangled private (`_parse_duration_seconds`) — not meant for cross-cog
# import — so it's duplicated here rather than reaching into that module or
# standing up a shared utils module for one function. Unlike timeouts, bans
# aren't capped at 28 days by Discord's API, so there's no clamp here.
_DURATION_RE = re.compile(r"^(\d+)\s*([smhd])$", re.IGNORECASE)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_DURATION_FORMAT_HELP = "Use a number + unit: `30m`, `2h`, `1d`, `45s` (s/m/h/d)."


def _parse_duration_seconds(duration_str: str) -> int | None:
    match = _DURATION_RE.match(duration_str.strip().lower().replace(" ", ""))
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    seconds = amount * _UNIT_SECONDS[unit]
    return seconds if seconds > 0 else None


class _DurationArg(commands.Converter[str]):
    """Validates a =ban duration token, raising instead of accepting any
    string. `duration` is Optional in the =ban signature below, so when this
    raises, discord.py's built-in Optional-converter fallback rewinds the
    text-command parser to the un-consumed word instead of erroring — that
    word then flows into `reason` as ordinary text. Without this raise (e.g.
    if `duration` were typed as plain `str`), the identity conversion always
    "succeeds", so the first word after the member would always get eaten as
    a duration attempt even when it's actually the start of the reason.
    Slash invocations aren't affected — duration is already its own input
    box there, so a bad value still raises normally.
    """

    async def convert(self, ctx: Context, argument: str) -> str:
        if _parse_duration_seconds(argument) is None:
            raise commands.BadArgument(f"Couldn't parse `{argument}` as a duration. {_DURATION_FORMAT_HELP}")
        return argument


class _DeleteHistoryArg(commands.Converter[str]):
    """Validates =ban's delete_history token. This can't reuse _DurationArg
    as-is: =ban already has one bare duration-shaped optional positional
    param (temp-ban length) immediately before this one, and a prefix parser
    consumes tokens left-to-right — a second bare `3d`-shaped token would
    always get greedily eaten by `duration` first, leaving no way to set
    delete_history alone (e.g. "permanent ban + purge their spam") without
    it silently turning into a temp ban instead. So prefix invocations must
    write this one as `purge:3d` to disambiguate; slash invocations get a
    separate, unambiguous labeled input box, so a plain `3d` works there.
    """

    async def convert(self, ctx: Context, argument: str) -> str:
        if ctx.interaction is not None:
            if _parse_duration_seconds(argument) is None:
                raise commands.BadArgument(f"Couldn't parse `{argument}` as a duration. {_DURATION_FORMAT_HELP}")
            return argument

        match = re.match(r"^purge:(.+)$", argument.strip(), re.IGNORECASE)
        if not match:
            raise commands.BadArgument("Not a delete_history token.")
        duration_str = match.group(1)
        if _parse_duration_seconds(duration_str) is None:
            raise commands.BadArgument(f"Couldn't parse `{duration_str}` as a duration. {_DURATION_FORMAT_HELP}")
        return duration_str


# ── Temp-ban persistence ─────────────────────────────────────────────────────
# Temp-bans need fast, guild-scoped lookups on every tick of the background
# expiry loop, which the case log's append-only `cases` table isn't shaped
# for — so this stays a standalone gitignored JSON file rather than a table.
# Keyed by "guild_id:user_id" for O(1) lookup/removal.
# banCog.py is two folders below the repo root (cogs/moderation/) — three
# dirname() calls are needed to reach it, matching every other cog's own
# _DATA_DIR (e.g. squadPingCog.py). This used to be two, which quietly
# pointed at a nonexistent cogs/data/ instead of the shared data/ folder.
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
_TEMPBANS_FILE = os.path.join(_DATA_DIR, "tempbans.json")


async def setup(bot: TerrierBot):
    await bot.add_cog(BanCog(bot))


# ── Cog ───────────────────────────────────────────────────────────────────────

class BanCog(
    commands.Cog,
    name="Ban",
    description="Bans/unbans a member.",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot
        self.tempbans: dict[str, dict] = self.load_tempbans()
        self._tempban_check.start()

    def cog_unload(self) -> None:
        self._tempban_check.cancel()

    # ── Shared helpers ───────────────────────────────────────────────────────

    @staticmethod
    async def _require_mod(ctx: Context) -> bool:
        if not isinstance(ctx.author, discord.Member) or not any(
            r.id == MOD_ROLE_ID for r in ctx.author.roles
        ):
            await ctx.send("Oops! You can't run that... mods only!", ephemeral=True)
            return False
        return True

    # ── Temp-ban persistence ────────────────────────────────────────────────

    @staticmethod
    def load_tempbans() -> dict[str, dict]:
        if not os.path.exists(_TEMPBANS_FILE):
            os.makedirs(_DATA_DIR, exist_ok=True)
            with open(_TEMPBANS_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f)
            return {}
        with open(_TEMPBANS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_tempbans(self) -> None:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_TEMPBANS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.tempbans, f, indent=2)

    def _add_tempban(self, *, guild_id: int, user_id: int, unban_at: float, reason: str) -> None:
        key = f"{guild_id}:{user_id}"
        self.tempbans[key] = {
            "user_id": user_id,
            "guild_id": guild_id,
            "unban_at": unban_at,
            "reason": reason,
        }
        self.save_tempbans()

    def _remove_tempban(self, *, guild_id: int, user_id: int) -> None:
        key = f"{guild_id}:{user_id}"
        if key in self.tempbans:
            del self.tempbans[key]
            self.save_tempbans()

    # ── Auto-unban background task ──────────────────────────────────────────

    @tasks.loop(seconds=60)
    async def _tempban_check(self) -> None:
        now_ts = discord.utils.utcnow().timestamp()
        for key, record in list(self.tempbans.items()):
            if record["unban_at"] > now_ts:
                continue

            guild = self.bot.get_guild(record["guild_id"])
            if guild is None:
                continue  # bot isn't currently in that guild — retry next tick

            target = discord.Object(id=record["user_id"])
            try:
                await guild.unban(target, reason="Temporary ban expired")
            except discord.NotFound:
                pass  # already unbanned some other way — still clean up below
            except discord.HTTPException:
                continue  # transient failure — leave the record, retry next tick

            del self.tempbans[key]
            self.save_tempbans()

            # The unban above triggers on_member_unban; suppress ModLogCog's
            # duplicate before posting our own (richer) embed for it below.
            suppress_mod_log(record["user_id"], "unban")

            await self._log_auto_unban(
                guild=guild,
                user_id=record["user_id"],
                original_reason=record.get("reason") or "No reason provided",
            )
            self._record_unban_case(user_id=record["user_id"])

    @_tempban_check.before_loop
    async def _before_tempban_check(self) -> None:
        await self.bot.wait_until_ready()

    async def _log_auto_unban(self, *, guild: discord.Guild, user_id: int, original_reason: str) -> None:
        log_channel = get_log_channel(self.bot, LogChannels.MOD)
        if log_channel is None:
            return

        user_display = f"`{user_id}`"
        try:
            user = await self.bot.fetch_user(user_id)
            user_display = f"{user} (`{user_id}`)"
        except discord.HTTPException:
            pass

        embed = discord.Embed(
            title="⏰ Temporary ban expired — auto-unbanned",
            description=(
                f"**Target:** {user_display}\n"
                f"**Guild:** {guild.name}\n"
                f"**Original ban reason:** {original_reason}\n"
                f"**Reason:** Temporary ban expired"
            ),
            color=LogColors.MOD,
            timestamp=discord.utils.utcnow(),
        )
        try:
            await log_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    def _record_unban_case(self, *, user_id: int) -> None:
        # Auto-unban has no human moderator — attribute the case to the bot
        # itself rather than leaving moderator_id unset.
        try:
            record_case(
                user_id=user_id,
                moderator_id=self.bot.user.id if self.bot.user else 0,
                case_type="unban",
                reason="Temporary ban expired",
            )
        except Exception:
            logging.exception("Failed to record case log entry for auto-unban of %s", user_id)

    async def _log_ban(
        self,
        *,
        target_display: str,
        target_id: int,
        moderator: discord.abc.User,
        rule: int | None,
        reason: str,
        dm_delivered: bool,
        unban_at: float | None = None,
        purge_seconds: int = 0,
    ) -> None:
        log_channel = get_log_channel(self.bot, LogChannels.MOD)
        if log_channel is None:
            return
        lines = [
            # Plain text, not a live mention — the target may no longer
            # share a guild with the bot once banned.
            f"**Target:** {target_display} (`{target_id}`)",
            f"**Moderator:** {user_line(moderator)}",
        ]
        if rule is not None:
            lines.append(f"**Rule:** {rule}. {RULES[rule]}")
        lines.append(f"**Reason:** {reason}")
        if purge_seconds > 0:
            lines.append(f"**Message purge:** last {format_duration(timedelta(seconds=purge_seconds))}, server-wide")
        if unban_at is not None:
            lines.append(f"**Expires:** <t:{int(unban_at)}:R> (temporary ban)")

        embed = discord.Embed(
            title="🔨 Member banned",
            description="\n".join(lines),
            color=LogColors.MOD if dm_delivered else discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )
        if dm_delivered:
            embed.add_field(name="DM status", value="✅ Appeal DM delivered.", inline=False)
        else:
            embed.add_field(
                name="⚠️ DM status",
                value="DM undeliverable — no appeal path available for this user.",
                inline=False,
            )
        try:
            await log_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    async def _announce_ban(
        self,
        *,
        target_display: str,
        target_id: int,
        rule: int | None,
        reason: str,
        unban_at: float | None,
    ) -> None:
        """Public-facing ban announcement — more detail than the old
        one-liner, but deliberately no moderator identity (that's the
        internal #mod-log's job; see _log_ban above)."""
        announce_channel = get_log_channel(self.bot, LogChannels.ANNOUNCE)
        if announce_channel is None:
            return
        lines = [f"**User:** {target_display} (`{target_id}`)"]
        if rule is not None:
            lines.append(f"**Rule:** {rule}. {RULES[rule]}")
        lines.append(f"**Reason:** {reason}")
        if unban_at is not None:
            lines.append(f"**Expires:** <t:{int(unban_at)}:R> (temporary ban)")
        else:
            lines.append("**Duration:** Permanent")

        embed = discord.Embed(
            title="🔨 Member banned",
            description="\n".join(lines),
            color=LogColors.MOD,
            timestamp=discord.utils.utcnow(),
        )
        try:
            await announce_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    async def _log_unban(
        self, *, target_display: str, target_id: int, moderator: discord.abc.User, reason: str
    ) -> None:
        log_channel = get_log_channel(self.bot, LogChannels.MOD)
        if log_channel is None:
            return
        embed = discord.Embed(
            title="🔓 Member unbanned",
            description=(
                f"**Target:** {target_display} (`{target_id}`)\n"
                f"**Moderator:** {user_line(moderator)}\n"
                f"**Reason:** {reason}"
            ),
            color=LogColors.MOD,
            timestamp=discord.utils.utcnow(),
        )
        try:
            await log_channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    # ── =ban ─────────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="ban", description="Ban a member from the server.")
    @app_commands.describe(
        member="The member to ban",
        rule="Rule being violated",
        duration="Optional: e.g. 30m, 2h, 1d — omit for a permanent ban. Prefix: must be the first word to count.",
        delete_history="Optional: delete this member's messages server-wide from the last e.g. 2h, 3d — up to 7d. Overrides the automatic rule-8 purge. Prefix: write it as purge:3d.",
        reason="Reason for the ban (prefix: just type it normally, no special phrasing needed)",
    )
    @app_commands.choices(
        rule=[app_commands.Choice(name=f"{k}. {v}", value=k) for k, v in RULES.items()],
    )
    async def ban(
        self,
        ctx: Context,
        member: discord.Member,
        rule: int | None = None,
        duration: _DurationArg | None = None,
        delete_history: _DeleteHistoryArg | None = None,
        *,
        reason: str | None = None,
    ):
        if not await self._require_mod(ctx):
            return
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        # Slash still forces a rule pick via the choices decorator's UI, but
        # since `rule` itself is now Optional (so =ban alone still works),
        # that's enforced here instead. Prefix invocations may omit it.
        if ctx.interaction is not None and rule is None:
            await ctx.send("You must select a rule.", ephemeral=True)
            return

        if rule is not None and rule not in RULES:
            valid = ", ".join(f"{k} ({v})" for k, v in RULES.items())
            await ctx.send(f"Invalid rule number. Valid rules: {valid}", ephemeral=True)
            return

        # duration/delete_history have already been validated as parseable by
        # _DurationArg's converter by this point (or are None) — no
        # "couldn't parse" branch needed here.
        duration_seconds = _parse_duration_seconds(duration) if duration is not None else None

        delete_history_seconds = _parse_duration_seconds(delete_history) if delete_history is not None else None
        if delete_history_seconds is not None and delete_history_seconds > _MAX_DELETE_HISTORY_SECONDS:
            await ctx.send("Message deletion window can't exceed 7 days.", ephemeral=True)
            return

        if member.id == guild.owner_id:
            await ctx.send("I can't ban the server owner.", ephemeral=True)
            return
        if any(r.id == MOD_ROLE_ID for r in member.roles):
            await ctx.send("Mods can't be banned via this command.", ephemeral=True)
            return
        bot_member = guild.me
        if bot_member.top_role <= member.top_role:
            await ctx.send(
                "I can't ban that member — their top role is at or above my own.", ephemeral=True
            )
            return

        # All checks passed — defer now. The DM send + guild.ban() below are
        # two sequential network calls, which combined can outrun Discord's
        # 3-second interaction ack window and make ctx.send() below fail with
        # a 404 Unknown interaction even though the ban itself went through.
        await ctx.defer(ephemeral=True)

        reason_text = reason or "No reason provided"
        unban_at = discord.utils.utcnow().timestamp() + duration_seconds if duration_seconds else None

        # DM must be attempted before the ban — banning removes the shared guild.
        dm_delivered = True
        dm_lines = [
            f"You were banned from **{guild.name}**.",
            "",
        ]
        if rule is not None:
            dm_lines.append(f"**Rule:** {rule}. {RULES[rule]}")
        dm_lines.append(f"**Reason:** {reason_text}")
        if unban_at is not None:
            dm_lines += ["", f"This ban is temporary — you'll be auto-unbanned <t:{int(unban_at)}:R>."]
        dm_lines += [
            "",
            "If you believe this was a mistake, or would like a second chance, join our appeals "
            "server to submit an appeal: https://discord.gg/WtECbmPch6",
        ]
        dm_embed = discord.Embed(
            title="You have been banned",
            description="\n".join(dm_lines),
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        try:
            await member.send(embed=dm_embed)
        except (discord.Forbidden, discord.HTTPException):
            dm_delivered = False

        target_display = str(member)
        target_id = member.id

        if delete_history_seconds is not None:
            delete_message_seconds = delete_history_seconds
        elif rule == 8:
            delete_message_seconds = _RULE_8_PURGE_SECONDS
        else:
            delete_message_seconds = 0

        try:
            await guild.ban(
                member,
                reason=f"{reason_text} — by {ctx.author} ({ctx.author.id})",
                delete_message_seconds=delete_message_seconds,
            )
        except discord.Forbidden:
            await ctx.send("I don't have permission to ban that member.", ephemeral=True)
            return
        except discord.HTTPException as exc:
            await ctx.send(f"Failed to ban that member: {exc}", ephemeral=True)
            return

        # The ban above triggers on_member_ban; suppress ModLogCog's
        # duplicate before posting our own (richer) embed for it below.
        suppress_mod_log(target_id, "ban")

        if ctx.interaction is None:
            # Prefix invocation (=ban): the command message itself shows the
            # moderator's name/avatar as its author, which the banned member
            # could otherwise still see for a moment — delete it so identity
            # is only ever recorded in the mod log, not visible in-channel.
            try:
                await ctx.message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass

        if unban_at is not None:
            self._add_tempban(guild_id=guild.id, user_id=target_id, unban_at=unban_at, reason=reason_text)

        dm_note = "" if dm_delivered else " ⚠️ DM could not be delivered."
        duration_note = (
            f" (temporary — auto-unban in {format_duration(timedelta(seconds=duration_seconds))})"
            if duration_seconds
            else ""
        )
        purge_note = (
            f" Purged their messages from the last {format_duration(timedelta(seconds=delete_message_seconds))} server-wide."
            if delete_message_seconds > 0
            else ""
        )
        await ctx.send(
            f"Banned {target_display} (`{target_id}`).{duration_note}{dm_note} Reason: {reason_text}{purge_note}",
            ephemeral=True,
        )

        await self._log_ban(
            target_display=target_display,
            target_id=target_id,
            moderator=ctx.author,
            rule=rule,
            reason=reason_text,
            dm_delivered=dm_delivered,
            unban_at=unban_at,
            purge_seconds=delete_message_seconds,
        )

        await self._announce_ban(
            target_display=target_display,
            target_id=target_id,
            rule=rule,
            reason=reason_text,
            unban_at=unban_at,
        )

        try:
            record_case(
                user_id=target_id,
                moderator_id=ctx.author.id,
                case_type="ban",
                reason=reason_text,
                duration_seconds=duration_seconds,
            )
        except Exception:
            logging.exception("Failed to record case log entry for ban of %s", target_id)

    # ── =unban ───────────────────────────────────────────────────────────────

    @commands.hybrid_command(name="unban", description="Unban a user by ID.")
    @app_commands.describe(user_id="The banned user's ID (or mention)", reason="Reason for the unban")
    async def unban(self, ctx: Context, user_id: str, *, reason: str | None = None):
        if not await self._require_mod(ctx):
            return
        guild = ctx.guild
        if guild is None:
            await ctx.send("This command can only be used in a server.", ephemeral=True)
            return

        parsed_id = _parse_user_id(user_id)
        if parsed_id is None:
            await ctx.send(f"Couldn't parse `{user_id}` as a user ID.", ephemeral=True)
            return

        # All checks passed — defer now. fetch_ban() + guild.unban() below are
        # two sequential network calls, which combined can outrun Discord's
        # 3-second interaction ack window and make ctx.send() below fail with
        # a 404 Unknown interaction even though the unban itself went through.
        await ctx.defer(ephemeral=True)

        reason_text = reason or "No reason provided"
        target = discord.Object(id=parsed_id)

        try:
            ban_entry = await guild.fetch_ban(target)
        except discord.NotFound:
            await ctx.send(f"User ID `{parsed_id}` isn't currently banned.", ephemeral=True)
            return
        except discord.HTTPException as exc:
            await ctx.send(f"Failed to look up that ban: {exc}", ephemeral=True)
            return

        try:
            await guild.unban(target, reason=f"{reason_text} — by {ctx.author} ({ctx.author.id})")
        except discord.HTTPException as exc:
            await ctx.send(f"Failed to unban that user: {exc}", ephemeral=True)
            return

        # The unban above triggers on_member_unban; suppress ModLogCog's
        # duplicate before posting our own (richer) embed for it below.
        suppress_mod_log(parsed_id, "unban")

        self._remove_tempban(guild_id=guild.id, user_id=parsed_id)

        target_display = str(ban_entry.user)
        await ctx.send(f"Unbanned {target_display} (`{parsed_id}`). Reason: {reason_text}", ephemeral=True)

        await self._log_unban(
            target_display=target_display,
            target_id=parsed_id,
            moderator=ctx.author,
            reason=reason_text,
        )

        try:
            record_case(
                user_id=parsed_id,
                moderator_id=ctx.author.id,
                case_type="unban",
                reason=reason_text,
            )
        except Exception:
            logging.exception("Failed to record case log entry for unban of %s", parsed_id)
