from __future__ import annotations

from difflib import SequenceMatcher
import re

import aiohttp
import discord
from discord.ext import commands

from bot import TerrierBot, Context

RMP_GRAPHQL_URL = "https://www.ratemyprofessors.com/graphql"
BU_DISPLAY_NAME = "Boston University"


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
        query = """
        query TeacherDetails($id: ID!) {
          node(id: $id) {
            ... on Teacher {
              id
              courseCodes {
                courseName
                courseCount
              }
              ratings(first: 20) {
                edges {
                  node {
                    class
                    date
                  }
                }
              }
            }
          }
        }
        """
        data = await self._graphql(query, {"id": teacher_id})
        node = data.get("data", {}).get("node", {})
        return node if isinstance(node, dict) else {}

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
                clean = name.strip()
                if clean and clean not in classes:
                    classes.append(clean)

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

    @commands.command(name="rmp")
    async def rmp(self, ctx: Context, *, professor_name: str):
        """Look up a Boston University professor on RateMyProfessors.

        Usage: =rmp Firstname Lastname, or =rmp Lastname
        """
        cleaned = " ".join(professor_name.split())
        if not cleaned:
            await ctx.send("Please provide a professor name. Example: =rmp Jane Smith or =rmp Smith")
            return

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
            await ctx.send(f"RMP lookup failed: {type(exc).__name__}: {exc}")
            return

        is_bu_result = len(bu_results) > 0
        results = bu_results if is_bu_result else fallback_results
        results = self._rank_matches(cleaned, results)

        if not results:
            await ctx.send(f"No Boston University professor found for '{cleaned}'.")
            return

        prof = results[0]
        teacher_id = prof.get("id")
        first = prof.get("firstName", "")
        last = prof.get("lastName", "")
        dept = prof.get("department") or "Unknown department"
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

        # Fast path: search results can already include course codes.
        self._add_course_names(classes, prof.get("courseCodes", []))

        if isinstance(teacher_id, str) and teacher_id:
            try:
                detail = await self._get_teacher_detail(teacher_id)

                self._add_course_names(classes, detail.get("courseCodes", []))

                edges = detail.get("ratings", {}).get("edges", [])
                if isinstance(edges, list):
                    for edge in edges:
                        node = edge.get("node", {}) if isinstance(edge, dict) else {}
                        reviewed_class = node.get("class") if isinstance(node, dict) else None
                        if isinstance(reviewed_class, str):
                            clean = reviewed_class.strip()
                            if clean and clean not in classes:
                                classes.append(clean)
            except Exception:
                # Keep the command resilient; class details are extra context.
                pass

        classes_text = ", ".join(classes[:10]) if classes else "N/A"

        embed = discord.Embed(
            title=f"{first} {last}".strip() or cleaned,
            description=(
                f"RateMyProfessors result for {BU_DISPLAY_NAME}"
                if is_bu_result
                else f"No BU match found. Closest RateMyProfessors result for '{cleaned}' (might not be BU)."
            ),
            color=discord.Color.red(),
        )
        embed.add_field(name="Department", value=dept, inline=True)
        embed.add_field(name="Rating", value=rating_text, inline=True)
        embed.add_field(name="Difficulty", value=difficulty_text, inline=True)
        embed.add_field(name="# Ratings", value=count_text, inline=True)
        embed.add_field(name="Would Take Again", value=take_again_text, inline=True)
        embed.add_field(name="Reviewed Classes", value=classes_text, inline=False)

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

        await ctx.send(embed=embed)
