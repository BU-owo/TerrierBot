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
        "`=modlogs <member>` / `/modlogs`",
        "Check a member's full history (warns, kicks, timeouts, hardmutes, bans) before deciding how to escalate.",
    ),
    (
        "⚠️ Warn",
        "`=warn <member> <rule> <reason> [send_dm]` — issue a formal warning; warnings are permanent until removed\n"
        "`=warncount` / `=warninfo <member>` — see who has active warnings, or one member's full history\n"
        "`=warnremove <warn_id>` — remove a warning",
        "For rule violations that don't need removal from the server; warnings build the paper trail modlogs surfaces later.",
    ),
    (
        "🗑️ Warn Nullify",
        "`/warnnullify <warn_id> <reason>`",
        "Permanently deletes a warning row from the database. Only use for egregious errors.",
    ),
    (
        "🔇 Timeout / Untimeout",
        "`=timeout <member> <duration> [reason]` / `=untimeout <member> [reason]`",
        "Quick cooldown for minor or heated behavior; untimeout lifts it early once things calm down.",
    ),
    (
        "🔇 Hardmute / Unmute",
        "`=hardmute <member>` / `=unmute <member>`",
        "Strips a member's roles and confines them indefinitely, for questioning potential bots. `=unmute` restores. No auto-expiry.",
    ),
    (
        "👢 Kick",
        "`=kick <member> [reason]`",
        "Removes a member immediately without banning.",
    ),
    (
        "🔨 Ban / Unban",
        "`=ban <member> [rule] [duration] [purge:Xd] [reason]` / `=unban <user_id> [reason]`",
        "/ban requires picking a rule from the dropdown; =ban can skip it. Add a duration for a temp ban, omit for permanent. Rule 8 (scams) auto-purges last 4h.",
    ),
    (
        "🧹 Purge",
        "`=purge <amount>` (1-100) / `=purgeafter [target]` / `=purgeuser <member> <amount>` (1-100)",
        "Purgeafter deletes everything after a target message (reply to it, or pass its ID/link) in the current channel. Purgeuser deletes member's messages in current channel.",
    ),
    (
        "🔒 Lockdown / Unlock",
        "`=lockdown` / `=unlock`",
        "Locks the current channel from @everyone; unlock restores it.",
    ),
    (
        "🗳️ Modvote",
        "`/modvote start <target> <options> <duration_minutes>` / `/modvote close [vote_id]`",
        "Anonymous vote for mods only.",
    ),
    (
        "🏛️ Politics Application",
        "`=joinpolitics` — post the application embed in a channel",
        "Members apply through the embed's button. Approve trustworthy users",
    ),
    (
        "🏛️ Kick from Politics",
        "`/kickpolitics <user>`",
        "Removes the Politics role from a member. Also usable by the Politics Mod role.",
    ),
    (
        "😐 Unserious Mode",
        "`/unserious <enable|disable> <member>`",
        "Toggles a member's access to the Serious category on/off.",
    ),
    (
        "📝 View Edits",
        "`=viewedits [target]` / `/viewedits [message]`",
        "Shows a message's edit history. =viewedits (reply to the message) posts to logs; /viewedits replies ephemerally.",
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
            await ctx.send("Oops! You can't run that... mods only!", ephemeral=True)
            return

        embed = discord.Embed(
            title="Moderation Commands",
            description="Quick reference for everything gated to the mod role — discipline, case-management, and a few other mod-only actions.",
            color=LogColors.MOD,
        )
        for name, syntax, usage in _FIELDS:
            embed.add_field(name=name, value=f"{syntax}\n{usage}", inline=False)

        await ctx.send(embed=embed)
