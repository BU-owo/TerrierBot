import shelve
from datetime import datetime, time
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

from bot import Context, TerrierBot

ET = ZoneInfo("America/New_York")


async def setup(bot: TerrierBot):
    await bot.add_cog(PositivityCog(bot))


class PositivityCog(commands.Cog, name="Positivity", description="Positivity Tuesday — randomly selects a member to share something positive. Requires Manage Server to configure."):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot

        self.default_interval = 100
        self.enabled_by_guild: dict[int, bool] = {}
        self.interval_by_guild: dict[int, int] = {}
        self.count_by_guild: dict[int, int] = {}
        self.recent_selected_by_guild: dict[int, list[int]] = {}
        self.selection_cooldown_size = 5
        # Guilds that have opted into auto-enable (set when first manually enabled)
        self.opted_in_by_guild: dict[int, bool] = {}
        # Guilds that manually disabled during the current Tuesday — skip auto-enable until next week
        self.manually_disabled_by_guild: dict[int, bool] = {}

        with shelve.open("terrierbot.shelve") as sh:
            self.enabled_by_guild = sh.get("positivity_enabled_by_guild", {})
            self.interval_by_guild = sh.get("positivity_interval_by_guild", {})
            self.count_by_guild = sh.get("positivity_count_by_guild", {})
            self.recent_selected_by_guild = sh.get("positivity_recent_selected_by_guild", {})
            self.opted_in_by_guild = sh.get("positivity_opted_in_by_guild", {})
            self.manually_disabled_by_guild = sh.get("positivity_manually_disabled_by_guild", {})

        self.tuesday_task.start()
        print("Positivity Cog Ready")

    def cog_unload(self):
        self.tuesday_task.cancel()

    def _save_state(self):
        with shelve.open("terrierbot.shelve") as sh:
            sh["positivity_enabled_by_guild"] = self.enabled_by_guild
            sh["positivity_interval_by_guild"] = self.interval_by_guild
            sh["positivity_count_by_guild"] = self.count_by_guild
            sh["positivity_recent_selected_by_guild"] = self.recent_selected_by_guild
            sh["positivity_opted_in_by_guild"] = self.opted_in_by_guild
            sh["positivity_manually_disabled_by_guild"] = self.manually_disabled_by_guild

    def _auto_enable_all(self):
        """Enable all opted-in guilds that haven't manually disabled this week."""
        for guild_id, opted in self.opted_in_by_guild.items():
            if opted and not self.manually_disabled_by_guild.get(guild_id, False):
                self.enabled_by_guild[guild_id] = True
                self.count_by_guild[guild_id] = 0
        self._save_state()

    def _auto_disable_all(self):
        """Disable all guilds and reset the manual-disable flag for next week."""
        for guild_id in list(self.enabled_by_guild.keys()):
            self.enabled_by_guild[guild_id] = False
        self.manually_disabled_by_guild.clear()
        self._save_state()

    @tasks.loop(time=time(0, 0, tzinfo=ET))
    async def tuesday_task(self):
        now = datetime.now(ET)
        if now.weekday() == 1:   # Tuesday just started
            self._auto_enable_all()
        else:
            self._auto_disable_all()

    @tuesday_task.before_loop
    async def before_tuesday_task(self):
        await self.bot.wait_until_ready()
        # Sync state on startup so stale enabled flags do not leak into non-Tuesdays.
        if datetime.now(ET).weekday() == 1:
            self._auto_enable_all()
        else:
            self._auto_disable_all()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.guild is None:
            return

        guild_id = message.guild.id
        if not self.enabled_by_guild.get(guild_id, False):
            return

        # Hard safety check: Positivity Tuesday should never run outside Tuesday ET.
        if datetime.now(ET).weekday() != 1:
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
                f"Happy Positivity Tuesday, <@{author_id}>! 🌸✨ You have been selected to make a positive comment about yourself, a fellow member, or anything else. 💖",
                allowed_mentions=discord.AllowedMentions(users=False)
            )
            return

        # Persist occasionally to keep message count across restarts.
        if current_count % 10 == 0:
            self._save_state()

    @commands.group(name="positivity", invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def positivity_group(self, ctx: Context):
        """Show the current Positivity Tuesday status and interval for this server. (Requires Manage Server)"""
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
        """Enable Positivity Tuesday. Optionally set how often it triggers: =positivity enable [every_x_messages] (Requires Manage Server)"""
        if ctx.guild is None:
            _ = await ctx.send("This command can only be used in a server.")
            return

        guild_id = ctx.guild.id

        if datetime.now(ET).weekday() != 1:  # 1 = Tuesday
            day_name = datetime.now(ET).strftime("%A")
            _ = await ctx.send(f"You silly goose, it is {day_name}!")
            return

        interval = every_x_messages or self.interval_by_guild.get(guild_id, self.default_interval)
        if interval < 1:
            _ = await ctx.send("Interval must be at least 1 message.")
            return

        self.enabled_by_guild[guild_id] = True
        self.interval_by_guild[guild_id] = interval
        self.count_by_guild[guild_id] = 0
        self.opted_in_by_guild[guild_id] = True
        self.manually_disabled_by_guild[guild_id] = False
        self._save_state()

        _ = await ctx.send(
            f"Enabled Positivity Tuesday. I will send the message around every {interval} messages."
        )

    @positivity_group.command(name="disable")
    @commands.has_permissions(manage_guild=True)
    async def positivity_disable(self, ctx: Context):
        """Disable Positivity Tuesday for this server. (Requires Manage Server)"""
        if ctx.guild is None:
            _ = await ctx.send("This command can only be used in a server.")
            return

        guild_id = ctx.guild.id
        self.enabled_by_guild[guild_id] = False
        self.count_by_guild[guild_id] = 0
        # Flag so auto-enable skips this guild until next Tuesday
        if datetime.now(ET).weekday() == 1:
            self.manually_disabled_by_guild[guild_id] = True
        self._save_state()

        _ = await ctx.send("Disabled Positivity Tuesday for this server.")

    @positivity_group.command(name="interval")
    @commands.has_permissions(manage_guild=True)
    async def positivity_interval(self, ctx: Context, every_x_messages: int):
        """Change how often Positivity Tuesday triggers: =positivity interval <every_x_messages> (Requires Manage Server)"""
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
        """Show the recent Positivity Tuesday cooldown list (members who were recently selected). (Requires Manage Server)"""
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
                entries.append(member.display_name)
            else:
                entries.append("Unknown User")
        _ = await ctx.send(
            "Positivity cooldown list (most recent first): "
            + ", ".join(entries)
        )
