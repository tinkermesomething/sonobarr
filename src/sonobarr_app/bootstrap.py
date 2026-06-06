from __future__ import annotations

import logging
import secrets

from sqlalchemy.exc import OperationalError, ProgrammingError

from .extensions import db
from .models import User


def bootstrap_first_admin(logger: logging.Logger) -> None:
    """Seed a local admin account on fresh local-auth installs.

    No-op when OIDC is configured (first OIDC login becomes admin)
    or when users already exist.
    """
    try:
        if User.query.count() > 0:
            return
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("Database not ready during admin bootstrap: %s", exc)
        db.session.rollback()
        return

    from .config import get_env_value
    if get_env_value("OIDC_CLIENT_ID"):
        logger.info(
            "OIDC configured — first OIDC login will become admin. Skipping local bootstrap."
        )
        return

    password = secrets.token_urlsafe(16)
    admin = User(username="admin", display_name="Admin", is_admin=True, wizard_completed=False)
    admin.set_password(password)
    db.session.add(admin)

    try:
        db.session.commit()
    except (OperationalError, ProgrammingError) as exc:
        logger.warning("Failed to commit admin bootstrap: %s", exc)
        db.session.rollback()
        return

    logger.warning(
        "Created default admin. Username: admin  Password: %s  — Change this after first login!",
        password,
    )


def promote_if_first_user(user: User, logger: logging.Logger) -> bool:
    """Unconditionally promote user to admin if they are the first user in the DB.

    Call this after the user row is added to the session but before commit.
    Returns True if promoted.
    """
    try:
        # count() includes the current unsaved user only if already flushed
        count = User.query.count()
    except (OperationalError, ProgrammingError):
        return False

    # count == 1 means this user is the only one (just inserted + flushed)
    if count != 1:
        return False

    user.is_admin = True
    logger.info("User '%s' is the first user — promoted to admin.", user.username)
    return True
