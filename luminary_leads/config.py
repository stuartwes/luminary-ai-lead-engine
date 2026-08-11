from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


REQUIRED_SECRETS = (
    "COMPANIES_HOUSE_API_KEY",
    "FIRECRAWL_API_KEY",
    "CLICKUP_API_TOKEN",
    "CLICKUP_LIST_ID",
)

SYNC_REQUIRED_SECRETS = (
    "CLICKUP_API_TOKEN",
    "CLICKUP_LIST_ID",
    "INSTANTLY_API_KEY",
)

FLORIDA_REQUIRED_SECRETS = (
    "FIRECRAWL_API_KEY",
    "CLICKUP_API_TOKEN",
    "CLICKUP_LIST_ID",
)

WEB_DESIGN_REQUIRED_SECRETS = (
    "GOOGLE_PLACES_API_KEY",
    "FIRECRAWL_API_KEY",
    "CLICKUP_API_TOKEN",
    "WEB_DESIGN_CLICKUP_LIST_ID",
)


def load_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a YAML mapping")
    return config


def load_secrets(*, allow_missing: bool = False) -> dict[str, str]:
    values = {name: os.getenv(name, "").strip() for name in REQUIRED_SECRETS}
    missing = [name for name, value in values.items() if not value]
    if missing and not allow_missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
    return values


def load_sync_secrets(*, allow_missing: bool = False) -> dict[str, str]:
    values = {name: os.getenv(name, "").strip() for name in SYNC_REQUIRED_SECRETS}
    missing = [name for name, value in values.items() if not value]
    if missing and not allow_missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
    return values


def load_florida_secrets(*, allow_missing: bool = False) -> dict[str, str]:
    values = {name: os.getenv(name, "").strip() for name in FLORIDA_REQUIRED_SECRETS}
    missing = [name for name, value in values.items() if not value]
    if missing and not allow_missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
    return values


def load_web_design_secrets(*, allow_missing: bool = False) -> dict[str, str]:
    values = {name: os.getenv(name, "").strip() for name in WEB_DESIGN_REQUIRED_SECRETS}
    missing = [name for name, value in values.items() if not value]
    if missing and not allow_missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
    return values
