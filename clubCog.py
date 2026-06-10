from __future__ import annotations

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

RESULTS_PER_PAGE = 10
MAX_DESC_LEN = 100

CATEGORY_KEYWORDS: dict[str, int] = {
    "political": 12693,
}

SOCIAL_ICONS: dict[str, str] = {
    "instagram": "📸",
    "facebook": "📘",
    "twitter": "🐦",
    "x": "🐦",
    "linkedin": "💼",
    "youtube": "▶️",
    "tiktok": "🎵",
    "discord": "💬",
    "snapchat": "👻",
    "website": "🌐",
    "email": "📧",
}


async def setup(bot: TerrierBot) -> None:
    await bot.add_cog(ClubCog(bot))


def _truncate(text: str, max_len: int = MAX_DESC_LEN) -> str:
    if not text:
        return ""
    text = text.strip()
    return text if len(text) <= max_len else text[:max_len].rstrip() + "…"


def _get(obj: dict, *keys: str) -> Any:
    """Try multiple key variants (handles both camelCase and PascalCase)."""
    for key in keys:
        val = obj.get(key)
        if val is not None and val != "" and val != []:
            return val
    return None


def _social_links(org: dict[str, Any]) -> list[str]:
    links: list[str] = []

    # SocialLinks array: [{"Uri": "...", "Type": "Instagram"}, ...]
    social_list = _get(org, "SocialLinks", "socialLinks") or []
    for item in social_list:
        if not isinstance(item, dict):
            continue
        uri = _get(item, "Uri", "uri", "Url", "url")
        kind = (_get(item, "Type", "type") or "website").lower()
        if not uri:
            continue
        if not uri.startswith("http"):
            uri = "https://" + uri
        icon = SOCIAL_ICONS.get(kind, "🔗")
        label = kind.title() if kind else "Link"
        links.append(f"[{icon} {label}]({uri})")

    # External website
    ext_url = _get(org, "ExternalWebsiteUrl", "externalWebsiteUrl", "websiteUrl", "WebsiteUrl")
    if ext_url:
        if not ext_url.startswith("http"):
            ext_url = "https://" + ext_url
        links.append(f"[🌐 Website]({ext_url})")

    # Contacts: [{"EmailAddress": "...", "Name": "..."}, ...]
    contacts = _get(org, "Contacts", "contacts") or []
    for contact in contacts:
        if not isinstance(contact, dict):
            continue
        email = _get(contact, "EmailAddress", "emailAddress", "Email", "email")
        if email:
            links.append(f"[📧 Email](mailto:{email})")
            break  # one email is enough

    return links


def _org_page_url(org: dict[str, Any]) -> str:
    slug = _get(org, "ShortName", "shortName", "WebsiteKey", "websiteKey", "UrlIdentifier", "urlIdentifier")
    if slug:
        clean = str(slug).strip("/").split("/")[-1]
        return f"{ENGAGE_BASE_URL}/organization/{clean}"
    name = _get(org, "Name", "name") or ""
    return f"{ENGAGE_BASE_URL}/organizations?query={urllib.parse.quote(str(name))}"


def _org_name(org: dict[str, Any]) -> str:
    return str(_get(org, "Name", "name") or "Unknown Organization")


def _org_summary(org: dict[str, Any]) -> str:
    return _truncate(str(_get(org, "Summary", "summary", "Description", "description") or ""))


def _build_embed(
    results: list[dict[str, Any]],
    display: str,
    page: int,
    total: int,
    search_url: str,
) -> discord.Embed:
    total_pages = max(1, (total + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE)
    embed = discord.Embed(
        title=f"BU Clubs — {display}",
        description=f"**{total}** organization(s) found · Page {page} of {total_pages}",
        color=discord.Color.red(),
        url=search_url,
    )
    for org in results:
        name = _org_name(org)
        summary = _org_summary(org)
        links = _social_links(org)
        page_link = _org_page_url(org)

        parts: list[str] = []
        if summary:
            parts.append(f"*{summary}*")
        parts.append(f"[Terrier Central]({page_link})")
        if links:
            parts.append("  ".join(links))

        embed.add_field(name=name, value="\n".join(parts), inline=False)

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
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):  # type: ignore[override]
        await self._go_to(interaction, self.current_page - 1)

    @discord.ui.button(label="· / ·", style=discord.ButtonStyle.grey, disabled=True)
    async def page_label(self, interaction: discord.Interaction, button: discord.ui.Button):  # type: ignore[override]
        await interaction.response.defer()

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):  # type: ignore[override]
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
        params: dict[str, Any] = {
            "status": 1,
            "take": take,
            "skip": skip,
            "orderBy": "UpperName",
        }
        if query:
            params["query"] = query
            
        # --- CHANGE THIS PART ---
        if category_id is not None:
            # Engage's OData API often expects collection filters wrapped in brackets 
            # or passed specifically as a list element for aiohttp to map correctly
            params["categories"] = [category_id] 
        # ------------------------

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
        m = re.match(r"categories=(\d+)", raw.strip(), re.IGNORECASE)
        if m:
            cat_id = int(m.group(1))
            return None, cat_id, f"Category #{cat_id}"
        if raw.strip().isdigit():
            cat_id = int(raw.strip())
            return None, cat_id, f"Category #{cat_id}"
        normalized = raw.strip().lower()
        if normalized in CATEGORY_KEYWORDS:
            cat_id = CATEGORY_KEYWORDS[normalized]
            return None, cat_id, normalized.title()
        return raw.strip(), None, f'"{raw.strip()}"'

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
                color=discord.Color.red(),
                url=search_url,
            )
            await ctx.send(embed=embed)
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
        await ctx.send(embed=embed, view=view)

    # ------------------------------------------------------------------ #
    # Prefix command
    # ------------------------------------------------------------------ #

    @commands.command(name="club")
    async def club(self, ctx: Context, *, query: str):
        """Search BU clubs. =club blood | =club political | =club categories=12693"""
        async with ctx.typing():
            await self._respond(ctx, query.strip())

    # ------------------------------------------------------------------ #
    # Slash command
    # ------------------------------------------------------------------ #

    @app_commands.command(name="club", description="Search BU clubs on Terrier Central.")
    @app_commands.describe(query='Keyword (e.g. "blood"), category name ("political"), or "categories=12693"')
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
                color=discord.Color.red(),
                url=search_url,
            )
            await interaction.followup.send(embed=embed)
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
        await interaction.followup.send(embed=embed, view=view)

    # ------------------------------------------------------------------ #
    # Debug: owner-only raw JSON dump to identify real field names
    # ------------------------------------------------------------------ #

    @commands.command(name="clubdebug")
    @commands.is_owner()
    async def club_debug(self, ctx: Context, *, query: str = "blood"):
        """Dump raw API JSON for a query (Owner only). Helps identify real field names."""
        params: dict[str, Any] = {
            "status": 1,
            "take": 1,
            "skip": 0,
            "query": query,
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(
                ENGAGE_SEARCH_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"Accept": "application/json"},
            ) as resp:
                raw = await resp.text()

        # Pretty-print first 1900 chars
        try:
            pretty = json.dumps(json.loads(raw), indent=2)
        except Exception:
            pretty = raw
        snippet = pretty[:1900]
        await ctx.send(f"```json\n{snippet}\n```")