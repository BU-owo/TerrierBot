from __future__ import annotations

import discord
from discord.ext import commands

from bot import Context, TerrierBot

BUPD_NUMBER = "617-353-2121"
BUPD_MEDICAL_CAMPUS_NUMBER = "617-358-4444"

# 24/7 emergency lines, shown below BUPD (kept smaller/lower-priority — BUPD
# is who you call first for anything urgent on campus).
EMERGENCY_LINES: list[tuple[str, str]] = [
    ("Medical Emergencies (non-life threatening)", "617-353-3575"),
    ("Mental Health Emergencies", "617-353-3569"),
    ("SARP (sexual assault, dating violence, etc)", "617-353-7277"),
    ("Facilities Emergencies/Urgent Issues", "617-353-2105"),
]


async def setup(bot: TerrierBot):
    await bot.add_cog(EmergencyCog(bot))


class EmergencyCog(
    commands.Cog,
    name="Emergency",
    description="Shows BU emergency contact numbers.",
):
    def __init__(self, bot: TerrierBot):
        self.bot = bot

    def _build_embed(self) -> discord.Embed:
        # BUPD goes in the title — the largest text an embed has — so it's
        # unmistakably the number to call first for an on-campus emergency.
        embed = discord.Embed(
            title=f"🚨 BU POLICE (Emergency): {BUPD_NUMBER}",
            description=(
                f"**Call BU Police first for any on-campus emergency.**\n"
                f"Medical Campus: **{BUPD_MEDICAL_CAMPUS_NUMBER}**\n"
                f"Off-campus? Call **911**."
            ),
            color=discord.Color.red(),
        )
        embed.add_field(
            name="24/7 Emergency Lines",
            value="\n".join(f"**{label}:** {number}" for label, number in EMERGENCY_LINES),
            inline=False,
        )
        embed.set_footer(text="Save these — don't wait until you need them to look them up.")
        return embed

    @commands.hybrid_command(
        name="emergency", description="Show BU emergency contact numbers (BU Police, medical, mental health, SARP, facilities)."
    )
    async def emergency(self, ctx: Context) -> None:
        await ctx.send(embed=self._build_embed())
