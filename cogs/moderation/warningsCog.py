import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import os
from datetime import datetime, timezone

from ..logging.logConfig import LogChannels, LogColors, MOD_ROLE_ID, get_log_channel, user_line

DB_DIR = os.path.expanduser("~/terrierbot_data")
DB_PATH = os.path.join(DB_DIR, "warnings.db")

RULES = {
    1: "No Harassment or Insults",
    2: "No Hate Speech or Slurs",
    3: "No Edgy or Baiting Behavior",
    4: "No Spam or Ping Abuse",
    5: "No Doxxing or Sharing DMs",
    6: "No Threats or Endangering Safety",
    7: "No NSFW/NSFL Content",
    8: "No Scams / Unapproved Self-Promo",
    9: "Mods Have Final Say",
}

class WarningsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._init_db()

    @staticmethod
    async def _require_mod(ctx: commands.Context) -> bool:
        if not isinstance(ctx.author, discord.Member) or not any(
            r.id == MOD_ROLE_ID for r in ctx.author.roles
        ):
            await ctx.send("Oops! You can't run that... mods only!", ephemeral=True)
            return False
        return True

    def _init_db(self):
        os.makedirs(DB_DIR, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                rule INTEGER NOT NULL,
                reason TEXT NOT NULL,
                warned_at TEXT NOT NULL,
                expires_at TEXT,
                active INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.commit()

        # Migration: tracks how a warning was removed (e.g. "appeal"), NULL
        # for manual =warnremove or warnings still active. Wrapped so it's
        # idempotent across restarts once the column already exists.
        try:
            conn.execute("ALTER TABLE warnings ADD COLUMN removed_via TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass

        conn.close()

    def _conn(self):
        return sqlite3.connect(DB_PATH)

    async def _log_to_mod_channel(self, embed: discord.Embed) -> None:
        channel = get_log_channel(self.bot, LogChannels.MOD)
        if channel is None:
            return
        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    # ---------- /warn ----------
    @commands.hybrid_command(name="warn", description="Warn a user for violating a rule")
    @app_commands.describe(
        user="User to warn",
        rule="Rule being violated",
        reason="Brief description of the violation",
        send_dm="Send the user a DM about this warning (default: Yes)",
    )
    @app_commands.choices(
        rule=[app_commands.Choice(name=f"{k}. {v}", value=k) for k, v in RULES.items()],
    )
    async def warn(
        self,
        ctx: commands.Context,
        user: discord.Member,
        rule: int,
        reason: str,
        send_dm: bool = True,
    ):
        if not await self._require_mod(ctx):
            return
        if rule not in RULES:
            valid = ", ".join(f"{k} ({v})" for k, v in RULES.items())
            await ctx.send(f"Invalid rule number. Valid rules: {valid}", ephemeral=True)
            return

        warned_at = datetime.now(timezone.utc)

        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO warnings (user_id, moderator_id, rule, reason, warned_at, expires_at, active) "
            "VALUES (?, ?, ?, ?, ?, ?, 1)",
            (
                user.id,
                ctx.author.id,
                rule,
                reason,
                warned_at.isoformat(),
                None,
            ),
        )
        warn_id = cur.lastrowid
        conn.commit()
        conn.close()

        # DM the user (best-effort, only if send_dm is True)
        if send_dm:
            try:
                dm_embed = discord.Embed(
                    title="You've received a warning",
                    color=discord.Color.orange(),
                )
                dm_embed.add_field(name="Rule", value=f"{rule}. {RULES[rule]}", inline=False)
                dm_embed.add_field(name="Reason", value=reason, inline=False)
                dm_embed.add_field(
                    name="Appeals",
                    value="Warnings can be appealed. To appeal, use the `/warnappeal` command.",
                    inline=False,
                )
                dm_embed.set_footer(text=f"Warning ID: {warn_id}")
                await user.send(embed=dm_embed)
                dm_status = "DM sent"
            except discord.Forbidden:
                dm_status = "Could not DM user (DMs closed)"
        else:
            dm_status = "DM skipped"

        confirm_embed = discord.Embed(
            title=f"Warning #{warn_id} issued",
            color=discord.Color.orange(),
        )
        confirm_embed.add_field(name="User", value=user.mention, inline=True)
        confirm_embed.add_field(name="Rule", value=f"{rule}. {RULES[rule]}", inline=True)
        confirm_embed.add_field(name="Reason", value=reason, inline=False)
        confirm_embed.set_footer(text=dm_status)

        if ctx.interaction is not None:
            # Slash invocation: ack privately so only the moderator who ran
            # it sees anything — the channel itself gets no visible trace.
            await ctx.send(embed=confirm_embed, ephemeral=True)
        else:
            # Prefix invocation (=warn): no interaction to ack, so stay
            # silent in-channel and remove the command message too. The DM
            # above and the mod-log embed below are the only record left.
            try:
                await ctx.message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass

        mod_log_embed = discord.Embed(
            title=f"⚠️ Warning #{warn_id} issued",
            description=(
                f"**Target:** {user.mention} (`{user.id}`)\n"
                f"**Moderator:** {user_line(ctx.author)}\n"
                f"**Rule:** {rule}. {RULES[rule]}\n"
                f"**Reason:** {reason}\n"
                f"**DM:** {dm_status}"
            ),
            color=LogColors.MOD,
            timestamp=discord.utils.utcnow(),
        )
        mod_log_embed.set_thumbnail(url=user.display_avatar.url)
        await self._log_to_mod_channel(mod_log_embed)

        try:
            await ctx.channel.send(
                f"{user} has been warned.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            pass

    # ---------- /warncount ----------
    @commands.hybrid_command(name="warncount", description="List all users with active warnings")
    async def warncount(self, ctx: commands.Context):
        if not await self._require_mod(ctx):
            return
        conn = self._conn()
        rows = conn.execute(
            "SELECT user_id, COUNT(*) FROM warnings WHERE active = 1 GROUP BY user_id ORDER BY COUNT(*) DESC"
        ).fetchall()
        conn.close()

        if not rows:
            await ctx.send("No active warnings.")
            return

        lines = []
        for user_id, count in rows:
            member = ctx.guild.get_member(user_id)
            name = member.mention if member else f"<@{user_id}> (left server)"
            lines.append(f"{name} — {count} warning(s)")

        embed = discord.Embed(
            title="Active Warnings by User",
            description="\n".join(lines),
            color=discord.Color.orange(),
        )
        await ctx.send(embed=embed)

    # ---------- /warninfo ----------
    @commands.hybrid_command(name="warninfo", description="Show a user's warning history")
    @app_commands.describe(user="User to look up")
    async def warninfo(self, ctx: commands.Context, user: discord.Member):
        if not await self._require_mod(ctx):
            return
        conn = self._conn()
        rows = conn.execute(
            "SELECT id, rule, reason, warned_at, active FROM warnings "
            "WHERE user_id = ? ORDER BY warned_at DESC",
            (user.id,),
        ).fetchall()
        conn.close()

        if not rows:
            await ctx.send(f"{user.mention} has no warnings on record.")
            return

        embed = discord.Embed(title=f"Warning history — {user.display_name}", color=discord.Color.orange())
        for warn_id, rule, reason, warned_at, active in rows:
            date_str = datetime.fromisoformat(warned_at).strftime("%Y-%m-%d")
            status_str = "Active" if active else "Removed"
            embed.add_field(
                name=f"#{warn_id} — Rule {rule} ({date_str})",
                value=f"{reason}\nStatus: {status_str}",
                inline=False,
            )
        await ctx.send(embed=embed)

    # ---------- /mywarns ----------
    @commands.hybrid_command(name="mywarns", description="Show your own active warnings")
    async def mywarns(self, ctx: commands.Context):
        conn = self._conn()
        rows = conn.execute(
            "SELECT id, rule, reason, warned_at FROM warnings "
            "WHERE user_id = ? AND active = 1 ORDER BY warned_at DESC",
            (ctx.author.id,),
        ).fetchall()
        conn.close()

        if not rows:
            await ctx.send("You have no active warnings.", ephemeral=True)
            return

        embed = discord.Embed(title="Your active warnings", color=discord.Color.orange())
        for warn_id, rule, reason, warned_at in rows:
            date_str = datetime.fromisoformat(warned_at).strftime("%Y-%m-%d")
            embed.add_field(
                name=f"#{warn_id} — Rule {rule}: {RULES.get(rule, 'Unknown')} ({date_str})",
                value=reason,
                inline=False,
            )
        await ctx.send(embed=embed, ephemeral=True)

    # ---------- /warnremove ----------
    async def _warn_id_autocomplete(self, interaction: discord.Interaction, current: str):
        conn = self._conn()
        rows = conn.execute(
            "SELECT id, user_id, rule, reason FROM warnings WHERE active = 1 ORDER BY id DESC LIMIT 200"
        ).fetchall()
        conn.close()

        choices = []
        for warn_id, user_id, rule, reason in rows:
            member = interaction.guild.get_member(user_id) if interaction.guild else None
            name = member.display_name if member else f"user {user_id}"
            label = f"#{warn_id} — {name} — Rule {rule} — {reason}"[:100]
            if current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label, value=warn_id))
        return choices[:25]

    @commands.hybrid_command(name="warnremove", description="Manually remove a warning")
    @app_commands.describe(warn_id="Warning to remove (start typing to search)")
    @app_commands.autocomplete(warn_id=_warn_id_autocomplete)
    async def warnremove(self, ctx: commands.Context, warn_id: int):
        if not await self._require_mod(ctx):
            return
        conn = self._conn()
        row = conn.execute(
            "SELECT user_id, rule, reason FROM warnings WHERE id = ? AND active = 1", (warn_id,)
        ).fetchone()
        if not row:
            conn.close()
            await ctx.send(f"No active warning #{warn_id} found.")
            return

        user_id, rule, reason = row
        conn.execute("UPDATE warnings SET active = 0 WHERE id = ?", (warn_id,))
        conn.commit()
        conn.close()
        await ctx.send(f"Warning #{warn_id} removed for <@{user_id}>.")

        mod_log_embed = discord.Embed(
            title=f"✅ Warning #{warn_id} removed",
            description=(
                f"**Target:** <@{user_id}> (`{user_id}`)\n"
                f"**Moderator:** {user_line(ctx.author)}\n"
                f"**Original rule:** {rule}. {RULES.get(rule, 'Unknown')}\n"
                f"**Original reason:** {reason}"
            ),
            color=LogColors.MOD,
            timestamp=discord.utils.utcnow(),
        )
        await self._log_to_mod_channel(mod_log_embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(WarningsCog(bot))