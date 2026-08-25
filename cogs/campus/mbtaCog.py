from __future__ import annotations

import difflib
from dataclasses import dataclass
from datetime import datetime, timezone

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from bot import Context, TerrierBot

MBTA_PREDICTIONS_URL = "https://api-v3.mbta.com/predictions"
MBTA_SCHEDULES_URL = "https://api-v3.mbta.com/schedules"
MBTA_ALERTS_URL = "https://api-v3.mbta.com/alerts"

# MBTA direction_id convention for the Green Line (all branches share it):
# 0 = outbound (westbound/southbound away from downtown)
# 1 = inbound (eastbound toward downtown)
DIR_WESTBOUND = 0
DIR_EASTBOUND = 1

# Requested BU Green Line B stops in user-specified order. Used for the
# default (no-argument) =mbta / /mbta view.
BU_GREEN_B_STOPS: list[tuple[str, str]] = [
    ("Babcock Street", "place-babck"),
    ("Amory Street", "place-amory"),
    ("Boston University Central", "place-bucen"),
    ("Boston University East", "place-buest"),
    ("Blandford Street", "place-bland"),
]


@dataclass(frozen=True)
class GreenLineStop:
    name: str
    stop_id: str
    routes: tuple[str, ...]  # e.g. ("Green-B",) or ("Green-B", "Green-C", "Green-D")


ROUTE_BRANCH_LABEL: dict[str, str] = {
    "Green-B": "B",
    "Green-C": "C",
    "Green-D": "D",
    "Green-E": "E",
}

LINE_DISPLAY_NAME: dict[str, str] = {
    "Green-B": "Green Line B",
    "Green-C": "Green Line C",
    "Green-D": "Green Line D",
    "Green-E": "Green Line E",
}

# Full list of Green Line stations across all branches (B/C/D/E), pulled from
# MBTA's official station directory. Shared/trunk stops list every branch
# that serves them so we can label which line each predicted train is on.
GREEN_LINE_STOPS: list[GreenLineStop] = [
    GreenLineStop("Allston Street", "place-alsgr", ("Green-B",)),
    GreenLineStop("Amory Street", "place-amory", ("Green-B",)),
    GreenLineStop("Arlington", "place-armnl", ("Green-B", "Green-C", "Green-D", "Green-E")),
    GreenLineStop("Babcock Street", "place-babck", ("Green-B",)),
    GreenLineStop("Back of the Hill", "place-bckhl", ("Green-E",)),
    GreenLineStop("Ball Square", "place-balsq", ("Green-E",)),
    GreenLineStop("Beaconsfield", "place-bcnfd", ("Green-D",)),
    GreenLineStop("Blandford Street", "place-bland", ("Green-B",)),
    GreenLineStop("Boston College", "place-lake", ("Green-B",)),
    GreenLineStop("Boston University Central", "place-bucen", ("Green-B",)),
    GreenLineStop("Boston University East", "place-buest", ("Green-B",)),
    GreenLineStop("Boylston", "place-boyls", ("Green-B", "Green-C", "Green-D", "Green-E")),
    GreenLineStop("Brandon Hall", "place-bndhl", ("Green-C",)),
    GreenLineStop("Brigham Circle", "place-brmnl", ("Green-E",)),
    GreenLineStop("Brookline Hills", "place-brkhl", ("Green-D",)),
    GreenLineStop("Brookline Village", "place-bvmnl", ("Green-D",)),
    GreenLineStop("Chestnut Hill", "place-chhil", ("Green-D",)),
    GreenLineStop("Chestnut Hill Avenue", "place-chill", ("Green-B",)),
    GreenLineStop("Chiswick Road", "place-chswk", ("Green-B",)),
    GreenLineStop("Cleveland Circle", "place-clmnl", ("Green-C",)),
    GreenLineStop("Coolidge Corner", "place-cool", ("Green-C",)),
    GreenLineStop("Copley", "place-coecl", ("Green-B", "Green-C", "Green-D", "Green-E")),
    GreenLineStop("Dean Road", "place-denrd", ("Green-C",)),
    GreenLineStop("East Somerville", "place-esomr", ("Green-E",)),
    GreenLineStop("Eliot", "place-eliot", ("Green-D",)),
    GreenLineStop("Englewood Avenue", "place-engav", ("Green-C",)),
    GreenLineStop("Fairbanks Street", "place-fbkst", ("Green-C",)),
    GreenLineStop("Fenway", "place-fenwy", ("Green-D",)),
    GreenLineStop("Fenwood Road", "place-fenwd", ("Green-E",)),
    GreenLineStop("Gilman Square", "place-gilmn", ("Green-E",)),
    GreenLineStop("Government Center", "place-gover", ("Green-B", "Green-C", "Green-D", "Green-E")),
    GreenLineStop("Griggs Street", "place-grigg", ("Green-B",)),
    GreenLineStop("Harvard Avenue", "place-harvd", ("Green-B",)),
    GreenLineStop("Hawes Street", "place-hwsst", ("Green-C",)),
    GreenLineStop("Haymarket", "place-haecl", ("Green-D", "Green-E")),
    GreenLineStop("Heath Street", "place-hsmnl", ("Green-E",)),
    GreenLineStop("Hynes Convention Center", "place-hymnl", ("Green-B", "Green-C", "Green-D")),
    GreenLineStop("Kenmore", "place-kencl", ("Green-B", "Green-C", "Green-D")),
    GreenLineStop("Kent Street", "place-kntst", ("Green-C",)),
    GreenLineStop("Lechmere", "place-lech", ("Green-D", "Green-E")),
    GreenLineStop("Longwood", "place-longw", ("Green-D",)),
    GreenLineStop("Longwood Medical Area", "place-lngmd", ("Green-E",)),
    GreenLineStop("Magoun Square", "place-mgngl", ("Green-E",)),
    GreenLineStop("Medford/Tufts", "place-mdftf", ("Green-E",)),
    GreenLineStop("Mission Park", "place-mispk", ("Green-E",)),
    GreenLineStop("Museum of Fine Arts", "place-mfa", ("Green-E",)),
    GreenLineStop("Newton Centre", "place-newto", ("Green-D",)),
    GreenLineStop("Newton Highlands", "place-newtn", ("Green-D",)),
    GreenLineStop("North Station", "place-north", ("Green-D", "Green-E")),
    GreenLineStop("Northeastern University", "place-nuniv", ("Green-E",)),
    GreenLineStop("Packard's Corner", "place-brico", ("Green-B",)),
    GreenLineStop("Park Street", "place-pktrm", ("Green-B", "Green-C", "Green-D", "Green-E")),
    GreenLineStop("Prudential", "place-prmnl", ("Green-E",)),
    GreenLineStop("Reservoir", "place-rsmnl", ("Green-D",)),
    GreenLineStop("Riverside", "place-river", ("Green-D",)),
    GreenLineStop("Riverway", "place-rvrwy", ("Green-E",)),
    GreenLineStop("Saint Mary's Street", "place-smary", ("Green-C",)),
    GreenLineStop("Saint Paul Street", "place-stpul", ("Green-C",)),
    GreenLineStop("Science Park/West End", "place-spmnl", ("Green-D", "Green-E")),
    GreenLineStop("South Street", "place-sougr", ("Green-B",)),
    GreenLineStop("Summit Avenue", "place-sumav", ("Green-C",)),
    GreenLineStop("Sutherland Road", "place-sthld", ("Green-B",)),
    GreenLineStop("Symphony", "place-symcl", ("Green-E",)),
    GreenLineStop("Tappan Street", "place-tapst", ("Green-C",)),
    GreenLineStop("Union Square", "place-unsqu", ("Green-D",)),
    GreenLineStop("Waban", "place-waban", ("Green-D",)),
    GreenLineStop("Warren Street", "place-wrnst", ("Green-B",)),
    GreenLineStop("Washington Square", "place-bcnwa", ("Green-C",)),
    GreenLineStop("Washington Street", "place-wascm", ("Green-B",)),
    GreenLineStop("Woodland", "place-woodl", ("Green-D",)),
]


def _parse_iso_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _minutes_away_text(prediction_time: datetime, now_utc: datetime) -> str:
    diff_seconds = (prediction_time - now_utc).total_seconds()
    mins = max(0, int(diff_seconds // 60))
    if mins <= 1:
        return "arriving"
    return f"{mins} min"


def _direction_label(direction_id: int) -> str:
    return "Eastbound" if direction_id == DIR_EASTBOUND else "Westbound"


def _line_for_direction(
    direction_id: int,
    eta_text: str,
    *,
    status: str | None = None,
) -> str:
    arrow = "➡️" if direction_id == DIR_EASTBOUND else "⬅️"
    line = f"{arrow} {_direction_label(direction_id)}: {eta_text}"
    if status and status.strip() and status.strip().lower() not in {"on time", "no data"}:
        line += f" · ⚠️ {status.strip()}"
    return line


def _build_parent_map(payload: dict) -> dict[str, str]:
    """Map child/platform stop IDs to their parent station (place-*) ID."""
    parent_by_stop_id: dict[str, str] = {}
    for included in payload.get("included", []):
        if included.get("type") != "stop":
            continue
        child_id = included.get("id")
        if not isinstance(child_id, str):
            continue
        parent_data = included.get("relationships", {}).get("parent_station", {}).get("data")
        parent_id = parent_data.get("id") if isinstance(parent_data, dict) else None
        parent_by_stop_id[child_id] = parent_id if isinstance(parent_id, str) else child_id
    return parent_by_stop_id


async def setup(bot: TerrierBot):
    await bot.add_cog(MBTACog(bot))


class MBTACog(commands.Cog, name="MBTA", description="Live MBTA Green Line ETAs for any Green Line stop."):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot
        print("MBTA Cog Ready")

    # ------------------------------------------------------------------
    # Station lookup helpers
    # ------------------------------------------------------------------

    def _find_station(self, query: str) -> GreenLineStop | list[GreenLineStop] | None:
        """Resolve a free-typed station name to a GreenLineStop.

        Returns a single GreenLineStop on a confident match, a list of
        candidate stops if the query is ambiguous, or None if nothing
        reasonably matches.
        """
        q = query.strip().lower()
        if not q:
            return None

        for stop in GREEN_LINE_STOPS:
            if stop.name.lower() == q:
                return stop

        substring_matches = [s for s in GREEN_LINE_STOPS if q in s.name.lower()]
        if len(substring_matches) == 1:
            return substring_matches[0]
        if len(substring_matches) > 1:
            return substring_matches

        close_names = difflib.get_close_matches(
            q, [s.name.lower() for s in GREEN_LINE_STOPS], n=5, cutoff=0.6
        )
        if close_names:
            matches = [s for s in GREEN_LINE_STOPS if s.name.lower() in close_names]
            if len(matches) == 1:
                return matches[0]
            return matches

        return None

    # ------------------------------------------------------------------
    # MBTA API calls
    # ------------------------------------------------------------------

    async def _fetch_next_eta_by_stop(self) -> dict[str, str]:
        stop_ids = ",".join(stop_id for _, stop_id in BU_GREEN_B_STOPS)
        params = {
            "filter[route]": "Green-B",
            "filter[stop]": stop_ids,
            "sort": "departure_time",
            "page[limit]": "100",
            "include": "stop",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(MBTA_PREDICTIONS_URL, params=params, timeout=15) as resp:
                    if resp.status != 200:
                        return {
                            name: "\n".join(
                                [
                                    _line_for_direction(DIR_EASTBOUND, "API unavailable"),
                                    _line_for_direction(DIR_WESTBOUND, "API unavailable"),
                                ]
                            )
                            for name, _ in BU_GREEN_B_STOPS
                        }
                    payload = await resp.json()
        except (aiohttp.ClientError, TimeoutError):
            return {
                name: "\n".join(
                    [
                        _line_for_direction(DIR_EASTBOUND, "API unavailable"),
                        _line_for_direction(DIR_WESTBOUND, "API unavailable"),
                    ]
                )
                for name, _ in BU_GREEN_B_STOPS
            }

        # MBTA predictions often reference child platform stop IDs. Normalize
        # them to parent station place-* IDs when available.
        parent_by_stop_id = _build_parent_map(payload)

        by_stop: dict[str, list[dict]] = {}
        for item in payload.get("data", []):
            rel = item.get("relationships", {})
            stop_data = rel.get("stop", {}).get("data")
            if not stop_data:
                continue
            stop_id = stop_data.get("id")
            if not isinstance(stop_id, str):
                continue
            normalized_stop_id = parent_by_stop_id.get(stop_id, stop_id)
            by_stop.setdefault(normalized_stop_id, []).append(item)

        now_utc = datetime.now(timezone.utc)
        result: dict[str, str] = {}
        missing_directions: list[tuple[str, str, int]] = []

        for stop_name, stop_id in BU_GREEN_B_STOPS:
            predictions = by_stop.get(stop_id, [])
            best_info_by_direction: dict[int, tuple[datetime, str | None]] = {}

            for prediction in predictions:
                attrs = prediction.get("attributes", {})
                direction_id = attrs.get("direction_id")
                if direction_id not in (DIR_EASTBOUND, DIR_WESTBOUND):
                    continue
                t = _parse_iso_time(attrs.get("departure_time") or attrs.get("arrival_time"))
                if t is None or t < now_utc:
                    continue
                status = attrs.get("status") if isinstance(attrs.get("status"), str) else None
                current_best = best_info_by_direction.get(direction_id)
                if current_best is None or t < current_best[0]:
                    best_info_by_direction[direction_id] = (t, status)

            east_info = best_info_by_direction.get(DIR_EASTBOUND)
            west_info = best_info_by_direction.get(DIR_WESTBOUND)
            east_time = east_info[0] if east_info is not None else None
            west_time = west_info[0] if west_info is not None else None

            if east_time is None:
                missing_directions.append((stop_name, stop_id, DIR_EASTBOUND))
            if west_time is None:
                missing_directions.append((stop_name, stop_id, DIR_WESTBOUND))

            east_text = _minutes_away_text(east_time, now_utc) if east_time is not None else "no live prediction"
            west_text = _minutes_away_text(west_time, now_utc) if west_time is not None else "no live prediction"
            result[stop_name] = "\n".join(
                [
                    _line_for_direction(DIR_EASTBOUND, east_text, status=east_info[1] if east_info else None),
                    _line_for_direction(DIR_WESTBOUND, west_text, status=west_info[1] if west_info else None),
                ]
            )

        if missing_directions:
            schedule_times = await self._fetch_next_schedule_times(missing_directions)
            for stop_name, stop_id, direction_id in missing_directions:
                scheduled_time = schedule_times.get((stop_id, direction_id))
                if scheduled_time is None:
                    continue

                scheduled_text = f"~{_minutes_away_text(scheduled_time, now_utc)} (scheduled)"
                lines = result.get(
                    stop_name,
                    "Eastbound: no live prediction\nWestbound: no live prediction",
                ).split("\n")

                if direction_id == DIR_EASTBOUND:
                    lines[0] = _line_for_direction(DIR_EASTBOUND, scheduled_text)
                else:
                    lines[1] = _line_for_direction(DIR_WESTBOUND, scheduled_text)

                result[stop_name] = "\n".join(lines)

        return result

    async def _fetch_next_schedule_times(
        self,
        missing_directions: list[tuple[str, str, int]],
    ) -> dict[tuple[str, int], datetime]:
        if not missing_directions:
            return {}

        unique_stop_ids = sorted({stop_id for _, stop_id, _ in missing_directions})
        unique_direction_ids = sorted({direction_id for _, _, direction_id in missing_directions})

        params = {
            "filter[route]": "Green-B",
            "filter[stop]": ",".join(unique_stop_ids),
            "filter[direction_id]": ",".join(str(x) for x in unique_direction_ids),
            "sort": "departure_time",
            "page[limit]": "100",
            "include": "stop",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(MBTA_SCHEDULES_URL, params=params, timeout=15) as resp:
                    if resp.status != 200:
                        return {}
                    payload = await resp.json()
        except (aiohttp.ClientError, TimeoutError):
            return {}

        parent_by_stop_id = _build_parent_map(payload)

        best_by_stop_and_direction: dict[tuple[str, int], datetime] = {}
        now_utc = datetime.now(timezone.utc)

        for item in payload.get("data", []):
            stop_data = item.get("relationships", {}).get("stop", {}).get("data")
            if not isinstance(stop_data, dict):
                continue
            stop_id = stop_data.get("id")
            if not isinstance(stop_id, str):
                continue
            normalized_stop_id = parent_by_stop_id.get(stop_id, stop_id)

            attrs = item.get("attributes", {})
            direction_id = attrs.get("direction_id")
            if direction_id not in (DIR_EASTBOUND, DIR_WESTBOUND):
                continue

            t = _parse_iso_time(attrs.get("departure_time") or attrs.get("arrival_time"))
            if t is None or t < now_utc:
                continue

            key = (normalized_stop_id, direction_id)
            current_best = best_by_stop_and_direction.get(key)
            if current_best is None or t < current_best:
                best_by_stop_and_direction[key] = t

        return best_by_stop_and_direction

    async def _fetch_station_predictions(
        self, stop: GreenLineStop
    ) -> tuple[dict[int, list[tuple[datetime, str, str | None]]], bool]:
        """Fetch up to the next 2 upcoming predictions per direction for a
        single Green Line stop, across whichever branches serve it.

        Returns (predictions_by_direction, api_error_occurred).
        """
        params = {
            "filter[route]": ",".join(stop.routes),
            "filter[stop]": stop.stop_id,
            "sort": "departure_time",
            "page[limit]": "100",
            "include": "stop",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(MBTA_PREDICTIONS_URL, params=params, timeout=15) as resp:
                    if resp.status != 200:
                        return {}, True
                    payload = await resp.json()
        except (aiohttp.ClientError, TimeoutError):
            return {}, True

        parent_by_stop_id = _build_parent_map(payload)
        now_utc = datetime.now(timezone.utc)

        by_direction: dict[int, list[tuple[datetime, str, str | None]]] = {
            DIR_EASTBOUND: [],
            DIR_WESTBOUND: [],
        }

        for item in payload.get("data", []):
            rel = item.get("relationships", {})
            stop_data = rel.get("stop", {}).get("data")
            if not isinstance(stop_data, dict):
                continue
            stop_id = stop_data.get("id")
            if not isinstance(stop_id, str):
                continue
            normalized_stop_id = parent_by_stop_id.get(stop_id, stop_id)
            if normalized_stop_id != stop.stop_id:
                continue

            route_data = rel.get("route", {}).get("data")
            route_id = route_data.get("id") if isinstance(route_data, dict) else None
            if not isinstance(route_id, str):
                route_id = ""

            attrs = item.get("attributes", {})
            direction_id = attrs.get("direction_id")
            if direction_id not in (DIR_EASTBOUND, DIR_WESTBOUND):
                continue

            t = _parse_iso_time(attrs.get("departure_time") or attrs.get("arrival_time"))
            if t is None or t < now_utc:
                continue

            status = attrs.get("status") if isinstance(attrs.get("status"), str) else None
            by_direction[direction_id].append((t, route_id, status))

        for direction_id in by_direction:
            by_direction[direction_id].sort(key=lambda entry: entry[0])
            by_direction[direction_id] = by_direction[direction_id][:2]

        return by_direction, False

    async def _fetch_active_alerts(
        self,
        stop_ids: list[str] | None = None,
        routes: list[str] | None = None,
        limit: int = 3,
    ) -> list[str]:
        if stop_ids is None:
            stop_ids = [stop_id for _, stop_id in BU_GREEN_B_STOPS]
        if routes is None:
            routes = ["Green-B"]

        params = {
            "filter[route]": ",".join(routes),
            "filter[stop]": ",".join(stop_ids),
            "sort": "-severity,-updated_at",
            "page[limit]": str(limit * 2),
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(MBTA_ALERTS_URL, params=params, timeout=15) as resp:
                    if resp.status != 200:
                        return []
                    payload = await resp.json()
        except (aiohttp.ClientError, TimeoutError):
            return []

        items: list[str] = []
        seen: set[str] = set()

        for alert in payload.get("data", []):
            attrs = alert.get("attributes", {})
            header = attrs.get("header")
            effect = attrs.get("effect")
            if not isinstance(header, str) or not header.strip():
                continue

            effect_text = effect.strip().replace("_", " ").title() if isinstance(effect, str) and effect.strip() else "Service Alert"
            key = f"{effect_text}:{header.strip()}"
            if key in seen:
                continue
            seen.add(key)

            text = f"{effect_text}: {header.strip()}"
            if len(text) > 170:
                text = text[:167] + "..."
            items.append(f"- {text}")

            if len(items) >= limit:
                break

        return items

    # ------------------------------------------------------------------
    # Embed builders
    # ------------------------------------------------------------------

    async def _build_mbta_embed(self) -> discord.Embed:
        eta_by_stop = await self._fetch_next_eta_by_stop()
        alerts = await self._fetch_active_alerts()

        embed = discord.Embed(
            title="Green Line at BU!",
            description="Cute train board for your BU stops",
            color=discord.Color.from_rgb(99, 179, 127),
        )

        for stop_name, _ in BU_GREEN_B_STOPS:
            embed.add_field(name=stop_name, value=eta_by_stop.get(stop_name, "unknown"), inline=False)

        if alerts:
            embed.add_field(
                name="Heads-Up Service Alerts 🚧",
                value="\n".join(alerts),
                inline=False,
            )
        else:
            embed.add_field(
                name="Service Status ✨",
                value="No active Green Line B alerts at these BU stops right now.",
                inline=False,
            )

        now_local = datetime.now().strftime("%I:%M %p").lstrip("0")
        embed.set_footer(text=f"Source: MBTA v3 API • Updated {now_local}")
        return embed

    def _format_direction_block(
        self,
        direction_id: int,
        entries: list[tuple[datetime, str, str | None]],
        now_utc: datetime,
        show_branch: bool,
    ) -> str:
        if not entries:
            return _line_for_direction(direction_id, "no live prediction")

        parts: list[str] = []
        for t, route_id, status in entries:
            eta_text = _minutes_away_text(t, now_utc)
            if show_branch:
                branch = ROUTE_BRANCH_LABEL.get(route_id, route_id or "?")
                eta_text = f"{eta_text} ({branch})"
            if status and status.strip() and status.strip().lower() not in {"on time", "no data"}:
                eta_text += f" ⚠️{status.strip()}"
            parts.append(eta_text)

        arrow = "➡️" if direction_id == DIR_EASTBOUND else "⬅️"
        label = _direction_label(direction_id)
        return f"{arrow} {label}: " + " · ".join(parts)

    async def _build_station_embed(self, stop: GreenLineStop) -> discord.Embed:
        predictions_by_direction, api_error = await self._fetch_station_predictions(stop)
        alerts = await self._fetch_active_alerts(stop_ids=[stop.stop_id], routes=list(stop.routes))
        now_utc = datetime.now(timezone.utc)

        show_branch = len(stop.routes) > 1
        line_names = ", ".join(LINE_DISPLAY_NAME.get(r, r) for r in stop.routes)

        embed = discord.Embed(
            title=stop.name,
            description=f"🚊 {line_names}",
            color=discord.Color.from_rgb(99, 179, 127),
        )

        if api_error:
            embed.add_field(
                name="Status",
                value="⚠️ MBTA API is currently unavailable. Please try again shortly.",
                inline=False,
            )
        else:
            east_line = self._format_direction_block(
                DIR_EASTBOUND, predictions_by_direction.get(DIR_EASTBOUND, []), now_utc, show_branch
            )
            west_line = self._format_direction_block(
                DIR_WESTBOUND, predictions_by_direction.get(DIR_WESTBOUND, []), now_utc, show_branch
            )
            embed.add_field(name="Upcoming Trains", value=f"{east_line}\n{west_line}", inline=False)

        if alerts:
            embed.add_field(
                name="Heads-Up Service Alerts 🚧",
                value="\n".join(alerts),
                inline=False,
            )
        else:
            embed.add_field(
                name="Service Status ✨",
                value="No active alerts for this station right now.",
                inline=False,
            )

        now_local = datetime.now().strftime("%I:%M %p").lstrip("0")
        embed.set_footer(text=f"Source: MBTA v3 API • Updated {now_local}")
        return embed

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    @commands.command(name="mbta")
    async def mbta(self, ctx: Context, *, station: str | None = None):
        """Show live Green Line ETAs. Give a station name (e.g. `=mbta Coolidge Corner`)
        for any Green Line stop, or leave it blank for the BU stops."""
        if station is None or not station.strip():
            embed = await self._build_mbta_embed()
            _ = await ctx.send(embed=embed)
            return

        match = self._find_station(station)
        if match is None:
            _ = await ctx.send(
                f"Couldn't find a Green Line station matching **{station.strip()}**. "
                "Try the full or partial station name, e.g. `=mbta Coolidge Corner`."
            )
            return
        if isinstance(match, list):
            suggestions = ", ".join(s.name for s in match[:10])
            _ = await ctx.send(f"A few stations match **{station.strip()}** — did you mean: {suggestions}?")
            return

        embed = await self._build_station_embed(match)
        _ = await ctx.send(embed=embed)

    @app_commands.command(name="mbta", description="Check how far Green Line trains are from a station.")
    @app_commands.describe(station="Green Line station name (leave blank for the BU stops)")
    async def mbta_slash(self, interaction: discord.Interaction, station: str | None = None):
        if station is None or not station.strip():
            embed = await self._build_mbta_embed()
            await interaction.response.send_message(embed=embed)
            return

        match = self._find_station(station)
        if match is None:
            await interaction.response.send_message(
                f"Couldn't find a Green Line station matching **{station.strip()}**.",
                ephemeral=True,
            )
            return
        if isinstance(match, list):
            suggestions = ", ".join(s.name for s in match[:10])
            await interaction.response.send_message(
                f"A few stations match **{station.strip()}** — did you mean: {suggestions}?",
                ephemeral=True,
            )
            return

        embed = await self._build_station_embed(match)
        await interaction.response.send_message(embed=embed)

    @mbta_slash.autocomplete("station")
    async def mbta_station_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        current_lower = current.strip().lower()
        if current_lower:
            matches = [s.name for s in GREEN_LINE_STOPS if current_lower in s.name.lower()]
        else:
            matches = [s.name for s in GREEN_LINE_STOPS]
        matches.sort()
        return [app_commands.Choice(name=name, value=name) for name in matches[:25]]