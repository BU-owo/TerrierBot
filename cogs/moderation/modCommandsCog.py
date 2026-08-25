from __future__ import annotations

import discord
from discord.ext import commands

from bot import Context, TerrierBot
from .logConfig import LogColors, MOD_ROLE_ID

# Discipline and case-management tools only — community/config features
# (positivity, starboard, feedbacksetup) and fun toggles (towoken) live
# elsewhere in =help, not here.
_FIELDS = [
    (
        "📋 Case History",
        "`=modlogs <member_or_id>` / `/modlogs`",
        "Check a member's full history (warns, kicks, timeouts, bans) before deciding how to escalate.",
    ),
    (
        "⚠️ Warn",
        "`=warn <member> <rule> <reason> [expiry_months]` — issue a formal warning, auto-expires by default\n"
        "`=warncount` / `=warninfo <member>` — see who has active warnings, or one member's full history\n"
        "`=warnremove <warn_id>` — remove a warning early",
        "For rule violations that don't need removal from the server; warnings build the paper trail modlogs surfaces later.",
    ),
    (
        "🔇 Timeout / Untimeout",
        "`=timeout <member> <duration> [reason]` / `=untimeout <member> [reason]`",
        "Quick cooldown for minor or heated behavior; untimeout lifts it early once things calm down.",
    ),
    (
        "👢 Kick",
        "`=kick <member> [reason]`",
        "Removes a member immediately without banning.",
    ),
    (
        "🔨 Ban / Unban",
        "`=ban <member> [duration] [reason]` / `=unban <user_id> [reason]`",
        "For serious or repeated violations; add a duration (e.g. `2h`) right after the member for a temp ban, omit it for permanent — everything else is just the reason, no special phrasing needed. Unban reverses it by ID. Requires vote.",
    ),
    (
        "🧹 Purge",
        "`=purge <amount>` (1-100) / `=purgeafter [target]`",
        "Purge bulk-deletes recent messages. Purgeafter deletes everything after a target message (reply to it, or pass its ID/link) in the current channel, capped at 200.",
    ),
    (
        "🔒 Lockdown / Unlock",
        "`=lockdown` / `=unlock`",
        "Locks the current channel from @everyone; unlock restores it.",
    ),
    (
        "🗳️ Modvote",
        "`/modvote start <target> <options> <duration_minutes> <quorum>` / `/modvote close [vote_id]`",
        "For a discipline call that shouldn't rest on one mod alone — anonymous, quorum-gated team vote.",
    ),
]


async def setup(bot: TerrierBot):
    await bot.add_cog(ModCommandsCog(bot))


class ModCommandsCog(
    commands.Cog,
    name="ModCommands",
    description="Posts a quick-reference embed of moderation commands and when to use them.",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot

    @commands.hybrid_command(
        name="modcommands", description="Show a reference of moderation commands and when to use them."
    )
    async def modcommands(self, ctx: Context):
        if not isinstance(ctx.author, discord.Member) or not any(
            r.id == MOD_ROLE_ID for r in ctx.author.roles
        ):
            await ctx.send("You don't have permission to use this command.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Moderation Commands",
            description="Quick reference for TerrierBot's discipline and case-management tools.",
            color=LogColors.MOD,
        )
        for name, syntax, usage in _FIELDS:
            embed.add_field(name=name, value=f"{syntax}\n{usage}", inline=False)

        await ctx.send(embed=embed)
