"""Runtime settings: persisted values + live Gemini/env application."""

from __future__ import annotations

import os
from typing import Any

from database import get_all_settings, get_setting, set_setting as sqlite_set_setting


RUNTIME_KEYS = (
    "bot_name",
    "system_prompt",
    "gemini_api_key",
    "gemini_model",
    "campaign_file",
    "calendar_file",
    "private_unauthorized_mode",
)


def get_runtime_setting(key: str, default: str = "") -> str:
    return get_setting(key, default)


def set_runtime_setting(key: str, value: str) -> None:
    sqlite_set_setting(key, value)
    if key == "gemini_api_key" and value:
        os.environ["GOOGLE_API_KEY"] = value
    if key == "gemini_model" and value:
        os.environ["GOOGLE_MODEL"] = value


def load_all_runtime_settings() -> dict[str, str]:
    settings = get_all_settings()
    apply_runtime_env(settings)
    return settings


def apply_runtime_env(settings: dict[str, str] | None = None) -> None:
    data = settings or get_all_settings()
    api_key = data.get("gemini_api_key") or os.getenv("GOOGLE_API_KEY", "")
    model = data.get("gemini_model") or os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")
    if api_key:
        os.environ["GOOGLE_API_KEY"] = api_key
    if model:
        os.environ["GOOGLE_MODEL"] = model


def get_settings_for_api() -> dict[str, Any]:
    raw = get_all_settings()
    return {
        "bot_name": raw.get("bot_name", ""),
        "system_prompt": raw.get("system_prompt", ""),
        "gemini_api_key": "***" if raw.get("gemini_api_key") else "",
        "gemini_model": raw.get("gemini_model", "gemini-2.5-flash"),
        "campaign_file": raw.get("campaign_file", ""),
        "calendar_file": raw.get("calendar_file", ""),
        "private_unauthorized_mode": raw.get("private_unauthorized_mode", "ignore"),
    }
