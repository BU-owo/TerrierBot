from __future__ import annotations

import csv
import os
import re

import discord
from discord import app_commands
from discord.ext import commands

from bot import TerrierBot, Context

# ─── Constants ────────────────────────────────────────────────────────────────

CSV_PATH = os.path.join(os.path.dirname(__file__), "bu_courses_all.csv")

PAGE_SIZE = 25      # Discord select max options

HUB_COLS: list[str] = [
    "PLM", "AEX", "HCO", "SI1", "SI2",
    "SO1", "SO2", "QR1", "QR2", "IIC",
    "GCI", "ETR", "WIN", "OSC", "DME",
    "CRT", "RIL", "TWC", "CRI",
]

HUB_LABELS: dict[str, str] = {
    "PLM": "Philosophical/Aesthetic/Historical Interpretation",
    "AEX": "Aesthetic Exploration",
    "HCO": "Historical Consciousness",
    "SI1": "Scientific Inquiry I",
    "SI2": "Scientific Inquiry II",
    "SO1": "Social Inquiry I",
    "SO2": "Social Inquiry II",
    "QR1": "Quantitative Reasoning I",
    "QR2": "Quantitative Reasoning II",
    "IIC": "Individual in Community",
    "GCI": "Global Citizenship & Intercultural Literacy",
    "ETR": "Ethical Reasoning",
    "WIN": "Writing-Intensive",
    "OSC": "Oral/Signed Communication",
    "DME": "Digital/Multimedia Expression",
    "CRT": "Critical Thinking",
    "RIL": "Research & Information Literacy",
    "TWC": "Teamwork/Collaboration",
    "CRI": "Creative/Innovative Thinking",
}

SCHOOL_LABELS: dict[str, str] = {
    "CAS": "Arts & Sciences",
    "CFA": "Fine Arts",
    "CGS": "General Studies",
    "COM": "Communication",
    "ENG": "Engineering",
    "KHC": "Kilachand Honors",
    "LAW": "Law",
    "MET": "Metropolitan College",
    "QST": "Questrom (Business)",
    "SAR": "Rehabilitation Sciences",
    "SHA": "Hospitality Administration",
    "SPH": "Public Health",
    "SSW": "Social Work",
    "STH": "Theology",
    "WED": "Wheelock (Education)",
}

_SCHOOL_SLUG: dict[str, str] = {
    "CAS": "cas",       "CFA": "cfa",   "CGS": "cgs",       "COM": "com",
    "ENG": "eng",       "KHC": "khc",   "LAW": "law",       "MET": "met",
    "QST": "questrom",  "SAR": "sar",   "SHA": "sha",       "SPH": "sph",
    "SSW": "ssw",       "STH": "sth",   "WED": "wheelock",
}

# ─── Data helpers ─────────────────────────────────────────────────────────────

_courses_cache: list[dict] = []


def _load_courses() -> list[dict]:
    global _courses_cache
    if not _courses_cache:
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            _courses_cache = list(csv.DictReader(f))
    return _courses_cache


def _search(
    schools: list[str],
    dept: str,
    hub_units: list[str],
    hub_mode: str = "any",
) -> tuple[list[dict], bool]:
    """Return all matching results."""
    dept_upper = dept.upper().strip() if dept else ""
    hub_set = set(hub_units)
    results: list[dict] = []

    for row in _load_courses():
        parts = row["Course Number"].split()
        if len(parts) < 3:
            continue
        school, subject = parts[0], parts[1]

        if schools and school not in schools:
            continue
        if dept_upper and subject != dept_upper:
            continue
        if hub_set:
            matching = {h for h in hub_set if row.get(h, "").strip() == "X"}
            if hub_mode == "all" and len(matching) < len(hub_set):
                continue
            if hub_mode == "any" and not matching:
                continue

        results.append(row)

    return results, False


def _course_embed(row: dict) -> discord.Embed:
    """Build a detail embed for a single course from CSV data."""
    num = row["Course Number"]
    name = row["Course Name"] or "Untitled"
    prereqs = row.get("Prerequisites", "").strip()
    desc = row.get("Description", "").strip()
    hubs = [f"**{h}** — {HUB_LABELS[h]}" for h in HUB_COLS if row.get(h, "").strip() == "X"]

    parts = num.split()
    url: str | None = None
    if len(parts) == 3:
        school, subj, number = parts
        slug = _SCHOOL_SLUG.get(school, school.lower())
        url = f"https://www.bu.edu/academics/{slug}/courses/{school.lower()}-{subj.lower()}-{number.lower()}/"

    embed = discord.Embed(
        title=f"{num}: {name}",
        url=url,
        color=discord.Color.from_rgb(204, 0, 0),
    )
    if desc:
        embed.description = desc[:4000]
    if prereqs:
        embed.add_field(name="Prerequisites", value=prereqs[:1024], inline=False)
    if hubs:
        embed.add_field(name="HUB Units", value="\n".join(hubs)[:1024], inline=False)
    embed.set_footer(text=f"Use =class {num} for live section listings & enrollment info")
    return embed


# ─── Results view ─────────────────────────────────────────────────────────────

class ResultsView(discord.ui.View):
    def __init__(self, results: list[dict], query_summary: str, capped: bool = False) -> None:
        super().__init__(timeout=300)
        self.results = results
        self.query_summary = query_summary
        self.capped = capped
        self.page = 0
        # Precompute dept → first-page and course-count maps (keyed as "SCHOOL DEPT")
        self._dept_page_map: dict[str, int] = {}
        self._dept_counts: dict[str, int] = {}
        for i, row in enumerate(results):
            parts = row["Course Number"].split()
            if len(parts) >= 3:
                key = f"{parts[0]} {parts[1]}"
                self._dept_counts[key] = self._dept_counts.get(key, 0) + 1
                if key not in self._dept_page_map:
                    self._dept_page_map[key] = i // PAGE_SIZE
        self._rebuild()

    def _rebuild(self) -> None:
        self.clear_items()
        total = len(self.results)
        start = self.page * PAGE_SIZE
        end = min(start + PAGE_SIZE, total)
        page_results = self.results[start:end]
        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

        # ── Row 0: course select dropdown ────────────────────────────────────
        select = discord.ui.Select(
            placeholder=f"Pick a course for full details  ({start + 1}–{end} of {total}{'+'  if self.capped else ''})",
            options=[
                discord.SelectOption(
                    label=r["Course Number"],
                    description=(r["Course Name"] or "")[:100],
                    value=r["Course Number"],
                )
                for r in page_results
            ],
        )
        select.callback = self._on_course_select
        self.add_item(select)

        # ── Row 1: jump-to-dept select (only when results span multiple depts) ───
        if len(self._dept_counts) > 1:
            dept_opts = [
                discord.SelectOption(
                    label=f"{key}  —  {count} course{'s' if count != 1 else ''}",
                    value=key,
                )
                for key, count in sorted(self._dept_counts.items())
            ][:25]
            dept_select = discord.ui.Select(
                placeholder="📚  Jump to department...",
                options=dept_opts,
            )
            dept_select.callback = self._on_dept_jump
            self.add_item(dept_select)

        # ── Row 2 (or 1 if no dept select): navigation buttons ───────────────
        prev_btn = discord.ui.Button(
            label="◀ Prev",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page == 0),
        )
        prev_btn.callback = self._on_prev
        self.add_item(prev_btn)

        self.add_item(discord.ui.Button(
            label=f"Page {self.page + 1} / {total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
        ))

        next_btn = discord.ui.Button(
            label="Next ▶",
            style=discord.ButtonStyle.secondary,
            disabled=(end >= total),
        )
        next_btn.callback = self._on_next
        self.add_item(next_btn)

        new_btn = discord.ui.Button(
            label="🔍 New Search",
            style=discord.ButtonStyle.primary,
        )
        new_btn.callback = self._on_new_search
        self.add_item(new_btn)

    def _results_embed(self) -> discord.Embed:
        total = len(self.results)
        start = self.page * PAGE_SIZE
        end = min(start + PAGE_SIZE, total)
        page_results = self.results[start:end]
        cap_note = ""

        lines: list[str] = []
        for r in page_results:
            num = r["Course Number"]
            name = r["Course Name"] or "Untitled"
            hubs = [h for h in HUB_COLS if r.get(h, "").strip() == "X"]
            hub_tag = (" `" + "` `".join(hubs) + "`") if hubs else ""
            lines.append(f"**{num}** — {name}{hub_tag}")

        embed = discord.Embed(
            title="🔍 BU Course Search Results",
            color=discord.Color.from_rgb(204, 0, 0),
        )
        embed.description = (
            f"**{total}{'+' if self.capped else ''} course{'s' if total != 1 else ''} found**"
            f" — {self.query_summary}{cap_note}\n"
            f"*Showing {start + 1}–{end}*\n\u200b\n"
            + "\n".join(lines)
        )[:4096]
        embed.set_footer(text="Select a course from the dropdown to see full details.")
        return embed

    async def _on_course_select(self, interaction: discord.Interaction) -> None:
        course_num = interaction.data["values"][0]  # type: ignore[index]
        row = next((r for r in self.results if r["Course Number"] == course_num), None)
        if row is None:
            await interaction.response.send_message("Course not found.", ephemeral=True)
            return
        await interaction.response.send_message(embed=_course_embed(row), ephemeral=True)

    async def _on_dept_jump(self, interaction: discord.Interaction) -> None:
        key = interaction.data["values"][0]  # type: ignore[index]
        self.page = self._dept_page_map.get(key, 0)
        self._rebuild()
        await interaction.response.edit_message(embed=self._results_embed(), view=self)

    async def _on_prev(self, interaction: discord.Interaction) -> None:
        self.page = max(0, self.page - 1)
        self._rebuild()
        await interaction.response.edit_message(embed=self._results_embed(), view=self)

    async def _on_next(self, interaction: discord.Interaction) -> None:
        self.page = min((len(self.results) - 1) // PAGE_SIZE, self.page + 1)
        self._rebuild()
        await interaction.response.edit_message(embed=self._results_embed(), view=self)

    async def _on_new_search(self, interaction: discord.Interaction) -> None:
        view = SearchView()
        await interaction.response.edit_message(embed=view._form_embed(), view=view)


# ─── No-results back-view ─────────────────────────────────────────────────────

class _BackView(discord.ui.View):
    def __init__(self, search_view: SearchView) -> None:
        super().__init__(timeout=300)
        self._sv = search_view

    @discord.ui.button(label="← Modify Search", style=discord.ButtonStyle.secondary)
    async def go_back(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self._sv._rebuild()
        await interaction.response.edit_message(embed=self._sv._form_embed(), view=self._sv)


# ─── Search form view ─────────────────────────────────────────────────────────

class SearchView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=300)
        self._selected_schools: list[str] = []
        self._selected_hub: list[str] = []
        self._hub_mode: str = "any"
        self._rebuild()

    def _rebuild(self) -> None:
        self.clear_items()

        # ── Row 0: school multi-select ────────────────────────────────────────
        school_select = discord.ui.Select(
            placeholder="🏛  Filter by school  (optional — pick one or more)",
            min_values=0,
            max_values=len(SCHOOL_LABELS),
            options=[
                discord.SelectOption(
                    label=f"{code} — {label}",
                    value=code,
                    default=(code in self._selected_schools),
                )
                for code, label in SCHOOL_LABELS.items()
            ],
        )
        school_select.callback = self._on_school
        self.add_item(school_select)

        # ── Row 1: HUB multi-select ───────────────────────────────────────────
        hub_select = discord.ui.Select(
            placeholder="🎓  Filter by HUB unit  (optional — pick one or more)",
            min_values=0,
            max_values=len(HUB_LABELS),
            options=[
                discord.SelectOption(
                    label=f"{code} — {label}",
                    value=code,
                    default=(code in self._selected_hub),
                )
                for code, label in HUB_LABELS.items()
            ],
        )
        hub_select.callback = self._on_hub
        self.add_item(hub_select)

        # ── Row 2: HUB match-mode select ─────────────────────────────────────
        mode_select = discord.ui.Select(
            placeholder=f"HUB match mode: {'any selected unit' if self._hub_mode == 'any' else 'all selected units'}",
            options=[
                discord.SelectOption(
                    label="Match ANY selected HUB unit",
                    value="any",
                    default=(self._hub_mode == "any"),
                    description="Course fulfills at least one of your chosen HUB units",
                ),
                discord.SelectOption(
                    label="Match ALL selected HUB units",
                    value="all",
                    default=(self._hub_mode == "all"),
                    description="Course must fulfill every selected HUB unit",
                ),
            ],
        )
        mode_select.callback = self._on_mode
        self.add_item(mode_select)

        # ── Row 3: search button ───────────────────────────────────────────────────
        search_btn = discord.ui.Button(
            label="🔍  Search",
            style=discord.ButtonStyle.success,
        )
        search_btn.callback = self._on_search
        self.add_item(search_btn)

    def _form_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🔍 BU Course Search",
            description=(
                "Use the dropdowns below to filter courses, then click **Search**.\n"
                "All filters are optional — leave them blank to browse broadly.\n\u200b"
            ),
            color=discord.Color.from_rgb(204, 0, 0),
        )
        embed.add_field(
            name="Schools",
            value=", ".join(f"`{s}`" for s in self._selected_schools) if self._selected_schools else "*Any*",
            inline=True,
        )

        hub_mode_label = "match **any**" if self._hub_mode == "any" else "match **all**"
        embed.add_field(
            name=f"HUB Units ({hub_mode_label})",
            value=(
                " ".join(f"`{h}`" for h in self._selected_hub)
                if self._selected_hub
                else "*Any*"
            ),
            inline=False,
        )
        return embed

    async def _on_school(self, interaction: discord.Interaction) -> None:
        self._selected_schools = interaction.data["values"]  # type: ignore[index]
        self._rebuild()
        await interaction.response.edit_message(embed=self._form_embed(), view=self)

    async def _on_hub(self, interaction: discord.Interaction) -> None:
        self._selected_hub = interaction.data["values"]  # type: ignore[index]
        self._rebuild()
        await interaction.response.edit_message(embed=self._form_embed(), view=self)

    async def _on_mode(self, interaction: discord.Interaction) -> None:
        self._hub_mode = interaction.data["values"][0]  # type: ignore[index]
        self._rebuild()
        await interaction.response.edit_message(embed=self._form_embed(), view=self)

    async def _on_search(self, interaction: discord.Interaction) -> None:
        results, capped = _search(
            self._selected_schools, "", self._selected_hub, self._hub_mode
        )

        query_parts: list[str] = []
        if self._selected_schools:
            query_parts.append(f"schools: {', '.join(self._selected_schools)}")
        if self._selected_hub:
            mode_word = "any of" if self._hub_mode == "any" else "all of"
            query_parts.append(f"HUB ({mode_word}): {', '.join(self._selected_hub)}")
        query_summary = " | ".join(query_parts) if query_parts else "all courses"

        if not results:
            embed = discord.Embed(
                title="No Results Found",
                description="No courses matched your filters. Try broadening your search.",
                color=discord.Color.red(),
            )
            await interaction.response.edit_message(embed=embed, view=_BackView(self))
            return

        results_view = ResultsView(results, query_summary, capped=capped)
        await interaction.response.edit_message(
            embed=results_view._results_embed(), view=results_view
        )


# ─── Cog ──────────────────────────────────────────────────────────────────────

class SearchCog(commands.Cog, name="Search", description="Search BU courses by school, department, or HUB units."):
    def __init__(self, bot: TerrierBot) -> None:
        self.bot = bot
        _load_courses()   # pre-load CSV at startup
        print("Search Cog Ready")

    @app_commands.command(name="search", description="Search BU courses by school, department, or HUB units")
    async def search_slash(self, interaction: discord.Interaction) -> None:
        """Opens an interactive search form (only you can see it)."""
        view = SearchView()
        await interaction.response.send_message(embed=view._form_embed(), view=view, ephemeral=True)

    @commands.command(
        name="search",
        help=(
            "Search BU courses interactively, or pass filters directly.\n"
            "Usage:\n"
            "  =search                        — opens interactive form\n"
            "  =search CAS CS                 — all CAS CS courses\n"
            "  =search ENG --hub CRT RIL      — ENG courses with CRT or RIL\n"
            "  =search CAS --hub CRT --all    — CAS courses with BOTH CRT\n"
            "  =search CAS COM --hub ETR WIN  — CAS or COM with ETR or WIN\n\n"
            "School codes: CAS CFA CGS COM ENG KHC LAW MET QST SAR SHA SPH SSW STH WED\n"
            "HUB codes: PLM AEX HCO SI1 SI2 SO1 SO2 QR1 QR2 IIC GCI ETR WIN OSC DME CRT RIL TWC CRI"
        ),
    )
    async def search_cmd(self, ctx: Context, *, args: str = "") -> None:
        if not args.strip():
            view = SearchView()
            await ctx.reply(embed=view._form_embed(), view=view)
            return

        tokens = args.upper().split()
        schools: list[str] = []
        dept: str = ""
        hub_units: list[str] = []
        hub_mode: str = "any"

        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok == "--HUB":
                i += 1
                while i < len(tokens) and not tokens[i].startswith("--"):
                    if tokens[i] in HUB_COLS:
                        hub_units.append(tokens[i])
                    i += 1
            elif tok == "--ALL":
                hub_mode = "all"
                i += 1
            elif tok in SCHOOL_LABELS:
                schools.append(tok)
                i += 1
            elif re.match(r"^[A-Z]{2,4}$", tok):
                # HUB codes are 2–3 uppercase letters and are in HUB_COLS;
                # anything else that looks like 2–4 letters is treated as a dept code.
                if tok in HUB_COLS:
                    hub_units.append(tok)
                elif not dept:
                    dept = tok
                i += 1
            else:
                i += 1

        results, capped = _search(schools, dept, hub_units, hub_mode)

        if not results:
            await ctx.reply("No courses found with those filters. Try `=search` for the interactive form.")
            return

        query_parts: list[str] = []
        if schools:
            query_parts.append(f"schools: {', '.join(schools)}")
        if dept:
            query_parts.append(f"dept: {dept}")
        if hub_units:
            mode_word = "any of" if hub_mode == "any" else "all of"
            query_parts.append(f"HUB ({mode_word}): {', '.join(hub_units)}")
        query_summary = " | ".join(query_parts) if query_parts else "all courses"

        view = ResultsView(results, query_summary, capped=capped)
        await ctx.reply(embed=view._results_embed(), view=view)


async def setup(bot: TerrierBot) -> None:
    await bot.add_cog(SearchCog(bot))
