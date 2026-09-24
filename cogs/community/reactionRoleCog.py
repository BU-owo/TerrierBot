import shelve
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from bot import TerrierBot, Context

# Seed preset — only used the first time the bot ever runs with no shelve
# data yet. After that, self.presets (loaded from shelve) is the source of
# truth and this constant is ignored. The old "Freshmen" reaction-based
# preset has been dropped along with reaction-role support entirely.
_SEED_PRESETS = {
    "Scavenger": {
        "role_id": 1420106696222703636,
        "emoji": "<:e:1421470279355338813>",
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
        emoji = discord.PartialEmoji.from_str(data["emoji"])
        add_button = discord.ui.Button(
            label="Add role",
            style=discord.ButtonStyle.success,
            emoji=emoji,
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


class ReactionRoleCog(commands.Cog, name="ReactionRole", description="Self-assignable button roles. Requires Manage Roles to configure."):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot

        with shelve.open("terrierbot.shelve") as sh:
            self.presets: dict[str, dict] = sh.get("reactionrole_presets")
            if self.presets is None:
                self.presets = dict(_SEED_PRESETS)
                sh["reactionrole_presets"] = self.presets

        print("ReactionRole Cog Ready")

    async def cog_load(self) -> None:
        for data in self.presets.values():
            self.bot.add_view(RoleButtonView(data))

    def _save_presets(self) -> None:
        with shelve.open("terrierbot.shelve") as sh:
            sh["reactionrole_presets"] = self.presets

    async def _preset_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=name, value=name)
            for name in self.presets
            if current.lower() in name.lower()
        ][:25]

    @app_commands.command(name="reactionrole", description="Post a button role message from a preset.")
    @app_commands.describe(preset="Which preset message to post")
    @app_commands.autocomplete(preset=_preset_autocomplete)
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_roles=True)
    async def reactionrole(self, interaction: discord.Interaction, preset: str):
        data = self.presets.get(preset)
        if data is None:
            await interaction.response.send_message(f"No preset named `{preset}`.", ephemeral=True)
            return

        embed = discord.Embed(title=data.get("title"), description=data["description"], color=discord.Color.blurple())
        await interaction.channel.send(embed=embed, view=RoleButtonView(data))
        await interaction.response.send_message("Reaction role posted.", ephemeral=True)

    @app_commands.command(name="addreactionrole", description="Register a new button role preset (does not post it).")
    @app_commands.describe(
        name="Unique key for this preset, used with /reactionrole",
        title="Embed title",
        description="Embed description",
        role="Role granted/removed by the buttons",
        emoji="Emoji shown on the Add role button — normal or custom",
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_roles=True)
    async def addreactionrole(
        self,
        interaction: discord.Interaction,
        name: str,
        title: str,
        description: str,
        role: discord.Role,
        emoji: str,
    ):
        if name in self.presets:
            await interaction.response.send_message(f"A preset named `{name}` already exists.", ephemeral=True)
            return

        parsed_emoji = discord.PartialEmoji.from_str(emoji)
        # Custom emoji: validate it's actually usable by the bot (from_str will
        # happily parse a well-formed <:name:id> string even if the emoji
        # doesn't exist/isn't accessible).
        if parsed_emoji.id is not None and discord.utils.get(self.bot.emojis, id=parsed_emoji.id) is None:
            await interaction.response.send_message(
                "I can't find that custom emoji — make sure it's from a server I'm in.", ephemeral=True
            )
            return

        data = {
            "role_id": role.id,
            "emoji": str(parsed_emoji),
            "title": title,
            "description": description,
        }
        self.presets[name] = data
        self._save_presets()
        self.bot.add_view(RoleButtonView(data))

        await interaction.response.send_message(
            f"Registered preset `{name}`. Post it with `/reactionrole preset:{name}`.", ephemeral=True
        )