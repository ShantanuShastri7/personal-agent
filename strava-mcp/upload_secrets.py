"""
One-time script: uploads all Strava secrets from .env into GCP Secret Manager.
Run this once before deploying to Cloud Run.

Usage:
    python upload_secrets.py
"""

import os
import sys
from dotenv import load_dotenv
from google.cloud import secretmanager  # noqa: F401 (not shadowed anymore)

load_dotenv("../.env")

SECRETS = [
    "STRAVA_CLIENT_ID",
    "STRAVA_CLIENT_SECRET",
    "STRAVA_ACCESS_TOKEN",
    "STRAVA_REFRESH_TOKEN",
    "STRAVA_TOKEN_EXPIRES_AT",
]

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")

if not PROJECT_ID:
    print("ERROR: Set GOOGLE_CLOUD_PROJECT env var or run: gcloud config set project personalagent")
    sys.exit(1)


def create_or_update_secret(client, name: str, value: str):
    parent = f"projects/{PROJECT_ID}"
    resource = f"{parent}/secrets/{name}"

    # Create the secret if it doesn't exist
    try:
        client.create_secret(
            request={
                "parent": parent,
                "secret_id": name,
                "secret": {"replication": {"automatic": {}}},
            }
        )
        print(f"  Created secret: {name}")
    except Exception:
        print(f"  Secret already exists: {name}")

    # Add a new version with the value
    client.add_secret_version(
        request={"parent": resource, "payload": {"data": value.encode("utf-8")}}
    )
    print(f"  Uploaded value for: {name}")


def main():
    client = secretmanager.SecretManagerServiceClient()
    print(f"Uploading secrets to project: {PROJECT_ID}\n")

    for name in SECRETS:
        value = os.getenv(name)
        if not value:
            print(f"  SKIPPED (empty): {name}")
            continue
        create_or_update_secret(client, name, value)

    print("\nDone. All secrets are in Secret Manager.")


if __name__ == "__main__":
    main()
