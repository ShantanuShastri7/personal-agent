"""
Calendar tools for run planning.
These functions are registered as MCP tools in server.py.
"""

from datetime import datetime, timedelta, timezone, date
from zoneinfo import ZoneInfo
from calendar_client import CalendarClient

client = CalendarClient()

LOCAL_TZ = ZoneInfo("America/New_York")
DAY_START_HOUR = 6   # earliest a run could start
DAY_END_HOUR = 22    # latest a run could end


def _parse_date(date_str: str | None) -> date:
    if not date_str:
        return date.today()
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def _week_bounds(d: date) -> tuple[datetime, datetime]:
    monday = d - timedelta(days=d.weekday())
    week_start = datetime(monday.year, monday.month, monday.day, 0, 0, tzinfo=LOCAL_TZ)
    week_end = week_start + timedelta(days=7)
    return week_start, week_end


def _event_times(event: dict) -> tuple[datetime | None, datetime | None]:
    """Return (start, end) as timezone-aware datetimes, or None for all-day events."""
    start_raw = event["start"].get("dateTime")
    end_raw = event["end"].get("dateTime")
    if not start_raw or not end_raw:
        return None, None
    return (
        datetime.fromisoformat(start_raw).astimezone(LOCAL_TZ),
        datetime.fromisoformat(end_raw).astimezone(LOCAL_TZ),
    )


def _merge_busy(periods: list[tuple]) -> list[tuple]:
    """Merge overlapping time periods."""
    if not periods:
        return []
    periods = sorted(periods)
    merged = [list(periods[0])]
    for start, end in periods[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [tuple(p) for p in merged]


def get_week_events(date: str = None) -> str:
    """
    Get all calendar events for the week containing the given date.
    Shows events from all calendars including shared ones (e.g. CMU + personal).

    Args:
        date: Date in YYYY-MM-DD format. Defaults to the current week.

    Returns:
        A day-by-day summary of events for the week with times and calendar names.
    """
    d = _parse_date(date)
    week_start, week_end = _week_bounds(d)
    events = client.get_events(week_start, week_end)

    # Group by day
    days: dict[str, list[str]] = {}
    monday = week_start.date()
    for i in range(7):
        day_label = (monday + timedelta(days=i)).strftime("%A %b %d")
        days[day_label] = []

    for event in events:
        start, end = _event_times(event)
        cal_name = event.get("_calendarName", "")
        title = event.get("summary", "Busy")

        if start:
            day_label = start.strftime("%A %b %d")
            time_str = f"{start.strftime('%I:%M %p')} – {end.strftime('%I:%M %p')}"
        else:
            # All-day event
            raw_date = event["start"]["date"]
            day_label = datetime.strptime(raw_date, "%Y-%m-%d").strftime("%A %b %d")
            time_str = "all day"

        if day_label in days:
            days[day_label].append(f"  • {title} ({time_str}) [{cal_name}]")

    lines = [f"Week of {week_start.strftime('%B %d, %Y')}:\n"]
    for day_label, items in days.items():
        if items:
            lines.append(f"{day_label}:")
            lines.extend(items)
        else:
            lines.append(f"{day_label}: Free")
        lines.append("")

    return "\n".join(lines).strip()


def get_free_slots(date: str = None, min_duration_minutes: int = 30) -> str:
    """
    Get free time windows on a specific day suitable for a run.
    Checks all calendars and returns gaps in the schedule.

    Args:
        date: Date in YYYY-MM-DD format. Defaults to today.
        min_duration_minutes: Minimum gap length to include (default 30 minutes).

    Returns:
        A list of free time windows with their duration.
    """
    d = _parse_date(date)
    day_start = datetime(d.year, d.month, d.day, DAY_START_HOUR, 0, tzinfo=LOCAL_TZ)
    day_end = datetime(d.year, d.month, d.day, DAY_END_HOUR, 0, tzinfo=LOCAL_TZ)

    events = client.get_events(day_start, day_end)

    busy = []
    for event in events:
        start, end = _event_times(event)
        if start and end:
            busy.append((
                max(start, day_start),
                min(end, day_end),
            ))

    merged = _merge_busy(busy)

    free_slots = []
    cursor = day_start
    for busy_start, busy_end in merged:
        if cursor < busy_start:
            duration = int((busy_start - cursor).total_seconds() / 60)
            if duration >= min_duration_minutes:
                free_slots.append((cursor, busy_start, duration))
        cursor = max(cursor, busy_end)

    if cursor < day_end:
        duration = int((day_end - cursor).total_seconds() / 60)
        if duration >= min_duration_minutes:
            free_slots.append((cursor, day_end, duration))

    if not free_slots:
        return f"No free windows of {min_duration_minutes}+ minutes on {d.strftime('%A %B %d')}."

    lines = [f"Free windows on {d.strftime('%A %B %d')} ({min_duration_minutes}+ min):\n"]
    for start, end, duration in free_slots:
        hrs = duration // 60
        mins = duration % 60
        dur_str = f"{hrs}h {mins}m" if hrs else f"{mins}m"
        lines.append(f"  • {start.strftime('%I:%M %p')} – {end.strftime('%I:%M %p')} ({dur_str})")

    return "\n".join(lines)


def get_busy_days(week_start: str = None) -> str:
    """
    Summarise how busy each day is this week to help decide run intensity and duration.
    Classifies each day as Light, Moderate, or Heavy based on scheduled hours.

    Args:
        week_start: Monday date in YYYY-MM-DD format. Defaults to current week.

    Returns:
        A per-day commitment summary with a light/moderate/heavy classification.
    """
    d = _parse_date(week_start)
    w_start, w_end = _week_bounds(d)
    events = client.get_events(w_start, w_end)

    # Accumulate busy minutes per day
    busy_minutes: dict[str, int] = {}
    monday = w_start.date()
    day_labels = {
        (monday + timedelta(days=i)): (monday + timedelta(days=i)).strftime("%A %b %d")
        for i in range(7)
    }
    for d_obj in day_labels:
        busy_minutes[day_labels[d_obj]] = 0

    for event in events:
        start, end = _event_times(event)
        if not start or not end:
            continue
        event_date = start.date()
        if event_date in day_labels:
            duration = int((end - start).total_seconds() / 60)
            busy_minutes[day_labels[event_date]] += duration

    def classify(mins: int) -> str:
        hours = mins / 60
        if hours >= 6:
            return "Heavy"
        elif hours >= 3:
            return "Moderate"
        else:
            return "Light"

    lines = [f"Week of {w_start.strftime('%B %d, %Y')} — daily load:\n"]
    for day_label, mins in busy_minutes.items():
        hrs = mins // 60
        remaining_mins = mins % 60
        busy_str = f"{hrs}h {remaining_mins}m" if hrs else f"{remaining_mins}m"
        label = classify(mins)
        lines.append(f"  {day_label}: {label} ({busy_str} of commitments)")

    return "\n".join(lines)
