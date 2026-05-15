"""
Secret access layer.
- Local dev: reads/writes from ../.env via python-dotenv
- Cloud Run:  reads/writes from GCP Secret Manager

Cloud Run is detected by the K_SERVICE env var, which GCP sets automatically
on every Cloud Run container. No manual configuration needed.
"""

import os


def _is_cloud() -> bool:
    return os.getenv("K_SERVICE") is not None


def get_secret(name: str) -> str:
    if _is_cloud():
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        resource = f"projects/{project}/secrets/{name}/versions/latest"
        response = client.access_secret_version(name=resource)
        return response.payload.data.decode("utf-8")
    else:
        return os.getenv(name, "")


def set_secret(name: str, value: str):
    if _is_cloud():
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        parent = f"projects/{project}/secrets/{name}"
        client.add_secret_version(
            request={"parent": parent, "payload": {"data": value.encode("utf-8")}}
        )
    else:
        from dotenv import set_key
        set_key("../.env", name, value)
