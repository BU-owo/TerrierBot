import discord
from discord.ext import commands
from bot import TerrierBot, Context

MEAN_EMOJI_ID = 1499771566475706553
NICE_EMOJI_ID = 1499771565670137886

MEAN_PHRASES = [
    "bad bot", "shut up", "stupid", "dumb", "idiot", "hate you",
    "worst bot", "terrible bot", "awful bot", "useless bot", "annoying bot",
    "trash bot", "garbage bot", "you suck", "i hate you", "go away",
    "you're dumb", "youre dumb", "you are dumb",
    "you're stupid", "youre stupid", "you are stupid",
    "horrible bot", "pathetic bot", "be quiet", "shut it",
    "nobody asked", "no one asked", "stop talking",
]

NICE_PHRASES = [
    "good bot", "nice bot", "love you", "love u", "thank you", "thanks",
    "thank u", "thx", "you're the best", "youre the best", "you are the best",
    "you're great", "youre great", "you are great",
    "you're awesome", "youre awesome", "you are awesome",
    "cute bot", "best bot", "smart bot", "good job", "well done",
    "amazing bot", "wonderful bot", "i love you", "i love u", "ily",
    "appreciate you", "you're helpful", "youre helpful", "great bot",
    "you're cute", "youre cute", "you're sweet", "youre sweet","you're so cute"
]

async def setup(bot : TerrierBot):
    await bot.add_cog(ReactionCog(bot))

class ReactionCog(commands.Cog, name="Reaction", description="Reacts to kindness and meanness directed at TerrierBot."):
    def __init__(self, bot : TerrierBot):
        self.bot : TerrierBot = bot
        print("Reaction Cog Ready")

    def _get_sentiment(self, content: str) -> str | None:
        """Return 'mean', 'nice', or None based on phrase matching."""
        lower = content.lower()
        if any(phrase in lower for phrase in MEAN_PHRASES):
            return "mean"
        if any(phrase in lower for phrase in NICE_PHRASES):
            return "nice"
        return None

    @commands.Cog.listener()
    async def on_message(self, message : discord.Message):
        if message.author == self.bot.user:
            return

        # Check if this message is directed at TerrierBot
        is_reply_to_bot = (
            message.reference is not None
            and isinstance(message.reference.resolved, discord.Message)
            and message.reference.resolved.author == self.bot.user
        )
        mentions_bot = "terrier bot" in message.content.lower()

        if not is_reply_to_bot and not mentions_bot:
            return

        sentiment = self._get_sentiment(message.content)
        if sentiment is None:
            return

        emoji_id = MEAN_EMOJI_ID if sentiment == "mean" else NICE_EMOJI_ID
        emoji = self.bot.get_emoji(emoji_id) or discord.PartialEmoji(name="e", id=emoji_id)
        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            pass
