import re
import discord
from discord.ext import commands
from bot import TerrierBot, Context

MEAN_EMOJI_ID = 1499771566475706553
NICE_EMOJI_ID = 1499771565670137886

# Words that negate the keyword that follows them (checked up to 2 words back)
NEGATIONS = {
    "not", "no", "never", "don't", "dont", "doesn't", "doesnt",
    "isn't", "isnt", "wasn't", "wasnt", "aren't", "arent",
    "can't", "cant", "won't", "wont", "wouldn't", "wouldnt",
    "hardly", "barely", "scarcely",
}

# Multi-word phrases — always trigger, no negation check needed
MEAN_PHRASES = [
    "shut up", "go away", "bad bot", "worst bot", "kill yourself", "kys",
    "stfu", "sybau", "no one asked", "nobody asked", "stop talking",
    "be quiet", "shut it", "pipe down", "zip it", "leave me alone",
    "get out", "get lost", "scram", "buzz off", "back off", "cut it out",
    "i hate you", "hate you", "hate this bot", "i hate this bot",
    "you suck", "suck it", "sucks it", "you're the worst", "youre the worst", "you are the worst",
    "worst bot ever", "worst thing ever", "end yourself", "delete yourself",
    "log off", "uninstall", "l bot", "l ratio", "bot moment", "skill issue",
    "cope", "touch grass", "what are you doing", "you make no sense",
    "that makes no sense", "go die", "get out of here",
]

NICE_PHRASES = [
    "good bot", "great bot", "nice bot", "good job", "great job", "nice job",
    "well done", "nice work", "great work", "amazing work", "excellent work",
    "good morning", "good night", "good evening", "good afternoon",
    "thank you", "thank u", "i love you", "i love u", "ily", "ily so much",
    "i adore you", "i adore this bot", "i love this bot", "love this bot",
    "best bot ever", "you're a lifesaver", "youre a lifesaver", "you saved me",
    "you're my favorite", "youre my favorite", "i like you", "like this bot",
    "i appreciate you", "appreciate you", "appreciate it", "i appreciate it",
    "proud of you", "i'm proud of you", "you're the goat", "youre the goat",
    "sending love", "much love", "lots of love", "keep it up", "you did great",
    "you did amazing", "you did awesome", "you did well",
]

# Single keywords — checked with negation detection (e.g. "not cute" won't trigger)
MEAN_KEYWORDS = {
    "stupid", "dumb", "idiot", "moron", "imbecile", "braindead", "foolish", "mindless", "senseless",
    "incompetent", "inept", "inadequate", "inferior", "subpar", "mediocre",
    "hate", "hatred", "despise", "loathe", "detest",
    "trash", "garbage", "terrible", "awful", "horrible", "pathetic", "vile", "wretched", "despicable",
    "detestable", "disgusting", "repulsive", "deplorable", "appalling",
    "useless", "unhelpful", "worthless", "hopeless", "annoying", "dreadful", "atrocious", "disgraceful",
    "embarrassing", "disappointing", "frustrating", "infuriating", "obnoxious",
    "cringe", "lame", "mid", "boring", "pointless", "irrelevant", "meh", "bleh", "absurd",
    "ridiculous", "laughable", "pitiful", "feeble", "weak", "flawed",
    "broken", "busted", "glitchy", "rotten", "lousy", "clanker", "defective", "dysfunctional",
    "corrupt", "buggy", "error", "outdated", "obsolete", "primitive", "unreliable", "inaccurate",
    "misleading", "confusing", "unimpressive", "ugly", "cursed", "chaotic", "messy", "sloppy",
    "junk", "scrap", "waste", "dull", "lazy", "failure", "wrong", "clown", "joke",
    "die", "kill", "suck", "sucks", "ratio", "bad", "worst",
}

NICE_KEYWORDS = {
    "cute", "adorable", "sweet", "precious", "wholesome", "lovely",
    "delightful", "charming", "endearing", "beautiful", "warm", "pleasant",
    "awesome", "amazing", "wonderful", "fantastic", "excellent",
    "brilliant", "incredible", "outstanding", "superb", "perfect",
    "flawless", "legendary", "helpful", "smart", "kind", "clever", "genius", "gifted", "talented",
    "skilled", "capable", "efficient", "effective", "reliable", "dependable", "trustworthy",
    "accurate", "supportive", "friendly", "useful", "impressive",
    "creative", "innovative", "thoughtful", "caring", "positive", "uplifting",
    "encouraging", "motivating", "inspiring", "exceptional", "remarkable", "extraordinary",
    "enjoyable", "entertaining", "fun", "cool", "epic", "fire", "lit", "slay", "iconic",
    "elite", "stellar", "phenomenal", "spectacular", "magnificent", "glorious", "marvelous",
    "blessed", "joyful", "cheerful", "mvp", "icon", "king", "queen", "goat", "top", "peak",
    "thanks", "thx", "ty", "tyvm", "tysm", "thankful", "grateful",
    "love", "appreciate", "appreciated", "valid", "based", "goated",
    "nice", "great", "good", "best",
}

async def setup(bot : TerrierBot):
    await bot.add_cog(ReactionCog(bot))

class ReactionCog(commands.Cog, name="Reaction", description="Reacts to kindness and meanness directed at TerrierBot."):
    def __init__(self, bot : TerrierBot):
        self.bot : TerrierBot = bot
        print("Reaction Cog Ready")

    def _is_negated(self, words: list[str], idx: int) -> bool:
        """Return True if the word at idx is preceded by a negation within 2 words."""
        for offset in (1, 2):
            if idx >= offset and words[idx - offset] in NEGATIONS:
                return True
        return False

    def _get_sentiment(self, content: str) -> str | None:
        """Return 'mean', 'nice', or None based on phrase and keyword matching."""
        lower = content.lower()

        # Multi-word phrases first — always trigger
        if any(phrase in lower for phrase in MEAN_PHRASES):
            return "mean"
        if any(phrase in lower for phrase in NICE_PHRASES):
            return "nice"

        # Single keyword check with negation detection
        words = [re.sub(r"[.,!?;:'\"()]", "", w) for w in lower.split()]
        for i, word in enumerate(words):
            if word in MEAN_KEYWORDS and not self._is_negated(words, i):
                return "mean"
        for i, word in enumerate(words):
            if word in NICE_KEYWORDS and not self._is_negated(words, i):
                return "nice"

        return None

    @commands.Cog.listener()
    async def on_message(self, message : discord.Message):
        if message.author == self.bot.user:
            return

        # Check if this message is directed at TerrierBot
        is_pinged = self.bot.user is not None and self.bot.user in message.mentions
        is_reply_to_bot = (
            message.reference is not None
            and isinstance(message.reference.resolved, discord.Message)
            and message.reference.resolved.author == self.bot.user
        )
        mentions_bot = "terrier bot" in message.content.lower()

        if not is_pinged and not is_reply_to_bot and not mentions_bot:
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
