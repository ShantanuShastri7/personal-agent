"""
One-time Google Calendar OAuth setup.
Before running this, create OAuth 2.0 credentials in GCP Console:
  1. Go to console.cloud.google.com > APIs & Services > Credentials
  2. Create Credentials > OAuth client ID > Desktop app
  3. Download the JSON and save it as credentials.json in this directory
  4. Enable the Google Calendar API in GCP Console

Usage: python setup_auth.py
"""

import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import set_key

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]
CREDENTIALS_FILE = "credentials.json"
ENV_PATH = "../.env"


def main():
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"ERROR: {CREDENTIALS_FILE} not found.")
        print("Download it from GCP Console > APIs & Services > Credentials > your OAuth client.")
        return

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=8080)

    with open(CREDENTIALS_FILE) as f:
        client_info = json.load(f)["installed"]

    set_key(ENV_PATH, "GOOGLE_CLIENT_ID", client_info["client_id"])
    set_key(ENV_PATH, "GOOGLE_CLIENT_SECRET", client_info["client_secret"])
    set_key(ENV_PATH, "GOOGLE_ACCESS_TOKEN", creds.token)
    set_key(ENV_PATH, "GOOGLE_REFRESH_TOKEN", creds.refresh_token)
    set_key(ENV_PATH, "GOOGLE_TOKEN_EXPIRY", creds.expiry.isoformat() if creds.expiry else "")

    print("Google Calendar tokens saved to .env successfully.")


if __name__ == "__main__":
    main()
