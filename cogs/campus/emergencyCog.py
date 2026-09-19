from __future__ import annotations

import discord
from discord.ext import commands

from bot import Context, TerrierBot

BUPD_NUMBER = "617-353-2121"
BUPD_MEDICAL_CAMPUS_NUMBER = "617-358-4444"

EMERGENCY_LINES: list[tuple[str, str]] = [
    ("Medical Emergencies", "617-353-3575 (non-life threatening)"),
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
        # BUPD goes in the title — the largest text an embed has.
        embed = discord.Embed(
            title=f"🚨 BU Police: {BUPD_NUMBER}",
            description=(
                f"{BUPD_MEDICAL_CAMPUS_NUMBER} (Medical Campus)\n"
                f"Call 911 if you are off-campus"
            ),
            color=discord.Color.red(),
        )
        embed.add_field(
            name="24/7 Emergency Lines",
            value="\n".join(f"**{label}:** {number}" for label, number in EMERGENCY_LINES),
            inline=False,
        )
        return embed

    @commands.hybrid_command(name="emergency", description="Show BU emergency contact numbers.")
    async def emergency(self, ctx: Context) -> None:
        await ctx.send(embed=self._build_embed())
