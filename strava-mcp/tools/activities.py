"""
Strava tools: recent runs and athlete stats.
These functions are registered as MCP tools in server.py.
"""

import math
from datetime import datetime
from strava_client import StravaClient

client = StravaClient()


def _meters_to_km(meters: float) -> float:
    return round(meters / 1000, 2)


def _seconds_to_pace(seconds_per_meter: float) -> str:
    """Convert Strava's speed (m/s) to min/km pace string."""
    if seconds_per_meter == 0:
        return "N/A"
    seconds_per_km = (1 / seconds_per_meter) * 1000 / 60
    minutes = int(seconds_per_km)
    seconds = int((seconds_per_km - minutes) * 60)
    return f"{minutes}:{seconds:02d} /km"


def _elevation(meters: float) -> str:
    return f"{round(meters)}m"


def get_recent_runs(count: int = 7) -> str:
    """
    Fetch the most recent running activities from Strava.

    Args:
        count: Number of recent runs to fetch (default 7, max 20)

    Returns:
        A formatted summary of recent runs including date, distance, pace, and elevation.
    """
    count = min(count, 20)
    runs = client.get_recent_runs(count)

    if not runs:
        return "No recent runs found."

    lines = [f"Last {len(runs)} runs:\n"]
    for run in runs:
        date = datetime.fromisoformat(run["start_date_local"]).strftime("%a %b %d")
        distance = _meters_to_km(run["distance"])
        pace = _seconds_to_pace(run["average_speed"])
        elevation = _elevation(run.get("total_elevation_gain", 0))
        duration_min = round(run["moving_time"] / 60)
        name = run.get("name", "Run")

        lines.append(
            f"• {date} | {name}\n"
            f"  Distance: {distance} km | Pace: {pace} | Duration: {duration_min} min | Elevation: {elevation}"
        )

    return "\n".join(lines)


def get_athlete_stats() -> str:
    """
    Fetch overall athlete running statistics from Strava.

    Returns:
        A summary of recent (4 weeks), year-to-date, and all-time running stats.
    """
    stats = client.get_athlete_stats()
    profile = client.get_athlete_profile()

    name = f"{profile.get('firstname', '')} {profile.get('lastname', '')}".strip()

    def fmt_totals(totals: dict) -> str:
        dist = _meters_to_km(totals.get("distance", 0))
        runs = totals.get("count", 0)
        time_hrs = round(totals.get("moving_time", 0) / 3600, 1)
        elev = _elevation(totals.get("elevation_gain", 0))
        return f"{runs} runs | {dist} km | {time_hrs} hrs | {elev} gain"

    recent = stats.get("recent_run_totals", {})
    ytd = stats.get("ytd_run_totals", {})
    all_time = stats.get("all_run_totals", {})

    return (
        f"Athlete: {name}\n\n"
        f"Last 4 weeks:\n  {fmt_totals(recent)}\n\n"
        f"Year to date:\n  {fmt_totals(ytd)}\n\n"
        f"All time:\n  {fmt_totals(all_time)}"
    )


def get_athlete_profile() -> str:
    """
    Fetch the athlete's Strava profile information.

    Returns:
        Basic profile info including name, location, and fitness level indicators.
    """
    profile = client.get_athlete_profile()

    name = f"{profile.get('firstname', '')} {profile.get('lastname', '')}".strip()
    city = profile.get("city", "Unknown")
    country = profile.get("country", "Unknown")
    ftp = profile.get("ftp")
    weight = profile.get("weight")

    lines = [
        f"Name: {name}",
        f"Location: {city}, {country}",
    ]
    if weight:
        lines.append(f"Weight: {weight} kg")
    if ftp:
        lines.append(f"FTP: {ftp} W")

    return "\n".join(lines)
