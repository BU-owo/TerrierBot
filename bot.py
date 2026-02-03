from __future__ import annotations
from typing import Any, Callable, override
import discord
from discord.ext import commands
import logging
import asyncio
import shelve

logging.basicConfig(level=logging.INFO)

type Context = commands.Context[TerrierBot]

class TerrierBot(commands.Bot):

    def __init__(self, command_prefix : Callable[[TerrierBot, discord.Message], list[str]], **options : Any) -> None: # pyright: ignore[reportAny, reportExplicitAny]
        super().__init__(command_prefix, **options) # pyright: ignore[reportAny]

        self.prefixes : dict[int, str] = {}
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

    #============================================
    #Error Handling
    #============================================

    @override
    async def on_command_error(self, ctx : Context, error : commands.CommandError):
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

bot.help_command = commands.DefaultHelpCommand()

#============================================
#Utility
#============================================

@bot.command()
@commands.is_owner()
async def disconnect(ctx : Context):
    _ = await ctx.send("Bye!")
    await bot.close()

@bot.command()
@commands.is_owner()
async def delete(ctx : Context):
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
    if ctx.invoked_subcommand is None:
        _ = await ctx.send("Invalid cog command")

@cog.command(name="load")
async def loadCog(ctx : Context, cogName : str):
    await bot.load_extension(cogName if cogName.endswith("Cog") else cogName + "Cog")
    logging.info("Loaded Cog \"{}\"".format(cogName))
    _ = await ctx.send("Loaded Cog \"{}\"".format(cogName))

@cog.command(name="unload")
async def unloadCog(ctx : Context, cogName : str):
    await bot.unload_extension(cogName if cogName.endswith("Cog") else cogName + "Cog")
    logging.info("Unloaded Cog \"{}\"".format(cogName))
    _ = await ctx.send("Unloaded Cog \"{}\"".format(cogName))

@cog.command(name="reload")
async def reloadCog(ctx : Context, cogName : str):
    await bot.reload_extension(cogName if cogName.endswith("Cog") else cogName + "Cog")
    logging.info("Reloaded Cog \"{}\"".format(cogName))
    _ = await ctx.send("Reloaded Cog \"{}\"".format(cogName))

@cog.command(name="list")
async def listCogs(ctx : Context):
    loadedCogs = list(map(lambda x: x.split("Cog")[0], bot.extensions.keys()))
    _ = await ctx.send(
        "**Loaded Cogs:**\n{}\n**Unloaded Cogs:**\n{}".format(
            "\n".join(loadedCogs), "\n".join([x for x in cogList if x not in loadedCogs])
        )
    )
    
#============================================
#Make bot go
#============================================

cogList = ["test"]
defaultCogs = ["test"]

async def main():
    async with bot:
        for cog in defaultCogs:
            await bot.load_extension(cog + "Cog")
        # '''
        with open("token.txt") as f:
            token = f.read()
        '''
        token = os.environ["DISCORD_TOKEN"]
        '''
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
