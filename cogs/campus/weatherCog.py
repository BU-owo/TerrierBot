from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, time
from zoneinfo import ZoneInfo

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot import Context, TerrierBot

EASTERN = ZoneInfo("America/New_York")

# BU Charles River Campus (Marsh Plaza area).
BU_LAT = 42.3505
BU_LON = -71.1054

NWS_POINTS_URL = f"https://api.weather.gov/points/{BU_LAT},{BU_LON}"
# api.weather.gov asks callers to identify themselves with a descriptive
# User-Agent rather than a browser string.
NWS_HEADERS = {
    "User-Agent": "TerrierBot (BU Terrier Hub Discord bot)",
    "Accept": "application/geo+json",
}

WEATHER_ANNOUNCE_CHANNEL_ID = 1396542256445391069

# Detailed forecast text gets truncated to this many characters (at the last
# whole word) so a single embed field never gets close to Discord's 1024
# character field-value limit.
DETAIL_TEXT_LIMIT = 400


def _c_to_f(celsius: float) -> float:
    return celsius * 9 / 5 + 32


def _f_to_c(fahrenheit: float) -> float:
    return (fahrenheit - 32) * 5 / 9


def _kmh_to_mph(kmh: float) -> float:
    return kmh * 0.621371


# (upper bound in whole mph, label), checked in order; anything above the
# last bound is "Whipping".
WIND_LABELS = (
    (3, "Calm"),
    (7, "Light breeze"),
    (12, "Breezy"),
    (18, "Windy"),
    (24, "Very windy"),
    (31, "Blustery"),
)


def _wind_label(mph: float) -> str:
    # Bucket on the rounded value so the label always agrees with the mph
    # number shown next to it.
    rounded = round(mph)
    for upper, label in WIND_LABELS:
        if rounded <= upper:
            return label
    return "Whipping"


# Matches NWS forecast wind phrases like "18 mph" or "9 to 15 mph".
WIND_PHRASE_RE = re.compile(r"(\d+)(?:\s+to\s+(\d+))?\s+mph")


def _label_wind_phrases(text: str) -> str:
    """Tag each wind speed in NWS forecast text with its plain-language label,
    e.g. "wind 9 to 15 mph" -> "wind 9 to 15 mph (breezy to windy)"."""

    def tag(match: re.Match[str]) -> str:
        low = int(match.group(1))
        high = int(match.group(2)) if match.group(2) else low
        label = _wind_label(max(low, high)).lower()
        return f"{match.group(0)} ({label})"

    return WIND_PHRASE_RE.sub(tag, text)


def _truncate_text(text: str, limit: int = DETAIL_TEXT_LIMIT) -> str:
    if len(text) <= limit:
        return text
    truncated = text[:limit]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return f"{truncated.rstrip(',.;: ')}..."


def _weather_emoji(forecast_text: str, is_daytime: bool) -> str:
    text = forecast_text.lower()
    if "thunderstorm" in text or "tstorm" in text:
        return "⛈️"
    if "snow" in text or "flurries" in text or "blizzard" in text:
        return "❄️"
    if "sleet" in text or "freezing rain" in text or "ice" in text:
        return "🧊"
    if "rain" in text or "showers" in text or "drizzle" in text:
        return "🌧️"
    if "fog" in text or "haze" in text or "mist" in text:
        return "🌫️"
    if "windy" in text or "breezy" in text:
        return "💨"
    if "sunny" in text or (is_daytime and "clear" in text):
        return "☀️"
    if "clear" in text:
        return "🌙"
    if "partly" in text or "mostly sunny" in text:
        return "⛅" if is_daytime else "🌙"
    if "cloudy" in text or "overcast" in text:
        return "☁️"
    return "🌡️"


def _is_daytime_now() -> bool:
    hour = datetime.now(EASTERN).hour
    return 6 <= hour < 19


@dataclass(frozen=True)
class CurrentConditions:
    description: str
    temp_f: float | None
    temp_c: float | None
    humidity: float | None
    wind_speed_mph: float | None
    wind_direction_deg: float | None


@dataclass(frozen=True)
class ForecastPeriod:
    name: str
    short_forecast: str
    detailed_forecast: str
    temp_f: int
    temp_c: float
    is_daytime: bool


async def setup(bot: TerrierBot):
    await bot.add_cog(WeatherCog(bot))


class WeatherCog(commands.Cog, name="Weather", description="BU campus weather via the National Weather Service."):
    def __init__(self, bot: TerrierBot):
        self.bot: TerrierBot = bot
        self.daily_weather.start()
        print("Weather Cog Ready")

    def cog_unload(self) -> None:
        self.daily_weather.cancel()

    # ------------------------------------------------------------------
    # NWS API calls
    # ------------------------------------------------------------------

    async def _fetch_json(self, session: aiohttp.ClientSession, url: str) -> dict | None:
        try:
            async with session.get(url, headers=NWS_HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError):
            return None

    async def _fetch_endpoints(
        self, session: aiohttp.ClientSession
    ) -> tuple[str | None, str | None, str | None]:
        """Resolve BU's forecast URL, hourly forecast URL, and
        observation-stations URL from the NWS gridpoint for our coordinates."""
        points = await self._fetch_json(session, NWS_POINTS_URL)
        if points is None:
            return None, None, None
        props = points.get("properties", {})
        forecast_url = props.get("forecast")
        hourly_url = props.get("forecastHourly")
        stations_url = props.get("observationStations")
        return (
            forecast_url if isinstance(forecast_url, str) else None,
            hourly_url if isinstance(hourly_url, str) else None,
            stations_url if isinstance(stations_url, str) else None,
        )

    async def _fetch_hourly_wind_mph(self, session: aiohttp.ClientSession, hourly_url: str | None) -> float | None:
        """Forecast wind speed for the current hour, e.g. "17 mph"."""
        if hourly_url is None:
            return None
        data = await self._fetch_json(session, hourly_url)
        if data is None:
            return None
        periods = data.get("properties", {}).get("periods", [])
        if not periods:
            return None
        wind = periods[0].get("windSpeed")
        if not isinstance(wind, str):
            return None
        # Take the highest number in case NWS gives a range ("9 to 15 mph").
        speeds = [int(n) for n in re.findall(r"\d+", wind)]
        return float(max(speeds)) if speeds else None

    async def _fetch_forecast_periods(
        self, session: aiohttp.ClientSession, forecast_url: str | None
    ) -> list[ForecastPeriod] | None:
        if forecast_url is None:
            return None
        data = await self._fetch_json(session, forecast_url)
        if data is None:
            return None

        periods = data.get("properties", {}).get("periods", [])
        result: list[ForecastPeriod] = []
        for period in periods[:2]:
            name = period.get("name")
            short_forecast = period.get("shortForecast")
            temp = period.get("temperature")
            temp_unit = period.get("temperatureUnit", "F")
            if not isinstance(name, str) or not isinstance(short_forecast, str) or not isinstance(temp, (int, float)):
                continue

            temp_f = temp if temp_unit == "F" else _c_to_f(temp)
            temp_c = _f_to_c(temp_f)
            detailed = period.get("detailedForecast")

            result.append(
                ForecastPeriod(
                    name=name,
                    short_forecast=short_forecast,
                    detailed_forecast=detailed if isinstance(detailed, str) else short_forecast,
                    temp_f=round(temp_f),
                    temp_c=round(temp_c),
                    is_daytime=bool(period.get("isDaytime", True)),
                )
            )

        return result or None

    async def _fetch_current_conditions(
        self, session: aiohttp.ClientSession, stations_url: str | None
    ) -> CurrentConditions | None:
        if stations_url is None:
            return None
        stations_data = await self._fetch_json(session, stations_url)
        if stations_data is None:
            return None

        features = stations_data.get("features", [])
        if not features:
            return None
        station_id = features[0].get("id")
        if not isinstance(station_id, str):
            return None

        obs = await self._fetch_json(session, f"{station_id}/observations/latest")
        if obs is None:
            return None

        props = obs.get("properties", {})
        description = props.get("textDescription")
        if not isinstance(description, str) or not description.strip():
            description = "Unknown"

        temp_c = props.get("temperature", {}).get("value")
        humidity = props.get("relativeHumidity", {}).get("value")
        wind_speed_kmh = props.get("windSpeed", {}).get("value")
        wind_direction = props.get("windDirection", {}).get("value")

        return CurrentConditions(
            description=description,
            temp_f=_c_to_f(temp_c) if isinstance(temp_c, (int, float)) else None,
            temp_c=temp_c if isinstance(temp_c, (int, float)) else None,
            humidity=humidity if isinstance(humidity, (int, float)) else None,
            wind_speed_mph=_kmh_to_mph(wind_speed_kmh) if isinstance(wind_speed_kmh, (int, float)) else None,
            wind_direction_deg=wind_direction if isinstance(wind_direction, (int, float)) else None,
        )

    # ------------------------------------------------------------------
    # Embed builder
    # ------------------------------------------------------------------

    async def _build_weather_embed(self, intro: str) -> discord.Embed:
        async with aiohttp.ClientSession() as session:
            forecast_url, hourly_url, stations_url = await self._fetch_endpoints(session)
            periods = await self._fetch_forecast_periods(session, forecast_url)
            current = await self._fetch_current_conditions(session, stations_url)
            # KBOS frequently reports no wind reading (null, QC flag "Z"), so
            # fall back to the hourly forecast's wind for the current hour.
            if current is not None and current.wind_speed_mph is None:
                hourly_wind = await self._fetch_hourly_wind_mph(session, hourly_url)
                if hourly_wind is not None:
                    current = replace(current, wind_speed_mph=hourly_wind)

        embed = discord.Embed(
            title="🐾 BU Campus Weather",
            description=intro,
            color=discord.Color.from_rgb(204, 0, 0),
        )

        if current is not None:
            lines = [f"{_weather_emoji(current.description, _is_daytime_now())} {current.description}"]
            if current.temp_f is not None and current.temp_c is not None:
                lines.append(f"🌡️ {current.temp_f:.0f}°F / {current.temp_c:.0f}°C")
            if current.humidity is not None:
                lines.append(f"💧 Humidity: {current.humidity:.0f}%")
            if current.wind_speed_mph is not None:
                mph = round(current.wind_speed_mph)
                lines.append(f"💨 Wind: {_wind_label(mph)} ({mph} mph)")
            embed.add_field(name="Current Conditions", value="\n".join(lines), inline=False)
        else:
            embed.add_field(
                name="Current Conditions",
                value="⚠️ Current conditions are unavailable right now.",
                inline=False,
            )

        if periods:
            for period in periods:
                emoji = _weather_emoji(period.short_forecast, period.is_daytime)
                value = (
                    f"{emoji} **{period.temp_f}°F / {period.temp_c:.0f}°C** — {period.short_forecast}\n"
                    f"{_truncate_text(_label_wind_phrases(period.detailed_forecast))}"
                )
                embed.add_field(name=period.name, value=value, inline=False)
        else:
            embed.add_field(
                name="Forecast",
                value="⚠️ The forecast is currently unavailable. Please try again shortly.",
                inline=False,
            )

        now_et = datetime.now(EASTERN).strftime("%Y-%m-%d %I:%M %p %Z")
        embed.set_footer(text=f"National Weather Service • BU campus • {now_et}")
        return embed

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------

    @commands.command(name="weather")
    async def weather(self, ctx: Context) -> None:
        """Show today's forecast for BU campus."""
        embed = await self._build_weather_embed("Here's today's forecast for campus:")
        await ctx.send(embed=embed)

    @app_commands.command(name="weather", description="Show today's forecast for BU campus.")
    async def weather_slash(self, interaction: discord.Interaction) -> None:
        # Defer immediately — resolving the NWS gridpoint, forecast, and
        # observation station can take several sequential requests, which can
        # easily outrun Discord's 3-second initial-response window. Not
        # ephemeral — this is meant to be visible to everyone in the channel.
        await interaction.response.defer()
        embed = await self._build_weather_embed("Here's today's forecast for campus:")
        await interaction.followup.send(embed=embed)

    @tasks.loop(time=time(9, 0, tzinfo=EASTERN))
    async def daily_weather(self) -> None:
        try:
            channel = self.bot.get_channel(WEATHER_ANNOUNCE_CHANNEL_ID)
            if not isinstance(channel, discord.TextChannel):
                return
            embed = await self._build_weather_embed("Wakey wakey Terriers! Here is your daily weather:")
            await channel.send(embed=embed)
        except Exception as exc:
            # NWS being down (or any other failure) shouldn't kill the loop —
            # report it and just skip today's post.
            await self.bot.report_exception(category="task", affected="weatherCog.daily_weather", error=exc)

    @daily_weather.before_loop
    async def before_daily_weather(self) -> None:
        await self.bot.wait_until_ready()
