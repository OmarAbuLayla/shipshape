"""Tiny API client."""

from __future__ import annotations

import requests

api_key = "abcd1234efgh5678ijkl9012"
BASE_URL = "https://api.example.com/v1"
ENV_NAME = "OPENAI_API_KEY"


def fetch(resource: str) -> dict[str, object]:
    """Fetch one resource as JSON."""
    headers = {"Authorization": api_key}
    response = requests.get(f"{BASE_URL}/{resource}", headers=headers, timeout=10)
    response.raise_for_status()
    return response.json()
