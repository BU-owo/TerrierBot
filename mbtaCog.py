from __future__ import annotations

from datetime import datetime, timezone

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from bot import Context, TerrierBot

MBTA_PREDICTIONS_URL = "https://api-v3.mbta.com/predictions"
MBTA_SCHEDULES_URL = "https://api-v3.mbta.com/schedules"
MBTA_ALERTS_URL = "https://api-v3.mbta.com/alerts"

# MBTA direction_id convention for Green-B:
# 0 = outbound (westbound toward Boston College)
# 1 = inbound (eastbound toward downtown)
DIR_WESTBOUND = 0
DIR_EASTBOUND = 1

# Requested BU Green Line B stops in user-specified order.
BU_GREEN_B_STOPS: list[tuple[str, str]] = [
    ("Babcock Street", "place-babck"),
    ("Amory Street", "place-amory"),
    ("Boston University Central", "place-bucen"),
    ("Boston University East", "place-buest"),
    ("Blandford Street", "place-bland"),
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


async def setup(bot: TerrierBot):
    await bot.add_cog(MBTACog(bot))


class MBTACog(commands.Cog, name="MBTA", description="Live MBTA Green Line ETAs for BU stops."):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot
        print("MBTA Cog Ready")

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

    async def _fetch_active_alerts(self) -> list[str]:
        stop_ids = ",".join(stop_id for _, stop_id in BU_GREEN_B_STOPS)
        params = {
            "filter[route]": "Green-B",
            "filter[stop]": stop_ids,
            "sort": "-severity,-updated_at",
            "page[limit]": "6",
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

            if len(items) >= 3:
                break

        return items
    
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

    @commands.command(name="mbta")
    async def mbta(self, ctx: Context):
        """Show live Green Line B ETAs for BU stops."""
        embed = await self._build_mbta_embed()
        _ = await ctx.send(embed=embed)

    @app_commands.command(name="mbta", description="Check how far Green Line B trains are from BU stops.")
    async def mbta_slash(self, interaction: discord.Interaction):
        embed = await self._build_mbta_embed()
        await interaction.response.send_message(embed=embed)
