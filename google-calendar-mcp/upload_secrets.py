"""
One-time script: uploads Google Calendar secrets from .env to GCP Secret Manager.
Run this once before deploying to Cloud Run.

Usage: GOOGLE_CLOUD_PROJECT=personal-agent-496411 python upload_secrets.py
"""

import os
import sys
from dotenv import load_dotenv
from google.cloud import secretmanager

load_dotenv("../.env")

SECRETS = [
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_ACCESS_TOKEN",
    "GOOGLE_REFRESH_TOKEN",
    "GOOGLE_TOKEN_EXPIRY",
]

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")

if not PROJECT_ID:
    print("ERROR: Set GOOGLE_CLOUD_PROJECT env var first.")
    sys.exit(1)


def create_or_update_secret(client, name: str, value: str):
    parent = f"projects/{PROJECT_ID}"
    resource = f"{parent}/secrets/{name}"
    try:
        client.create_secret(
            request={
                "parent": parent,
                "secret_id": name,
                "secret": {"replication": {"automatic": {}}},
            }
        )
        print(f"  Created: {name}")
    except Exception:
        print(f"  Already exists: {name}")

    client.add_secret_version(
        request={"parent": resource, "payload": {"data": value.encode("utf-8")}}
    )
    print(f"  Uploaded value for: {name}")


def main():
    client = secretmanager.SecretManagerServiceClient()
    print(f"Uploading Google Calendar secrets to project: {PROJECT_ID}\n")
    for name in SECRETS:
        value = os.getenv(name)
        if not value:
            print(f"  SKIPPED (empty): {name}")
            continue
        create_or_update_secret(client, name, value)
    print("\nDone.")


if __name__ == "__main__":
    main()
