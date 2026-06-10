from __future__ import annotations

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
ENGAGE_ORG_URL = "https://terriercentral.bu.edu/organization/{}"

RESULTS_PER_PAGE = 5
MAX_DESCRIPTION_LEN = 120

# Known category name → ID mappings for autocomplete / convenience.
# Run =club categories to see the full list from the API.
CATEGORY_KEYWORDS: dict[str, int] = {
    "political": 12693,
}


async def setup(bot: TerrierBot) -> None:
    await bot.add_cog(ClubCog(bot))


def _truncate(text: str, max_len: int = MAX_DESCRIPTION_LEN) -> str:
    if not text:
        return ""
    text = text.strip()
    return text if len(text) <= max_len else text[:max_len].rstrip() + "…"


def _social_links(org: dict[str, Any]) -> list[str]:
    """Extract social / contact links from an org search result."""
    links: list[str] = []

    # Primary website
    website: str | None = org.get("websiteKey") or org.get("externalUrl")
    if website:
        if not website.startswith("http"):
            website = "https://" + website
        links.append(f"[Website]({website})")

    # Social media channels returned by the API
    social_map = {
        "facebookUrl": "Facebook",
        "twitterUrl": "Twitter/X",
        "instagramUrl": "Instagram",
        "linkedinUrl": "LinkedIn",
        "youtubeUrl": "YouTube",
        "tiktokUrl": "TikTok",
        "discordUrl": "Discord",
        "snapchatUrl": "Snapchat",
    }
    for key, label in social_map.items():
        url: str | None = org.get(key)
        if url:
            if not url.startswith("http"):
                url = "https://" + url
            links.append(f"[{label}]({url})")

    # Contact email
    email: str | None = org.get("contactEmail") or org.get("primaryContactEmail")
    if email:
        links.append(f"[Email](mailto:{email})")

    return links


def _org_page_url(org: dict[str, Any]) -> str:
    slug: str | None = org.get("webUrl") or org.get("shortName") or org.get("urlIdentifier")
    if slug:
        clean = slug.strip("/").split("/")[-1]
        return ENGAGE_ORG_URL.format(clean)
    # fallback: search page with the name
    name: str = org.get("name", "")
    return f"{ENGAGE_BASE_URL}/organizations?query={urllib.parse.quote(name)}"


def _build_org_embed(
    results: list[dict[str, Any]],
    query_display: str,
    page: int,
    total: int,
    page_size: int,
    search_url: str,
) -> discord.Embed:
    total_pages = max(1, (total + page_size - 1) // page_size)
    embed = discord.Embed(
        title=f"BU Clubs — {query_display}",
        description=f"Found **{total}** result(s) · Page {page}/{total_pages}",
        color=discord.Color.red(),
        url=search_url,
    )

    for org in results:
        name: str = org.get("name") or "Unnamed Organization"
        description: str = _truncate(org.get("summary") or org.get("description") or "")
        links = _social_links(org)
        page_link = _org_page_url(org)
        links_str = "  ".join(links) if links else "No links listed"

        value = f"[View on Terrier Central]({page_link})\n{links_str}"
        if description:
            value = f"*{description}*\n{value}"

        embed.add_field(name=name, value=value, inline=False)

    embed.set_footer(text="Terrier Central · terriercentral.bu.edu")
    return embed


class ClubCog(commands.Cog, name="Clubs", description="Search BU clubs on Terrier Central."):
    def __init__(self, bot: TerrierBot) -> None:
        self.bot = bot
        print("Club Cog Ready")

    # ------------------------------------------------------------------ #
    # Core fetch
    # ------------------------------------------------------------------ #

    async def _search(
        self,
        *,
        query: str | None = None,
        category_id: int | None = None,
        skip: int = 0,
        take: int = RESULTS_PER_PAGE,
    ) -> tuple[list[dict[str, Any]], int]:
        """
        Returns (results, totalCount).
        Pass query for keyword search, category_id for category filter.
        Both can be combined.
        """
        params: dict[str, Any] = {
            "status": 1,  # active orgs only
            "take": take,
            "skip": skip,
            "orderBy": "UpperName",
        }
        if query:
            params["query"] = query
        if category_id is not None:
            params["categories"] = category_id

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

    # ------------------------------------------------------------------ #
    # Argument parsing helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_args(raw: str) -> tuple[str | None, int | None, str]:
        """
        Detect whether raw looks like 'categories=12693' or a plain query.
        Returns (query, category_id, display_label).
        """
        # explicit categories=N
        m = re.match(r"categories=(\d+)", raw.strip(), re.IGNORECASE)
        if m:
            cat_id = int(m.group(1))
            return None, cat_id, f"Category #{cat_id}"

        # pure integer → treat as category id
        if raw.strip().isdigit():
            cat_id = int(raw.strip())
            return None, cat_id, f"Category #{cat_id}"

        # known keyword → category
        normalized = raw.strip().lower()
        if normalized in CATEGORY_KEYWORDS:
            cat_id = CATEGORY_KEYWORDS[normalized]
            return None, cat_id, normalized.title()

        # everything else → text query
        return raw.strip(), None, f'"{raw.strip()}"'

    # ------------------------------------------------------------------ #
    # Shared responder
    # ------------------------------------------------------------------ #

    async def _respond(
        self,
        send_fn,  # coroutine(embed) or interaction.response.send_message
        raw: str,
        page: int = 1,
    ) -> None:
        query, category_id, display = self._parse_args(raw)
        skip = (page - 1) * RESULTS_PER_PAGE

        results, total = await self._search(
            query=query,
            category_id=category_id,
            skip=skip,
            take=RESULTS_PER_PAGE,
        )

        # Build the canonical Terrier Central URL that mirrors the search
        tc_params: dict[str, str] = {}
        if query:
            tc_params["query"] = query
        if category_id is not None:
            tc_params["categories"] = str(category_id)
        search_url = f"{ENGAGE_BASE_URL}/organizations"
        if tc_params:
            search_url += "?" + urllib.parse.urlencode(tc_params)

        if not results:
            embed = discord.Embed(
                title=f"BU Clubs — {display}",
                description="No active organizations found for that search.",
                color=discord.Color.red(),
                url=search_url,
            )
            await send_fn(embed=embed)
            return

        embed = _build_org_embed(results, display, page, total, RESULTS_PER_PAGE, search_url)
        await send_fn(embed=embed)

    # ------------------------------------------------------------------ #
    # Prefix command
    # ------------------------------------------------------------------ #

    @commands.command(name="club")
    async def club(self, ctx: Context, *, query: str):
        """
        Search BU clubs on Terrier Central.

        Usage:
          =club blood              — keyword search
          =club political          — named category shortcut
          =club categories=12693   — explicit category ID
          =club 12693              — same, by raw number
          =club blood page:2       — paginate results
        """
        # Optional page:N suffix
        page = 1
        page_match = re.search(r"\bpage:(\d+)\b", query, re.IGNORECASE)
        if page_match:
            page = max(1, int(page_match.group(1)))
            query = query[: page_match.start()].strip()

        async with ctx.typing():
            await self._respond(ctx.send, query, page)

    # ------------------------------------------------------------------ #
    # Slash command
    # ------------------------------------------------------------------ #

    @app_commands.command(name="club", description="Search BU clubs on Terrier Central.")
    @app_commands.describe(
        query='Keyword (e.g. "blood"), category keyword ("political"), or "categories=12693"',
        page="Result page number (default 1)",
    )
    async def club_slash(
        self,
        interaction: discord.Interaction,
        query: str,
        page: int = 1,
    ) -> None:
        await interaction.response.defer()
        await self._respond(interaction.followup.send, query, max(1, page))
