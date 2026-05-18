"""
Google Calendar API client.
Reads from all calendars in the authenticated account — including shared
calendars like a CMU calendar shared to a personal Gmail account.
"""

import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from gcp_secrets import get_secret, set_secret

load_dotenv("../.env")

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

# Marker stored in event extendedProperties so we can identify agent-created events
AGENT_MARKER_KEY = "running_coach_agent"
AGENT_MARKER_VALUE = "true"
WRITE_CALENDAR_ID = "primary"
TOKEN_URI = "https://oauth2.googleapis.com/token"


class CalendarClient:
    def __init__(self):
        self._service = None

    def _get_credentials(self) -> Credentials:
        creds = Credentials(
            token=get_secret("GOOGLE_ACCESS_TOKEN"),
            refresh_token=get_secret("GOOGLE_REFRESH_TOKEN"),
            token_uri=TOKEN_URI,
            client_id=get_secret("GOOGLE_CLIENT_ID"),
            client_secret=get_secret("GOOGLE_CLIENT_SECRET"),
            scopes=SCOPES,
        )

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            set_secret("GOOGLE_ACCESS_TOKEN", creds.token)
            set_secret("GOOGLE_TOKEN_EXPIRY", creds.expiry.isoformat() if creds.expiry else "")

        return creds

    def _get_service(self):
        if not self._service:
            creds = self._get_credentials()
            self._service = build("calendar", "v3", credentials=creds)
        return self._service

    def list_calendars(self) -> list[dict]:
        service = self._get_service()
        result = service.calendarList().list().execute()
        return result.get("items", [])

    def get_events(self, time_min: datetime, time_max: datetime) -> list[dict]:
        """Fetch events from all calendars within the given time range."""
        service = self._get_service()
        calendars = self.list_calendars()

        all_events = []
        for cal in calendars:
            try:
                result = service.events().list(
                    calendarId=cal["id"],
                    timeMin=time_min.astimezone(timezone.utc).isoformat(),
                    timeMax=time_max.astimezone(timezone.utc).isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                ).execute()

                for event in result.get("items", []):
                    event["_calendarName"] = cal.get("summary", "Unknown")
                    all_events.append(event)

            except Exception:
                # Skip calendars we can't read (e.g. holidays, birthdays)
                continue

        all_events.sort(
            key=lambda e: e["start"].get("dateTime", e["start"].get("date", ""))
        )
        return all_events

    def create_event(self, event_body: dict) -> dict:
        """Create an event in the primary calendar. Returns the created event."""
        service = self._get_service()
        return service.events().insert(
            calendarId=WRITE_CALENDAR_ID,
            body=event_body,
        ).execute()

    def get_event(self, event_id: str) -> dict:
        """Fetch a single event by ID from the primary calendar."""
        service = self._get_service()
        return service.events().get(
            calendarId=WRITE_CALENDAR_ID,
            eventId=event_id,
        ).execute()

    def update_event(self, event_id: str, event_body: dict) -> dict:
        """Update an existing event. Returns the updated event."""
        service = self._get_service()
        return service.events().update(
            calendarId=WRITE_CALENDAR_ID,
            eventId=event_id,
            body=event_body,
        ).execute()

    def list_agent_events(self, time_min: datetime, time_max: datetime) -> list[dict]:
        """List only events created by this agent in the primary calendar."""
        service = self._get_service()
        result = service.events().list(
            calendarId=WRITE_CALENDAR_ID,
            timeMin=time_min.astimezone(timezone.utc).isoformat(),
            timeMax=time_max.astimezone(timezone.utc).isoformat(),
            privateExtendedProperty=f"{AGENT_MARKER_KEY}={AGENT_MARKER_VALUE}",
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        return result.get("items", [])
