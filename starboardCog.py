import shelve

import discord
from discord import app_commands
from discord.ext import commands

from bot import Context, TerrierBot

STAR_EMOJI = "⭐"
DEFAULT_THRESHOLD = 3
LEADERBOARD_SIZE = 10


async def setup(bot: TerrierBot):
    await bot.add_cog(StarboardCog(bot))


class StarboardCog(commands.Cog, name="Starboard", description="Starboard and star leaderboard. Requires Manage Server to configure."):

    starboard_slash = app_commands.Group(
        name="starboard",
        description="Starboard configuration. Requires Manage Server.",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot

        # guild_id -> starboard channel_id
        self.channel_by_guild: dict[int, int] = {}
        # guild_id -> star threshold
        self.threshold_by_guild: dict[int, int] = {}
        # guild_id -> enabled
        self.enabled_by_guild: dict[int, bool] = {}
        # guild_id -> orig_message_id -> starboard_message_id
        self.posted_messages: dict[int, dict[int, int]] = {}
        # guild_id -> message_id -> author_id (persisted so leaderboard survives restarts)
        self.message_authors: dict[int, dict[int, int]] = {}
        # guild_id -> message_id -> current ⭐ count (excluding self-stars)
        self.message_star_counts: dict[int, dict[int, int]] = {}
        # guild_id -> user_id -> total stars received across all their messages
        self.user_star_totals: dict[int, dict[int, int]] = {}

        with shelve.open("terrierbot.shelve") as sh:
            self.channel_by_guild = sh.get("starboard_channel_by_guild", {})
            self.threshold_by_guild = sh.get("starboard_threshold_by_guild", {})
            self.enabled_by_guild = sh.get("starboard_enabled_by_guild", {})
            self.posted_messages = sh.get("starboard_posted_messages", {})
            self.message_authors = sh.get("starboard_message_authors", {})
            self.message_star_counts = sh.get("starboard_message_star_counts", {})
            self.user_star_totals = sh.get("starboard_user_star_totals", {})

        print("Starboard Cog Ready")

    def _save_state(self) -> None:
        with shelve.open("terrierbot.shelve") as sh:
            sh["starboard_channel_by_guild"] = self.channel_by_guild
            sh["starboard_threshold_by_guild"] = self.threshold_by_guild
            sh["starboard_enabled_by_guild"] = self.enabled_by_guild
            sh["starboard_posted_messages"] = self.posted_messages
            sh["starboard_message_authors"] = self.message_authors
            sh["starboard_message_star_counts"] = self.message_star_counts
            sh["starboard_user_star_totals"] = self.user_star_totals

    def _star_label(self, count: int) -> str:
        if count >= 15:
            return "💫"
        if count >= 8:
            return "🌟"
        return "⭐"

    def _build_star_embed(self, message: discord.Message, star_count: int) -> tuple[str, discord.Embed]:
        label = self._star_label(star_count)
        content = f"{label} **{star_count}** | {message.channel.mention}"

        embed = discord.Embed(
            description=message.content or None,
            color=discord.Color.gold(),
            timestamp=message.created_at,
        )
        embed.set_author(
            name=message.author.display_name,
            icon_url=message.author.display_avatar.url,
        )

        image_set = False
        for att in message.attachments:
            if att.content_type and att.content_type.startswith("image/"):
                embed.set_image(url=att.url)
                image_set = True
                break
        if not image_set:
            for e in message.embeds:
                if e.image and e.image.url:
                    embed.set_image(url=e.image.url)
                    break

        embed.add_field(name="", value=f"[Jump to message]({message.jump_url})", inline=False)
        embed.set_footer(text=f"Message ID: {message.id}")
        return content, embed

    async def _handle_reaction_change(self, guild_id: int, channel_id: int, message_id: int) -> None:
        """Recalculate star count for a message and update the starboard accordingly."""
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return

        starboard_channel_id = self.channel_by_guild.get(guild_id)

        # Don't star messages posted inside the starboard channel itself
        if starboard_channel_id is not None and channel_id == starboard_channel_id:
            return

        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        try:
            message = await channel.fetch_message(message_id)
        except (discord.NotFound, discord.Forbidden):
            return

        # Don't star bot messages
        if message.author.bot:
            return

        # Count ⭐ reactions, excluding a self-star from the message author
        star_reaction = discord.utils.get(message.reactions, emoji=STAR_EMOJI)
        if star_reaction is None:
            star_count = 0
        else:
            star_count = star_reaction.count
            try:
                async for user in star_reaction.users():
                    if user.id == message.author.id:
                        star_count -= 1
                        break
            except discord.Forbidden:
                pass

        # --- Update leaderboard tracking ---
        guild_authors = self.message_authors.setdefault(guild_id, {})
        guild_counts = self.message_star_counts.setdefault(guild_id, {})
        guild_totals = self.user_star_totals.setdefault(guild_id, {})

        author_id = message.author.id
        guild_authors[message_id] = author_id

        old_count = guild_counts.get(message_id, 0)
        delta = star_count - old_count
        guild_counts[message_id] = star_count

        if delta != 0:
            guild_totals[author_id] = max(0, guild_totals.get(author_id, 0) + delta)

        # --- Update starboard channel ---
        if not self.enabled_by_guild.get(guild_id, False) or starboard_channel_id is None:
            self._save_state()
            return

        starboard_channel = guild.get_channel(starboard_channel_id)
        if not isinstance(starboard_channel, discord.TextChannel):
            self._save_state()
            return

        threshold = self.threshold_by_guild.get(guild_id, DEFAULT_THRESHOLD)
        guild_posts = self.posted_messages.setdefault(guild_id, {})
        existing_star_msg_id = guild_posts.get(message_id)
        content, embed = self._build_star_embed(message, star_count)

        if star_count >= threshold:
            if existing_star_msg_id is None:
                # Post new entry to starboard
                try:
                    star_msg = await starboard_channel.send(content, embed=embed)
                    guild_posts[message_id] = star_msg.id
                except discord.Forbidden:
                    pass
            else:
                # Edit existing entry to update star count
                try:
                    star_msg = await starboard_channel.fetch_message(existing_star_msg_id)
                    await star_msg.edit(content=content, embed=embed)
                except discord.NotFound:
                    # Starboard message was manually deleted — re-post
                    try:
                        star_msg = await starboard_channel.send(content, embed=embed)
                        guild_posts[message_id] = star_msg.id
                    except discord.Forbidden:
                        pass
                except discord.Forbidden:
                    pass

        self._save_state()

    # =========================================================
    # Reaction listeners
    # =========================================================

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if str(payload.emoji) != STAR_EMOJI:
            return
        if payload.guild_id is None:
            return
        await self._handle_reaction_change(payload.guild_id, payload.channel_id, payload.message_id)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        if str(payload.emoji) != STAR_EMOJI:
            return
        if payload.guild_id is None:
            return
        await self._handle_reaction_change(payload.guild_id, payload.channel_id, payload.message_id)

    # =========================================================
    # Slash — configuration (Manage Server required)
    # =========================================================

    @starboard_slash.command(name="setchannel", description="Set the channel where starred messages are posted.")
    @app_commands.describe(channel="The text channel to use as the starboard.")
    async def starboard_setchannel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        assert interaction.guild_id is not None
        self.channel_by_guild[interaction.guild_id] = channel.id
        self._save_state()
        await interaction.response.send_message(f"Starboard channel set to {channel.mention}.", ephemeral=True)

    @starboard_slash.command(name="threshold", description="Set how many ⭐ reactions a message needs to appear on the starboard.")
    @app_commands.describe(count="Minimum star count required (default: 3).")
    async def starboard_threshold(self, interaction: discord.Interaction, count: int) -> None:
        assert interaction.guild_id is not None
        if count < 1:
            await interaction.response.send_message("Threshold must be at least 1.", ephemeral=True)
            return
        self.threshold_by_guild[interaction.guild_id] = count
        self._save_state()
        await interaction.response.send_message(f"Starboard threshold set to {count} ⭐.", ephemeral=True)

    @starboard_slash.command(name="enable", description="Enable the starboard.")
    async def starboard_enable(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None
        if interaction.guild_id not in self.channel_by_guild:
            await interaction.response.send_message(
                "Set a starboard channel first with `/starboard setchannel`.", ephemeral=True
            )
            return
        self.enabled_by_guild[interaction.guild_id] = True
        self._save_state()
        await interaction.response.send_message("Starboard enabled.", ephemeral=True)

    @starboard_slash.command(name="disable", description="Disable the starboard.")
    async def starboard_disable(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None
        self.enabled_by_guild[interaction.guild_id] = False
        self._save_state()
        await interaction.response.send_message("Starboard disabled.", ephemeral=True)

    @starboard_slash.command(name="status", description="Show the current starboard configuration.")
    async def starboard_status(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None
        guild_id = interaction.guild_id
        enabled = self.enabled_by_guild.get(guild_id, False)
        threshold = self.threshold_by_guild.get(guild_id, DEFAULT_THRESHOLD)
        channel_id = self.channel_by_guild.get(guild_id)
        channel_str = f"<#{channel_id}>" if channel_id else "*not set*"

        embed = discord.Embed(title="Starboard Status", color=discord.Color.gold())
        embed.add_field(name="Enabled", value="Yes" if enabled else "No", inline=True)
        embed.add_field(name="Channel", value=channel_str, inline=True)
        embed.add_field(name="Threshold", value=f"{threshold} ⭐", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # =========================================================
    # Leaderboard (public)
    # =========================================================

    def _build_leaderboard_embed(self, guild: discord.Guild) -> discord.Embed:
        guild_totals = self.user_star_totals.get(guild.id, {})
        top = sorted(
            ((uid, s) for uid, s in guild_totals.items() if s > 0),
            key=lambda x: x[1],
            reverse=True,
        )[:LEADERBOARD_SIZE]

        embed = discord.Embed(title="⭐ Star Leaderboard", color=discord.Color.gold())
        if not top:
            embed.description = "No stars have been given yet!"
        else:
            medals = ["🥇", "🥈", "🥉"]
            lines: list[str] = []
            for i, (user_id, stars) in enumerate(top):
                prefix = medals[i] if i < 3 else f"**{i + 1}.**"
                member = guild.get_member(user_id)
                name = member.display_name if member else f"<@{user_id}>"
                star_word = "star" if stars == 1 else "stars"
                lines.append(f"{prefix} {name} — {stars} {star_word}")
            embed.description = "\n".join(lines)
        return embed

    @commands.command(name="starleaderboard")
    @commands.guild_only()
    async def starleaderboard_prefix(self, ctx: Context) -> None:
        """Show the star leaderboard."""
        assert ctx.guild is not None
        embed = self._build_leaderboard_embed(ctx.guild)
        await ctx.send(embed=embed)

    @app_commands.command(name="starleaderboard", description="Show who has received the most ⭐ stars.")
    async def starleaderboard_slash(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return
        embed = self._build_leaderboard_embed(interaction.guild)
        await interaction.response.send_message(embed=embed)
