from __future__ import annotations
from typing import Any, Callable, override
import os
import threading
from flask import Flask
from werkzeug.serving import make_server
import discord
from discord import app_commands
from discord.ext import commands
import logging
import asyncio
import shelve
from datetime import datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO)

type Context = commands.Context[TerrierBot]

class TerrierBot(commands.Bot):

    def __init__(self, command_prefix : Callable[[TerrierBot, discord.Message], list[str]], **options : Any) -> None: # pyright: ignore[reportAny, reportExplicitAny]
        super().__init__(command_prefix, **options) # pyright: ignore[reportAny]

        self.prefixes : dict[int, str] = {}
        self._first_ready : bool = True
        with shelve.open("terrierbot.shelve") as sh:
            if "prefixes" in sh:
                self.prefixes = sh["prefixes"]

    async def on_ready(self):
        # We know this to be true and this satisfies the type checker
        assert self.user is not None

        logging.info('Logged in as')
        logging.info(self.user.name)
        logging.info(self.user.id)
        logging.info('------')

        if self._first_ready:
            self._first_ready = False
            now = datetime.now(timezone.utc)
            with shelve.open("terrierbot.shelve") as sh:
                last_startup = sh.get("last_startup_msg")
                if last_startup is None or (now - last_startup) > timedelta(hours=1):
                    sh["last_startup_msg"] = now
                    channel = self.get_channel(1396542256445391069)
                    if isinstance(channel, discord.TextChannel):
                        await channel.send("Hello, I have restarted and am ready to help! 🐾")



    #============================================
    #Error Handling
    #============================================

    @override
    async def on_command_error(self, ctx : Context, error : commands.CommandError):
        http_error = None
        if isinstance(error, discord.HTTPException):
            http_error = error
        elif isinstance(error, commands.CommandInvokeError) and isinstance(error.original, discord.HTTPException):
            http_error = error.original

        if http_error is not None and http_error.status == 429:
            logging.warning("Discord rate limit hit (429) in command error handler; skipping ctx.send")
            return

        if isinstance(error, commands.CommandNotFound):
            logging.debug(f"command not found {ctx.message.content} (by {ctx.author})")
            return
        if isinstance(error, commands.MaxConcurrencyReached):
            _ = await ctx.send("Too many people running this command at a time")
            return
        if isinstance(error, commands.CommandInvokeError):
            _ = await ctx.send(f"{type(error.original).__name__}: {error.original}")
            return
        if isinstance(error, commands.NotOwner):
            _ = await ctx.send("That command is not for you")
            if isinstance(ctx.channel, discord.DMChannel):
                logging.info(f"{ctx.author.display_name} is trying to run the owner-only command \"{ctx.message.content}\" in a DM")
            else:
                if ctx.guild is not None and isinstance(ctx.channel, SENDABLE_CHANNEL):
                    location = f"in \"{ctx.guild.name}: #{ctx.channel.name}\""
                else:
                    location = ""
                logging.info(f"{ctx.author.display_name} is trying to run the owner-only command \"{ctx.message.content}\" {location}")
            return
        if isinstance(error, commands.MemberNotFound) or isinstance(error, commands.UserNotFound):
            _ = await ctx.send("User not found")
            return
        if isinstance(error, commands.CommandOnCooldown):
            _ = await ctx.send(f"You are on cooldown. Try again in {error.retry_after}s")
            return
        if isinstance(error, commands.MissingRequiredArgument):
            _ = await ctx.send(f"Missing argument {error.param}")
            return
        
        if isinstance(ctx.channel, discord.DMChannel):
            logging.error(f"{type(error).__name__}: {error} on command \"{ctx.message.content}\" from \"{ctx.author.display_name}\" in a DM")
        else:
            if ctx.guild is not None and isinstance(ctx.channel, SENDABLE_CHANNEL):
                location = f"in \"{ctx.guild.name}: #{ctx.channel.name}\""
            else:
                location = ""
            logging.error(f"{type(error).__name__}: {error} on command \"{ctx.message.content}\" from \"{ctx.author.display_name}\" {location}")
        _ = await ctx.send(f"Error - {type(error).__name__}: {error}")


#============================================
#Bot Initialization
#============================================

description = '''Terrier Bot'''

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

def prefix_for(bot : TerrierBot, guild : discord.Guild | None):
    if guild:
        return bot.prefixes.get(guild.id, "=")
    else:
        return "="

def command_prefix(bot : TerrierBot, msg : discord.Message):
    return commands.when_mentioned_or(prefix_for(bot, msg.guild))(bot, msg)
bot = TerrierBot(command_prefix=command_prefix, description=description, intents=intents)

bot.help_command = None


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
) -> None:
    msg = (
        f"{type(error.original).__name__}: {error.original}"
        if isinstance(error, app_commands.CommandInvokeError)
        else str(error)
    )
    logging.error("App command error: %s", error)
    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception:
        pass


#============================================
#Utility
#============================================

@bot.command(name="help")
async def help_command(ctx: Context):
    """Show categorized TerrierBot commands."""
    embed = discord.Embed(
        title="TerrierBot Commands",
        description="Commands work with `=` prefix or `/` slash commands.",
        color=discord.Color.red(),
    )

    embed.add_field(
        name="Academic",
        value=(
            "`=rmp` or `/rmp` `<firstname lastname|lastname>` - RateMyProfessors lookup for BU\n"
            "`=class` or `/class` `<CASCH101|CAS CH 101|CH 101>` - BU Bulletin course info"
        ),
        inline=False,
    )

    embed.add_field(
        name="Information",
        value=(
            "`=banner` or `/banner` - Banner submission info\n"
            "`=boost` or `/boost` - Server booster perks"
        ),
        inline=False,
    )

    embed.add_field(
        name="Fun",
        value=(
            "`=hello` or `/hello` - Say hi\n"
            "`=love` or `/love` - Terrier love\n"
            "`=starleaderboard` or `/starleaderboard` - Star leaderboard"
        ),
        inline=False,
    )

    embed.add_field(
        name="Other",
        value=(
            "`=end` or `/end` - Semester countdown message\n"
            "`=test` or `/test` - Test bot response"
        ),
        inline=False,
    )

    embed.add_field(
        name="Mod / Restricted",
        value=(
            "Manage Server required:\n"
            "`=positivity`, `/positivity status/enable/disable/interval/cooldown`\n\n"
            "Owner only (prefix only, no slash):\n"
            "`=disconnect`, `=delete`, `=cog load`, `=cog unload`, `=cog reload`, `=cog list`, `=exportmembers`, `=exportprunecandidates`, `=sync`\n\n"
            "Manage Server required (slash only):\n"
            "`/starboard setchannel/threshold/enable/disable/status`"
        ),
        inline=False,
    )

    await ctx.send(embed=embed)

@bot.command()
@commands.is_owner()
async def sync(ctx: Context):
    """Sync slash commands to this server. (Owner only)"""
    assert ctx.guild is not None
    bot.tree.copy_global_to(guild=ctx.guild)
    synced = await bot.tree.sync(guild=ctx.guild)
    await ctx.send(f"Synced {len(synced)} slash command(s) to this server.")

@bot.command()
@commands.is_owner()
async def disconnect(ctx : Context):
    """Shut down TerrierBot. (Owner only)"""
    _ = await ctx.send("Bye!")
    await bot.close()

@bot.command()
@commands.is_owner()
async def delete(ctx : Context):
    """Delete the bot's most recent message in this channel. (Owner only)"""
    msg = await discord.utils.get(ctx.channel.history(), author=bot.user)
    if msg is None:
        error_msg = await ctx.send("I've never spoken here!")
        await error_msg.delete(delay=3)
        return
    await msg.delete()
    if ctx.guild is not None and ctx.channel.permissions_for(ctx.guild.me).manage_messages:
        await ctx.message.delete()

SENDABLE_CHANNEL = (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.Thread, discord.GroupChannel, discord.DMChannel)

#============================================
#Cog Management
#============================================

@bot.group()
@commands.is_owner()
async def cog(ctx : Context):
    """Manage cogs: load, unload, reload, and list. (Owner only)"""
    if ctx.invoked_subcommand is None:
        _ = await ctx.send("Invalid cog command")

@cog.command(name="load")
async def loadCog(ctx : Context, cogName : str):
    """Load a cog by name, like: =cog load members."""
    await bot.load_extension(cogName if cogName.endswith("Cog") else cogName + "Cog")
    logging.info("Loaded Cog \"{}\"".format(cogName))
    _ = await ctx.send("Loaded Cog \"{}\"".format(cogName))

@cog.command(name="unload")
async def unloadCog(ctx : Context, cogName : str):
    """Unload a cog by name, like: =cog unload members."""
    await bot.unload_extension(cogName if cogName.endswith("Cog") else cogName + "Cog")
    logging.info("Unloaded Cog \"{}\"".format(cogName))
    _ = await ctx.send("Unloaded Cog \"{}\"".format(cogName))

@cog.command(name="reload")
async def reloadCog(ctx : Context, cogName : str):
    """Reload a cog by name, like: =cog reload members."""
    await bot.reload_extension(cogName if cogName.endswith("Cog") else cogName + "Cog")
    logging.info("Reloaded Cog \"{}\"".format(cogName))
    _ = await ctx.send("Reloaded Cog \"{}\"".format(cogName))

@cog.command(name="list")
async def listCogs(ctx : Context):
    """Show loaded and unloaded cogs."""
    loadedCogs = list(map(lambda x: x.split("Cog")[0], bot.extensions.keys()))
    _ = await ctx.send(
        "**Loaded Cogs:**\n{}\n**Unloaded Cogs:**\n{}".format(
            "\n".join(loadedCogs), "\n".join([x for x in cogList if x not in loadedCogs])
        )
    )
    
#============================================
#Make bot go
#============================================
cogList = ["test", "hello", "love", "boost", "positivity", "members", "end", "banner", "reaction", "rmp", "class", "embed", "starboard", "towoken", "club", "mbta"]
defaultCogs = ["test", "hello", "love", "boost", "positivity", "members", "banner", "reaction", "rmp", "class", "embed", "starboard", "towoken", "club", "mbta"]


def _get_token() -> str:
    token = os.environ.get("DISCORD_TOKEN")
    if token:
        return token
    with open("token.txt") as f:
        return f.read().strip()


async def main():
    async with bot:
        for cog in defaultCogs:
            await bot.load_extension(cog + "Cog")
        await bot.start(_get_token())

def run_web_server(stop_event: threading.Event) -> None:
    app = Flask(__name__)

    @app.route("/")
    def index():
        return "OK", 200

    port = int(os.environ.get("PORT", 8080))
    server = make_server("0.0.0.0", port, app)
    server.timeout = 1
    while not stop_event.is_set():
        server.handle_request()
    server.server_close()


async def run_services() -> None:
    stop_event = threading.Event()
    web_task = asyncio.create_task(asyncio.to_thread(run_web_server, stop_event))
    try:
        await main()
    finally:
        stop_event.set()
        await web_task


if __name__ == "__main__":
    asyncio.run(run_services())
