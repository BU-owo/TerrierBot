from __future__ import annotations

import html
import re

import aiohttp
import discord
from discord.ext import commands

from bot import TerrierBot, Context


def _code_range(prefix: str, start: str, end: str) -> list[str]:
    return [f"{prefix}{chr(c)}" for c in range(ord(start), ord(end) + 1)]


SCHOOL_TO_SUBJECTS: dict[str, set[str]] = {
    "CAS": {
        "AA", "AH", "AI", "AM", "AN", "AR", "AS", "BB", "BI", "CC", "CG", "CH", "CI", "CL",
        "CS", "EC", "EE", "EI", "EN", "FY", "HI", "HU", "ID", "IN", "IP", "IR", "JS", "MA",
        "ME", "MR", "MS", "MU", "NE", "NS", "PH", "PO", "PS", "PY", "RN", "RO", "SO", "SS",
        "SY", "TL", "WR", "WS", "XL",
        *_code_range("L", "A", "Z"),
    },
    "CDS": {"BF", "DS", "DX"},
    "CFA": {"AR", "FA", "ME", "ML", "MP", "MT", "MU", "TH"},
    "CGS": {"HU", "MA", "NS", "RH", "SS"},
    "COM": {"CI", "CM", "CO", "EM", "FT", "JO"},
    "ENG": {"BE", "BF", "EC", "EK", "ME", "MS", "SE"},
    "GMS": {"AN", "BC", "BI", "BN", "BT", "BY", "CI", "FA", "FC", "FS", "GC", "GE", "HS", "IM", "MA", "MD", "MH", "MI", "MM", "MS", "NU", "OB", "OH", "PA", "PH", "PM"},
    "HUB": {"CC", "FY", "IC", "RL", "SA", "SJ", "XC"},
    "KHC": set(),
    "LAW": {"AM", "BK", "JD", "TX", "XB"},
    "MED": set(),
    "MET": {"AD", "AH", "AN", "AR", "AT", "BI", "BT", "CH", "CJ", "CM", "CS", "EC", "EN", "ES", "HC", "HI", "HU", "IS", "LD", "LX", "MA", "MG", "ML", "PH", "PO", "PS", "PY", "SO", "UA"},
    "OTP": {"AS", "MS", "NS"},
    "QST": {"AC", "BA", "DS", "ES", "FE", "FI", "HF", "HM", "IM", "IS", "LA", "MF", "MG", "MK", "MO", "MS", "OM", "PL", "QM", "SI", "SM"},
    "SAR": {"HP", "HS", "OT", "PT", "RS", "SH", "SR"},
    "SDM": {"EN", "GD", "MB", "MD", "OB", "OD", "OP", "OR", "OS", "PA", "PD", "PE", "PH", "PR", "RS"},
    "SHA": {"HF", "RE", "SE"},
    "SPH": {"BS", "EH", "EP", "GH", "LW", "MC", "PH", "PM", "SB"},
    "SSW": {"CP", "ET", "FE", "HB", "IS", "KC", "MP", "SR", "WP"},
    "STH": {"DM", "TA", "TC", "TE", "TF", "TH", "TJ", "TM", "TN", "TO", "TR", "TS", "TT", "TX", "TY", "TZ"},
    "SUM": set(),
    "WED": {"AP", "BI", "CE", "CH", "CL", "CT", "DE", "DS", "EC", "ED", "EM", "EN", "HD", "HE", "HR", "IE", "LC", "LR", "LS", "LW", "ME", "PE", "RS", "SC", "SE", "SO", "TL", "WL", "YJ"},
    "XAS": {"NS"},
    "XRG": {"AN", "BC", "BD", "ED", "GC", "HB", "HC", "HD", "HU", "SJ", "TF"},
}

# Canonical school codes users might type.
SCHOOL_ALIASES: dict[str, str] = {
    "QUESTROM": "QST",
    "QST": "QST",
    "OTP": "OTP",
    "ROTC": "OTP",
}

# Slug in https://www.bu.edu/academics/<slug>/courses/<school>-<subject>-<number>/
SCHOOL_SLUG: dict[str, str] = {
    "CAS": "cas",
    "CDS": "cds",
    "CFA": "cfa",
    "CGS": "cgs",
    "COM": "com",
    "ENG": "eng",
    "GMS": "gms",
    "HUB": "hub",
    "KHC": "khc",
    "LAW": "law",
    "MED": "camed",
    "MET": "met",
    "OTP": "rotc",
    "QST": "questrom",
    "SAR": "sar",
    "SDM": "sdm",
    "SHA": "sha",
    "SPH": "sph",
    "SSW": "ssw",
    "STH": "sth",
    "SUM": "summer",
    "WED": "wheelock",
    "XAS": "xas",
    "XRG": "xrg",
}

SUBJECT_TO_SCHOOLS: dict[str, set[str]] = {}
for school, subjects in SCHOOL_TO_SUBJECTS.items():
    for subject in subjects:
        SUBJECT_TO_SCHOOLS.setdefault(subject, set()).add(school)


def _normalize_school(value: str | None) -> str | None:
    if value is None:
        return None
    upper = value.upper()
    return SCHOOL_ALIASES.get(upper, upper)


def _clean_text_fragment(fragment: str) -> str:
    txt = re.sub(r"<[^>]+>", " ", fragment)
    txt = html.unescape(txt)
    txt = re.sub(r"\s+", " ", txt)
    return txt.strip()


def _extract_text(html_doc: str) -> str:
    cleaned = re.sub(r"<script.*?</script>", " ", html_doc, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<style.*?</style>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</(p|div|h1|h2|h3|h4|h5|h6|li|ul|ol|section|article|tr|table)>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\r", "", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n\s*\n+", "\n", cleaned)
    return cleaned.strip()


def _trim_description(text: str) -> str:
    trimmed = re.sub(r"\s+", " ", text).strip()
    stop_patterns = [
        r"\bEffective\s+Fall\b",
        r"\b(?:FALL|SPRG|SUMR|SUMMER)\s+\d{4}\s+Schedule\b",
        r"\bSchedule\s+Section\s+Instructor\s+Location\s+Schedule\s+Notes\b",
        r"\bNote that this information\b",
        r"\bTerms of Use\b",
    ]

    cut_at: int | None = None
    for pattern in stop_patterns:
        m = re.search(pattern, trimmed, flags=re.IGNORECASE)
        if m:
            if cut_at is None or m.start() < cut_at:
                cut_at = m.start()

    if cut_at is not None:
        trimmed = trimmed[:cut_at].strip(" -;,.\n\t")

    return trimmed


def _parse_course_query(raw_query: str) -> tuple[str | None, str, str]:
    upper = raw_query.upper().strip()
    upper = re.sub(r"[^A-Z0-9 ]", " ", upper)
    upper = re.sub(r"\s+", " ", upper).strip()

    if not upper:
        raise ValueError("Please provide a course code. Example: =class CAS EE 100")

    compact = upper.replace(" ", "")

    # CASEE100 / CASEE 100 style.
    m = re.fullmatch(r"([A-Z]{3})([A-Z]{2,3})(\d{3}[A-Z]?)", compact)
    if m:
        return _normalize_school(m.group(1)), m.group(2), m.group(3)

    # EE100 style.
    m = re.fullmatch(r"([A-Z]{2,3})(\d{3}[A-Z]?)", compact)
    if m:
        return None, m.group(1), m.group(2)

    tokens = upper.split(" ")

    # CAS EE 100
    if len(tokens) == 3 and re.fullmatch(r"[A-Z]{3}", tokens[0]) and re.fullmatch(r"[A-Z]{2,3}", tokens[1]) and re.fullmatch(r"\d{3}[A-Z]?", tokens[2]):
        return _normalize_school(tokens[0]), tokens[1], tokens[2]

    # EE 100
    if len(tokens) == 2 and re.fullmatch(r"[A-Z]{2,3}", tokens[0]) and re.fullmatch(r"\d{3}[A-Z]?", tokens[1]):
        return None, tokens[0], tokens[1]

    # CAS EE100
    if len(tokens) == 2 and re.fullmatch(r"[A-Z]{3}", tokens[0]):
        m = re.fullmatch(r"([A-Z]{2,3})(\d{3}[A-Z]?)", tokens[1])
        if m:
            return _normalize_school(tokens[0]), m.group(1), m.group(2)

    # CASEE 100
    if len(tokens) == 2:
        m = re.fullmatch(r"([A-Z]{3})([A-Z]{2,3})", tokens[0])
        if m and re.fullmatch(r"\d{3}[A-Z]?", tokens[1]):
            return _normalize_school(m.group(1)), m.group(2), tokens[1]

    raise ValueError("Couldn't parse course code. Try: =class CAS EE 100, =class CASEE100, or =class EE 100")


def _resolve_school(explicit_school: str | None, subject: str) -> tuple[str, list[str]]:
    subj_schools = sorted(SUBJECT_TO_SCHOOLS.get(subject, set()))

    if explicit_school:
        school = _normalize_school(explicit_school)
        if school is None:
            raise ValueError("Invalid school code.")
        if school not in SCHOOL_SLUG:
            raise ValueError(f"Unsupported school code '{school}'.")
        if subj_schools and school not in subj_schools:
            raise ValueError(f"{school} does not typically use subject code {subject}.")
        return school, []

    if not subj_schools:
        raise ValueError(f"Unknown subject code '{subject}'. Include school code, e.g. =class CAS {subject} 100")

    if len(subj_schools) == 1:
        return subj_schools[0], []

    return subj_schools[0], subj_schools


async def setup(bot: TerrierBot):
    await bot.add_cog(ClassCog(bot))


class ClassCog(commands.Cog, name="Class", description="Lookup BU Bulletin course details."):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot
        print("Class Cog Ready")

    async def _fetch_course_html(self, url: str) -> str | None:
        headers = {
            "User-Agent": "Mozilla/5.0",
        }
        timeout = aiohttp.ClientTimeout(total=30)
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=headers, allow_redirects=True) as resp:
                        if resp.status == 404:
                            return None
                        resp.raise_for_status()
                        return await resp.text()
            except (aiohttp.ServerTimeoutError, TimeoutError) as exc:
                last_exc = exc
                continue
        raise last_exc

    async def lookup_course(self, query: str) -> tuple[discord.Embed | None, str | None]:
        try:
            explicit_school, subject, number = _parse_course_query(query)
            school, ambiguous = _resolve_school(explicit_school, subject)
        except ValueError as exc:
            return None, str(exc)

        if ambiguous:
            return (
                None,
                f"Subject code {subject} exists in multiple schools: {', '.join(ambiguous)}. "
                f"Please include school code, e.g. =class CAS {subject} {number}",
            )

        slug = SCHOOL_SLUG.get(school)
        if slug is None:
            return None, f"I don't have a bulletin path mapping for {school} yet."

        url = f"https://www.bu.edu/academics/{slug}/courses/{school.lower()}-{subject.lower()}-{number.lower()}/"

        try:
            page_html = await self._fetch_course_html(url)
        except Exception as exc:
            return None, f"Bulletin lookup failed: {type(exc).__name__}: {exc}"

        if page_html is None:
            return None, f"Course not found on the BU Bulletin: {school} {subject} {number}\n{url}"

        details = self._parse_course_page(page_html)

        embed = discord.Embed(
            title=details["title"],
            description=details["code"],
            color=discord.Color.purple(),
            url=url,
        )
        embed.add_field(name="Units", value=details["units"], inline=True)
        embed.add_field(name="Prereqs", value=details["prereqs"][:1024], inline=False)
        embed.add_field(name="BU Hub", value=details["hubs"][:1024], inline=False)
        embed.add_field(name="Description", value=details["description"][:1024], inline=False)

        return embed, None

    def _parse_course_page(self, html_doc: str) -> dict[str, str]:
        title = ""
        code = ""

        # Prefer a tight h1->h2 course block match.
        paired = re.search(
            r"<h1[^>]*>\s*(?!<a\b)(.*?)\s*</h1>\s*<h2[^>]*>([A-Z]{3}\s+[A-Z]{2,3}\s+\d{3}[A-Z]?)</h2>",
            html_doc,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if paired:
            title = _clean_text_fragment(paired.group(1))
            code = _clean_text_fragment(paired.group(2)).upper()

        text = _extract_text(html_doc)

        if not title:
            # Fallback: first line that is not the site title.
            for line in text.split("\n"):
                s = line.strip()
                if (
                    s
                    and s.lower() != "boston university academics"
                    and "admissions" not in s.lower()
                    and "schools & colleges" not in s.lower()
                    and "search academics" not in s.lower()
                    and "home" != s.lower()
                    and len(s) > 4
                ):
                    title = s
                    break

        if not code:
            m = re.search(r"\b([A-Z]{3}\s+[A-Z]{2,3}\s+\d{3}[A-Z]?)\b", text)
            if m:
                code = m.group(1).upper()

        units = "N/A"
        m = re.search(r"\bUnits:\s*([0-9]+(?:\.[0-9]+)?)\b", text, flags=re.IGNORECASE)
        if m:
            units = m.group(1)

        prereqs = "None listed"
        description = "Description unavailable"

        prereq_match = re.search(
            r"((?:Undergraduate|Graduate)\s+Prerequisites?:\s*.+?)(?=\n[A-Z]{3,4}\s+\d{4}\s+Schedule|\nNote that this information|$)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if prereq_match:
            prereq_block = re.sub(r"\s+", " ", prereq_match.group(1)).strip()
            split = prereq_block.split(" - ", 1)
            prereqs = split[0]
            if len(split) > 1 and split[1].strip():
                description = _trim_description(split[1]) or "Description unavailable"

        if description == "Description unavailable":
            desc_match = re.search(
                r"\bUnits:\s*[0-9]+(?:\.[0-9]+)?\b\s*(.+?)(?=\n[A-Z]{3,4}\s+\d{4}\s+Schedule|\nNote that this information|$)",
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if desc_match:
                block = re.sub(r"\s+", " ", desc_match.group(1)).strip()
                # Remove prereq prefix if present.
                block = re.sub(r"^(?:Undergraduate|Graduate)\s+Prerequisites?:\s*[^-]+-\s*", "", block, flags=re.IGNORECASE)
                if block:
                    description = _trim_description(block) or "Description unavailable"

        hub_areas: list[str] = []
        for match in re.finditer(r"BU Hub areas?:\s*([^\.]+)", text, flags=re.IGNORECASE):
            areas = [a.strip() for a in match.group(1).split(",")]
            hub_areas = [a for a in areas if a]

        if not hub_areas:
            # Secondary pattern for pages that phrase this differently.
            alt = re.search(r"fulfills .*? BU Hub .*?:\s*([^\.]+)", text, flags=re.IGNORECASE)
            if alt:
                areas = [a.strip() for a in alt.group(1).split(",")]
                hub_areas = [a for a in areas if a]

        hubs = ", ".join(hub_areas) if hub_areas else "None listed"

        return {
            "title": title or "Unknown course",
            "code": code or "Unknown code",
            "units": units,
            "prereqs": prereqs,
            "description": description,
            "hubs": hubs,
        }

    @commands.command(name="class")
    async def class_(self, ctx: Context, *, query: str):
        """Lookup a BU course from the Bulletin.

        Examples:
        =class CASEE100
        =class CAS EE 100
        =class EE 100
        """
        embed, error = await self.lookup_course(query)
        if error:
            await ctx.send(error)
            return
        if embed is None:
            await ctx.send("Unknown class lookup error.")
            return

        await ctx.send(embed=embed)
