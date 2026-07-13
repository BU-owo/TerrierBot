from __future__ import annotations

import html
import json
import re
import urllib.parse
from typing import Any

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from bot import Context, TerrierBot

ENGAGE_SEARCH_URL = "https://terriercentral.bu.edu/api/discovery/search/organizations"
ENGAGE_BASE_URL = "https://terriercentral.bu.edu"

RESULTS_PER_PAGE = 20

CATEGORY_KEYWORDS: dict[str, int] = {
    "political": 12693,
}


async def setup(bot: TerrierBot) -> None:
    await bot.add_cog(ClubCog(bot))


def _get(obj: dict, *keys: str) -> Any:
    """Try multiple key variants (handles both camelCase and PascalCase)."""
    for key in keys:
        val = obj.get(key)
        if val is not None and val != "" and val != []:
            return val
    return None


def _org_page_url(org: dict[str, Any]) -> str:
    """Extracts the native unique URL key directly from the payload."""
    slug = _get(org, "WebsiteKey", "websiteKey", "UrlIdentifier", "urlIdentifier")
    if slug:
        clean_slug = str(slug).strip("/").split("/")[-1]
        return f"{ENGAGE_BASE_URL}/organization/{clean_slug}"
    
    name = _get(org, "Name", "name") or ""
    return f"{ENGAGE_BASE_URL}/organizations?query={urllib.parse.quote(str(name))}"


def _org_name(org: dict[str, Any]) -> str:
    raw_name = str(_get(org, "Name", "name") or "Unknown Organization")
    return html.unescape(raw_name)


def _build_embed(
    results: list[dict[str, Any]],
    display: str,
    page: int,
    total: int,
    search_url: str,
) -> discord.Embed:
    club_lines = []
    for org in results:
        name = _org_name(org)
        page_link = _org_page_url(org)
        club_lines.append(f"• [{name}]({page_link})")
        
    full_description = "\n".join(club_lines)

    embed = discord.Embed(
        title=f"BU Clubs — {display}",
        description=full_description,
        color=discord.Color.from_rgb(254, 231, 92),  # Cute yellow 💛
        url=search_url,
    )

    embed.set_footer(text="terriercentral.bu.edu")
    return embed


# ------------------------------------------------------------------ #
# Pagination view
# ------------------------------------------------------------------ #

class ClubPaginationView(discord.ui.View):
    def __init__(
        self,
        cog: "ClubCog",
        raw_query: str,
        query: str | None,
        category_id: int | None,
        display: str,
        search_url: str,
        current_page: int,
        total_pages: int,
    ):
        super().__init__(timeout=120)
        self.cog = cog
        self.raw_query = raw_query
        self.query = query
        self.category_id = category_id
        self.display = display
        self.search_url = search_url
        self.current_page = current_page
        self.total_pages = total_pages
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_button.disabled = self.current_page <= 1
        self.next_button.disabled = self.current_page >= self.total_pages
        self.page_label.label = f"{self.current_page} / {self.total_pages}"

    async def _go_to(self, interaction: discord.Interaction, page: int) -> None:
        self.current_page = page
        skip = (page - 1) * RESULTS_PER_PAGE
        results, total = await self.cog._search(
            query=self.query,
            category_id=self.category_id,
            skip=skip,
        )
        self.total_pages = max(1, (total + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE)
        self._update_buttons()
        embed = _build_embed(results, self.display, page, total, self.search_url)
        # display reflects the original user query; club names come from the Engage API — suppress all pings.
        await interaction.response.edit_message(embed=embed, view=self, allowed_mentions=discord.AllowedMentions.none())

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go_to(interaction, self.current_page - 1)

    @discord.ui.button(label="· / ·", style=discord.ButtonStyle.grey, disabled=True)
    async def page_label(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go_to(interaction, self.current_page + 1)

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True


# ------------------------------------------------------------------ #
# Cog
# ------------------------------------------------------------------ #

class ClubCog(commands.Cog, name="Clubs", description="Search BU clubs on Terrier Central."):
    def __init__(self, bot: TerrierBot) -> None:
        self.bot = bot
        print("Club Cog Ready")

    async def _search(
        self,
        *,
        query: str | None = None,
        category_id: int | None = None,
        skip: int = 0,
        take: int = RESULTS_PER_PAGE,
    ) -> tuple[list[dict[str, Any]], int]:
        # Removed orderBy parameter to default to similarity ranking
        params: dict[str, Any] = {
            "status": 1,
            "top": take,
            "skip": skip,
        }
        
        if category_id is not None:
            params["categoryIds[0]"] = category_id
        
        if query and query.strip():
            params["query"] = query.strip()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    ENGAGE_SEARCH_URL,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15),
                    headers={"Accept": "application/json"},
                ) as resp:
                    if resp.status != 200:
                        return [], 0
                    data: dict[str, Any] = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError):
            return [], 0

        items: list[dict[str, Any]] = data.get("value", [])
        total: int = data.get("@odata.count", len(items))
        return items, total

    @staticmethod
    def _parse_args(raw: str) -> tuple[str | None, int | None, str]:
        cleaned = raw.strip()
        
        m = re.match(r"categories=(\d+)", cleaned, re.IGNORECASE)
        if m:
            cat_id = int(m.group(1))
            return None, cat_id, f"Category #{cat_id}"
            
        if cleaned.isdigit():
            cat_id = int(cleaned)
            return None, cat_id, f"Category #{cat_id}"
            
        words = cleaned.lower().split()
        for word in words:
            if word in CATEGORY_KEYWORDS:
                cat_id = CATEGORY_KEYWORDS[word]
                return cleaned, cat_id, cleaned.title()
                
        return cleaned, None, f'"{cleaned}"'

    async def _respond(self, ctx: Context, raw: str) -> None:
        query, category_id, display = self._parse_args(raw)

        tc_params: dict[str, str] = {}
        if query:
            tc_params["query"] = query
        if category_id is not None:
            tc_params["categories"] = str(category_id)
            
        search_url = ENGAGE_BASE_URL + "/organizations"
        if tc_params:
            search_url += "?" + urllib.parse.urlencode(tc_params)

        results, total = await self._search(query=query, category_id=category_id, skip=0)

        if not results:
            embed = discord.Embed(
                title=f"BU Clubs — {display}",
                description="No active organizations found.",
                color=discord.Color.from_rgb(254, 231, 92),
                url=search_url,
            )
            # display reflects user query — suppress all pings.
            await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            return

        total_pages = max(1, (total + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE)
        embed = _build_embed(results, display, 1, total, search_url)
        view = ClubPaginationView(
            cog=self,
            raw_query=raw,
            query=query,
            category_id=category_id,
            display=display,
            search_url=search_url,
            current_page=1,
            total_pages=total_pages,
        )
        # display reflects user query; club names from Engage API could contain mention syntax — suppress all pings.
        await ctx.send(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())

    # ------------------------------------------------------------------ #
    # Prefix command
    # ------------------------------------------------------------------ #

    @commands.command(name="club")
    async def club(self, ctx: Context, *, query: str):
        """Search BU clubs. =club blood | =club political"""
        async with ctx.typing():
            await self._respond(ctx, query)

    # ------------------------------------------------------------------ #
    # Slash command
    # ------------------------------------------------------------------ #

    @app_commands.command(name="club", description="Search BU clubs on Terrier Central.")
    @app_commands.describe(query='Keyword (e.g. "blood"), category name ("political")')
    async def club_slash(self, interaction: discord.Interaction, query: str) -> None:
        await interaction.response.defer()

        q, category_id, display = self._parse_args(query)
        tc_params: dict[str, str] = {}
        if q:
            tc_params["query"] = q
        if category_id is not None:
            tc_params["categories"] = str(category_id)
            
        search_url = ENGAGE_BASE_URL + "/organizations"
        if tc_params:
            search_url += "?" + urllib.parse.urlencode(tc_params)

        results, total = await self._search(query=q, category_id=category_id, skip=0)

        if not results:
            embed = discord.Embed(
                title=f"BU Clubs — {display}",
                description="No active organizations found.",
                color=discord.Color.from_rgb(254, 231, 92),
                url=search_url,
            )
            # display reflects user query — suppress all pings.
            await interaction.followup.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            return

        total_pages = max(1, (total + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE)
        embed = _build_embed(results, display, 1, total, search_url)
        view = ClubPaginationView(
            cog=self,
            raw_query=query,
            query=q,
            category_id=category_id,
            display=display,
            search_url=search_url,
            current_page=1,
            total_pages=total_pages,
        )
        # display reflects user query; club names from Engage API could contain mention syntax — suppress all pings.
        await interaction.followup.send(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())

    # ------------------------------------------------------------------ #
    # Debug
    # ------------------------------------------------------------------ #

    @commands.command(name="clubdebug")
    @commands.is_owner()
    async def club_debug(self, ctx: Context, *, query: str = "blood"):
        """Dump raw API JSON for a query (Owner only)."""
        params = {"status": 1, "top": 1, "skip": 0, "query": query}
        async with aiohttp.ClientSession() as session:
            async with session.get(
                ENGAGE_SEARCH_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"Accept": "application/json"},
            ) as resp:
                raw = await resp.text()

        try:
            pretty = json.dumps(json.loads(raw), indent=2)
        except Exception:
            pretty = raw
        snippet = pretty[:1900]
        # Raw API JSON could contain arbitrary text — suppress all pings.
        await ctx.send(f"```json\n{snippet}\n```", allowed_mentions=discord.AllowedMentions.none())