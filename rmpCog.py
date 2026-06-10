from __future__ import annotations

from difflib import SequenceMatcher
import re

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from bot import TerrierBot, Context
from classCog import _parse_course_query

RMP_GRAPHQL_URL = "https://www.ratemyprofessors.com/graphql"
BU_DISPLAY_NAME = "Boston University"
RMP_CHANNEL_ID = 1404891150871040050
RMP_WARNING_EMOJI = "<:terrierbot:1472754408440860984>"

DEPARTMENT_DEFAULT_SCHOOL: dict[str, str] = {
    "biology": "CAS",
    "chemistry": "CAS",
    "chemistry and biochemistry": "CAS",
    "computer science": "CAS",
    "economics": "CAS",
    "english": "CAS",
    "history": "CAS",
    "mathematics": "CAS",
    "math": "CAS",
    "philosophy": "CAS",
    "physics": "CAS",
    "political science": "CAS",
    "psychology": "CAS",
}


class ClassLookupView(discord.ui.View):
    def __init__(self, bot: TerrierBot, classes: list[str], preferred_school: str | None = None):
        super().__init__(timeout=180)
        self.bot = bot
        self.preferred_school = preferred_school

        if len(classes) > 6:
            self.add_item(ClassLookupSelect(classes[:25]))
        else:
            for cls in classes[:6]:
                self.add_item(ClassLookupButton(cls))

    async def send_lookup(self, interaction: discord.Interaction, class_code: str) -> None:
        class_cog = self.bot.get_cog("Class")
        if class_cog is None or not hasattr(class_cog, "lookup_course"):
            await interaction.response.send_message("Class lookup cog is not loaded.", ephemeral=True)
            return

        query = class_code
        if self.preferred_school and re.fullmatch(r"[A-Z]{2,3}\s+[0-9]{3}[A-Z]?", class_code):
            query = f"{self.preferred_school} {class_code}"

        await interaction.response.defer(thinking=True)
        embed, _view, error = await class_cog.lookup_course(query)
        if error:
            await interaction.followup.send(error, ephemeral=True)
            return
        if embed is None:
            await interaction.followup.send("Unknown class lookup error.", ephemeral=True)
            return

        await interaction.followup.send(embed=embed, ephemeral=True)


class ClassLookupSelect(discord.ui.Select):
    def __init__(self, classes: list[str]):
        options = [discord.SelectOption(label=cls, value=cls) for cls in classes]
        super().__init__(placeholder="Pick a class to open its BU Bulletin page", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.view is None or not isinstance(self.view, ClassLookupView):
            await interaction.response.send_message("This menu is no longer active.", ephemeral=True)
            return

        await self.view.send_lookup(interaction, self.values[0])


class ClassLookupButton(discord.ui.Button[ClassLookupView]):
    def __init__(self, class_code: str):
        super().__init__(label=class_code, style=discord.ButtonStyle.secondary)
        self.class_code = class_code

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.view is None:
            await interaction.response.send_message("This button is no longer active.", ephemeral=True)
            return

        await self.view.send_lookup(interaction, self.class_code)


async def setup(bot: TerrierBot):
    await bot.add_cog(RMPCog(bot))


class RMPCog(commands.Cog, name="RMP", description="RateMyProfessors lookup for Boston University."):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot
        self._bu_school_id: str | None = None
        print("RMP Cog Ready")

    async def _graphql(self, query: str, variables: dict[str, object]) -> dict:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
            "Origin": "https://www.ratemyprofessors.com",
            "Referer": "https://www.ratemyprofessors.com/",
        }
        payload = {"query": query, "variables": variables}

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(RMP_GRAPHQL_URL, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                data = await resp.json()
                if "errors" in data:
                    raise RuntimeError(str(data["errors"]))
                return data

    async def _get_bu_school_id(self) -> str:
        if self._bu_school_id is not None:
            return self._bu_school_id

        query = """
        query NewSearchSchools($query: SchoolSearchQuery!) {
          newSearch {
            schools(query: $query) {
              edges {
                node {
                  id
                  name
                  city
                  state
                }
              }
            }
          }
        }
        """

        variables = {"query": {"text": BU_DISPLAY_NAME}}
        data = await self._graphql(query, variables)
        edges = data.get("data", {}).get("newSearch", {}).get("schools", {}).get("edges", [])

        for edge in edges:
            node = edge.get("node", {})
            if node.get("name") == BU_DISPLAY_NAME:
                self._bu_school_id = node.get("id")
                if self._bu_school_id:
                    return self._bu_school_id

        if edges:
            fallback_id = edges[0].get("node", {}).get("id")
            if fallback_id:
                self._bu_school_id = fallback_id
                return fallback_id

        raise RuntimeError("Could not resolve Boston University school ID on RateMyProfessors")

    async def _search_professors(self, full_name: str, school_id: str | None, fallback: bool) -> list[dict]:
        query = """
        query NewSearchTeachers($query: TeacherSearchQuery!) {
          newSearch {
            teachers(query: $query) {
              edges {
                node {
                  id
                  legacyId
                  firstName
                  lastName
                  department
                                    courseCodes {
                                        courseName
                                        courseCount
                                    }
                  avgRating
                  avgDifficulty
                  numRatings
                  wouldTakeAgainPercent
                }
              }
            }
          }
        }
        """

        query_vars: dict[str, object] = {
            "text": full_name,
            "fallback": fallback,
        }
        if school_id is not None:
            query_vars["schoolID"] = school_id

        variables = {"query": query_vars}
        data = await self._graphql(query, variables)
        edges = data.get("data", {}).get("newSearch", {}).get("teachers", {}).get("edges", [])
        return [edge.get("node", {}) for edge in edges if edge.get("node")]

    async def _get_teacher_detail(self, teacher_id: str) -> dict:
        rich_query = """
        query TeacherDetails($id: ID!, $after: String) {
                    node(id: $id) {
                        ... on Teacher {
                            id
                            courseCodes {
                                courseName
                                courseCount
                            }
                            ratings(first: 100, after: $after) {
                                edges {
                                    node {
                                        class
                                        date
                                        helpfulRatingRounded
                                        difficultyRatingRounded
                                        qualityRating
                                    }
                                }
                                pageInfo {
                                    hasNextPage
                                    endCursor
                                }
                            }
                        }
                    }
                }
                """

        fallback_query = """
        query TeacherDetails($id: ID!, $after: String) {
                    node(id: $id) {
                        ... on Teacher {
                            id
                            courseCodes {
                                courseName
                                courseCount
                            }
                            ratings(first: 100, after: $after) {
                                edges {
                                    node {
                                        class
                                        date
                                    }
                                }
                                pageInfo {
                                    hasNextPage
                                    endCursor
                                }
                            }
                        }
                    }
                }
                """

        try:
            cursor: str | None = None
            merged_node: dict = {}
            merged_edges: list[dict] = []

            while True:
                data = await self._graphql(rich_query, {"id": teacher_id, "after": cursor})
                node = data.get("data", {}).get("node", {})
                if not isinstance(node, dict):
                    break

                if not merged_node:
                    merged_node = node
                else:
                    for key in ("courseCodes", "id"):
                        if key in node and key not in merged_node:
                            merged_node[key] = node[key]

                ratings = node.get("ratings", {})
                edges = ratings.get("edges", []) if isinstance(ratings, dict) else []
                if isinstance(edges, list):
                    merged_edges.extend(edge for edge in edges if isinstance(edge, dict))

                page_info = ratings.get("pageInfo", {}) if isinstance(ratings, dict) else {}
                has_next_page = bool(page_info.get("hasNextPage")) if isinstance(page_info, dict) else False
                cursor = page_info.get("endCursor") if isinstance(page_info, dict) else None
                if not has_next_page or not cursor:
                    break

            if merged_node:
                merged_node["ratings"] = {"edges": merged_edges}
            return merged_node
        except Exception:
            try:
                data = await self._graphql(fallback_query, {"id": teacher_id, "after": None})
            except Exception:
                return {}

            node = data.get("data", {}).get("node", {})
            return node if isinstance(node, dict) else {}

    def _subject_number_key(self, class_code: str) -> str:
        """Return the 'SUBJECT NUMBER' part of a code, stripping any school prefix.

        e.g. 'CAS PY 211' -> 'PY 211', 'PY 211' -> 'PY 211'
        """
        m = re.match(r"^[A-Z]{3}\s+([A-Z]{2,3}\s+[0-9]{3}[A-Z]?)$", class_code.upper().strip())
        if m:
            return m.group(1)
        return class_code

    def _normalize_class_code(self, raw: str) -> str | None:
        cleaned = " ".join(raw.upper().split())
        if not cleaned:
            return None

        try:
            school, subject, number = _parse_course_query(cleaned)
            if school:
                return f"{school} {subject} {number}"
        except ValueError:
            pass

        m = re.search(r"\b([A-Z]{3})\s*([A-Z]{2,3})\s*([0-9]{3}[A-Z]?)\b", cleaned)
        if m:
            return f"{m.group(1)} {m.group(2)} {m.group(3)}"

        m = re.search(r"\b([A-Z]{2,3})\s*([0-9]{3}[A-Z]?)\b", cleaned)
        if m:
            return f"{m.group(1)} {m.group(2)}"

        return cleaned

    def _preferred_school_for_department(self, department: str | None) -> str | None:
        if not isinstance(department, str):
            return None

        normalized = re.sub(r"\s+", " ", department.strip().lower())
        if not normalized:
            return None

        return DEPARTMENT_DEFAULT_SCHOOL.get(normalized)

    def _add_course_names(self, classes: list[str], course_items: object) -> None:
        if not isinstance(course_items, list):
            return

        for item in course_items:
            if isinstance(item, dict):
                name = item.get("courseName")
            elif isinstance(item, str):
                name = item
            else:
                name = None

            if isinstance(name, str):
                clean = self._normalize_class_code(name) or name.strip()
                if clean and clean not in classes:
                    classes.append(clean)

    def _course_count_map(self, course_items: object) -> dict[str, int]:
        counts: dict[str, int] = {}
        if not isinstance(course_items, list):
            return counts

        for item in course_items:
            if not isinstance(item, dict):
                continue

            raw_name = item.get("courseName")
            if not isinstance(raw_name, str):
                continue

            key = self._normalize_class_code(raw_name)
            if not key:
                continue

            raw_count = item.get("courseCount")
            count = int(raw_count) if isinstance(raw_count, int) else 0
            counts[key] = max(counts.get(key, 0), count)

        return counts

    def _name_tokens(self, text: str) -> list[str]:
        return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]

    def _match_score(self, query_name: str, prof: dict) -> float:
        query_parts = [p.strip().lower() for p in query_name.split() if p.strip()]
        if not query_parts:
            return 0.0

        is_single_token_query = len(query_parts) == 1
        q_first = query_parts[0]
        q_last = query_parts[-1]
        p_first = str(prof.get("firstName", "")).strip().lower()
        p_last = str(prof.get("lastName", "")).strip().lower()
        p_full = f"{p_first} {p_last}".strip()
        q_full = " ".join(query_parts)
        q_given = query_parts[:-1]

        score = 0.0

        # Prioritize last-name fit heavily (especially for single-token searches).
        if p_last == q_last:
            score += 140 if is_single_token_query else 120
        else:
            score += (95 if is_single_token_query else 80) * SequenceMatcher(None, q_last, p_last).ratio()

        # For full-name queries, also compare first-name fit (handles typos like alexia/alexis).
        if not is_single_token_query:
            if p_first == q_first:
                score += 70
            else:
                score += 45 * SequenceMatcher(None, q_first, p_first).ratio()

            # Handle compound/hyphenated names (e.g., "min chang" vs "ming-chang").
            p_first_tokens = self._name_tokens(p_first)
            token_sim = 0.0
            for q_tok in q_given:
                local_best = 0.0
                for p_tok in p_first_tokens:
                    local_best = max(local_best, SequenceMatcher(None, q_tok, p_tok).ratio())
                token_sim += local_best
            if q_given:
                score += 60 * (token_sim / len(q_given))

            # Bonus for exact token overlap in given-name parts.
            overlap = len(set(q_given) & set(p_first_tokens))
            score += 25 * overlap

        # Whole-name tie breaker.
        score += 30 * SequenceMatcher(None, q_full, p_full).ratio()

        # Tiny preference for records with more ratings.
        num_ratings = prof.get("numRatings")
        if isinstance(num_ratings, int):
            score += min(num_ratings, 50) / 50

        return score

    def _rank_matches(self, query_name: str, matches: list[dict]) -> list[dict]:
        return sorted(matches, key=lambda p: self._match_score(query_name, p), reverse=True)

    def _score_emoji(self, value: float | None, *, is_difficulty: bool = False) -> str:
        if not isinstance(value, (int, float)):
            return "⚪"

        score = float(value)
        if is_difficulty:
            if score <= 2.0:
                return "🟢"
            if score <= 3.5:
                return "🟡"
            return "🔴"

        if score >= 4.0:
            return "🟢"
        if score >= 3.0:
            return "🟡"
        return "🔴"

    def _class_sort_key(self, class_code: str) -> tuple[str, int, str]:
        compact = " ".join(class_code.upper().split())
        m = re.match(r"^(?:([A-Z]{2,3})\s+)?([A-Z]{2,3})(\d{3}[A-Z]?)$", compact.replace(" ", ""))
        if m:
            school = m.group(1) or ""
            subject = m.group(2)
            number_part = m.group(3)
        else:
            parts = compact.split()
            school = parts[0] if len(parts) == 3 else ""
            subject = parts[1] if len(parts) == 3 else (parts[0] if parts else compact)
            number_part = parts[2] if len(parts) == 3 else (parts[1] if len(parts) > 1 else "")

        number_match = re.match(r"(\d+)([A-Z]?)", number_part)
        number = int(number_match.group(1)) if number_match else 0
        suffix = number_match.group(2) if number_match else ""
        return (subject, number, f"{school} {suffix}".strip())

    def _embed_color_for_rating(self, value: float | None) -> discord.Color:
        if not isinstance(value, (int, float)):
            return discord.Color.light_grey()

        score = float(value)
        if score >= 4.0:
            return discord.Color.green()
        if score >= 3.0:
            return discord.Color.gold()
        return discord.Color.red()

    def _dedupe_by_id(self, matches: list[dict]) -> list[dict]:
        seen: set[str] = set()
        unique: list[dict] = []
        for prof in matches:
            pid = prof.get("id")
            if not isinstance(pid, str):
                continue
            if pid in seen:
                continue
            seen.add(pid)
            unique.append(prof)
        return unique

    async def _build_rmp_response(
        self, professor_name: str
    ) -> tuple[discord.Embed | None, discord.ui.View | None, str | None]:
        """Core RMP lookup. Returns (embed, view, error_message)."""
        cleaned = " ".join(professor_name.split())
        if not cleaned:
            return None, None, "Please provide a professor name. Example: =rmp Jane Smith or =rmp Smith"

        try:
            school_id = await self._get_bu_school_id()
            # First pass: strict BU-only match.
            bu_results = await self._search_professors(cleaned, school_id=school_id, fallback=False)

            # For multi-part names, widen BU-only candidate pool with targeted variants.
            parts = cleaned.split()
            if len(parts) >= 3:
                first_last = f"{parts[0]} {parts[-1]}"
                bu_results += await self._search_professors(first_last, school_id=school_id, fallback=False)

                hyphen_first_last = f"{'-'.join(parts[:-1])} {parts[-1]}"
                bu_results += await self._search_professors(hyphen_first_last, school_id=school_id, fallback=False)

            bu_results = self._dedupe_by_id(bu_results)

            # Second pass (optional): broader match, explicitly labeled as possibly non-BU.
            fallback_results = await self._search_professors(cleaned, school_id=None, fallback=True)
        except Exception as exc:
            return None, None, f"RMP lookup failed: {type(exc).__name__}: {exc}"

        is_bu_result = len(bu_results) > 0
        results = bu_results if is_bu_result else fallback_results
        results = self._rank_matches(cleaned, results)

        if not results:
            return None, None, f"No Boston University professor found for '{cleaned}'."

        prof = results[0]
        teacher_id = prof.get("id")
        first = prof.get("firstName", "")
        last = prof.get("lastName", "")
        dept = prof.get("department") or "Unknown department"
        preferred_school = self._preferred_school_for_department(dept if isinstance(dept, str) else None)
        rating = prof.get("avgRating")
        difficulty = prof.get("avgDifficulty")
        num_ratings = prof.get("numRatings")
        would_take_again = prof.get("wouldTakeAgainPercent")
        legacy_id = prof.get("legacyId")

        rating_text = f"{rating}/5" if isinstance(rating, (int, float)) else "N/A"
        difficulty_text = f"{difficulty}/5" if isinstance(difficulty, (int, float)) else "N/A"
        count_text = str(num_ratings) if isinstance(num_ratings, int) else "N/A"

        if isinstance(would_take_again, (int, float)):
            take_again_text = f"{would_take_again}%"
        else:
            take_again_text = "N/A"

        classes: list[str] = []
        per_class_helpful: dict[str, list[float]] = {}
        per_class_difficulty: dict[str, list[float]] = {}
        per_class_review_counts: dict[str, int] = {}
        per_class_counts: dict[str, int] = {}

        # Fast path: search results can already include course codes.
        self._add_course_names(classes, prof.get("courseCodes", []))
        per_class_counts.update(self._course_count_map(prof.get("courseCodes", [])))

        if isinstance(teacher_id, str) and teacher_id:
            try:
                detail = await self._get_teacher_detail(teacher_id)

                self._add_course_names(classes, detail.get("courseCodes", []))
                detail_counts = self._course_count_map(detail.get("courseCodes", []))
                for key, value in detail_counts.items():
                    per_class_counts[key] = max(per_class_counts.get(key, 0), value)

                edges = detail.get("ratings", {}).get("edges", [])
                if isinstance(edges, list):
                    for edge in edges:
                        node = edge.get("node", {}) if isinstance(edge, dict) else {}
                        reviewed_class = node.get("class") if isinstance(node, dict) else None
                        if isinstance(reviewed_class, str):
                            clean = self._normalize_class_code(reviewed_class) or reviewed_class.strip()
                            if clean and clean not in classes:
                                classes.append(clean)
                            if clean:
                                per_class_review_counts[clean] = per_class_review_counts.get(clean, 0) + 1

                            helpful = node.get("helpfulRatingRounded") if isinstance(node, dict) else None
                            if not isinstance(helpful, (int, float)):
                                helpful = node.get("qualityRating") if isinstance(node, dict) else None
                            if isinstance(helpful, (int, float)):
                                per_class_helpful.setdefault(clean, []).append(float(helpful))

                            difficulty_val = node.get("difficultyRatingRounded") if isinstance(node, dict) else None
                            if isinstance(difficulty_val, (int, float)):
                                per_class_difficulty.setdefault(clean, []).append(float(difficulty_val))
            except Exception:
                # Keep the command resilient; class details are extra context.
                pass

        # Merge variants like "PY 211" and "CAS PY 211" — same course, different how RMP stored it.
        sn_map: dict[str, str] = {}  # subject_number_key -> canonical code
        for code in classes:
            key = self._subject_number_key(code)
            existing = sn_map.get(key)
            if existing is None:
                sn_map[key] = code
            elif code != existing:
                # Prefer the school-qualified form as the canonical display name.
                canonical = code if re.match(r"^[A-Z]{3}\s+", code) else existing
                other = existing if canonical == code else code
                sn_map[key] = canonical
                per_class_helpful.setdefault(canonical, []).extend(per_class_helpful.pop(other, []))
                per_class_difficulty.setdefault(canonical, []).extend(per_class_difficulty.pop(other, []))
                per_class_review_counts[canonical] = per_class_review_counts.get(canonical, 0) + per_class_review_counts.pop(other, 0)
                per_class_counts[canonical] = max(per_class_counts.get(canonical, 0), per_class_counts.pop(other, 0))
        # Rebuild list with only canonical entries, preserving order.
        classes = list(dict.fromkeys(sn_map[self._subject_number_key(c)] for c in classes))

        ordered_classes = sorted(classes, key=self._class_sort_key)
        classes_text = ", ".join(ordered_classes[:10]) if ordered_classes else "N/A"
        class_lines: list[str] = []
        class_width = max((len(code) for code in ordered_classes), default=0)
        for class_code in ordered_classes:
            helpful_vals = per_class_helpful.get(class_code, [])
            difficulty_vals = per_class_difficulty.get(class_code, [])
            review_count = per_class_review_counts.get(class_code, 0)
            if review_count == 0:
                review_count = per_class_counts.get(class_code, 0)

            if helpful_vals:
                avg_helpful = sum(helpful_vals) / len(helpful_vals)
                helpful_text = f"{self._score_emoji(avg_helpful)} {avg_helpful:.2f}/5"
            elif review_count > 0 and isinstance(rating, (int, float)):
                helpful_text = f"{self._score_emoji(rating)} {float(rating):.2f}/5 (est)"
            else:
                helpful_text = f"{self._score_emoji(None)} N/A"

            if difficulty_vals:
                avg_difficulty = sum(difficulty_vals) / len(difficulty_vals)
                difficulty_text_local = f"{self._score_emoji(avg_difficulty, is_difficulty=True)} {avg_difficulty:.2f}/5"
            elif review_count > 0 and isinstance(difficulty, (int, float)):
                difficulty_text_local = f"{self._score_emoji(difficulty, is_difficulty=True)} {float(difficulty):.2f}/5 (est)"
            else:
                difficulty_text_local = f"{self._score_emoji(None, is_difficulty=True)} N/A"

            class_lines.append(
                f"{class_code}: Rating {helpful_text}, Difficulty {difficulty_text_local}, Reviews {review_count}"
            )

        class_ratings_text = "\n".join(class_lines[:10]) if class_lines else "N/A"

        embed = discord.Embed(
            title=f"{first} {last}".strip() or cleaned,
            description=(
                f"RateMyProfessors result for {BU_DISPLAY_NAME}"
                if is_bu_result
                else f"No BU match found. Closest RateMyProfessors result for '{cleaned}' (might not be BU)."
            ),
            color=self._embed_color_for_rating(rating if isinstance(rating, (int, float)) else None),
        )
        embed.add_field(name="Department", value=dept, inline=True)
        embed.add_field(name="Rating", value=f"{self._score_emoji(rating)} {rating_text}", inline=True)
        embed.add_field(name="Difficulty", value=f"{self._score_emoji(difficulty, is_difficulty=True)} {difficulty_text}", inline=True)
        embed.add_field(name="# Ratings", value=count_text, inline=True)
        embed.add_field(name="Would Take Again", value=take_again_text, inline=True)
        embed.add_field(name="Reviewed Classes", value=classes_text, inline=False)
        embed.add_field(name="Per-Class Ratings", value=class_ratings_text[:1024], inline=False)

        if legacy_id:
            embed.add_field(
                name="Profile",
                value=f"https://www.ratemyprofessors.com/professor/{legacy_id}",
                inline=False,
            )

        if len(results) > 1:
            alternatives = []
            for alt in results[1:4]:
                alt_name = f"{alt.get('firstName', '')} {alt.get('lastName', '')}".strip()
                alt_dept = alt.get("department") or "Unknown"
                if alt_name:
                    alternatives.append(f"- {alt_name} ({alt_dept})")
            if alternatives:
                embed.add_field(
                    name="Other matches" if is_bu_result else "Other possible matches (might not be BU)",
                    value="\n".join(alternatives),
                    inline=False,
                )

        class_buttons = [c for c in classes if re.search(r"\d{3}[A-Z]?$", c)]
        view = ClassLookupView(self.bot, class_buttons, preferred_school=preferred_school) if class_buttons else None
        return embed, view, None

    def _needs_channel_warning(self, channel: discord.abc.GuildChannel | discord.Thread | None) -> bool:
        return channel is None or channel.id != RMP_CHANNEL_ID

    def _channel_warning_text(self, user: discord.abc.User) -> str:
        return (
            f"{user.mention}, you really gotta be doing bot commands in <#{RMP_CHANNEL_ID}> bruh. "
            f"OwO is gonna get mad and blame, me, Terrier Bot {RMP_WARNING_EMOJI}"
        )

    @commands.command(name="rmp")
    async def rmp(self, ctx: Context, *, professor_name: str):
        """Look up a Boston University professor on RateMyProfessors.

        Usage: =rmp Firstname Lastname, or =rmp Lastname
        """
        embed, view, error = await self._build_rmp_response(professor_name)
        if error:
            await ctx.send(error)
            return
        if view:
            await ctx.send(embed=embed, view=view)
        else:
            await ctx.send(embed=embed)

        if self._needs_channel_warning(ctx.channel if isinstance(ctx.channel, (discord.abc.GuildChannel, discord.Thread)) else None):
            await ctx.send(self._channel_warning_text(ctx.author))

    @app_commands.command(name="rmp", description="Look up a BU professor on RateMyProfessors.")
    @app_commands.describe(professor_name="Professor's name (e.g. Jane Smith or Smith)")
    async def rmp_slash(self, interaction: discord.Interaction, professor_name: str):
        await interaction.response.defer()
        embed, view, error = await self._build_rmp_response(professor_name)
        if error:
            await interaction.followup.send(error)
            return
        if view:
            await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.followup.send(embed=embed)

        if self._needs_channel_warning(interaction.channel if isinstance(interaction.channel, (discord.abc.GuildChannel, discord.Thread)) else None):
            await interaction.followup.send(self._channel_warning_text(interaction.user))
