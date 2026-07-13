import io
import discord
from discord.ext import commands
from PIL import Image
import imagehash

# Add known scam image hashes here (perceptual hashes, as strings).
# Generate one with: imagehash.phash(Image.open("scam.png"))
KNOWN_SCAM_HASHES = [
    "c5ba36c9caa4318f",
    "e1f0e187981f0ade",
    "c59932cccdc338f4",
    "91aced9293ab09a7",
    "91ac6d9293ab09b7",
]

# Hamming distance threshold for a "match" — lower = stricter.
# 0 = exact hash match, 5-10 is typically a reasonable fuzzy-match range.
HASH_THRESHOLD = 8

TIMEOUT_MINUTES = 60
MOD_LOG_CHANNEL_ID = 1441889164898341098  # set to a channel ID if you want match alerts logged
SCAMCATCHER_ROLE_ID = 1402095379935395934


class ScamImageCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _hash_matches(self, image_bytes: bytes) -> bool:
        try:
            img = Image.open(io.BytesIO(image_bytes))
            h = imagehash.phash(img)
        except Exception:
            return False

        for known in KNOWN_SCAM_HASHES:
            known_hash = imagehash.hex_to_hash(known)
            if (h - known_hash) <= HASH_THRESHOLD:
                return True
        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if not message.attachments:
            return

        for attachment in message.attachments:
            if not attachment.content_type or not attachment.content_type.startswith("image/"):
                continue

            image_bytes = await attachment.read()
            if await self._hash_matches(image_bytes):
                await self._handle_scam(message)
                return  # only need to act once per message

    async def _handle_scam(self, message: discord.Message):
        try:
            await message.delete()
        except discord.HTTPException:
            pass

        member = message.author
        try:
            import datetime
            await member.timeout(
                datetime.timedelta(minutes=TIMEOUT_MINUTES),
                reason="Posted known scam image",
            )
        except discord.Forbidden:
            pass  # bot lacks permission or role hierarchy issue
        except discord.HTTPException:
            pass

        try:
            await message.channel.send(
                f"{member.mention}'s message was removed and they were timed out "
                f"for {TIMEOUT_MINUTES} minutes (known scam image detected).",
                delete_after=15,
            )
        except discord.HTTPException:
            pass

        if MOD_LOG_CHANNEL_ID:
            log_channel = self.bot.get_channel(MOD_LOG_CHANNEL_ID)
            if log_channel:
                embed = discord.Embed(
                    title="Scam image detected",
                    description=f"User: {member.mention} ({member.id})\nChannel: {message.channel.mention}",
                    color=discord.Color.red(),
                )
                await log_channel.send(
                    content=f"<@&{SCAMCATCHER_ROLE_ID}>",
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions(roles=True),
                )


async def setup(bot: commands.Bot):
    await bot.add_cog(ScamImageCog(bot))
