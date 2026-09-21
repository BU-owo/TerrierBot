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
        "emoji_id": 1421470279355338813,
        "title": "🔍 Scavenger Hunt Alerts",
        "description": (
            "Get alerted to our energy drink (and more) scavenger hunt hides! "
            "Celsius, Monster, Stickers, Dunkin, and more!\n\n"
            "**React with {emoji} below to add the role.** React again to remove it."
        ),
    },
}


async def setup(bot: TerrierBot):
    await bot.add_cog(ReactionRoleCog(bot))


class ReactionRoleCog(commands.Cog, name="ReactionRole", description="Self-assignable reaction roles. Requires Manage Roles to configure."):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot

        with shelve.open("terrierbot.shelve") as sh:
            self.role_messages: dict[str, int] = sh.get("reactionroles", {})

        print("ReactionRole Cog Ready")

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

        emoji = data.get("emoji")
        if emoji is None and data.get("emoji_id") is not None:
            emoji = self.bot.get_emoji(data["emoji_id"])
            if emoji is None:
                await interaction.followup.send(
                    "Couldn't find the configured emoji for this preset (the bot may not share a server with it).",
                    ephemeral=True,
                )
                return

        description = data["description"].format(emoji=emoji) if "{emoji}" in data["description"] else data["description"]
        embed = discord.Embed(title=data.get("title"), description=description, color=discord.Color.blurple())
        message = await interaction.channel.send(embed=embed, allowed_mentions=discord.AllowedMentions(roles=True))
        await message.add_reaction(emoji)

        self.role_messages[str(message.id)] = data["role_id"]
        self._save_state()

        await interaction.followup.send("Reaction role posted.", ephemeral=True)

    def _preset_for_role(self, role_id: int) -> dict | None:
        for data in PRESETS.values():
            if data["role_id"] == role_id:
                return data
        return None

    def _emoji_matches(self, emoji: discord.PartialEmoji, preset: dict) -> bool:
        if preset.get("emoji_id") is not None:
            return emoji.id == preset["emoji_id"]
        return emoji.name == preset.get("emoji")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        role_id = self.role_messages.get(str(payload.message_id))
        if role_id is None:
            return

        preset = self._preset_for_role(role_id)
        if preset is None or not self._emoji_matches(payload.emoji, preset):
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
        if preset is None or not self._emoji_matches(payload.emoji, preset):
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
