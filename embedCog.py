import json as _json

import discord
from discord import app_commands
from discord.ext import commands

from bot import Context, TerrierBot


async def setup(bot: TerrierBot):
    await bot.add_cog(EmbedCog(bot))


class EmbedModal(discord.ui.Modal, title="Send Embed"):
    embed_title = discord.ui.TextInput(
        label="Title",
        placeholder="Embed title (optional)",
        required=False,
        max_length=256,
    )
    description = discord.ui.TextInput(
        label="Body (supports # headings, **bold**)",
        placeholder="# Big heading\n## Smaller heading\n\nRegular text, **bold**, *italic*, > quote...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=4000,
    )
    description2 = discord.ui.TextInput(
        label="Body (cont.)",
        placeholder="Continued text here...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1024,
    )
    color = discord.ui.TextInput(
        label="Color (hex, e.g. #cc0000)",
        placeholder="#cc0000",
        required=False,
        max_length=10,
    )
    footer = discord.ui.TextInput(
        label="Footer",
        placeholder="Footer text (optional)",
        required=False,
        max_length=2048,
    )

    def __init__(self, target: discord.abc.Messageable):
        super().__init__()
        self.target = target

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed()
        if self.embed_title.value:
            embed.title = self.embed_title.value
        if self.description.value:
            embed.description = self.description.value
        if self.color.value:
            try:
                embed.color = discord.Color(int(self.color.value.lstrip("#").lstrip("0x"), 16))
            except ValueError:
                await interaction.response.send_message("Invalid color — use hex like `#cc0000`.", ephemeral=True)
                return
        if self.description2.value:
            embed.add_field(name="\u200b", value=self.description2.value, inline=False)
        if self.footer.value:
            embed.set_footer(text=self.footer.value)
        await self.target.send(embed=embed)
        await interaction.response.send_message("Embed sent! ✅", ephemeral=True)


class EmbedCog(commands.Cog, name="Embed", description="Send rich embeds. Owner only."):
    def __init__(self, bot: TerrierBot):
        self.bot = bot
        print("Embed Cog Ready")

    @app_commands.command(name="embed", description="Send a rich embed. (Owner only)")
    @app_commands.describe(channel="Channel to send the embed to (defaults to current channel)")
    async def embed_slash(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("That command is not for you.", ephemeral=True)
            return
        target: discord.abc.Messageable = channel or interaction.channel  # type: ignore[assignment]
        await interaction.response.send_modal(EmbedModal(target))

    @commands.command(name="embed")
    @commands.is_owner()
    async def send_embed(self, ctx: Context, channel: discord.TextChannel | None = None, *, json_text: str = ""):
        """Send one or more rich embeds via JSON inline or attached file. (Owner only)

        Formats:
          Single:   {"title": "...", "description": "..."}
          Array:    [{"title": "Part 1"}, {"title": "Part 2"}]
          Gradient: {"gradient": ["#ff0000", "#0000ff"], "embeds": [{...}, {...}]}

        Per-embed fields: title, description, color (hex or int), footer,
        thumbnail (url), image (url), fields (list of {name, value, inline}).
        """
        if ctx.message.attachments:
            raw = await ctx.message.attachments[0].read()
            json_text = raw.decode("utf-8")

        if not json_text.strip():
            _ = await ctx.send("Provide JSON inline or attach a .json/.txt file.")
            return

        try:
            data = _json.loads(json_text)
        except _json.JSONDecodeError as e:
            _ = await ctx.send(f"Invalid JSON: {e}")
            return

        gradient_stops: list[tuple[int, int, int]] | None = None

        if isinstance(data, dict) and "embeds" in data:
            # Wrapper object — may have gradient
            raw_stops = data.get("gradient")
            if raw_stops and isinstance(raw_stops, list) and len(raw_stops) >= 2:
                def hex_to_rgb(h: str) -> tuple[int, int, int]:
                    v = int(str(h).lstrip("#").lstrip("0x"), 16)
                    return (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF
                gradient_stops = [hex_to_rgb(s) for s in raw_stops]
            items = data["embeds"]
            if not isinstance(items, list):
                items = [items]
        elif isinstance(data, dict):
            items = [data]
        elif isinstance(data, list):
            items = data
        else:
            _ = await ctx.send("JSON must be an object `{...}` or array `[...]`.")
            return

        def lerp_color(stops: list[tuple[int, int, int]], t: float) -> discord.Color:
            """Interpolate across multiple color stops. t in [0, 1]."""
            if len(stops) == 1:
                return discord.Color(stops[0][0] << 16 | stops[0][1] << 8 | stops[0][2])
            segment = t * (len(stops) - 1)
            lo = int(segment)
            hi = min(lo + 1, len(stops) - 1)
            local_t = segment - lo
            r = round(stops[lo][0] + (stops[hi][0] - stops[lo][0]) * local_t)
            g = round(stops[lo][1] + (stops[hi][1] - stops[lo][1]) * local_t)
            b = round(stops[lo][2] + (stops[hi][2] - stops[lo][2]) * local_t)
            return discord.Color(r << 16 | g << 8 | b)

        def build_embed(d: dict, color_override: discord.Color | None = None) -> discord.Embed:
            embed = discord.Embed()
            if title := d.get("title"):
                embed.title = str(title)
            if description := d.get("description"):
                embed.description = str(description)
            if color_override is not None:
                embed.color = color_override
            elif (color := d.get("color")) is not None:
                if isinstance(color, str):
                    color = int(color.lstrip("#").lstrip("0x"), 16)
                embed.color = discord.Color(int(color))
            if footer := d.get("footer"):
                embed.set_footer(text=str(footer))
            if thumbnail := d.get("thumbnail"):
                embed.set_thumbnail(url=str(thumbnail))
            if image := d.get("image"):
                embed.set_image(url=str(image))
            for field in d.get("fields", []):
                embed.add_field(
                    name=str(field.get("name", "") or "\u200b"),
                    value=str(field.get("value", "") or "\u200b"),
                    inline=bool(field.get("inline", False)),
                )
            return embed

        valid_items = [item for item in items if isinstance(item, dict)]
        n = len(valid_items)
        embeds: list[discord.Embed] = []
        for i, item in enumerate(valid_items):
            override = None
            if gradient_stops:
                t = i / (n - 1) if n > 1 else 0.0
                override = lerp_color(gradient_stops, t)
            embeds.append(build_embed(item, override))

        if not embeds:
            _ = await ctx.send("No valid embed objects found.")
            return

        target: discord.abc.Messageable = channel or ctx.channel
        for i in range(0, len(embeds), 10):
            await target.send(embeds=embeds[i:i+10])
        if channel is not None:
            await ctx.message.add_reaction("✅")
