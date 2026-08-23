from __future__ import annotations

import discord
from discord.ext import commands

from bot import Context, TerrierBot
from .logConfig import LogColors, MOD_ROLE_ID

# Roughly an escalation ladder: check history first, then light → heavy
# per-member actions, then the one channel-wide emergency tool.
_FIELDS = [
    (
        "📋 Case History",
        "`=modlogs <member_or_id>` / `/modlogs`",
        "Check a member's full history (warns, kicks, timeouts, bans) before deciding how to escalate.",
    ),
    (
        "🔇 Timeout / Untimeout",
        "`=timeout <member> <duration> [reason]` / `=untimeout <member> [reason]`",
        "Quick cooldown for minor or heated behavior; untimeout lifts it early once things calm down.",
    ),
    (
        "👢 Kick",
        "`=kick <member> [reason]`",
        "Removes a member immediately without banning — for when someone needs to leave now but doesn't deserve a ban.",
    ),
    (
        "🔨 Ban / Unban",
        "`=ban <member> [duration] [reason]` / `=unban <user_id> [reason]`",
        "For serious or repeated violations; add a duration for a temp ban, omit it for permanent. Unban reverses it by ID.",
    ),
    (
        "🔒 Lockdown / Unlock",
        "`=lockdown` / `=unlock`",
        "Locks the current channel from @everyone during a raid or pile-on; unlock restores it once resolved.",
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
            description="Quick reference for TerrierBot's moderation tools, roughly in escalation order.",
            color=LogColors.MOD,
        )
        for name, syntax, usage in _FIELDS:
            embed.add_field(name=name, value=f"{syntax}\n{usage}", inline=False)

        await ctx.send(embed=embed)
