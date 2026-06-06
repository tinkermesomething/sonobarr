"""One-time startup migration: settings_config.json → DB tables.

Called during app init (within app context) before DataHandler loads settings.
Safe to call on every startup — is a no-op once migration is complete.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path


def run(app, logger: logging.Logger) -> None:
    """Migrate settings_config.json to DB if needed, then seed AppSettings from env."""
    from ..models import LidarrServer, User
    from ..extensions import db
    from . import app_settings as appsettings
    from ..config import get_env_value
    from sqlalchemy.exc import OperationalError, ProgrammingError
    from sqlalchemy import text, inspect as sa_inspect

    # Guard: confirm all required tables and columns exist before doing anything.
    # This handles the case where startup_migration.run() is called during
    # `flask db upgrade`'s app import before migrations have been applied.
    try:
        inspector = sa_inspect(db.engine)
        tables = set(inspector.get_table_names())
        required = {"lidarr_servers", "app_settings", "users"}
        if not required.issubset(tables):
            logger.debug("Startup migration: required tables missing (%s), skipping.", required - tables)
            return
        user_cols = {c["name"] for c in inspector.get_columns("users")}
        if "wizard_completed" not in user_cols or "lidarr_server_id" not in user_cols:
            logger.debug("Startup migration: users table schema not ready, skipping.")
            return
    except (OperationalError, ProgrammingError) as exc:
        logger.debug("Startup migration: schema not ready (%s), skipping.", exc)
        return

    # Guard: tables may not exist yet if called during flask db upgrade import
    try:
        server_count = LidarrServer.query.count()
    except (OperationalError, ProgrammingError):
        logger.debug("Startup migration: tables not ready yet (pre-migration context), skipping.")
        return

    # Already migrated if any servers exist
    if server_count > 0:
        _migrate_oidc_env(logger)
        return

    settings_file = Path(app.config.get("SETTINGS_FILE", ""))

    if settings_file.exists() and settings_file.stat().st_size > 0:
        _migrate_json(settings_file, app, logger)
    else:
        logger.info("Startup migration: no settings_config.json — fresh install, wizard will run.")

    _migrate_oidc_env(logger)


def _migrate_json(settings_file: Path, app, logger: logging.Logger) -> None:
    from ..models import LidarrServer, User
    from ..extensions import db
    from . import app_settings as appsettings

    try:
        with settings_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        logger.error("Startup migration: could not read settings_config.json: %s", exc)
        return

    logger.info("Startup migration: importing settings_config.json into database")

    albums_raw = data.get("lidarr_albums_to_monitor", "")
    if isinstance(albums_raw, list):
        albums_text = "\n".join(str(a) for a in albums_raw if a)
    else:
        albums_text = str(albums_raw) if albums_raw else ""

    server = LidarrServer(
        name="Default",
        url=data.get("lidarr_address", ""),
        api_key=data.get("lidarr_api_key", ""),
        root_folder_path=data.get("root_folder_path", "/data/media/music/"),
        quality_profile_id=_int(data.get("quality_profile_id"), 1),
        metadata_profile_id=_int(data.get("metadata_profile_id"), 1),
        api_timeout=_float(data.get("lidarr_api_timeout"), 120.0),
        fallback_to_top_result=_bool(data.get("fallback_to_top_result"), False),
        search_for_missing_albums=_bool(data.get("search_for_missing_albums"), False),
        dry_run=_bool(data.get("dry_run_adding_to_lidarr"), False),
        monitor_option=data.get("lidarr_monitor_option") or "",
        monitored=_bool(data.get("lidarr_monitored"), True),
        monitor_new_items=data.get("lidarr_monitor_new_items") or "",
        albums_to_monitor=albums_text,
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(server)
    db.session.flush()

    appsettings.set("similar_artist_batch_size", str(data.get("similar_artist_batch_size", "10")))
    appsettings.set("auto_start", "true" if _bool(data.get("auto_start"), False) else "false")
    appsettings.set("auto_start_delay", str(data.get("auto_start_delay", "60")))
    appsettings.set("last_fm_api_key", data.get("last_fm_api_key", "") or "")
    appsettings.set("last_fm_api_secret", data.get("last_fm_api_secret", "") or "")
    appsettings.set("youtube_api_key", data.get("youtube_api_key", "") or "")
    appsettings.set("openai_api_key", data.get("openai_api_key", "") or "")
    appsettings.set("openai_model", data.get("openai_model", "") or "")
    appsettings.set("openai_api_base", data.get("openai_api_base", "") or "")
    appsettings.set("openai_extra_headers", data.get("openai_extra_headers", "") or "")
    appsettings.set("openai_max_seed_artists", str(data.get("openai_max_seed_artists", "5")))
    appsettings.set("api_key", data.get("api_key", "") or "")

    user_count = db.session.execute(text("SELECT count(*) FROM users")).scalar() or 0
    if user_count > 0:
        db.session.execute(
            text("UPDATE users SET wizard_completed = 1, lidarr_server_id = :sid"),
            {"sid": server.id},
        )
        logger.info("Startup migration: assigned %d existing users to server '%s'", user_count, server.name)

    db.session.commit()
    logger.info("Startup migration: complete.")

    try:
        settings_file.unlink()
        logger.info("Startup migration: removed settings_config.json")
    except Exception as exc:
        logger.warning("Startup migration: could not remove settings_config.json: %s", exc)


def _migrate_oidc_env(logger: logging.Logger) -> None:
    """Seed OIDC settings from env into AppSetting if not already stored."""
    from ..models import AppSetting
    from ..extensions import db
    from ..config import get_env_value
    from . import app_settings as appsettings

    changed = False
    for key, env_key, transform in [
        ("oidc_only", "OIDC_ONLY", lambda v: v.strip().lower()),
        ("oidc_admin_group", "OIDC_ADMIN_GROUP", lambda v: v.strip()),
    ]:
        if AppSetting.query.get(key) is None:
            env_val = get_env_value(env_key, "")
            if env_val:
                appsettings.set(key, transform(env_val))
                logger.info("Startup migration: seeded %s from env", key)
                changed = True
    if changed:
        db.session.commit()


def _int(val, default: int) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _float(val, default: float) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _bool(val, default: bool) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "yes", "on"}
