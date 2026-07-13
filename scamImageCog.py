import io
import json
import logging
import os
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image
import imagehash

log = logging.getLogger(__name__)

# Fallback constant — only used for one-time migration if data/scam_hashes.json is absent.
KNOWN_SCAM_HASHES = [
    "c5ba36c9caa4318f",
    "e1f0e187981f0ade",
    "c59932cccdc338f4",
    "91aced9293ab09a7",
    "91ac6d9293ab09b7",
]

# Hamming distance threshold for a "match" — lower = stricter.
# 0 = exact hash match, 5-10 is typically a reasonable fuzzy-match range.
HASH_THRESHOLD = 10

TIMEOUT_MINUTES = 60
MOD_LOG_CHANNEL_ID = 1441888579147141170  # #message-logs — all scam alerts and confirmation prompts
SCAMCATCHER_ROLE_ID = 1402095379935395934

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_HASHES_FILE = os.path.join(_DATA_DIR, "scam_hashes.json")


# ── Confirmation view ─────────────────────────────────────────────────────────

class _HashConfirmView(discord.ui.View):
    def __init__(self, cog: "ScamImageCog", new_hashes: list[str]):
        super().__init__(timeout=60)
        self.cog = cog
        self.new_hashes = new_hashes
        self.message: discord.Message | None = None

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True  # type: ignore[attr-defined]
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not any(r.id == SCAMCATCHER_ROLE_ID for r in interaction.user.roles):  # type: ignore[union-attr]
            await interaction.response.send_message(
                "You don't have permission to use this button.", ephemeral=True
            )
            return
        added, skipped = [], []
        for h in self.new_hashes:
            if h not in self.cog.known_hashes:
                self.cog.known_hashes.add(h)
                added.append(h)
            else:
                skipped.append(h)
        self.cog.save_hashes()

        for item in self.children:
            item.disabled = True  # type: ignore[attr-defined]

        parts = [f"✅ Added {len(added)} new hash(es) to blocklist."]
        if skipped:
            parts.append(f"{len(skipped)} already present (skipped).")
        try:
            await interaction.response.edit_message(content=" ".join(parts), view=self)
        except discord.HTTPException:
            pass

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not any(r.id == SCAMCATCHER_ROLE_ID for r in interaction.user.roles):  # type: ignore[union-attr]
            await interaction.response.send_message(
                "You don't have permission to use this button.", ephemeral=True
            )
            return
        for item in self.children:
            item.disabled = True  # type: ignore[attr-defined]
        try:
            await interaction.response.edit_message(
                content="Cancelled — no hashes added.", view=self
            )
        except discord.HTTPException:
            pass


# ── Cog ───────────────────────────────────────────────────────────────────────

class ScamImageCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.known_hashes: set[str] = set()
        self.load_hashes()

        self._ctx_menu = app_commands.ContextMenu(
            name="Report Image(s)",
            callback=self.report_images,
        )
        self.bot.tree.add_command(self._ctx_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self._ctx_menu.name, type=self._ctx_menu.type)

    # ── Hash persistence ──────────────────────────────────────────────────────

    def load_hashes(self) -> None:
        if not os.path.exists(_HASHES_FILE):
            os.makedirs(_DATA_DIR, exist_ok=True)
            self.known_hashes = set(KNOWN_SCAM_HASHES)
            self.save_hashes()
            log.info("scamImageCog: migrated KNOWN_SCAM_HASHES constant → %s", _HASHES_FILE)
            return
        with open(_HASHES_FILE, "r", encoding="utf-8") as f:
            self.known_hashes = set(json.load(f))

    def save_hashes(self) -> None:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_HASHES_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(self.known_hashes), f, indent=2)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _has_scamcatcher_role(self, member: discord.Member) -> bool:
        return any(r.id == SCAMCATCHER_ROLE_ID for r in member.roles)

    async def _hash_matches(self, image_bytes: bytes) -> bool:
        try:
            img = Image.open(io.BytesIO(image_bytes))
            h = imagehash.phash(img)
        except Exception:
            return False

        for known in self.known_hashes:
            known_hash = imagehash.hex_to_hash(known)
            if (h - known_hash) <= HASH_THRESHOLD:
                return True
        return False

    # ── Automatic on_message listener (unchanged) ─────────────────────────────

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

    # ── Context menu: Report Image(s) ─────────────────────────────────────────

    async def report_images(
        self, interaction: discord.Interaction, message: discord.Message
    ) -> None:
        if not self._has_scamcatcher_role(interaction.user):  # type: ignore[arg-type]
            await interaction.response.send_message(
                "You don't have permission to use this command.", ephemeral=True
            )
            return

        image_attachments = [
            a for a in message.attachments
            if a.content_type and a.content_type.startswith("image/")
        ]
        if not image_attachments:
            await interaction.response.send_message(
                "No images found on that message.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        # Timeout the reported author immediately — before any sweep work.
        target_author = message.author
        try:
            import datetime
            await target_author.timeout(
                datetime.timedelta(minutes=TIMEOUT_MINUTES),
                reason="Posted scam image (manually reported)",
            )
        except discord.Forbidden:
            pass  # bot lacks permission or role hierarchy issue
        except discord.HTTPException:
            pass

        # Compute hashes
        attachment_hashes: list[tuple[discord.Attachment, str]] = []
        for att in image_attachments:
            try:
                data = await att.read()
                img = Image.open(io.BytesIO(data))
                h = str(imagehash.phash(img))
                attachment_hashes.append((att, h))
            except Exception:
                pass

        # ── Multi-channel cleanup (last 5 min) ────────────────────────────────

        # Always delete the reported message immediately, regardless of age.
        try:
            await message.delete()
        except discord.HTTPException:
            pass

        cutoff = discord.utils.utcnow() - timedelta(minutes=5)
        log_channel = self.bot.get_channel(MOD_LOG_CHANNEL_ID) if MOD_LOG_CHANNEL_ID else None
        # (channel_name, deleted_count, first_img_bytes_or_None, first_img_filename_or_None)
        channel_records: list[tuple[str, int, bytes | None, str | None]] = []

        for channel in interaction.guild.text_channels:  # type: ignore[union-attr]
            deleted_in_channel = 0
            first_img: tuple[bytes, str] | None = None
            try:
                count = 0
                async for msg in channel.history(after=cutoff, oldest_first=False):
                    if count >= 200:
                        break
                    count += 1

                    if msg.author.id != target_author.id:
                        continue
                    img_attachments = [
                        a for a in msg.attachments
                        if a.content_type and a.content_type.startswith("image/")
                    ]
                    if not img_attachments:
                        continue

                    # Read bytes before deletion — URL dies after delete.
                    # Only need one representative image per channel.
                    saved: list[tuple[discord.Attachment, bytes]] = []
                    for att in img_attachments:
                        try:
                            saved.append((att, await att.read()))
                        except Exception:
                            pass

                    try:
                        await msg.delete()
                        deleted_in_channel += 1
                    except (discord.HTTPException, discord.Forbidden):
                        continue

                    # Keep the first successfully-saved image as the channel representative.
                    if first_img is None and saved:
                        first_img = (saved[0][1], saved[0][0].filename)

            except discord.Forbidden:
                pass

            if deleted_in_channel:
                channel_records.append((
                    channel.name,
                    deleted_in_channel,
                    first_img[0] if first_img else None,
                    first_img[1] if first_img else None,
                ))

        # Cleanup summary → one single embed with one representative image per channel
        total_deleted = sum(n for _, n, _, _ in channel_records)
        if log_channel and total_deleted:
            try:
                breakdown = "\n".join(f"• #{name}: {n}" for name, n, _, _ in channel_records)
                summary_embed = discord.Embed(
                    title="🗑️ Scam wave cleanup",
                    description=(
                        f"Deleted **{total_deleted}** message(s) from "
                        f"{target_author.mention} across **{len(channel_records)}** "
                        f"channel(s) (image scam wave)\n\n{breakdown}"
                    ),
                    color=discord.Color.red(),
                )
                rep_files = [
                    discord.File(io.BytesIO(b), filename=fname)
                    for _, _, b, fname in channel_records[:10]
                    if b is not None
                ]
                await log_channel.send(embed=summary_embed, files=rep_files)
            except (discord.HTTPException, discord.Forbidden):
                pass

        # ── Confirmation prompt → confirm channel ────────────────────────────
        if not attachment_hashes:
            await interaction.followup.send(
                f"Cleanup complete ({total_deleted} message(s) removed), "
                "but no images could be hashed.",
                ephemeral=True,
            )
            return

        hash_list = "\n".join(f"`{h}` — {att.filename}" for att, h in attachment_hashes)
        new_hashes = [h for _, h in attachment_hashes]
        view = _HashConfirmView(self, new_hashes)

        confirm_content = (
            f"{interaction.user.mention} Cleanup done ({total_deleted} message(s) removed).\n\n"
            f"Add these hash(es) to the blocklist?\n{hash_list}"
        )
        confirm_channel = log_channel
        if confirm_channel:
            try:
                confirm_msg = await confirm_channel.send(
                    content=confirm_content,
                    view=view,
                    allowed_mentions=discord.AllowedMentions(users=True),
                )
                view.message = confirm_msg
            except (discord.HTTPException, discord.Forbidden):
                pass
            try:
                await interaction.followup.send(
                    "Confirmation prompt posted in the scam-reports channel.", ephemeral=True
                )
            except discord.HTTPException:
                pass
        else:
            # Fallback if log channel is unavailable
            msg = await interaction.followup.send(
                content=confirm_content,
                view=view,
                ephemeral=True,
                wait=True,
            )
            view.message = msg

    # ── /removehash slash command ─────────────────────────────────────────────

    @app_commands.command(name="removehash", description="Remove a hash from the scam image blocklist.")
    @app_commands.describe(hash="The perceptual hash string to remove.")
    async def removehash(self, interaction: discord.Interaction, hash: str) -> None:
        if not self._has_scamcatcher_role(interaction.user):  # type: ignore[arg-type]
            await interaction.response.send_message(
                "You don't have permission to use this command.", ephemeral=True
            )
            return

        if hash in self.known_hashes:
            self.known_hashes.discard(hash)
            self.save_hashes()
            try:
                await interaction.response.send_message(
                    f"✅ Removed `{hash}` from the blocklist.", ephemeral=True
                )
            except discord.HTTPException:
                pass
        else:
            try:
                await interaction.response.send_message(
                    "Hash not found in blocklist.", ephemeral=True
                )
            except discord.HTTPException:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(ScamImageCog(bot))
