import discord
from discord import app_commands
from discord.ext import commands, tasks
import sqlite3
import os
from datetime import datetime, timedelta, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "warnings.db")
NOTICE_CHANNEL_ID = 1401924438341062798

RULES = {
    1: "Be Respectful",
    2: "Keep It Safe and Legal",
    3: "No Spam or Self-Promotion",
    4: "No NSFW/NSFL Content",
    5: "Respect Privacy",
    6: "Mods Have Final Say",
}

# Swap this out for your actual mod role check if you'd rather gate on a role
# instead of the manage_messages permission.
def is_mod():
    return commands.has_permissions(manage_messages=True)


class WarningsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._init_db()
        self.expiry_check.start()

    def cog_unload(self):
        self.expiry_check.cancel()

    def _init_db(self):
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
        conn.close()

    def _conn(self):
        return sqlite3.connect(DB_PATH)

    # ---------- /warn ----------
    @commands.hybrid_command(name="warn", description="Warn a user for violating a rule")
    @is_mod()
    @app_commands.describe(
        user="User to warn",
        rule="Rule being violated",
        reason="Brief description of the violation",
        expiry_months="Months until this warning expires (0-12, 0 = never expires)",
    )
    @app_commands.choices(
        rule=[app_commands.Choice(name=f"{k}. {v}", value=k) for k, v in RULES.items()]
    )
    async def warn(
        self,
        ctx: commands.Context,
        user: discord.Member,
        rule: int,
        reason: str,
        expiry_months: int = 3,
    ):
        if rule not in RULES:
            valid = ", ".join(f"{k} ({v})" for k, v in RULES.items())
            await ctx.send(f"Invalid rule number. Valid rules: {valid}", ephemeral=True)
            return

        expiry_months = max(0, min(12, expiry_months))
        warned_at = datetime.now(timezone.utc)
        expires_at = None if expiry_months == 0 else warned_at + timedelta(days=30 * expiry_months)

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
                expires_at.isoformat() if expires_at else None,
            ),
        )
        warn_id = cur.lastrowid
        conn.commit()
        conn.close()

        expiry_text = "Never" if expiry_months == 0 else f"{expiry_months} month(s)"

        # DM the user (best-effort)
        try:
            dm_embed = discord.Embed(
                title="You've received a warning",
                color=discord.Color.orange(),
            )
            dm_embed.add_field(name="Rule", value=f"{rule}. {RULES[rule]}", inline=False)
            dm_embed.add_field(name="Reason", value=reason, inline=False)
            dm_embed.add_field(name="Expires", value=expiry_text, inline=False)
            dm_embed.set_footer(text=f"Warning ID: {warn_id}")
            await user.send(embed=dm_embed)
            dm_status = "DM sent"
        except discord.Forbidden:
            dm_status = "Could not DM user (DMs closed)"

        confirm_embed = discord.Embed(
            title=f"Warning #{warn_id} issued",
            color=discord.Color.orange(),
        )
        confirm_embed.add_field(name="User", value=user.mention, inline=True)
        confirm_embed.add_field(name="Rule", value=f"{rule}. {RULES[rule]}", inline=True)
        confirm_embed.add_field(name="Expires", value=expiry_text, inline=True)
        confirm_embed.add_field(name="Reason", value=reason, inline=False)
        confirm_embed.set_footer(text=dm_status)
        await ctx.send(embed=confirm_embed)

    # ---------- /warncount ----------
    @commands.hybrid_command(name="warncount", description="List all users with active warnings")
    @is_mod()
    async def warncount(self, ctx: commands.Context):
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
    @is_mod()
    @app_commands.describe(user="User to look up")
    async def warninfo(self, ctx: commands.Context, user: discord.Member):
        conn = self._conn()
        rows = conn.execute(
            "SELECT id, rule, reason, warned_at, expires_at, active FROM warnings "
            "WHERE user_id = ? ORDER BY warned_at DESC",
            (user.id,),
        ).fetchall()
        conn.close()

        if not rows:
            await ctx.send(f"{user.mention} has no warnings on record.")
            return

        embed = discord.Embed(title=f"Warning history — {user.display_name}", color=discord.Color.orange())
        for warn_id, rule, reason, warned_at, expires_at, active in rows:
            date_str = datetime.fromisoformat(warned_at).strftime("%Y-%m-%d")
            if not active:
                expiry_str = "Expired/removed"
            elif expires_at is None:
                expiry_str = "Never"
            else:
                expiry_str = datetime.fromisoformat(expires_at).strftime("%Y-%m-%d")
            embed.add_field(
                name=f"#{warn_id} — Rule {rule} ({date_str})",
                value=f"{reason}\nExpires: {expiry_str}",
                inline=False,
            )
        await ctx.send(embed=embed)

    # ---------- /mywarns ----------
    @commands.hybrid_command(name="mywarns", description="Show your own active warnings")
    async def mywarns(self, ctx: commands.Context):
        conn = self._conn()
        rows = conn.execute(
            "SELECT id, rule, reason, warned_at, expires_at FROM warnings "
            "WHERE user_id = ? AND active = 1 ORDER BY warned_at DESC",
            (ctx.author.id,),
        ).fetchall()
        conn.close()

        if not rows:
            await ctx.send("You have no active warnings.", ephemeral=True)
            return

        embed = discord.Embed(title="Your active warnings", color=discord.Color.orange())
        for warn_id, rule, reason, warned_at, expires_at in rows:
            date_str = datetime.fromisoformat(warned_at).strftime("%Y-%m-%d")
            expiry_str = "Never" if expires_at is None else datetime.fromisoformat(expires_at).strftime("%Y-%m-%d")
            embed.add_field(
                name=f"#{warn_id} — Rule {rule}: {RULES.get(rule, 'Unknown')} ({date_str})",
                value=f"{reason}\nExpires: {expiry_str}",
                inline=False,
            )
        await ctx.send(embed=embed, ephemeral=True)

    # ---------- /warnremove ----------
    @commands.hybrid_command(name="warnremove", description="Manually remove a warning")
    @is_mod()
    @app_commands.describe(user="User the warning belongs to", warn_id="Warning ID to remove")
    async def warnremove(self, ctx: commands.Context, user: discord.Member, warn_id: int):
        conn = self._conn()
        row = conn.execute(
            "SELECT id FROM warnings WHERE id = ? AND user_id = ? AND active = 1",
            (warn_id, user.id),
        ).fetchone()
        if not row:
            conn.close()
            await ctx.send(f"No active warning #{warn_id} found for {user.mention}.")
            return

        conn.execute("UPDATE warnings SET active = 0 WHERE id = ?", (warn_id,))
        conn.commit()
        conn.close()
        await ctx.send(f"Warning #{warn_id} removed for {user.mention}.")

    # ---------- background expiry loop ----------
    @tasks.loop(minutes=30)
    async def expiry_check(self):
        now = datetime.now(timezone.utc)
        conn = self._conn()
        rows = conn.execute(
            "SELECT id, user_id, rule FROM warnings WHERE active = 1 AND expires_at IS NOT NULL AND expires_at <= ?",
            (now.isoformat(),),
        ).fetchall()

        if rows:
            conn.executemany(
                "UPDATE warnings SET active = 0 WHERE id = ?",
                [(warn_id,) for warn_id, _, _ in rows],
            )
            conn.commit()
        conn.close()

        if not rows:
            return

        channel = self.bot.get_channel(NOTICE_CHANNEL_ID)
        if channel is None:
            return

        for warn_id, user_id, rule in rows:
            embed = discord.Embed(
                title="Warning Expired",
                description=f"Warning #{warn_id} for <@{user_id}> (Rule {rule}: {RULES.get(rule, 'Unknown')}) has expired and been removed.",
                color=discord.Color.green(),
            )
            await channel.send(embed=embed)

    @expiry_check.before_loop
    async def before_expiry_check(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(WarningsCog(bot))
