from __future__ import annotations

import json
import os
import re

import discord
from discord import app_commands
from discord.ext import commands

# ── Persistence ──────────────────────────────────────────────────────────────
# Same pattern as banCog's tempbans.json: gitignored, runtime-generated JSON
# under data/, keyed by list name -> {"description": str, "members": [ids]}.
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
_SOFTPINGS_FILE = os.path.join(_DATA_DIR, "softpings.json")

_CHUNK_SIZE = 90  # stay under Discord's ~100-mention notify cap per message

# Seeded into softpings.json on first load if not already present. Anyone can
# create further lists at runtime via /softping.
_SEED_LISTS: dict[str, str] = {
    "badminton": "meet to play badminton",
}

# /join<name>, /leave<name>, and /ping<name> all get generated from a list's
# name, and Discord caps command names at 32 characters — "leave" (5 chars)
# is the longest prefix, so that's what bounds how long a name can be.
_PREFIXES: tuple[str, ...] = ("join", "leave", "ping")
_MAX_NAME_LENGTH = 32 - max(len(p) for p in _PREFIXES)
_NAME_RE = re.compile(rf"^[a-z0-9_-]{{1,{_MAX_NAME_LENGTH}}}$")
_MAX_DESCRIPTION_LENGTH = 100  # Discord's own per-command description cap


def _migrate(raw: dict) -> tuple[dict[str, dict], bool]:
    """Upgrade the old {name: [ids]} shape to {name: {"description", "members"}},
    and seed any lists from _SEED_LISTS that aren't present yet."""
    changed = False
    data: dict[str, dict] = {}
    for key, value in raw.items():
        if isinstance(value, list):
            data[key] = {"description": _SEED_LISTS.get(key, ""), "members": value}
            changed = True
        else:
            data[key] = value
    for key, description in _SEED_LISTS.items():
        if key not in data:
            data[key] = {"description": description, "members": []}
            changed = True
    return data, changed


def _load() -> dict[str, dict]:
    if not os.path.exists(_SOFTPINGS_FILE):
        data, _ = _migrate({})
        _save(data)
        return data
    with open(_SOFTPINGS_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)
    data, changed = _migrate(raw)
    if changed:
        _save(data)
    return data


def _save(data: dict[str, dict]) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_SOFTPINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


class SoftPingCog(commands.Cog, name="SoftPing", description="Roleless ping lists — join with /join<name>, ping with /ping<name>."):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.lists: dict[str, dict] = _load()

    async def cog_load(self) -> None:
        # Dynamically-registered commands live only in the tree, not in
        # __cog_app_commands__, so they don't survive a restart on their own
        # — re-add one set per saved list every time the cog loads.
        for name in self.lists:
            self._register_commands(name)

    def cog_unload(self) -> None:
        for name in self.lists:
            for prefix in _PREFIXES:
                self.bot.tree.remove_command(f"{prefix}{name}")

    # ── shared helpers ────────────────────────────────────────────────────────

    async def _join(self, interaction: discord.Interaction, key: str) -> None:
        ids = self.lists[key]["members"]
        if interaction.user.id in ids:
            await interaction.response.send_message(f"You're already on the {key} ping list.", ephemeral=True)
            return
        ids.append(interaction.user.id)
        _save(self.lists)
        await interaction.response.send_message(f"Added you to the {key} ping list.", ephemeral=True)

    async def _leave(self, interaction: discord.Interaction, key: str) -> None:
        ids = self.lists[key]["members"]
        if interaction.user.id not in ids:
            await interaction.response.send_message(f"You're not on the {key} ping list.", ephemeral=True)
            return
        ids.remove(interaction.user.id)
        _save(self.lists)
        await interaction.response.send_message(f"Removed you from the {key} ping list.", ephemeral=True)

    async def _ping(self, interaction: discord.Interaction, key: str) -> None:
        ids = self.lists[key]["members"]
        if not ids:
            await interaction.response.send_message("There is no one in this ping list.", ephemeral=True)
            return

        await interaction.response.send_message(f"Pinging {len(ids)} member(s) for {key}...", ephemeral=True)
        channel = interaction.channel
        for i in range(0, len(ids), _CHUNK_SIZE):
            chunk = ids[i:i + _CHUNK_SIZE]
            mentions = " ".join(f"<@{uid}>" for uid in chunk)
            await channel.send(
                f"{mentions}\n{interaction.user.mention} is pinging for **{key}**.",
                allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
            )

    # ── dynamic command registration ─────────────────────────────────────────

    def _register_commands(self, name: str) -> None:
        """Build and register /join<name>, /leave<name>, /ping<name> for a
        saved list. Safe to call again for a name that's already registered
        (e.g. on cog reload) — add_command(override=True) just replaces it."""

        async def join_callback(interaction: discord.Interaction) -> None:
            await self._join(interaction, name)

        async def leave_callback(interaction: discord.Interaction) -> None:
            await self._leave(interaction, name)

        async def ping_callback(interaction: discord.Interaction) -> None:
            await self._ping(interaction, name)

        ping_callback = app_commands.checks.cooldown(1, 30, key=lambda i: i.user.id)(ping_callback)

        join_cmd = app_commands.Command(
            name=f"join{name}", description=f"Join the {name} ping list", callback=join_callback
        )
        leave_cmd = app_commands.Command(
            name=f"leave{name}", description=f"Leave the {name} ping list", callback=leave_callback
        )
        ping_cmd = app_commands.Command(
            name=f"ping{name}", description=f"Ping everyone on the {name} list", callback=ping_callback
        )

        @ping_cmd.error
        async def ping_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
            if isinstance(error, app_commands.CommandOnCooldown):
                await interaction.response.send_message(
                    f"Slow down! You can use /ping{name} again in {error.retry_after:.0f}s.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message("Something went wrong running that command.", ephemeral=True)
                raise error

        for cmd in (join_cmd, leave_cmd, ping_cmd):
            self.bot.tree.add_command(cmd, override=True)

    # ── /softping ─────────────────────────────────────────────────────────────

    @app_commands.command(name="softping", description="Create a new soft-ping list.")
    @app_commands.describe(
        name="Short name for the list — lowercase letters/digits/-/_ only, e.g. \"boardgames\"",
        description="What this list is for",
    )
    async def softping(self, interaction: discord.Interaction, name: str, description: str) -> None:
        key = name.strip().lower()
        description = description.strip()

        if not _NAME_RE.match(key):
            await interaction.response.send_message(
                f"That name isn't valid — use 1-{_MAX_NAME_LENGTH} lowercase letters, digits, hyphens, or underscores.",
                ephemeral=True,
            )
            return

        if not description:
            await interaction.response.send_message("Description can't be empty.", ephemeral=True)
            return
        if len(description) > _MAX_DESCRIPTION_LENGTH:
            await interaction.response.send_message(
                f"Description is too long — keep it under {_MAX_DESCRIPTION_LENGTH} characters.",
                ephemeral=True,
            )
            return

        if key in self.lists:
            await interaction.response.send_message(f"A \"{key}\" ping list already exists.", ephemeral=True)
            return

        for prefix in _PREFIXES:
            if self.bot.tree.get_command(f"{prefix}{key}") is not None:
                await interaction.response.send_message(
                    f"\"{key}\" collides with an existing command — pick a different name.",
                    ephemeral=True,
                )
                return

        self.lists[key] = {"description": description, "members": []}
        _save(self.lists)
        self._register_commands(key)

        if interaction.guild is not None:
            # Mirrors bot.py's _sync_app_commands_to_joined_guilds/=sync — the
            # new commands need a guild sync before they're actually usable.
            self.bot.tree.copy_global_to(guild=interaction.guild)
            await self.bot.tree.sync(guild=interaction.guild)

        await interaction.response.send_message(
            f"Created the **{key}** ping list. Use `/join{key}` to join and `/ping{key}` to ping it.",
            ephemeral=True,
        )

    # ── /softpinglist ────────────────────────────────────────────────────────

    @app_commands.command(name="softpinglist", description="List all soft-ping lists.")
    async def softpinglist(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(title="📋 Soft-ping lists", color=discord.Color.blurple())
        if not self.lists:
            embed.description = "No soft-ping lists yet — create one with `/softping`."
        else:
            for key in sorted(self.lists):
                entry = self.lists[key]
                embed.add_field(
                    name=key,
                    value=f"{entry['description'] or '*No description*'}\n{len(entry['members'])} member(s)",
                    inline=False,
                )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SoftPingCog(bot))
