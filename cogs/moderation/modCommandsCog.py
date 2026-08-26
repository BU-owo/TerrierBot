from __future__ import annotations

import discord
from discord.ext import commands

from bot import Context, TerrierBot
from ..logging.logConfig import LogColors, MOD_ROLE_ID

# Tools gated to the MOD_ROLE_ID team, wherever they actually live in the
# repo — discipline/case-management (cogs/moderation/) plus a couple of
# other mod-only actions from cogs/community/. Excluded: manage_guild-gated
# server config (positivity, starboard, feedbacksetup — a different, higher
# permission tier than the mod role) and fun toggles (towoken) — those stay
# in the general =help instead.
_FIELDS = [
    (
        "📋 Case History",
        "`=modlogs <member_or_id>` / `/modlogs`",
        "Check a member's full history (warns, kicks, timeouts, hardmutes, bans) before deciding how to escalate.",
    ),
    (
        "⚠️ Warn",
        "`=warn <member> <rule> <reason> [send_dm]` — issue a formal warning; warnings are permanent until removed\n"
        "`=warncount` / `=warninfo <member>` — see who has active warnings, or one member's full history\n"
        "`=warnremove <warn_id>` — remove a warning",
        "For rule violations that don't need removal from the server; warnings build the paper trail modlogs surfaces later. Members can self-appeal via `/warnappeal` — you'll get an accept/reject prompt in response when they do.",
    ),
    (
        "🔇 Timeout / Untimeout",
        "`=timeout <member> <duration> [reason]` / `=untimeout <member> [reason]`",
        "Quick cooldown for minor or heated behavior; untimeout lifts it early once things calm down.",
    ),
    (
        "🔇 Hardmute / Unmute",
        "`=hardmute <member>` / `=unmute <member>`",
        "Strips a member's roles and confines them to one channel, indefinitely — useful when you're not sure if an account is a bot yet and want to question it somewhere isolated. `=unmute` restores their original roles. No auto-expiry; you have to lift it manually.",
    ),
    (
        "👢 Kick",
        "`=kick <member> [reason]`",
        "Removes a member immediately without banning.",
    ),
    (
        "🔨 Ban / Unban",
        "`=ban <member> [rule] [duration] [reason]` / `=unban <user_id> [reason]`",
        "For serious or repeated violations; `/ban` requires picking a rule from the dropdown, `=ban` can skip it. Add a duration (e.g. `2h`) right after the member for a temp ban, omit it for permanent — everything else is just the reason, no special phrasing needed. Unban reverses it by ID. Banned users get pointed to the appeals server in their DM; approve/deny shows up as buttons on the appeal post in mod-log.",
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
        "`/modvote start <target> <options> <duration_minutes>` / `/modvote close [vote_id]`",
        "For a discipline call that shouldn't rest on one mod alone — anonymous team vote.",
    ),
    (
        "🏛️ Politics Application",
        "`=joinpolitics` — post the application embed in a channel",
        "Members apply through the embed's button; you'll get an Approve/Deny prompt to review each application that comes in.",
    ),
    (
        "🚀 Roleboost",
        "`=roleboost <user> <role>`",
        "Grants a role tied to someone's booster status (they must already have the booster role); auto-removed if they lose it later.",
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
            description="Quick reference for everything gated to the mod role — discipline, case-management, and a few other mod-only actions.",
            color=LogColors.MOD,
        )
        for name, syntax, usage in _FIELDS:
            embed.add_field(name=name, value=f"{syntax}\n{usage}", inline=False)

        await ctx.send(embed=embed)
