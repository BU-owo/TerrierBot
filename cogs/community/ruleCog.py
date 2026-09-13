from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot import Context, TerrierBot

# 1-indexed — a rule's position here is the number members reference it by.
RULES: list[str] = [
    "No harassment or insults.",
    "No bigotry, hate speech, hate symbols, or use of slurs.",
    "Don't be edgy, provocative, or baiting in a way that upsets people or starts needless arguments.",
    "No spamming chat or misusing pings.",
    "No doxxing identities or personal information, including sharing DMs without permission.",
    "No threats of harm or encouraging any behaviors that endanger health/safety.",
    "No NSFW (sexual/flirting) or NSFL (gore/violent) content or language.",
    "No scams allowed. Self-promotion requires prior approval.",
    "Mods reserve the right to interpret, enforce, and change rules to keep the community healthy.",
]


async def setup(bot: TerrierBot):
    await bot.add_cog(RuleCog(bot))


class RuleCog(commands.Cog, name="Rule", description="Look up a server rule by number, or list them all."):
    def __init__(self, bot: TerrierBot):
        self.bot = bot

    def _all_rules_embed(self) -> discord.Embed:
        return discord.Embed(
            title="📜 Server Rules",
            description="\n".join(f"**{i}.** {text}" for i, text in enumerate(RULES, start=1)),
            color=discord.Color.blurple(),
        )

    async def _rule_number_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[int]]:
        current_lower = current.strip().lower()
        choices = []
        for i, text in enumerate(RULES, start=1):
            label = f"{i}. {text}"
            if current_lower and current_lower not in label.lower():
                continue
            choices.append(app_commands.Choice(name=label[:100], value=i))
        return choices[:25]

    @commands.hybrid_command(name="rule", description="Show a server rule by number, or all of them if left blank.")
    @app_commands.describe(number="Which rule to show — leave blank to see all of them")
    @app_commands.autocomplete(number=_rule_number_autocomplete)
    async def rule(self, ctx: Context, number: int | None = None) -> None:
        if number is None:
            await ctx.send(embed=self._all_rules_embed())
            return

        if not (1 <= number <= len(RULES)):
            await ctx.send(
                f"There's no rule #{number} — pick a number between 1 and {len(RULES)}.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"📜 Rule {number}",
            description=RULES[number - 1],
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=embed)
