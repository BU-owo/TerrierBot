from __future__ import annotations
import logging
import shelve

import discord
from discord import app_commands
from discord.ext import commands

from bot import TerrierBot, Context

log = logging.getLogger(__name__)

BOOST_ROLE_ID = 1415488019435098152
ROLEBOOST_MOD_ROLE_ID = 1402095379935395934
ANNOUNCE_CHANNEL_ID = 1441925119202164886

_SHELVE_FILE = "terrierbot.shelve"
_SHELVE_KEY = "roleboost_assignments"


async def setup(bot: TerrierBot):
    await bot.add_cog(RoleBoostCog(bot))


class RoleBoostCog(
    commands.Cog,
    name="RoleBoost",
    description="Lets boosters grant a role to a user, auto-removed when the booster loses their boost role.",
):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot
        # member_id -> role_id, for roles granted via /roleboost that should be
        # auto-removed once the member loses BOOST_ROLE_ID.
        self.assignments: dict[int, int] = {}
        with shelve.open(_SHELVE_FILE) as sh:
            self.assignments = sh.get(_SHELVE_KEY, {})

    def _save(self) -> None:
        with shelve.open(_SHELVE_FILE) as sh:
            sh[_SHELVE_KEY] = self.assignments

    def _has_boost_role(self, member: discord.Member) -> bool:
        return any(r.id == BOOST_ROLE_ID for r in member.roles)

    def _can_use_roleboost(self, member: discord.Member) -> bool:
        return any(r.id == ROLEBOOST_MOD_ROLE_ID for r in member.roles)

    # ── /roleboost ──────────────────────────────────────────────────────────

    @commands.hybrid_command(
        name="roleboost",
        description="Give a user a role tied to their booster status.",
    )
    @app_commands.describe(
        user="The member to give the role to",
        role="The role to assign",
    )
    async def roleboost(self, ctx: Context, user: discord.Member, role: discord.Role) -> None:
        """Assign [role] to [user]. Requires the invoker to have the roleboost mod
        role, and the target to already have the booster role. The role is
        auto-removed if the target later loses the booster role."""
        author = ctx.author
        if not isinstance(author, discord.Member) or not self._can_use_roleboost(author):
            await ctx.send("You don't have permission to use this command.", ephemeral=True)
            return

        if not self._has_boost_role(user):
            await ctx.send(
                f"{user.display_name} doesn't have the booster role, so this can't be applied.",
                ephemeral=True,
            )
            return

        try:
            await user.add_roles(role, reason=f"roleboost by {author.display_name}")
        except discord.Forbidden:
            await ctx.send("I don't have permission to assign that role.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await ctx.send(f"Failed to assign role: {e}", ephemeral=True)
            return

        self.assignments[user.id] = role.id
        self._save()

        await ctx.send(
            f"✅ Gave {user.mention} the {role.mention} role. "
            "It will be removed automatically if they lose the booster role.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    # ── Auto-removal on boost-role loss ────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        had_boost = any(r.id == BOOST_ROLE_ID for r in before.roles)
        has_boost = any(r.id == BOOST_ROLE_ID for r in after.roles)

        if not (had_boost and not has_boost):
            return  # only care about the transition from having it to losing it

        role_id = self.assignments.pop(after.id, None)
        if role_id is None:
            return
        self._save()

        guild = after.guild
        role = guild.get_role(role_id)

        if role is not None and role in after.roles:
            try:
                await after.remove_roles(role, reason="Lost booster role")
            except (discord.Forbidden, discord.HTTPException):
                pass

        channel = self.bot.get_channel(ANNOUNCE_CHANNEL_ID)
        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            role_mention = role.mention if role is not None else f"<@&{role_id}>"
            try:
                await channel.send(
                    f"{after.mention} is no longer boosting and lost {role_mention}.",
                    allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
                )
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        # Clean up a stale assignment if a tracked member leaves the guild.
        if member.id in self.assignments:
            self.assignments.pop(member.id, None)
            self._save()