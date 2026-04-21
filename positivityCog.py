import shelve

import discord
from discord.ext import commands

from bot import Context, TerrierBot


async def setup(bot: TerrierBot):
    await bot.add_cog(PositivityCog(bot))


class PositivityCog(commands.Cog, name="Positivity"):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot

        self.default_interval = 100
        self.enabled_by_guild: dict[int, bool] = {}
        self.interval_by_guild: dict[int, int] = {}
        self.count_by_guild: dict[int, int] = {}
        self.recent_selected_by_guild: dict[int, list[int]] = {}
        self.selection_cooldown_size = 5

        with shelve.open("terrierbot.shelve") as sh:
            self.enabled_by_guild = sh.get("positivity_enabled_by_guild", {})
            self.interval_by_guild = sh.get("positivity_interval_by_guild", {})
            self.count_by_guild = sh.get("positivity_count_by_guild", {})
            self.recent_selected_by_guild = sh.get("positivity_recent_selected_by_guild", {})

        print("Positivity Cog Ready")

    def _save_state(self):
        with shelve.open("terrierbot.shelve") as sh:
            sh["positivity_enabled_by_guild"] = self.enabled_by_guild
            sh["positivity_interval_by_guild"] = self.interval_by_guild
            sh["positivity_count_by_guild"] = self.count_by_guild
            sh["positivity_recent_selected_by_guild"] = self.recent_selected_by_guild

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.guild is None:
            return

        guild_id = message.guild.id
        if not self.enabled_by_guild.get(guild_id, False):
            return

        author_id = message.author.id

        interval = self.interval_by_guild.get(guild_id, self.default_interval)
        current_count = self.count_by_guild.get(guild_id, 0) + 1
        self.count_by_guild[guild_id] = current_count

        if current_count >= interval:
            recent_selected = self.recent_selected_by_guild.get(guild_id, [])

            # Only the user who just sent the triggering message can be selected.
            # If they are on cooldown, keep waiting until a different eligible user speaks.
            if author_id in recent_selected:
                self.count_by_guild[guild_id] = interval
                self._save_state()
                return

            self.count_by_guild[guild_id] = 0
            recent_selected.append(author_id)
            if len(recent_selected) > self.selection_cooldown_size:
                recent_selected = recent_selected[-self.selection_cooldown_size :]
            self.recent_selected_by_guild[guild_id] = recent_selected

            self._save_state()
            await message.channel.send(
                f"Happy Positivity Tuesday, <@{author_id}>! 🌸✨ You have been selected to make a positive comment about yourself, a fellow member, or anything else. 💖"
            )
            return

        # Persist occasionally to keep message count across restarts.
        if current_count % 10 == 0:
            self._save_state()

    @commands.group(name="positivity", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def positivity_group(self, ctx: Context):
        if ctx.guild is None:
            _ = await ctx.send("This command can only be used in a server.")
            return

        guild_id = ctx.guild.id
        enabled = self.enabled_by_guild.get(guild_id, False)
        interval = self.interval_by_guild.get(guild_id, self.default_interval)
        _ = await ctx.send(
            f"Positivity Tuesday is {'enabled' if enabled else 'disabled'} in this server. Current interval: every {interval} messages."
        )

    @positivity_group.command(name="enable")
    @commands.has_permissions(manage_guild=True)
    async def positivity_enable(self, ctx: Context, every_x_messages: int | None = None):
        if ctx.guild is None:
            _ = await ctx.send("This command can only be used in a server.")
            return

        guild_id = ctx.guild.id
        interval = every_x_messages or self.interval_by_guild.get(guild_id, self.default_interval)
        if interval < 1:
            _ = await ctx.send("Interval must be at least 1 message.")
            return

        self.enabled_by_guild[guild_id] = True
        self.interval_by_guild[guild_id] = interval
        self.count_by_guild[guild_id] = 0
        self._save_state()

        _ = await ctx.send(
            f"Enabled Positivity Tuesday. I will send the message around every {interval} messages."
        )

    @positivity_group.command(name="disable")
    @commands.has_permissions(manage_guild=True)
    async def positivity_disable(self, ctx: Context):
        if ctx.guild is None:
            _ = await ctx.send("This command can only be used in a server.")
            return

        guild_id = ctx.guild.id
        self.enabled_by_guild[guild_id] = False
        self.count_by_guild[guild_id] = 0
        self._save_state()

        _ = await ctx.send("Disabled Positivity Tuesday for this server.")

    @positivity_group.command(name="interval")
    @commands.has_permissions(manage_guild=True)
    async def positivity_interval(self, ctx: Context, every_x_messages: int):
        if ctx.guild is None:
            _ = await ctx.send("This command can only be used in a server.")
            return

        if every_x_messages < 1:
            _ = await ctx.send("Interval must be at least 1 message.")
            return

        guild_id = ctx.guild.id
        self.interval_by_guild[guild_id] = every_x_messages
        self.count_by_guild[guild_id] = 0
        self._save_state()

        _ = await ctx.send(f"Positivity interval is now every {every_x_messages} messages.")

    @positivity_group.command(name="cooldown")
    @commands.has_permissions(manage_guild=True)
    async def positivity_cooldown(self, ctx: Context):
        if ctx.guild is None:
            _ = await ctx.send("This command can only be used in a server.")
            return

        guild_id = ctx.guild.id
        recent_selected = self.recent_selected_by_guild.get(guild_id, [])

        if not recent_selected:
            _ = await ctx.send("Positivity cooldown list is currently empty.")
            return

        entries: list[str] = []
        for user_id in reversed(recent_selected):
            member = ctx.guild.get_member(user_id)
            if member is not None:
                entries.append(f"{member.display_name} ({user_id})")
            else:
                entries.append(f"Unknown User ({user_id})")
        _ = await ctx.send(
            "Positivity cooldown list (most recent first): "
            + ", ".join(entries)
        )
