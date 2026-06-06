"""App-wide settings backed by the app_settings DB table.

Replaces settings_config.json for all non-user-specific configuration.
All functions must be called within a Flask app context.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

DEFAULTS: dict[str, str] = {
    "oidc_only": "false",
    "oidc_admin_group": "",
    "similar_artist_batch_size": "10",
    "auto_start": "false",
    "auto_start_delay": "60",
    "last_fm_api_key": "",
    "last_fm_api_secret": "",
    "youtube_api_key": "",
    "openai_api_key": "",
    "openai_model": "",
    "openai_api_base": "",
    "openai_extra_headers": "",
    "openai_max_seed_artists": "5",
    "api_key": "",
}


def get(key: str, default: Optional[str] = None) -> Optional[str]:
    from ..models import AppSetting
    row = AppSetting.query.get(key)
    if row is None:
        return DEFAULTS.get(key, default)
    return row.value if row.value is not None else (DEFAULTS.get(key, default))


def set(key: str, value: str) -> None:
    from ..models import AppSetting
    from ..extensions import db
    row = AppSetting.query.get(key)
    if row is None:
        db.session.add(AppSetting(key=key, value=value, updated_at=datetime.utcnow()))
    else:
        row.value = value
        row.updated_at = datetime.utcnow()
    # Caller is responsible for db.session.commit()


def get_bool(key: str, default: bool = False) -> bool:
    val = get(key)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def get_int(key: str, default: int = 0) -> int:
    val = get(key)
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def get_float(key: str, default: float = 0.0) -> float:
    val = get(key)
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def set_many(pairs: dict[str, str]) -> None:
    """Set multiple keys without committing — caller must commit."""
    for key, value in pairs.items():
        set(key, value)
