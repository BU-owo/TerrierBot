import re
import random
import discord
from discord import app_commands
from discord.ext import commands

TROLL_ROLE_ID = 1529519978976379061

EMOTICONS = [
    "fwendo", "Huoh", "._.", ";-;", ";_;", "（；ω；）", "ÙωÙ", "UwU",
    "（人◕ω◕）", "（●´ω｀●）", "（✿ ♡‿♡）", "（◠‿◠✿）", "^-^", "^_^",
    "＞_＜", "＞_＞", ":P", ":3", ";3", "x3", ":D", "xD", "XDDD",
    "（＾ｖ＾）", "ㅇㅅㅇ", "（• o •）", "ʕ•̫͡•ʔ", "ʕʘ‿ʘʔ", "（　'◟ '）",
    "(˶˃ ᵕ ˂˶)", "(｡♥‿♥｡)", "(´｡• ᵕ •｡`)", "ദ്ദി(˵ •̀ ᴗ - ˵ )",
    "(｡•́‿•̀｡)", "(๑ᵕ⌣ᵕ๑)", "(⁄ ⁄•⁄ω⁄•⁄ ⁄)", "(◕‿◕✿)", "(＾▽＾)",
    "٩(｡•́‿•̀｡)۶", "(っ˘ω˘ς )", "( ˶ˆ ᗜ ˆ˵ )", "(｡U⁄ ⁄ ⁄ ⁄U｡)",
    "(灬♥ω♥灬)", "◝(⁰▿⁰)◜",
]

WORD_REPLACEMENTS = [
    (r"\byou\b", "uu"),
    (r"\bhave\b", "haz"),
    (r"\bhas\b", "haz"),
    (r"\bno\b", "nu"),
    (r"\bthe\b", "da"),
    (r"\bsmall\b", "smol"),
    (r"\blittle\b", "smol"),
    (r"\bthanks\b", "fanks"),
    (r"\bthank\b", "fank"),
]

# These get protected from the global r/l -> w pass so the "r" survives.
CAT_REPLACEMENTS = [
    (r"\bmeow+\b", "mrrrow"),
    (r"\bpurr+\b", "purrr"),
    (r"\bcat\b", "kitty"),
]

# Anything matching this stays completely untouched: URLs, custom Discord
# emoji (<:name:id> / <a:name:id>), and unicode emoji.
PROTECTED_PATTERN = re.compile(
    r"https?://\S+"
    r"|<a?:\w+:\d+>"
    r"|[\U0001F1E6-\U0001F1FF\U0001F300-\U0001F5FF\U0001F600-\U0001F64F"
    r"\U0001F680-\U0001F6FF\U0001F700-\U0001F77F\U0001F780-\U0001F7FF"
    r"\U0001F800-\U0001F8FF\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F"
    r"\U0001FA70-\U0001FAFF\u2600-\u26FF\u2700-\u27BF\uFE0F\u200D]+"
)
PLACEHOLDER_RE = re.compile(r"\uE000(\d+)\uE001")
PLACEHOLDER_ONLY_WORD_RE = re.compile(r"^(?:\uE000\d+\uE001)+$")

MID_WORD_STUTTER_CHANCE = 0.10
TILDE_CHANCE = 0.7
NYAIFY = True


def _nyaify(text: str) -> str:
    return re.sub(r"n([aeiou])", r"ny\1", text)


def _escalate_exclamations(text: str) -> str:
    return re.sub(r"!", lambda m: random.choice(["!", "!!", "!!!"]), text)


def owo_ify(text: str) -> str:
    if not text:
        return f"w-w-w-... {random.choice(EMOTICONS)}"

    tokens = []

    def _stash(m: re.Match) -> str:
        tokens.append(m.group(0))
        return f"\uE000{len(tokens) - 1}\uE001"

    masked = PROTECTED_PATTERN.sub(_stash, text)

    result = masked.lower()

    for pattern, repl in WORD_REPLACEMENTS:
        result = re.sub(pattern, repl, result)

    result = result.replace("=", " da")

    for pattern, repl in CAT_REPLACEMENTS:
        def _cat_stash(m: re.Match, _repl=repl) -> str:
            tokens.append(_repl)
            return f"\uE000{len(tokens) - 1}\uE001"
        result = re.sub(pattern, _cat_stash, result)

    if NYAIFY:
        result = _nyaify(result)

    result = re.sub(r"[rl]", "w", result)
    result = _escalate_exclamations(result)

    # Mid-message stutter: stutter the first real (non-placeholder) char,
    # with a randomized stutter length (w-, w-w-, or w-w-w-).
    if result and result[0] not in ("\uE000",):
        first_char = result[0]
        stutter_len = random.randint(1, 3)
        result = f"{(first_char + '-') * stutter_len}{result}"

    # Occasional per-word stutter + tilde sprinkle, skipping placeholder words.
    words = result.split(" ")
    for i, word in enumerate(words):
        if not word or PLACEHOLDER_ONLY_WORD_RE.match(word):
            continue
        if random.random() < MID_WORD_STUTTER_CHANCE:
            c = word[0]
            word = f"{c}-{word}"
        if random.random() < TILDE_CHANCE:
            word = f"{word}~"
        words[i] = word
    result = " ".join(words)

    # Restore protected tokens exactly as they were.
    result = PLACEHOLDER_RE.sub(lambda m: tokens[int(m.group(1))], result)

    result = f"{result} {random.choice(EMOTICONS)}"

    return result


WEBHOOK_NAME = "troll-webhook"


class TrollCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _get_webhook(self, channel: discord.TextChannel) -> discord.Webhook | None:
        try:
            webhooks = await channel.webhooks()
        except discord.Forbidden:
            return None

        for wh in webhooks:
            if wh.name == WEBHOOK_NAME:
                return wh

        try:
            return await channel.create_webhook(name=WEBHOOK_NAME)
        except discord.Forbidden:
            return None

    @app_commands.command(name="troll", description="Toggle owo-troll mode on a user (mod only)")
    @app_commands.describe(user="The user to toggle troll mode for", mode="enable or disable")
    @app_commands.choices(mode=[
        app_commands.Choice(name="enable", value="enable"),
        app_commands.Choice(name="disable", value="disable"),
    ])
    @app_commands.checks.has_permissions(manage_roles=True)
    async def troll(self, interaction: discord.Interaction, user: discord.Member, mode: app_commands.Choice[str]):
        role = interaction.guild.get_role(TROLL_ROLE_ID)
        if role is None:
            await interaction.response.send_message(
                "Troll role not found in this server.", ephemeral=True
            )
            return

        try:
            if mode.value == "enable":
                await user.add_roles(role, reason=f"Troll mode enabled by {interaction.user}")
                await interaction.response.send_message(
                    f"Troll mode enabled for {user.mention}.", ephemeral=True
                )
            else:
                await user.remove_roles(role, reason=f"Troll mode disabled by {interaction.user}")
                await interaction.response.send_message(
                    f"Troll mode disabled for {user.mention}.", ephemeral=True
                )
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to modify that user's roles.", ephemeral=True
            )

    @troll.error
    async def troll_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "You don't have permission to use this command.", ephemeral=True
            )
        else:
            raise error

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.guild is None:
            return

        role_ids = {r.id for r in message.author.roles}
        if TROLL_ROLE_ID not in role_ids:
            return

        original_content = message.content
        if not original_content:
            return

        transformed = owo_ify(original_content)

        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        target_channel = message.channel
        thread_kwarg = discord.utils.MISSING

        if isinstance(target_channel, discord.Thread):
            thread_kwarg = target_channel
            target_channel = target_channel.parent

        webhook = None
        if isinstance(target_channel, discord.TextChannel):
            webhook = await self._get_webhook(target_channel)

        if webhook is not None:
            try:
                await webhook.send(
                    content=transformed,
                    username=message.author.display_name,
                    avatar_url=message.author.display_avatar.url,
                    thread=thread_kwarg,
                )
                return
            except discord.Forbidden:
                pass

        # Fallback if webhook creation/send failed
        try:
            await message.channel.send(f"**{message.author.display_name} says:** {transformed}")
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(TrollCog(bot))