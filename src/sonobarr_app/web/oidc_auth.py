from flask import Blueprint, url_for, redirect, flash, current_app
from flask_login import login_user, logout_user
from ..extensions import oidc
from ..models import db, User

oidc_auth_bp = Blueprint('oidc_auth', __name__)

def _check_oidc_admin_group(user_info) -> bool:
    """Check if user is in the configured OIDC admin group (DB-backed, env fallback)."""
    from ..services import app_settings as appsettings
    admin_group = (appsettings.get("oidc_admin_group") or current_app.config.get('OIDC_ADMIN_GROUP', '') or '').strip()

    if not admin_group:
        return False

    user_groups = user_info.get('groups', [])
    if isinstance(user_groups, str):
        user_groups = [user_groups]

    is_admin = admin_group in user_groups
    current_app.logger.info(
        "OIDC groups: %s, admin group: %s, is_admin: %s", user_groups or "(none)", admin_group, is_admin
    )
    return is_admin


@oidc_auth_bp.route('/oidc/login')
def login():
    """
    Initiates the OIDC login flow.
    """
    redirect_uri = url_for('oidc_auth.callback', _external=True)
    return oidc.sonobarr.authorize_redirect(redirect_uri)

@oidc_auth_bp.route('/oidc/callback')
def callback():
    """
    Handles the OIDC callback after successful authentication.
    """
    try:
        token = oidc.sonobarr.authorize_access_token()
    except Exception as e:
        flash(f"OIDC authorization failed: {e}", "error")
        return redirect(url_for("auth.login"))

    user_info = token.get('userinfo')
    if not user_info:
        flash("Failed to get user info from OIDC provider.", "error")
        return redirect(url_for("auth.login"))

    # Use 'sub' as the unique, persistent identifier for the user
    oidc_user_id = user_info['sub']

    # Check if user should be admin based on OIDC groups
    is_admin_via_group = _check_oidc_admin_group(user_info)

    user = User.query.filter_by(oidc_id=oidc_user_id).first()

    if not user:
        username = user_info.get('email') or user_info.get('preferred_username')
        if not username:
            flash("OIDC token must provide 'email' or 'preferred_username' claim.", "error")
            return redirect(url_for("auth.login"))

        if User.query.filter_by(username=username).first():
            flash(f"User '{username}' already exists. Log in with your password to link your OIDC account.", "error")
            return redirect(url_for("auth.login"))

        user = User(
            oidc_id=oidc_user_id,
            username=username,
            display_name=user_info.get('name', username),
            is_admin=is_admin_via_group,
            wizard_completed=False,
        )
        db.session.add(user)
        db.session.flush()

        # First user ever → unconditional admin regardless of group config
        from ..bootstrap import promote_if_first_user
        was_promoted = promote_if_first_user(user, current_app.logger)
        if was_promoted:
            current_app.logger.info("OIDC user '%s' is the first user — promoted to admin.", username)
        elif is_admin_via_group:
            current_app.logger.info("OIDC user '%s' granted admin via group membership.", username)

        db.session.commit()
    else:
        # Existing user: sync group-based admin status (never demote the first/sole admin)
        old_admin_status = user.is_admin
        admin_count = User.query.filter_by(is_admin=True).count()
        if not (user.is_admin and admin_count <= 1 and not is_admin_via_group):
            user.is_admin = is_admin_via_group

        if old_admin_status != user.is_admin:
            db.session.commit()
            status_change = "promoted to admin" if user.is_admin else "demoted from admin"
            current_app.logger.info("OIDC user '%s' %s via group sync.", user.username, status_change)
            flash(f"Welcome back! You have been {'granted admin privileges' if user.is_admin else 'removed from admin'}.", "success" if user.is_admin else "warning")

    login_user(user)
    return redirect(url_for('main.home'))


@oidc_auth_bp.route('/oidc/logout')
def logout():
    """
    Logs the user out from the local session.
    A full OIDC logout would require redirecting to the provider's end_session_endpoint,
    which can be added as a future enhancement.
    """
    logout_user()
    return redirect(url_for('auth.logged_out'))
