import shelve
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands
from bot import TerrierBot, Context

PRESETS = {
    "Freshmen": {
        "role_id": 1541770660710191134,
        "emoji": "🧑‍🤝‍🧑",
        "title": "🧑‍🤝‍🧑 Freshmen Ping Role",
        "description": (
            "Freshmen! Are you interested in being invited to do "
            "**[insert anything you want to do]** with people from this server? "
            "<@&1541770660710191134> is pingable by anyone in your class, and it will "
            "**only reach people who have opted in to be pinged** (no constant pings @'30).\n\n"
            "**React with 🧑‍🤝‍🧑 below to add the role.**\n\n"
            "Ping when you are heading to the dining hall, exploring campus, getting coffee, "
            "going to an on campus event, etc.\n\n"
            "*This is for orientation week only.*"
        ),
    },
    "Scavenger": {
        "role_id": 1420106696222703636,
        "button": True,
        "emoji_id": 1421470279355338813,
        "title": "🔍 Scavenger Hunt Alerts",
        "description": (
            "Get alerted to our energy drink (and more) scavenger hunt hides! "
            "Celsius, Monster, Stickers, Dunkin, and more!\n\n"
            "**Use the buttons below to add or remove the role.**"
        ),
    },
}


class RoleButtonView(discord.ui.View):
    def __init__(self, data: dict):
        super().__init__(timeout=None)
        self.role_id: int = data["role_id"]
        add_button = discord.ui.Button(
            label="Add role",
            style=discord.ButtonStyle.success,
            emoji=discord.PartialEmoji(name="e", id=data["emoji_id"]),
            custom_id=f"reactionrole:{self.role_id}:add",
        )
        add_button.callback = self._add
        remove_button = discord.ui.Button(
            label="Remove role",
            style=discord.ButtonStyle.secondary,
            custom_id=f"reactionrole:{self.role_id}:remove",
        )
        remove_button.callback = self._remove
        self.add_item(add_button)
        self.add_item(remove_button)

    async def _add(self, interaction: discord.Interaction):
        await self._update(interaction, add=True)

    async def _remove(self, interaction: discord.Interaction):
        await self._update(interaction, add=False)

    async def _update(self, interaction: discord.Interaction, add: bool):
        role = interaction.guild.get_role(self.role_id)
        if role is None:
            await interaction.response.send_message("That role no longer exists.", ephemeral=True)
            return

        has_role = role in interaction.user.roles
        try:
            if add and has_role:
                message = f"You already have the {role.mention} role!"
            elif add:
                await interaction.user.add_roles(role)
                message = f"You now have the {role.mention} role!"
            elif has_role:
                await interaction.user.remove_roles(role)
                message = f"You removed the {role.mention} role."
            else:
                message = f"You don't have the {role.mention} role."
        except (discord.Forbidden, discord.HTTPException):
            message = "I couldn't update your role. Please let a mod know."

        await interaction.response.send_message(message, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: TerrierBot):
    await bot.add_cog(ReactionRoleCog(bot))


class ReactionRoleCog(commands.Cog, name="ReactionRole", description="Self-assignable reaction roles. Requires Manage Roles to configure."):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot

        with shelve.open("terrierbot.shelve") as sh:
            self.role_messages: dict[str, int] = sh.get("reactionroles", {})

        print("ReactionRole Cog Ready")

    async def cog_load(self) -> None:
        for data in PRESETS.values():
            if data.get("button"):
                self.bot.add_view(RoleButtonView(data))

    def _save_state(self) -> None:
        with shelve.open("terrierbot.shelve") as sh:
            sh["reactionroles"] = self.role_messages

    @app_commands.command(name="reactionrole", description="Post a reaction role message from a preset.")
    @app_commands.describe(preset="Which preset message to post")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_roles=True)
    async def reactionrole(self, interaction: discord.Interaction, preset: Literal[tuple(PRESETS.keys())]):
        await interaction.response.defer(ephemeral=True)

        data = PRESETS[preset]
        embed = discord.Embed(title=data.get("title"), description=data["description"], color=discord.Color.blurple())
        allowed = discord.AllowedMentions(roles=True)

        if data.get("button"):
            await interaction.channel.send(embed=embed, view=RoleButtonView(data), allowed_mentions=allowed)
        else:
            message = await interaction.channel.send(embed=embed, allowed_mentions=allowed)
            await message.add_reaction(data["emoji"])
            self.role_messages[str(message.id)] = data["role_id"]
            self._save_state()

        await interaction.followup.send("Reaction role posted.", ephemeral=True)

    def _preset_for_role(self, role_id: int) -> dict | None:
        for data in PRESETS.values():
            if data["role_id"] == role_id:
                return data
        return None

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        role_id = self.role_messages.get(str(payload.message_id))
        if role_id is None:
            return

        preset = self._preset_for_role(role_id)
        if preset is None or payload.emoji.name != preset.get("emoji"):
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        role = guild.get_role(role_id)
        if role is None or payload.member is None:
            return

        try:
            await payload.member.add_roles(role)
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        role_id = self.role_messages.get(str(payload.message_id))
        if role_id is None:
            return

        preset = self._preset_for_role(role_id)
        if preset is None or payload.emoji.name != preset.get("emoji"):
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        role = guild.get_role(role_id)
        if role is None:
            return

        try:
            member = await guild.fetch_member(payload.user_id)
            await member.remove_roles(role)
        except (discord.Forbidden, discord.HTTPException):
            pass
