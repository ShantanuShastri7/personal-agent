"""
Strava API client with automatic token refresh.
"""

import time
import httpx
from dotenv import load_dotenv
from gcp_secrets import get_secret, set_secret

load_dotenv("../.env")

BASE_URL = "https://www.strava.com/api/v3"


class StravaClient:
    def __init__(self):
        self.client_id = get_secret("STRAVA_CLIENT_ID")
        self.client_secret = get_secret("STRAVA_CLIENT_SECRET")
        self.access_token = get_secret("STRAVA_ACCESS_TOKEN")
        self.refresh_token = get_secret("STRAVA_REFRESH_TOKEN")
        self.expires_at = int(get_secret("STRAVA_TOKEN_EXPIRES_AT") or "0")

    def _refresh_if_needed(self):
        if time.time() < self.expires_at - 60:
            return

        response = httpx.post(
            "https://www.strava.com/oauth/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        tokens = response.json()

        self.access_token = tokens["access_token"]
        self.refresh_token = tokens["refresh_token"]
        self.expires_at = tokens["expires_at"]

        set_secret("STRAVA_ACCESS_TOKEN", self.access_token)
        set_secret("STRAVA_REFRESH_TOKEN", self.refresh_token)
        set_secret("STRAVA_TOKEN_EXPIRES_AT", str(self.expires_at))

    def _get(self, path: str, params: dict = None) -> dict:
        self._refresh_if_needed()
        response = httpx.get(
            f"{BASE_URL}{path}",
            headers={"Authorization": f"Bearer {self.access_token}"},
            params=params or {},
        )
        response.raise_for_status()
        return response.json()

    def get_recent_runs(self, count: int = 10) -> list[dict]:
        activities = self._get("/athlete/activities", {"per_page": count * 2})
        return [a for a in activities if a["type"] == "Run"][:count]

    def get_athlete_stats(self) -> dict:
        athlete = self._get("/athlete")
        return self._get(f"/athletes/{athlete['id']}/stats")

    def get_athlete_profile(self) -> dict:
        return self._get("/athlete")

    def get_activity_detail(self, activity_id: int) -> dict:
        return self._get(f"/activities/{activity_id}")
