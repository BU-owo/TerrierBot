from __future__ import annotations

import csv
import html
import re
from pathlib import Path

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from bot import TerrierBot, Context


# ---------------------------------------------------------------------------
# Fall 2026 schedule  (loaded once at import from the CSV pulled 2026-05-27)
# ---------------------------------------------------------------------------

_FALL_TERM = "2268"
_CSV_PATH  = Path("Fall2026Courses.csv")

# { (subject_area, catalog_nbr) : [raw CSV rows] }
_fall_schedule: dict[tuple[str, str], list[dict[str, str]]] = {}


def _load_fall_schedule() -> None:
    if not _CSV_PATH.exists():
        return
    try:
        with open(_CSV_PATH, newline="", encoding="utf-8-sig", errors="replace") as f:
            for row in csv.DictReader(f):
                if row.get("Term", "").strip() != _FALL_TERM:
                    continue
                key = (
                    row.get("Subject Area", "").strip().upper(),
                    row.get("Catalog Nbr",  "").strip(),
                )
                _fall_schedule.setdefault(key, []).append(row)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Could not load fall schedule CSV: %s", exc)


_load_fall_schedule()


def _get_fall_rows(school: str, subject: str, number: str) -> list[dict[str, str]]:
    return _fall_schedule.get((f"{school}{subject}".upper(), number), [])


_DAY_SHORT: dict[str, str] = {
    "Monday": "M",  "Tuesday": "Tu", "Wednesday": "W",
    "Thursday": "Th", "Friday": "F",  "Saturday": "Sa", "Sunday": "Su",
    "Mon": "M",     "Tue": "Tu",      "Wed": "W",
    "Thu": "Th",    "Fri": "F",       "Sat": "Sa",      "Sun": "Su",
}


def _short_days(days: str) -> str:
    """'Mon Wed Fri'  →  'MWF'"""
    return "".join(_DAY_SHORT.get(d, d) for d in days.split())


def _fmt_t(t: str) -> str:
    """'01:25PM' → '1:25PM',  '10:10AM' → '10:10AM'"""
    return t.lstrip("0") or t


def _build_sections(rows: list[dict[str, str]]) -> list[dict]:
    """
    Aggregate raw CSV rows into a list of section dicts, deduplicating
    instructors and real meeting times (skips NO ROOM entries).
    Returned list is sorted: Enrollment sections first, then alphabetically.
    """
    groups: dict[str, dict] = {}
    for row in rows:
        sec = row.get("Class Section", "").strip()
        if not sec:
            continue
        if sec not in groups:
            groups[sec] = {
                "section":     sec,
                "class_type":  row.get("Class Type", "Enrollment").strip(),
                "enrl_stat":   row.get("Enrl Stat",  "").strip(),
                "cap":         row.get("Cap Enrl",   "0").strip(),
                "enrolled":    row.get("Tot Enrl",   "0").strip(),
                "mode":        row.get("Mode",       "").strip(),
                "instructors": [],
                "meetings":    [],
            }
        g = groups[sec]
        last  = row.get("Instructor's Last Name",  "").strip()
        first = row.get("Instructor's First Name", "").strip()
        if last:
            name = f"{first} {last}".strip()
            if name not in g["instructors"]:
                g["instructors"].append(name)
        days  = row.get("Days Of The Week", "").strip()
        start = row.get("Start Time",       "").strip()
        end   = row.get("End Time",         "").strip()
        loc   = row.get("Facil ID",         "").strip()
        if days and start and loc.upper() != "NO ROOM":
            mtg = (days, start, end, loc)
            if mtg not in g["meetings"]:
                g["meetings"].append(mtg)
    return sorted(
        groups.values(),
        key=lambda g: (g["class_type"] != "Enrollment", g["section"]),
    )


def _fmt_section(g: dict, *, short: bool = False) -> str:
    """
    Format one section dict as 2 lines:
      **A1** · Open · 108/130
      MWF 2:30–3:20PM · SCI 113 · T. Januario
    If short=True, condense to a single line (for compact overflow notes).
    """
    try:
        seats = f"{int(g['enrolled'])}/{int(g['cap'])}"
    except ValueError:
        seats = ""
    stat   = g["enrl_stat"] or "?"
    mode   = g["mode"]
    header = f"**{g['section']}** · {stat}" + (f" · {seats}" if seats else "")
    if mode and mode.lower() not in ("in-person", ""):
        header += f" · {mode}"

    if g["meetings"]:
        days, start, end, loc = g["meetings"][0]
        time  = f"{_fmt_t(start)}–{_fmt_t(end)}" if end else _fmt_t(start)
        sched = f"{_short_days(days)} {time}" + (f" · {loc}" if loc else "")
    else:
        sched = "TBA"

    if g["instructors"]:
        instr = ", ".join(
            f"{n.split()[0][0]}. {n.split()[-1]}" if " " in n else n
            for n in g["instructors"]
        )
        sched += f" · {instr}"

    return f"{header} · {sched}" if short else f"{header}\n{sched}"


def _fall_field_and_instructors(
    school: str, subject: str, number: str
) -> tuple[str, list[str]]:
    """
    Build the embed field value for Fall 2026 and collect unique instructor names.
    Returns ('_Not offered Fall 2026._', []) when the course isn't in the schedule.
    """
    rows = _get_fall_rows(school, subject, number)
    if not rows:
        return "_Not offered Fall 2026._", []

    sections   = _build_sections(rows)
    enrollment = [s for s in sections if s["class_type"] == "Enrollment"]
    non_enroll = [s for s in sections if s["class_type"] != "Enrollment"]
    all_instrs: list[str] = []

    parts: list[str] = []
    for g in enrollment[:4]:
        parts.append(_fmt_section(g))
        for name in g["instructors"]:
            if name not in all_instrs:
                all_instrs.append(name)

    footer: list[str] = []
    if len(enrollment) > 4:
        footer.append(f"_+{len(enrollment) - 4} more lecture section(s) — use 📋 All Sections_")
    if non_enroll:
        footer.append(f"_{len(non_enroll)} lab/discussion section(s) — use 📋 All Sections_")
    if footer:
        parts.append("\n".join(footer))

    value = "\n\n".join(parts)
    if len(value) > 1020:
        value = value[:1017] + "…"
    return value, all_instrs


# ---------------------------------------------------------------------------
# Views: All Sections + RMP buttons
# ---------------------------------------------------------------------------

class _AllSectionsButton(discord.ui.Button["RMPView"]):
    def __init__(self, school: str, subject: str, number: str) -> None:
        super().__init__(label="All Sections", style=discord.ButtonStyle.gray, emoji="📋")
        self.school  = school
        self.subject = subject
        self.number  = number

    async def callback(self, interaction: discord.Interaction) -> None:
        rows     = _get_fall_rows(self.school, self.subject, self.number)
        sections = _build_sections(rows)
        enroll   = [s for s in sections if s["class_type"] == "Enrollment"]
        labs     = [s for s in sections if s["class_type"] != "Enrollment"]

        embed = discord.Embed(
            title=f"Fall 2026 — {self.school} {self.subject} {self.number}",
            color=discord.Color.purple(),
        )

        def _field_text(group: list[dict]) -> str:
            return "\n\n".join(_fmt_section(g) for g in group)

        if enroll:
            embed.add_field(
                name=f"Lectures ({len(enroll)})",
                value=_field_text(enroll)[:1024],
                inline=False,
            )
        if labs:
            embed.add_field(
                name=f"Labs / Discussions ({len(labs)})",
                value=_field_text(labs)[:1024],
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)


class _RMPButton(discord.ui.Button["RMPView"]):
    def __init__(self, label: str, instructor_name: str) -> None:
        super().__init__(label=label, style=discord.ButtonStyle.blurple, emoji="🎓")
        self.instructor_name = instructor_name

    async def callback(self, interaction: discord.Interaction) -> None:
        rmp_cog = interaction.client.get_cog("RMP")
        if rmp_cog is None or not hasattr(rmp_cog, "_build_rmp_response"):
            await interaction.response.send_message("RMP cog is not loaded.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        embed, view, error = await rmp_cog._build_rmp_response(self.instructor_name)
        if error:
            await interaction.followup.send(error, ephemeral=True)
        elif embed:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.followup.send("No RMP data found.", ephemeral=True)


class RMPView(discord.ui.View):
    """📋 All Sections button + 🎓 RMP button per instructor (max 4)."""
    def __init__(self, school: str, subject: str, number: str, instructors: list[str]) -> None:
        super().__init__(timeout=300)
        self.add_item(_AllSectionsButton(school, subject, number))
        seen: set[str] = set()
        for name in instructors[:4]:
            parts = name.split()
            label = f"RMP: {parts[-1]}" if parts else f"RMP: {name}"
            if label in seen:
                label = f"RMP: {name[:18]}"
            seen.add(label)
            self.add_item(_RMPButton(label=label, instructor_name=name))


# ---------------------------------------------------------------------------


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
        r"\bEffective\s+(?:Fall|Spring|Summer|Sprg|Sumr|Autumn)\b",
        r"\bthis\s+course\s+fulfills\b",
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
        raise ValueError("Please provide a course code. Example: =class CAS CH 101")

    compact = upper.replace(" ", "")

    # CASCH101 / CASCH 101 style.
    m = re.fullmatch(r"([A-Z]{3})([A-Z]{2,3})(\d{3}[A-Z]?)", compact)
    if m:
        return _normalize_school(m.group(1)), m.group(2), m.group(3)

    # CH101 style.
    m = re.fullmatch(r"([A-Z]{2,3})(\d{3}[A-Z]?)", compact)
    if m:
        return None, m.group(1), m.group(2)

    tokens = upper.split(" ")

    # CAS CH 101
    if len(tokens) == 3 and re.fullmatch(r"[A-Z]{3}", tokens[0]) and re.fullmatch(r"[A-Z]{2,3}", tokens[1]) and re.fullmatch(r"\d{3}[A-Z]?", tokens[2]):
        return _normalize_school(tokens[0]), tokens[1], tokens[2]

    # EE 100
    if len(tokens) == 2 and re.fullmatch(r"[A-Z]{2,3}", tokens[0]) and re.fullmatch(r"\d{3}[A-Z]?", tokens[1]):
        return None, tokens[0], tokens[1]

    # CAS CH101
    if len(tokens) == 2 and re.fullmatch(r"[A-Z]{3}", tokens[0]):
        m = re.fullmatch(r"([A-Z]{2,3})(\d{3}[A-Z]?)", tokens[1])
        if m:
            return _normalize_school(tokens[0]), m.group(1), m.group(2)

    # CASEE 100
    if len(tokens) == 2:
        m = re.fullmatch(r"([A-Z]{3})([A-Z]{2,3})", tokens[0])
        if m and re.fullmatch(r"\d{3}[A-Z]?", tokens[1]):
            return _normalize_school(m.group(1)), m.group(2), tokens[1]

    raise ValueError("Couldn't parse course code. Try: =class CAS CH 101, =class CASCH101, or =class CH 101")


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

    # Multiple schools: prefer CAS, then any non-MET school, then first alphabetically.
    if "CAS" in subj_schools:
        return "CAS", []
    non_met = [s for s in subj_schools if s != "MET"]
    return (non_met[0] if non_met else subj_schools[0]), []


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

    async def lookup_course(self, query: str) -> tuple[discord.Embed | None, discord.ui.View | None, str | None]:
        try:
            explicit_school, subject, number = _parse_course_query(query)
            school, ambiguous = _resolve_school(explicit_school, subject)
        except ValueError as exc:
            return None, None, str(exc)

        if ambiguous:
            return (
                None,
                None,
                f"Subject code {subject} exists in multiple schools: {', '.join(ambiguous)}. "
                f"Please include school code, e.g. =class CAS {subject} {number}",
            )

        slug = SCHOOL_SLUG.get(school)
        if slug is None:
            return None, None, f"I don't have a bulletin path mapping for {school} yet."

        url = f"https://www.bu.edu/academics/{slug}/courses/{school.lower()}-{subject.lower()}-{number.lower()}/"

        try:
            page_html = await self._fetch_course_html(url)
        except Exception as exc:
            return None, None, f"Bulletin lookup failed: {type(exc).__name__}: {exc}"

        if page_html is None:
            return None, None, f"Course not found on the BU Bulletin: {school} {subject} {number}\n{url}"

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

        fall_value, instructors = _fall_field_and_instructors(school, subject, number)
        embed.add_field(name="📅 Fall 2026", value=fall_value, inline=False)
        view: discord.ui.View | None = (
            RMPView(school, subject, number, instructors)
            if _get_fall_rows(school, subject, number)
            else None
        )

        return embed, view, None

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
        =class CASCH101
        =class CAS CH 101
        =class EE 100
        """
        embed, view, error = await self.lookup_course(query)
        if error:
            await ctx.send(error)
            return
        if embed is None:
            await ctx.send("Unknown class lookup error.")
            return

        if view is not None:
            await ctx.send(embed=embed, view=view)
        else:
            await ctx.send(embed=embed)

    @app_commands.command(name="class", description="Look up a BU course from the Bulletin.")
    @app_commands.describe(query="Course code (e.g. CAS CH 101, CASCH101, or CH 101)")
    async def class_slash(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        embed, view, error = await self.lookup_course(query)
        if error:
            await interaction.followup.send(error)
            return
        if embed is None:
            await interaction.followup.send("Unknown class lookup error.")
            return
        if view is not None:
            await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.followup.send(embed=embed)
