from __future__ import annotations
from typing import Any, Callable, override
import os
import re
import threading
import subprocess
import sys
import traceback
from pathlib import Path
from flask import Flask, jsonify
from werkzeug.serving import make_server
import discord
from discord import app_commands
from discord.ext import commands
import logging
import asyncio
import aiohttp
import shelve
from datetime import datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO)

ERROR_CHANNEL_ID = 1441925119202164886
STATUS_ROLE_ID = 1402095379935395934
ALERT_COOLDOWN_SECONDS = 10 * 60
STARTUP_FAILURE_WINDOW_SECONDS = 5 * 60
STARTUP_FAILURE_THRESHOLD = 5
STARTUP_SUPPRESSION_CATEGORY_PREFIX = "startup"
STARTUP_FAILURE_CATEGORIES = {"startup", "startup:cog_load"}
SHELVE_FILE = "terrierbot.shelve"
UPTIMEROBOT_API_URL = "https://api.uptimerobot.com/v2/getMonitors"
UPTIMEROBOT_MONITOR_URL_FRAGMENT = "158.101.102.156:8080"  # used to pick the right monitor out of the account
RECENT_ERROR_LIMIT = 15


def _safe_read_token_file() -> str | None:
    try:
        with open("token.txt") as f:
            return f.read().strip()
    except OSError:
        return None


def _get_git_commit_hash() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return "unknown"

    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"


type Context = commands.Context[TerrierBot]

class TerrierBot(commands.Bot):

    def __init__(self, command_prefix : Callable[[TerrierBot, discord.Message], list[str]], **options : Any) -> None: # pyright: ignore[reportAny, reportExplicitAny]
        super().__init__(command_prefix, **options) # pyright: ignore[reportAny]

        self.prefixes : dict[int, str] = {}
        self._first_ready : bool = True
        self._did_startup_sync : bool = False
        self._commit_hash: str = _get_git_commit_hash()
        self._started_at: datetime = datetime.now(timezone.utc)
        self._pending_error_reports: list[str] = []
        self._recent_errors: list[dict[str, str]] = []
        self._alert_state: dict[str, dict[str, int]] = {}
        self._startup_failure_timestamps: list[int] = []
        self._startup_alerts_suppressed: bool = False
        self._startup_loop_alert_sent: bool = False
        self._secrets_to_redact: set[str] = set()
        env_token = os.environ.get("DISCORD_TOKEN")
        if env_token:
            self._secrets_to_redact.add(env_token)
        file_token = _safe_read_token_file()
        if file_token:
            self._secrets_to_redact.add(file_token)
        with shelve.open(SHELVE_FILE) as sh:
            if "prefixes" in sh:
                self.prefixes = sh["prefixes"]
            self._alert_state = sh.get("error_alert_state", {})
            self._startup_failure_timestamps = sh.get("startup_failure_timestamps", [])
            self._startup_alerts_suppressed = sh.get("startup_alerts_suppressed", False)
            self._startup_loop_alert_sent = sh.get("startup_loop_alert_sent", False)

    def _save_monitoring_state(self) -> None:
        with shelve.open(SHELVE_FILE) as sh:
            sh["error_alert_state"] = self._alert_state
            sh["startup_failure_timestamps"] = self._startup_failure_timestamps
            sh["startup_alerts_suppressed"] = self._startup_alerts_suppressed
            sh["startup_loop_alert_sent"] = self._startup_loop_alert_sent

    def _error_signature(self, *, category: str, affected: str, error: BaseException) -> str:
        exc_name = type(error).__name__
        exc_msg = self._redact_secrets(str(error))
        tb = traceback.extract_tb(error.__traceback__)
        if tb:
            last = tb[-1]
            location = f"{Path(last.filename).name}:{last.lineno}:{last.name}"
        else:
            location = "unknown"
        return f"{category}|{affected}|{exc_name}|{exc_msg}|{location}"

    def _now_ts(self) -> int:
        return int(datetime.now(timezone.utc).timestamp())

    def _prune_startup_failures(self, now_ts: int) -> None:
        cutoff = now_ts - STARTUP_FAILURE_WINDOW_SECONDS
        self._startup_failure_timestamps = [ts for ts in self._startup_failure_timestamps if ts >= cutoff]

    def _register_startup_failure(self) -> tuple[bool, int]:
        now_ts = self._now_ts()
        self._prune_startup_failures(now_ts)
        self._startup_failure_timestamps.append(now_ts)

        if len(self._startup_failure_timestamps) > STARTUP_FAILURE_THRESHOLD:
            self._startup_alerts_suppressed = True

        should_send_loop_alert = self._startup_alerts_suppressed and not self._startup_loop_alert_sent
        if should_send_loop_alert:
            self._startup_loop_alert_sent = True

        self._save_monitoring_state()
        return should_send_loop_alert, len(self._startup_failure_timestamps)

    def _resolve_startup_loop_if_needed(self) -> bool:
        if not self._startup_alerts_suppressed and not self._startup_failure_timestamps:
            return False

        self._startup_failure_timestamps = []
        self._startup_alerts_suppressed = False
        self._startup_loop_alert_sent = False
        self._save_monitoring_state()
        return True

    def _record_recent_error(self, *, category: str, affected: str, error: BaseException) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "category": category,
            "affected": affected,
            "error": self._redact_secrets(f"{type(error).__name__}: {error}"),
        }
        self._recent_errors.append(entry)
        if len(self._recent_errors) > RECENT_ERROR_LIMIT:
            self._recent_errors = self._recent_errors[-RECENT_ERROR_LIMIT:]

    def _uptime_string(self) -> str:
        delta = datetime.now(timezone.utc) - self._started_at
        total = int(delta.total_seconds())
        days, rem = divmod(total, 86400)
        hours, rem = divmod(rem, 3600)
        mins, secs = divmod(rem, 60)
        if days:
            return f"{days}d {hours}h {mins}m {secs}s"
        if hours:
            return f"{hours}h {mins}m {secs}s"
        return f"{mins}m {secs}s"

    def _redact_secrets(self, text: str) -> str:
        redacted = text
        for secret in self._secrets_to_redact:
            redacted = redacted.replace(secret, "[REDACTED]")

        redacted = re.sub(r"mfa\.[A-Za-z0-9_-]{20,}", "[REDACTED]", redacted)
        redacted = re.sub(r"[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{20,}", "[REDACTED]", redacted)
        return redacted

    def _build_error_report(
        self,
        *,
        category: str,
        affected: str,
        error: BaseException,
        tb_text: str,
        repeat_count: int,
        high_priority: bool,
    ) -> str:
        timestamp = datetime.now(timezone.utc).isoformat()
        safe_error = self._redact_secrets(f"{type(error).__name__}: {error}")
        safe_tb = self._redact_secrets(tb_text)
        if len(safe_tb) > 1400:
            safe_tb = safe_tb[:1400] + "\n... <traceback truncated>"

        priority_label = "HIGH PRIORITY" if high_priority else "Error"
        repeat_line = ""
        if repeat_count > 1:
            repeat_line = f"TerrierBot has crashed {repeat_count} times with this same error since the last alert.\n"

        return (
            f"🚨 TerrierBot {priority_label}\n"
            f"Timestamp (UTC): {timestamp}\n"
            f"Category: {category}\n"
            f"Affected: {affected}\n"
            f"Git commit: {self._commit_hash}\n"
            f"{repeat_line}"
            f"Error: {safe_error}\n"
            f"Traceback:\n```py\n{safe_tb}\n```"
        )

    async def _deliver_error_report(self, report: str) -> None:
        original_report = report
        try:
            channel = self.get_channel(ERROR_CHANNEL_ID)
            if channel is None:
                channel = await self.fetch_channel(ERROR_CHANNEL_ID)

            if not hasattr(channel, "send"):
                raise TypeError(f"Channel {ERROR_CHANNEL_ID} is not sendable")

            while report:
                chunk = report[:1900]
                report = report[1900:]
                await channel.send(chunk)
        except Exception:
            logging.exception("Failed to send error report to Discord")
            self._pending_error_reports.append(original_report)

    async def report_exception(self, *, category: str, affected: str, error: BaseException) -> None:
        now_ts = self._now_ts()
        self._record_recent_error(category=category, affected=affected, error=error)
        logging.error(
            "%s | %s | %s",
            category,
            affected,
            self._redact_secrets(str(error)),
            exc_info=(type(error), error, error.__traceback__),
        )
        if category in STARTUP_FAILURE_CATEGORIES:
            send_loop_alert, fail_count = self._register_startup_failure()
            if self._startup_alerts_suppressed and not send_loop_alert:
                logging.warning(
                    "Suppressed startup alert due to crash loop mode (%d startup failures in %d seconds)",
                    fail_count,
                    STARTUP_FAILURE_WINDOW_SECONDS,
                )
                return

            if send_loop_alert:
                loop_error = RuntimeError(
                    f"TerrierBot failed to start more than {STARTUP_FAILURE_THRESHOLD} times within 5 minutes. "
                    "Normal crash alerts are now suppressed until startup succeeds."
                )
                loop_tb = "Startup crash loop detector triggered."
                loop_report = self._build_error_report(
                    category="startup:crash_loop",
                    affected=affected,
                    error=loop_error,
                    tb_text=loop_tb,
                    repeat_count=fail_count,
                    high_priority=True,
                )
                logging.critical("Startup crash loop detected: %d failures in window", fail_count)
                await self._deliver_error_report(loop_report)
                return

        if self._startup_alerts_suppressed and category != "startup:resolved":
            logging.warning("Suppressed alert during startup crash loop: %s | %s", category, affected)
            return

        signature = self._error_signature(category=category, affected=affected, error=error)
        state = self._alert_state.get(signature, {"last_alert_ts": 0, "suppressed_count": 0})
        last_alert_ts = int(state.get("last_alert_ts", 0))
        suppressed_count = int(state.get("suppressed_count", 0))

        if last_alert_ts and (now_ts - last_alert_ts) < ALERT_COOLDOWN_SECONDS:
            state["suppressed_count"] = suppressed_count + 1
            self._alert_state[signature] = state
            self._save_monitoring_state()
            logging.info("Alert cooldown active for signature; notification suppressed")
            return

        repeat_count = suppressed_count + 1 if last_alert_ts else 1
        tb_text = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        report = self._build_error_report(
            category=category,
            affected=affected,
            error=error,
            tb_text=tb_text,
            repeat_count=repeat_count,
            high_priority=False,
        )
        state["last_alert_ts"] = now_ts
        state["suppressed_count"] = 0
        self._alert_state[signature] = state
        self._save_monitoring_state()
        await self._deliver_error_report(report)

    async def _load_default_cogs(self) -> None:
        for cog in defaultCogs:
            module_name = "cogs." + cog + "Cog"
            try:
                await self.load_extension(module_name)
            except Exception as exc:
                await self.report_exception(category="startup:cog_load", affected=module_name, error=exc)
                raise

    @override
    async def setup_hook(self) -> None:
        await self._load_default_cogs()

    @override
    async def on_error(self, event_method: str, *args: object, **kwargs: object) -> None:
        _ = args
        _ = kwargs
        _exc_type, exc, _tb = sys.exc_info()
        _ = _exc_type
        _ = _tb
        if exc is None:
            logging.error("Unhandled event error in %s with no active exception", event_method)
            return
        await self.report_exception(category="event", affected=event_method, error=exc)

    async def _sync_app_commands_to_joined_guilds(self) -> None:
        """Copy global app commands into each joined guild for fast availability."""
        total_synced = 0
        for guild in self.guilds:
            try:
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                total_synced += len(synced)
                logging.info(
                    "Synced %d app command(s) to guild %s (%d)",
                    len(synced),
                    guild.name,
                    guild.id,
                )
            except Exception as exc:
                logging.exception(
                    "Failed to sync app commands for guild %s (%d)",
                    guild.name,
                    guild.id,
                )
                await self.report_exception(
                    category="startup:command_sync",
                    affected=f"guild:{guild.id}",
                    error=exc,
                )

        logging.info("Startup app command sync complete across %d guild(s), %d command(s) synced.", len(self.guilds), total_synced)

    async def on_ready(self):
        # We know this to be true and this satisfies the type checker
        assert self.user is not None

        if self._resolve_startup_loop_if_needed():
            resolved_error = RuntimeError("Startup recovered; normal crash notifications resumed.")
            resolved_report = self._build_error_report(
                category="startup:resolved",
                affected="bot_ready",
                error=resolved_error,
                tb_text="Startup completed and on_ready executed successfully.",
                repeat_count=1,
                high_priority=True,
            )
            await self._deliver_error_report(resolved_report)

        logging.info('Logged in as')
        logging.info(self.user.name)
        logging.info(self.user.id)
        logging.info('------')

        # One-time startup sync so slash commands are available without manual =sync.
        if not self._did_startup_sync:
            self._did_startup_sync = True
            await self._sync_app_commands_to_joined_guilds()

        if self._first_ready:
            self._first_ready = False
            now = datetime.now(timezone.utc)
            with shelve.open("terrierbot.shelve") as sh:
                last_startup = sh.get("last_startup_msg")
                if last_startup is None or (now - last_startup) > timedelta(hours=1):
                    sh["last_startup_msg"] = now
                    channel = self.get_channel(1396542256445391069)
                    if isinstance(channel, discord.TextChannel):
                        await channel.send("Hello, I have restarted and am ready to help! 🐾")

        if self._pending_error_reports:
            pending = list(self._pending_error_reports)
            self._pending_error_reports.clear()
            for report in pending:
                await self._deliver_error_report(report)



    #============================================
    #Error Handling
    #============================================

    @override
    async def on_command_error(self, ctx : Context, error : commands.CommandError):
        http_error = None
        if isinstance(error, discord.HTTPException):
            http_error = error
        elif isinstance(error, commands.CommandInvokeError) and isinstance(error.original, discord.HTTPException):
            http_error = error.original

        if http_error is not None and http_error.status == 429:
            logging.warning("Discord rate limit hit (429) in command error handler; skipping ctx.send")
            return

        if isinstance(error, commands.CommandNotFound):
            logging.debug(f"command not found {ctx.message.content} (by {ctx.author})")
            return
        if isinstance(error, commands.MaxConcurrencyReached):
            _ = await ctx.send("Too many people running this command at a time")
            return
        if isinstance(error, commands.CommandInvokeError):
            await self.report_exception(category="command", affected=ctx.command.qualified_name if ctx.command else "unknown", error=error.original)
            _ = await ctx.send(f"{type(error.original).__name__}: {error.original}")
            return
        if isinstance(error, commands.NotOwner):
            _ = await ctx.send("That command is not for you")
            if isinstance(ctx.channel, discord.DMChannel):
                logging.info(f"{ctx.author.display_name} is trying to run the owner-only command \"{ctx.message.content}\" in a DM")
            else:
                if ctx.guild is not None and isinstance(ctx.channel, SENDABLE_CHANNEL):
                    location = f"in \"{ctx.guild.name}: #{ctx.channel.name}\""
                else:
                    location = ""
                logging.info(f"{ctx.author.display_name} is trying to run the owner-only command \"{ctx.message.content}\" {location}")
            return
        if isinstance(error, commands.MemberNotFound) or isinstance(error, commands.UserNotFound):
            _ = await ctx.send("User not found")
            return
        if isinstance(error, commands.CommandOnCooldown):
            _ = await ctx.send(f"You are on cooldown. Try again in {error.retry_after}s")
            return
        if isinstance(error, commands.MissingRequiredArgument):
            _ = await ctx.send(f"Missing argument {error.param}")
            return
        
        if isinstance(ctx.channel, discord.DMChannel):
            logging.error(f"{type(error).__name__}: {error} on command \"{ctx.message.content}\" from \"{ctx.author.display_name}\" in a DM")
        else:
            if ctx.guild is not None and isinstance(ctx.channel, SENDABLE_CHANNEL):
                location = f"in \"{ctx.guild.name}: #{ctx.channel.name}\""
            else:
                location = ""
            logging.error(f"{type(error).__name__}: {error} on command \"{ctx.message.content}\" from \"{ctx.author.display_name}\" {location}")
        await self.report_exception(category="command", affected=ctx.command.qualified_name if ctx.command else "unknown", error=error)
        _ = await ctx.send(f"Error - {type(error).__name__}: {error}")


#============================================
#Bot Initialization
#============================================

description = '''Terrier Bot'''

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

def prefix_for(bot : TerrierBot, guild : discord.Guild | None):
    if guild:
        return bot.prefixes.get(guild.id, "=")
    else:
        return "="

def command_prefix(bot : TerrierBot, msg : discord.Message):
    return commands.when_mentioned_or(prefix_for(bot, msg.guild))(bot, msg)
bot = TerrierBot(
    command_prefix=command_prefix,
    description=description,
    intents=intents,
    # Safe global default: any cog that omits explicit allowed_mentions will still
    # suppress @everyone and role pings while preserving user mentions.
    allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True),
)

bot.help_command = None


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
) -> None:
    msg = (
        f"{type(error.original).__name__}: {error.original}"
        if isinstance(error, app_commands.CommandInvokeError)
        else str(error)
    )
    logging.error("App command error: %s", error)
    underlying_error: BaseException = error.original if isinstance(error, app_commands.CommandInvokeError) else error
    await bot.report_exception(
        category="app_command",
        affected=interaction.command.qualified_name if interaction.command else "unknown",
        error=underlying_error,
    )
    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception:
        pass


@bot.tree.command(name="status", description="Show TerrierBot runtime status.")
async def status_command(interaction: discord.Interaction) -> None:
    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
        return

    has_status_role = any(role.id == STATUS_ROLE_ID for role in interaction.user.roles)
    if not has_status_role:
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    # Defer immediately — _fetch_uptime_ratios() below makes an external API call
    # that can take longer than Discord's 3-second initial-response window.
    await interaction.response.defer(ephemeral=True)

    loaded = sorted(name.removeprefix("cogs.").removesuffix("Cog") for name in bot.extensions.keys())
    loaded_display = ", ".join(loaded) if loaded else "none"

    recent_errors = bot._recent_errors[-5:]
    if recent_errors:
        recent_lines = [
            f"[{entry['timestamp']}] {entry['category']} ({entry['affected']}): {entry['error']}"
            for entry in reversed(recent_errors)
        ]
        recent_display = "\n".join(recent_lines)
    else:
        recent_display = "No recent errors in this runtime."

    uptime_ratios = await _fetch_uptime_ratios()
    if uptime_ratios:
        uptime_display = (
            f"24h: {uptime_ratios['24h']}%  •  "
            f"7d: {uptime_ratios['7d']}%  •  "
            f"30d: {uptime_ratios['30d']}%"
        )
    else:
        uptime_display = "Unavailable"

    embed = discord.Embed(
        title="TerrierBot Status",
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Uptime (this run)", value=bot._uptime_string(), inline=False)
    embed.add_field(name="Uptime % (UptimeRobot)", value=uptime_display, inline=False)
    embed.add_field(name="Git Commit", value=bot._commit_hash, inline=True)
    embed.add_field(name="Python", value=sys.version.split()[0], inline=True)
    embed.add_field(name="Last Restart (UTC)", value=bot._started_at.isoformat(timespec="seconds"), inline=False)
    embed.add_field(name="Loaded Cogs", value=loaded_display[:1024], inline=False)
    embed.add_field(name="Recent Errors", value=(recent_display[:1021] + "...") if len(recent_display) > 1024 else recent_display, inline=False)

    await interaction.followup.send(embed=embed, ephemeral=True)


#============================================
#Utility
#============================================

@bot.command(name="help")
async def help_command(ctx: Context):
    """Show categorized TerrierBot commands."""
    embed = discord.Embed(
        title="TerrierBot Commands",
        description="Use the `=` prefix or `/` slash commands where available. Some commands need admin, moderator, or owner permissions.",
        color=discord.Color.red(),
    )

    embed.add_field(
        name="Campus & BU Info",
        value=(
            "`=class` or `/class` `<course>` - Look up BU Bulletin course information\n"
            "`=club` or `/club` `<query>` - Search Terrier Central clubs\n"
            "`=rmp` or `/rmp` `<name>` - Search RateMyProfessors for a BU instructor\n"
            "`=search` or `/search` `<query>` - Search BU courses by school, department, or HUB units\n"
            "`=mbta` or `/mbta` `<station>` - Check live MBTA Green Line ETAs"
        ),
        inline=False,
    )

    embed.add_field(
        name="Community & Fun",
        value=(
            "`=hello` or `/hello` - Say hello to the bot\n"
            "`=love` or `/love` - Share some Terrier love\n"
            "`=banner` or `/banner` - Learn how to submit a server banner idea\n"
            "`=boost` or `/boost` - See server boost perks\n"
            "`=pride` or `/pride` - Send the Pride message\n"
            "`=starleaderboard` or `/starleaderboard` - Show the most-starred posts"
        ),
        inline=False,
    )

    embed.add_field(
        name="Moderation & Feedback",
        value=(
            "Manage Server required:\n"
            "`=positivity` or `/positivity status/enable/disable/interval/cooldown` - Configure Positivity Tuesday\n"
            "`=feedbacksetup` or `/feedbacksetup` - Post the anonymous feedback prompt\n"
            "`/starboard setchannel/threshold/enable/disable/status` - Configure the starboard\n"
            "`/pingrole` - Ping one of the server role options\n\n"
            "Moderation tools:\n"
            "`=warn` / `/warn` - Warn a member\n"
            "`=warncount` / `/warncount` - List active warnings\n"
            "`=warninfo` / `/warninfo` - Show a user's warning history\n"
            "`=mywarns` / `/mywarns` - Show your own active warnings\n"
            "`=warnremove` / `/warnremove` - Remove a warning\n"
            "`=lockdown` / `/lockdown` - Lock the current channel (mod only)\n"
            "`=unlock` / `/unlock` - Unlock the current channel (mod only)\n"
            "`=timeout` / `/timeout` `<member> <duration> [reason]` - Time out a member (mod only)\n"
            "`=untimeout` / `/untimeout` `<member> [reason]` - Clear a member's timeout (mod only)\n"
            "`=ban` / `/ban` `<member> [reason]` - Ban a member, DMs them an appeal button (mod only)\n"
            "`=unban` / `/unban` `<user_id> [reason]` - Unban a user by ID (mod only)\n"
            "`=kick` / `/kick` `<member> [reason]` - Kick a member (mod only)\n"
            "`=modlogs` / `/modlogs` `<member_or_id>` - View a member's full case history: warns, kicks, timeouts, bans (mod only)\n"
            "`=joinpolitics` or `/joinpolitics` - Post the #politics application (mod only)\n"
            "`/modvote start/close` `<target> <options> <duration> <quorum>` - Run an anonymous disciplinary vote (mod only)"
        ),
        inline=False,
    )

    embed.add_field(
        name="Utility",
        value=(
            "`=end` or `/end` - See how many days are left until the semester ends\n"
            "`=test` or `/test` - Confirm that the bot is responding\n"
            "`=help` - Show this help message\n"
            "`=leavepolitics` or `/leavepolitics` - Leave the Politics role/channel"
        ),
        inline=False,
    )

    embed.add_field(
        name="Owner / Maintenance",
        value=(
            "Owner only (prefix commands):\n"
            "`=disconnect`, `=delete`, `=sync`, `=cog load`, `=cog unload`, `=cog reload`, `=cog list`, `=exportmembers`, `=exportprunecandidates`"
        ),
        inline=False,
    )

    await ctx.send(embed=embed)

@bot.command()
@commands.is_owner()
async def sync(ctx: Context):
    """Sync slash commands to this server. (Owner only)"""
    assert ctx.guild is not None
    bot.tree.copy_global_to(guild=ctx.guild)
    synced = await bot.tree.sync(guild=ctx.guild)
    await ctx.send(f"Synced {len(synced)} slash command(s) to this server.")

@bot.command()
@commands.is_owner()
async def disconnect(ctx : Context):
    """Shut down TerrierBot. (Owner only)"""
    _ = await ctx.send("Bye!")
    await bot.close()

@bot.command()
@commands.is_owner()
async def delete(ctx : Context):
    """Delete the bot's most recent message in this channel. (Owner only)"""
    msg = await discord.utils.get(ctx.channel.history(), author=bot.user)
    if msg is None:
        error_msg = await ctx.send("I've never spoken here!")
        await error_msg.delete(delay=3)
        return
    await msg.delete()
    if ctx.guild is not None and ctx.channel.permissions_for(ctx.guild.me).manage_messages:
        await ctx.message.delete()

SENDABLE_CHANNEL = (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.Thread, discord.GroupChannel, discord.DMChannel)


#============================================
#Cog Management
#============================================

@bot.group()
@commands.is_owner()
async def cog(ctx : Context):
    """Manage cogs: load, unload, reload, and list. (Owner only)"""
    if ctx.invoked_subcommand is None:
        _ = await ctx.send("Invalid cog command")

@cog.command(name="load")
async def loadCog(ctx : Context, cogName : str):
    """Load a cog by name, like: =cog load members."""
    full = (cogName if cogName.endswith("Cog") else cogName + "Cog")
    module_name = "cogs." + full
    try:
        await bot.load_extension(module_name)
    except Exception as exc:
        await bot.report_exception(category="cog_load", affected=module_name, error=exc)
        raise
    logging.info("Loaded Cog \"{}\"".format(cogName))
    _ = await ctx.send("Loaded Cog \"{}\"".format(cogName))

@cog.command(name="unload")
async def unloadCog(ctx : Context, cogName : str):
    """Unload a cog by name, like: =cog unload members."""
    full = (cogName if cogName.endswith("Cog") else cogName + "Cog")
    module_name = "cogs." + full
    try:
        await bot.unload_extension(module_name)
    except Exception as exc:
        await bot.report_exception(category="cog_unload", affected=module_name, error=exc)
        raise
    logging.info("Unloaded Cog \"{}\"".format(cogName))
    _ = await ctx.send("Unloaded Cog \"{}\"".format(cogName))

@cog.command(name="reload")
async def reloadCog(ctx : Context, cogName : str):
    """Reload a cog by name, like: =cog reload members."""
    full = (cogName if cogName.endswith("Cog") else cogName + "Cog")
    module_name = "cogs." + full
    try:
        await bot.reload_extension(module_name)
    except Exception as exc:
        await bot.report_exception(category="cog_reload", affected=module_name, error=exc)
        raise
    logging.info("Reloaded Cog \"{}\"".format(cogName))
    _ = await ctx.send("Reloaded Cog \"{}\"".format(cogName))

@cog.command(name="list")
async def listCogs(ctx : Context):
    """Show loaded and unloaded cogs."""
    loadedCogs = list(map(lambda x: x.removeprefix("cogs.").split("Cog")[0], bot.extensions.keys()))
    _ = await ctx.send(
        "**Loaded Cogs:**\n{}\n**Unloaded Cogs:**\n{}".format(
            "\n".join(loadedCogs), "\n".join([x for x in cogList if x not in loadedCogs])
        )
    )
    
#============================================
#Make bot go
#============================================
cogList = ["test", "hello", "love", "boost", "positivity", "members", "end", "start", "banner", "reaction", "rmp", "class", "embed", "starboard", "towoken", "club", "mbta", "scamImage", "feedback", "pingrole", "troll", "warnings", "roleboost", "ticket", "lockin", "joinLeave", "memberLog", "serverLog", "messageLog", "modLog", "leavePolitics", "joinPolitics", "modvote", "lockdown", "caseLog", "timeout", "ban", "kick"]
defaultCogs = ["test", "hello", "love", "boost", "positivity", "members", "start", "banner", "reaction", "rmp", "class", "embed", "starboard", "towoken", "club", "mbta", "scamImage", "feedback", "pingrole", "troll", "warnings", "roleboost", "ticket", "lockin", "joinLeave", "memberLog", "serverLog", "messageLog", "modLog", "leavePolitics", "joinPolitics", "modvote", "lockdown", "caseLog", "timeout", "ban", "kick"]


def _get_token() -> str:
    token = os.environ.get("DISCORD_TOKEN")
    if token:
        return token
    with open("token.txt") as f:
        return f.read().strip()


def _get_reload_secret() -> str | None:
    secret = os.environ.get("RELOAD_SECRET")
    if secret:
        return secret
    try:
        with open("reload_secret.txt") as f:
            return f.read().strip()
    except OSError:
        return None


def _get_uptimerobot_key() -> str | None:
    key = os.environ.get("UPTIMEROBOT_API_KEY")
    if key:
        return key
    try:
        with open("uptimerobot_key.txt") as f:
            return f.read().strip()
    except OSError:
        return None


async def _fetch_uptime_ratios() -> dict[str, str] | None:
    """Returns {'24h': '99.98', '7d': '99.50', '30d': '98.00'} or None on any failure."""
    api_key = _get_uptimerobot_key()
    if not api_key:
        return None

    payload = {
        "api_key": api_key,
        "format": "json",
        "custom_uptime_ratios": "1-7-30",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(UPTIMEROBOT_API_URL, data=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
    except Exception:
        logging.exception("Failed to fetch UptimeRobot data")
        return None

    if data.get("stat") != "ok":
        return None

    monitors = data.get("monitors", [])
    target = None
    for m in monitors:
        if UPTIMEROBOT_MONITOR_URL_FRAGMENT in m.get("url", ""):
            target = m
            break
    if target is None and monitors:
        target = monitors[0]  # fall back to first monitor if URL match fails
    if target is None:
        return None

    ratios = target.get("custom_uptime_ratio", "")
    parts = ratios.split("-")
    if len(parts) != 3:
        return None

    return {"24h": parts[0], "7d": parts[1], "30d": parts[2]}


async def main():
    async with bot:
        await bot.start(_get_token())

def run_web_server(stop_event: threading.Event, bot_loop: asyncio.AbstractEventLoop) -> None:
    app = Flask(__name__)
    reload_secret = _get_reload_secret()

    @app.route("/")
    def index():
        ready = bot.is_ready()
        return jsonify(latency=bot.latency), (200 if ready else 503)

    @app.route("/reload/<cog_name>", methods=["POST"])
    def reload_cog(cog_name: str):
        from flask import request
        if not reload_secret or request.headers.get("X-Reload-Secret") != reload_secret:
            return "Unauthorized", 401

        full = cog_name if cog_name.endswith("Cog") else cog_name + "Cog"
        module_name = "cogs." + full
        if module_name not in bot.extensions:
            return f"Cog {module_name} not currently loaded", 404

        future = asyncio.run_coroutine_threadsafe(bot.reload_extension(module_name), bot_loop)
        try:
            future.result(timeout=15)
        except Exception as e:
            logging.error(f"Reload of {module_name} failed: {e}")
            return f"Reload failed: {e}", 500

        logging.info(f"Hot-reloaded cog {module_name} via deploy webhook")
        return f"Reloaded {module_name}", 200

    port = int(os.environ.get("PORT", 8080))
    server = make_server("0.0.0.0", port, app)
    server.timeout = 1
    while not stop_event.is_set():
        server.handle_request()
    server.server_close()


async def run_services() -> None:
    loop = asyncio.get_running_loop()

    def _loop_exception_handler(loop: asyncio.AbstractEventLoop, context: dict[str, object]) -> None:
        err = context.get("exception")
        if isinstance(err, BaseException):
            loop.create_task(bot.report_exception(category="asyncio", affected="event_loop", error=err))
            return

        msg = str(context.get("message", "Unknown asyncio exception"))
        loop.create_task(
            bot.report_exception(
                category="asyncio",
                affected="event_loop",
                error=RuntimeError(msg),
            )
        )

    loop.set_exception_handler(_loop_exception_handler)

    stop_event = threading.Event()
    web_task = asyncio.create_task(asyncio.to_thread(run_web_server, stop_event, loop))
    try:
        await main()
    except Exception as exc:
        await bot.report_exception(category="startup", affected="run_services", error=exc)
        raise
    finally:
        stop_event.set()
        await web_task


if __name__ == "__main__":
    def _global_excepthook(exc_type: type[BaseException], exc_value: BaseException, exc_tb: object) -> None:
        logging.critical("Uncaught top-level exception", exc_info=(exc_type, exc_value, exc_tb))

    def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
        logging.critical(
            "Uncaught thread exception in %s",
            args.thread.name if args.thread else "unknown",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = _global_excepthook
    threading.excepthook = _thread_excepthook
    asyncio.run(run_services())