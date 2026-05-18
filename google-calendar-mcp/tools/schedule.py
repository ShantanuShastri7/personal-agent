"""
Calendar tools for run planning.
These functions are registered as MCP tools in server.py.
"""

import json
from datetime import datetime, timedelta, timezone, date
from zoneinfo import ZoneInfo
from calendar_client import CalendarClient, AGENT_MARKER_KEY, AGENT_MARKER_VALUE

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


# ---------------------------------------------------------------------------
# Run planning tools (write)
# ---------------------------------------------------------------------------

WARMUP_MINUTES = 10
COOLDOWN_MINUTES = 10


def _parse_pace(pace_str: str) -> float:
    """Parse 'MM:SS' or 'MM:SS /km' to decimal minutes per km."""
    pace_str = pace_str.replace("/km", "").strip()
    parts = pace_str.split(":")
    return int(parts[0]) + int(parts[1]) / 60


def _build_event_body(
    title: str,
    date_str: str,
    start_time_str: str,
    distance_km: float,
    pace_str: str,
    notes: str,
) -> dict:
    pace_min_per_km = _parse_pace(pace_str)
    run_minutes = distance_km * pace_min_per_km
    total_minutes = WARMUP_MINUTES + run_minutes + COOLDOWN_MINUTES

    start_dt = datetime.strptime(
        f"{date_str} {start_time_str}", "%Y-%m-%d %H:%M"
    ).replace(tzinfo=LOCAL_TZ)
    end_dt = start_dt + timedelta(minutes=total_minutes)

    pace_parts = pace_str.replace("/km", "").strip()
    description_lines = [
        f"Warm-up:   {WARMUP_MINUTES} min",
        f"Run:       {distance_km} km @ {pace_parts} /km (~{round(run_minutes)} min)",
        f"Cool-down: {COOLDOWN_MINUTES} min",
        f"Total:     {round(total_minutes)} min",
    ]
    if notes:
        description_lines += ["", notes]
    description_lines += ["", "—", "Created by Running Coach Agent"]

    return {
        "summary": f"🏃 {title} — {distance_km}km",
        "description": "\n".join(description_lines),
        "start": {"dateTime": start_dt.isoformat(), "timeZone": str(LOCAL_TZ)},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": str(LOCAL_TZ)},
        "colorId": "2",
        "extendedProperties": {
            "private": {AGENT_MARKER_KEY: AGENT_MARKER_VALUE}
        },
    }


def create_run_events(runs_json: str) -> str:
    """
    Create calendar events for a set of planned runs after the user has approved the plan.
    Each event includes warm-up (10 min), the run, and cool-down (10 min).
    Duration is calculated from distance x pace.

    Args:
        runs_json: JSON array of run objects. Each object must have:
                   - date: YYYY-MM-DD
                   - start_time: HH:MM (24h)
                   - distance_km: float
                   - pace: string in MM:SS format (e.g. "6:10")
                   - title: string (e.g. "Easy Run", "Long Run")
                   - notes: string (optional, training focus or tips)

    Returns:
        A summary of created events with their IDs (needed for future edits).
    """
    try:
        runs = json.loads(runs_json)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"

    created = []
    errors = []

    for run in runs:
        try:
            body = _build_event_body(
                title=run["title"],
                date_str=run["date"],
                start_time_str=run["start_time"],
                distance_km=float(run["distance_km"]),
                pace_str=run["pace"],
                notes=run.get("notes", ""),
            )
            event = client.create_event(body)
            created.append({
                "id": event["id"],
                "title": event["summary"],
                "date": run["date"],
                "start": run["start_time"],
            })
        except Exception as e:
            errors.append(f"  • {run.get('date', '?')} {run.get('title', '?')}: {e}")

    lines = [f"Created {len(created)} run event(s):\n"]
    for c in created:
        lines.append(f"  • {c['date']} {c['start']} — {c['title']}")
        lines.append(f"    Event ID: {c['id']}")

    if errors:
        lines.append("\nFailed:")
        lines.extend(errors)

    return "\n".join(lines)


def get_agent_run_events(week_start: str = None) -> str:
    """
    List all run events that were created by the running coach agent this week.
    Use this to find event IDs before editing them.

    Args:
        week_start: Monday date in YYYY-MM-DD format. Defaults to current week.

    Returns:
        List of agent-created run events with their IDs and details.
    """
    d = _parse_date(week_start)
    w_start, w_end = _week_bounds(d)
    events = client.list_agent_events(w_start, w_end)

    if not events:
        return f"No agent-created run events found for the week of {w_start.strftime('%B %d, %Y')}."

    lines = [f"Agent-created run events (week of {w_start.strftime('%B %d, %Y')}):\n"]
    for event in events:
        start_raw = event["start"].get("dateTime", "")
        start_dt = datetime.fromisoformat(start_raw).astimezone(LOCAL_TZ) if start_raw else None
        date_str = start_dt.strftime("%a %b %d %I:%M %p") if start_dt else "?"
        lines.append(f"  • {date_str} — {event.get('summary', 'Run')}")
        lines.append(f"    Event ID: {event['id']}")

    return "\n".join(lines)


def edit_run_event(
    event_id: str,
    date: str = None,
    start_time: str = None,
    distance_km: float = None,
    pace: str = None,
    title: str = None,
    notes: str = None,
) -> str:
    """
    Edit a run event previously created by the running coach agent.
    Refuses to edit any event not created by the agent.
    Only pass the fields you want to change — everything else stays the same.

    Args:
        event_id: The Google Calendar event ID (from create_run_events or get_agent_run_events)
        date: New date in YYYY-MM-DD format (optional)
        start_time: New start time in HH:MM 24h format (optional)
        distance_km: New distance in km (optional)
        pace: New pace in MM:SS format e.g. "6:10" (optional)
        title: New title e.g. "Tempo Run" (optional)
        notes: New notes or training focus (optional)

    Returns:
        Confirmation of what was updated, or an error if the event is not agent-created.
    """
    try:
        existing = client.get_event(event_id)
    except Exception as e:
        return f"Could not fetch event {event_id}: {e}"

    # Safety check — refuse to edit events not created by the agent
    private_props = existing.get("extendedProperties", {}).get("private", {})
    if private_props.get(AGENT_MARKER_KEY) != AGENT_MARKER_VALUE:
        return (
            "Cannot edit this event — it was not created by the running coach agent. "
            "Only agent-created run events can be modified."
        )

    current_start = datetime.fromisoformat(
        existing["start"]["dateTime"]
    ).astimezone(LOCAL_TZ)

    # Parse current distance from summary e.g. "🏃 Easy Run — 8.0km"
    summary = existing.get("summary", "")
    try:
        current_distance = float(summary.split("—")[-1].strip().replace("km", ""))
    except Exception:
        current_distance = 5.0

    current_title = summary.replace("🏃 ", "").split(" — ")[0] if " — " in summary else "Run"

    # Extract existing notes from description
    current_desc = existing.get("description", "")
    if notes is None:
        note_lines = [
            l for l in current_desc.split("\n")
            if l and not l.startswith(("Warm-up", "Run:", "Cool-down", "Total", "—", "Created"))
        ]
        notes = "\n".join(note_lines).strip()

    updated_body = _build_event_body(
        title=title or current_title,
        date_str=date or current_start.strftime("%Y-%m-%d"),
        start_time_str=start_time or current_start.strftime("%H:%M"),
        distance_km=distance_km if distance_km is not None else current_distance,
        pace_str=pace or "6:00",
        notes=notes,
    )

    try:
        client.update_event(event_id, updated_body)
    except Exception as e:
        return f"Failed to update event: {e}"

    changes = []
    if date: changes.append(f"date → {date}")
    if start_time: changes.append(f"start → {start_time}")
    if distance_km is not None: changes.append(f"distance → {distance_km}km")
    if pace: changes.append(f"pace → {pace}")
    if title: changes.append(f"title → {title}")

    return f"Updated '{existing.get('summary')}': {', '.join(changes) or 'no changes'}"
