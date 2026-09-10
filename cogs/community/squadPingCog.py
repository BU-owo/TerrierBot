from __future__ import annotations

import json
import os
import re
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from bot import TerrierBot, Context

# ── Persistence ──────────────────────────────────────────────────────────────
# Same pattern as banCog's tempbans.json: gitignored, runtime-generated JSON
# under data/, keyed by list name -> {"description": str, "members": [ids]}.
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
_SOFTPINGS_FILE = os.path.join(_DATA_DIR, "softpings.json")

_CHUNK_SIZE = 90  # stay under Discord's ~100-mention notify cap per message

# Seeded into softpings.json on first load if not already present. Anyone can
# create further lists at runtime via /squadpingcreate.
_SEED_LISTS: dict[str, str] = {
    "badminton": "meet to play badminton",
}

_MAX_NAME_LENGTH = 32
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


class SquadPingCog(
    commands.Cog,
    name="SquadPing",
    description="Roleless squad-ping lists — /squadpingcreate to make one, /squadpingmanage to join or leave, /squadping to ping it.",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot
        self.lists: dict[str, dict] = _load()

    # ── shared helpers ────────────────────────────────────────────────────────

    def _unknown_list_message(self, key: str) -> str:
        if not self.lists:
            return f"There is no \"{key}\" squad-ping list, and none exist yet — create one with `/squadpingcreate`."
        valid = ", ".join(sorted(self.lists))
        return f"There is no \"{key}\" squad-ping list. Valid lists: {valid}."

    async def _list_name_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        current_lower = current.strip().lower()
        matches = sorted(name for name in self.lists if current_lower in name.lower())
        return [app_commands.Choice(name=name, value=name) for name in matches[:25]]

    async def _join(self, ctx: Context, key: str) -> None:
        ids = self.lists[key]["members"]
        if ctx.author.id in ids:
            await ctx.send(f"You're already on the {key} ping list.", ephemeral=True)
            return
        ids.append(ctx.author.id)
        _save(self.lists)
        await ctx.send(f"Added you to the {key} ping list.", ephemeral=True)

    async def _leave(self, ctx: Context, key: str) -> None:
        ids = self.lists[key]["members"]
        if ctx.author.id not in ids:
            await ctx.send(f"You're not on the {key} ping list.", ephemeral=True)
            return
        ids.remove(ctx.author.id)
        _save(self.lists)
        await ctx.send(f"Removed you from the {key} ping list.", ephemeral=True)

    async def _ping(self, ctx: Context, key: str) -> None:
        ids = self.lists[key]["members"]
        if not ids:
            await ctx.send("There is no one in this ping list.", ephemeral=True)
            return

        await ctx.send(f"Pinging {len(ids)} member(s) for {key}...", ephemeral=True)
        channel = ctx.channel
        for i in range(0, len(ids), _CHUNK_SIZE):
            chunk = ids[i:i + _CHUNK_SIZE]
            mentions = " ".join(f"<@{uid}>" for uid in chunk)
            await channel.send(
                f"{mentions}\n{ctx.author.mention} is pinging for **{key}**.",
                allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
            )

    # ── /squadping ───────────────────────────────────────────────────────────

    @commands.hybrid_command(name="squadping", description="Ping everyone on a squad-ping list.")
    @app_commands.describe(name="Which squad-ping list to ping")
    @app_commands.autocomplete(name=_list_name_autocomplete)
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def squadping(self, ctx: Context, name: str) -> None:
        key = name.strip().lower()
        if key not in self.lists:
            await ctx.send(self._unknown_list_message(key), ephemeral=True)
            return
        await self._ping(ctx, key)

    # ── /squadpingcreate ─────────────────────────────────────────────────────

    @commands.hybrid_command(name="squadpingcreate", description="Create a new squad-ping list.")
    @app_commands.describe(
        name="Short name for the list — lowercase letters/digits/-/_ only, e.g. \"boardgames\"",
        description="What this list is for",
    )
    async def squadpingcreate(self, ctx: Context, name: str, *, description: str) -> None:
        key = name.strip().lower()
        description = description.strip()

        if not _NAME_RE.match(key):
            await ctx.send(
                f"That name isn't valid — use 1-{_MAX_NAME_LENGTH} lowercase letters, digits, hyphens, or underscores.",
                ephemeral=True,
            )
            return

        if not description:
            await ctx.send("Description can't be empty.", ephemeral=True)
            return
        if len(description) > _MAX_DESCRIPTION_LENGTH:
            await ctx.send(
                f"Description is too long — keep it under {_MAX_DESCRIPTION_LENGTH} characters.",
                ephemeral=True,
            )
            return

        if key in self.lists:
            await ctx.send(f"A \"{key}\" ping list already exists.", ephemeral=True)
            return

        self.lists[key] = {"description": description, "members": []}
        _save(self.lists)

        await ctx.send(
            f"Created the **{key}** ping list. Use `/squadpingmanage add {key}` to join and `/squadping {key}` to ping it.",
            ephemeral=True,
        )

    # ── /squadpinglist ───────────────────────────────────────────────────────

    @commands.hybrid_command(name="squadpinglist", description="List all squad-ping lists.")
    async def squadpinglist(self, ctx: Context) -> None:
        embed = discord.Embed(title="📋 Squad-ping lists", color=discord.Color.blurple())
        if not self.lists:
            embed.description = "No squad-ping lists yet — create one with `/squadpingcreate`."
        else:
            for key in sorted(self.lists):
                entry = self.lists[key]
                embed.add_field(
                    name=key,
                    value=f"{entry['description'] or '*No description*'}\n{len(entry['members'])} member(s)",
                    inline=False,
                )
        await ctx.send(embed=embed, ephemeral=True)

    # ── /squadpingmanage ─────────────────────────────────────────────────────

    @commands.hybrid_command(name="squadpingmanage", description="Join or leave a squad-ping list.")
    @app_commands.describe(action="add to join the list, remove to leave it", name="Which squad-ping list")
    @app_commands.autocomplete(name=_list_name_autocomplete)
    async def squadpingmanage(self, ctx: Context, action: Literal["add", "remove"], name: str) -> None:
        key = name.strip().lower()
        if key not in self.lists:
            await ctx.send(self._unknown_list_message(key), ephemeral=True)
            return
        if action == "add":
            await self._join(ctx, key)
        else:
            await self._leave(ctx, key)


async def setup(bot: TerrierBot):
    await bot.add_cog(SquadPingCog(bot))
