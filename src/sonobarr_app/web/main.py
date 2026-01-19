from __future__ import annotations

from datetime import datetime, timezone

import requests

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import User, ArtistRequest


bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def home():
    # Check which discovery tools are available based on user's configured API keys
    has_ai_enabled = bool(current_user.openai_api_key)
    has_lastfm_enabled = bool(current_user.lastfm_api_key and current_user.lastfm_username)
    has_listenbrainz_enabled = bool(current_user.listenbrainz_username)

    return render_template(
        "base.html",
        has_ai_enabled=has_ai_enabled,
        has_lastfm_enabled=has_lastfm_enabled,
        has_listenbrainz_enabled=has_listenbrainz_enabled,
    )


@bp.get("/settings")
@login_required
def settings():
    # Get the active tab from query parameter, default to 'profile'
    active_tab = request.args.get("tab", "profile")

    # Validate tab based on user permissions
    valid_tabs = ["profile"]
    if current_user.is_admin:
        valid_tabs.extend(["users", "requests", "system"])

    # Default to profile if invalid tab requested
    if active_tab not in valid_tabs:
        active_tab = "profile"

    # Fetch users list for Users tab
    users = None
    if active_tab == "users" and current_user.is_admin:
        users = User.query.order_by(User.username).all()

    # Fetch pending artist requests for Requests tab
    artist_requests = None
    if active_tab == "requests" and current_user.is_admin:
        artist_requests = ArtistRequest.query.filter_by(status="pending").order_by(
            ArtistRequest.created_at.desc()
        ).all()

    # Fetch current system configuration for System tab
    system_config = None
    if active_tab == "system" and current_user.is_admin:
        system_config = _get_system_config()

    return render_template("settings.html", active_tab=active_tab, users=users, artist_requests=artist_requests, system_config=system_config)


@bp.post("/settings")
@login_required
def update_settings():
    # Get which tab was submitted
    tab = request.form.get("tab", "profile")

    if tab == "profile":
        errors, password_changed, avatar_fetched = _update_user_profile(request.form, current_user)

        if errors:
            for message in errors:
                flash(message, "danger")
            db.session.rollback()
        else:
            db.session.commit()
            flash("Profile updated.", "success")
            if password_changed:
                flash("Password updated.", "success")
            if avatar_fetched:
                flash("Using your Last.fm profile picture. Change the Profile image URL field to use a custom avatar.", "info")
            _refresh_personal_sources(current_user)

    elif tab == "users" and current_user.is_admin:
        action = request.form.get("action")
        if action == "create":
            _create_user(request.form)
        elif action == "edit":
            _edit_user(request.form)
        elif action == "delete":
            _delete_user(request.form)

    elif tab == "requests" and current_user.is_admin:
        action = request.form.get("action")
        artist_request = _resolve_artist_request(request.form)
        if artist_request:
            if action == "approve":
                _approve_artist_request(artist_request)
            elif action == "reject":
                _reject_artist_request(artist_request)
            else:
                flash("Invalid action.", "danger")

    elif tab == "system" and current_user.is_admin:
        _save_system_config(request.form)

    return redirect(url_for("main.settings", tab=tab))


def _create_user(form):
    """Create a new user from form data."""
    username = (form.get("username") or "").strip()
    password = form.get("password") or ""
    confirm_password = (form.get("confirm_password") or "").strip()
    display_name = (form.get("display_name") or "").strip()
    avatar_url = (form.get("avatar_url") or "").strip()
    is_admin = form.get("is_admin") == "on"

    if not username or not password:
        flash("Username and password are required.", "danger")
        return
    if password != confirm_password:
        flash("Password confirmation does not match.", "danger")
        return
    if User.query.filter_by(username=username).first():
        flash("Username already exists.", "danger")
        return

    user = User(
        username=username,
        display_name=display_name or None,
        avatar_url=avatar_url or None,
        is_admin=is_admin,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    flash(f"User '{username}' created.", "success")


def _edit_user(form):
    """Edit an existing user from form data."""
    try:
        user_id = int(form.get("user_id", "0"))
    except ValueError:
        flash("Invalid user id.", "danger")
        return

    user = User.query.get(user_id)
    if not user:
        flash("User not found.", "danger")
        return

    # Update basic fields
    display_name = (form.get("display_name") or "").strip()
    avatar_url = (form.get("avatar_url") or "").strip()
    user.display_name = display_name or None
    user.avatar_url = avatar_url or None

    # Update active status
    user.is_active = form.get("is_active") == "on"

    # Update admin status with validation
    new_admin_status = form.get("is_admin") == "on"

    # Validate: can't remove last admin
    if user.is_admin and not new_admin_status:
        if User.query.filter_by(is_admin=True).count() <= 1:
            flash("At least one administrator must remain.", "warning")
            return

    # Apply admin status change
    if user.is_admin != new_admin_status:
        user.is_admin = new_admin_status
        status_text = "granted" if new_admin_status else "revoked"

        # Warn if this is an OIDC user (will be synced on next login)
        if user.oidc_id:
            flash(
                f"Admin privileges {status_text} for '{user.username}'. "
                f"Note: This user authenticates via SSO and will be re-synced on next login.",
                "warning"
            )
        else:
            flash(f"Admin privileges {status_text} for '{user.username}'.", "success")

    db.session.commit()
    flash(f"User '{user.username}' updated.", "success")


def _delete_user(form):
    """Delete a user from form data."""
    try:
        user_id = int(form.get("user_id", "0"))
    except ValueError:
        flash("Invalid user id.", "danger")
        return

    user = User.query.get(user_id)
    if not user:
        flash("User not found.", "danger")
        return
    if user.id == current_user.id:
        flash("You cannot delete your own account.", "warning")
        return
    if user.is_admin and User.query.filter_by(is_admin=True).count() <= 1:
        flash("At least one administrator must remain.", "warning")
        return

    # Delete associated artist requests first
    ArtistRequest.query.filter_by(requested_by_id=user_id).delete()
    ArtistRequest.query.filter_by(approved_by_id=user_id).delete()
    db.session.delete(user)
    db.session.commit()
    flash(f"User '{user.username}' deleted.", "success")


def _resolve_artist_request(form):
    """Validate and retrieve an artist request from form data."""
    request_id = form.get("request_id")
    if not request_id:
        flash("Invalid request ID.", "danger")
        return None
    try:
        request_id_int = int(request_id)
    except ValueError:
        flash("Invalid request ID.", "danger")
        return None

    artist_request = ArtistRequest.query.get(request_id_int)
    if not artist_request:
        flash("Artist request not found.", "danger")
        return None
    if artist_request.status != "pending":
        flash("Request has already been processed.", "warning")
        return None
    return artist_request


def _approve_artist_request(artist_request: ArtistRequest):
    """Approve an artist request and add to Lidarr."""
    data_handler = current_app.extensions.get("data_handler")
    if not data_handler:
        flash(f"Failed to add '{artist_request.artist_name}' to Lidarr. Request not approved.", "danger")
        return

    session_key = f"admin_{current_user.id}"
    data_handler.ensure_session(session_key, current_user.id, True)
    result_status = data_handler.add_artists(session_key, artist_request.artist_name)
    if result_status != "Added":
        flash(f"Failed to add '{artist_request.artist_name}' to Lidarr. Request not approved.", "danger")
        return

    artist_request.status = "approved"
    artist_request.approved_by_id = current_user.id
    artist_request.approved_at = datetime.now(timezone.utc)
    db.session.commit()

    approved_artist = {"Name": artist_request.artist_name, "Status": "Added"}
    data_handler.socketio.emit("refresh_artist", approved_artist)
    flash(f"Request for '{artist_request.artist_name}' approved and added to Lidarr.", "success")


def _reject_artist_request(artist_request: ArtistRequest):
    """Reject an artist request."""
    artist_request.status = "rejected"
    artist_request.approved_by_id = current_user.id
    artist_request.approved_at = datetime.now(timezone.utc)
    db.session.commit()

    data_handler = current_app.extensions.get("data_handler")
    if data_handler:
        rejected_artist = {"Name": artist_request.artist_name, "Status": "Rejected"}
        data_handler.socketio.emit("refresh_artist", rejected_artist)
    flash(f"Request for '{artist_request.artist_name}' rejected.", "success")


def _fetch_lastfm_avatar(lastfm_username: str) -> str | None:
    """Fetch Last.fm user profile image.

    Returns the image URL if successful, None otherwise.
    """
    if not lastfm_username:
        return None

    try:
        # Use Last.fm API user.getInfo method
        # Note: This uses a public API that doesn't require authentication
        response = requests.get(
            "https://ws.audioscrobbler.com/2.0/",
            params={
                "method": "user.getinfo",
                "user": lastfm_username,
                "api_key": "c1572082105bd40d247836b5c1819623",  # Public API key for read-only operations
                "format": "json"
            },
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()
            user_data = data.get("user", {})
            images = user_data.get("image", [])

            # Last.fm returns images in multiple sizes, get the largest
            for img in reversed(images):
                url = img.get("#text", "").strip()
                if url and not url.endswith("default_user_large.png"):
                    return url

    except Exception as exc:
        current_app.logger.warning("Failed to fetch Last.fm avatar for %s: %s", lastfm_username, exc)

    return None


def _update_user_profile(form_data, user):
    display_name = (form_data.get("display_name") or "").strip()
    avatar_url = (form_data.get("avatar_url") or "").strip()
    lastfm_username = (form_data.get("lastfm_username") or "").strip()
    listenbrainz_username = (form_data.get("listenbrainz_username") or "").strip()

    # Smart sync: Auto-fetch Last.fm avatar if no custom avatar is set
    avatar_fetched = False
    if lastfm_username and not avatar_url:
        fetched_avatar = _fetch_lastfm_avatar(lastfm_username)
        if fetched_avatar:
            avatar_url = fetched_avatar
            avatar_fetched = True

    # External API keys
    lastfm_api_key = (form_data.get("lastfm_api_key") or "").strip()
    lastfm_api_secret = (form_data.get("lastfm_api_secret") or "").strip()
    youtube_api_key = (form_data.get("youtube_api_key") or "").strip()
    openai_api_key = (form_data.get("openai_api_key") or "").strip()
    openai_model = (form_data.get("openai_model") or "").strip()
    openai_api_base = (form_data.get("openai_api_base") or "").strip()
    openai_extra_headers = (form_data.get("openai_extra_headers") or "").strip()
    openai_max_seed_artists = (form_data.get("openai_max_seed_artists") or "").strip()

    user.display_name = display_name or None
    user.avatar_url = avatar_url or None
    user.lastfm_username = lastfm_username or None
    user.listenbrainz_username = listenbrainz_username or None
    user.lastfm_api_key = lastfm_api_key or None
    user.lastfm_api_secret = lastfm_api_secret or None
    user.youtube_api_key = youtube_api_key or None
    user.openai_api_key = openai_api_key or None
    user.openai_model = openai_model or None
    user.openai_api_base = openai_api_base or None
    user.openai_extra_headers = openai_extra_headers or None
    user.openai_max_seed_artists = int(openai_max_seed_artists) if openai_max_seed_artists else None

    # Per-user API keys (optional overrides for global keys)
    lastfm_api_key = (form_data.get("lastfm_api_key") or "").strip()
    lastfm_api_secret = (form_data.get("lastfm_api_secret") or "").strip()
    youtube_api_key = (form_data.get("youtube_api_key") or "").strip()
    openai_api_key = (form_data.get("openai_api_key") or "").strip()
    openai_api_base = (form_data.get("openai_api_base") or "").strip()
    openai_model = (form_data.get("openai_model") or "").strip()
    openai_extra_headers = (form_data.get("openai_extra_headers") or "").strip()
    openai_max_seed_artists_raw = (form_data.get("openai_max_seed_artists") or "").strip()

    user.lastfm_api_key = lastfm_api_key or None
    user.lastfm_api_secret = lastfm_api_secret or None
    user.youtube_api_key = youtube_api_key or None
    user.openai_api_key = openai_api_key or None
    user.openai_api_base = openai_api_base or None
    user.openai_model = openai_model or None
    user.openai_extra_headers = openai_extra_headers or None

    if openai_max_seed_artists_raw:
        try:
            user.openai_max_seed_artists = int(openai_max_seed_artists_raw)
        except ValueError:
            user.openai_max_seed_artists = None
    else:
        user.openai_max_seed_artists = None

    new_password = form_data.get("new_password", "")
    confirm_password = form_data.get("confirm_password", "")
    current_password = form_data.get("current_password", "")
    errors: list[str] = []
    password_changed = False

    if not new_password:
        return errors, password_changed, avatar_fetched

    if new_password != confirm_password:
        errors.append("New password and confirmation do not match.")
    elif len(new_password) < 8:
        errors.append("New password must be at least 8 characters long.")
    elif not user.check_password(current_password):
        errors.append("Current password is incorrect.")
    else:
        user.set_password(new_password)
        password_changed = True

    return errors, password_changed, avatar_fetched


def _refresh_personal_sources(user):
    data_handler = current_app.extensions.get("data_handler")
    if not data_handler or user.id is None:
        return

    try:
        data_handler.refresh_personal_sources_for_user(int(user.id))
    except Exception as exc:  # pragma: no cover - defensive logging
        current_app.logger.error("Failed to refresh personal discovery state: %s", exc)


def _get_system_config():
    """Retrieve current system configuration from data_handler."""
    data_handler = current_app.extensions.get("data_handler")
    if not data_handler:
        return {}

    return {
        "lidarr_address": data_handler.lidarr_address,
        "lidarr_api_key": data_handler.lidarr_api_key,
        "root_folder_path": data_handler.root_folder_path,
        "quality_profile_id": data_handler.quality_profile_id,
        "metadata_profile_id": data_handler.metadata_profile_id,
        "lidarr_api_timeout": data_handler.lidarr_api_timeout,
        "fallback_to_top_result": data_handler.fallback_to_top_result,
        "search_for_missing_albums": data_handler.search_for_missing_albums,
        "dry_run_adding_to_lidarr": data_handler.dry_run_adding_to_lidarr,
        "lidarr_monitor_option": data_handler.lidarr_monitor_option,
        "lidarr_monitor_new_items": data_handler.lidarr_monitor_new_items,
        "lidarr_monitored": data_handler.lidarr_monitored,
        "lidarr_albums_to_monitor": data_handler.lidarr_albums_to_monitor,
        "similar_artist_batch_size": data_handler.similar_artist_batch_size,
        "auto_start": data_handler.auto_start,
        "auto_start_delay": data_handler.auto_start_delay,
        "api_key": data_handler.api_key,
    }


def _save_system_config(form_data):
    """Save system configuration from form data."""
    data_handler = current_app.extensions.get("data_handler")
    if not data_handler:
        flash("Configuration handler not available.", "danger")
        return

    try:
        # Build the payload dict from form data
        payload = {
            "lidarr_address": (form_data.get("lidarr_address") or "").strip(),
            "lidarr_api_key": (form_data.get("lidarr_api_key") or "").strip(),
            "root_folder_path": (form_data.get("root_folder_path") or "").strip(),
            "quality_profile_id": form_data.get("quality_profile_id", ""),
            "metadata_profile_id": form_data.get("metadata_profile_id", ""),
            "lidarr_api_timeout": form_data.get("lidarr_api_timeout", ""),
            "fallback_to_top_result": form_data.get("fallback_to_top_result") == "on",
            "search_for_missing_albums": form_data.get("search_for_missing_albums") == "on",
            "dry_run_adding_to_lidarr": form_data.get("dry_run_adding_to_lidarr") == "on",
            "lidarr_monitor_option": (form_data.get("lidarr_monitor_option") or "").strip(),
            "lidarr_monitor_new_items": (form_data.get("lidarr_monitor_new_items") or "").strip(),
            "lidarr_monitored": form_data.get("lidarr_monitored") == "on",
            "lidarr_albums_to_monitor": (form_data.get("lidarr_albums_to_monitor") or "").strip(),
            "similar_artist_batch_size": form_data.get("similar_artist_batch_size", ""),
            "auto_start": form_data.get("auto_start") == "on",
            "auto_start_delay": form_data.get("auto_start_delay", ""),
            "api_key": (form_data.get("api_key") or "").strip(),
        }

        # Update settings and save to file
        data_handler.update_settings(payload)
        data_handler.save_config_to_file()
        flash("Configuration saved successfully.", "success")

    except Exception as exc:
        current_app.logger.exception("Failed to save system configuration: %s", exc)
        flash("Failed to save configuration. Check the server logs for details.", "danger")


@bp.get("/profile")
@login_required
def profile():
    # Redirect old profile route to new unified settings page
    return redirect(url_for("main.settings", tab="profile"))


@bp.post("/profile")
@login_required
def update_profile():
    # Redirect old profile POST to new handler
    errors, password_changed, avatar_fetched = _update_user_profile(request.form, current_user)

    if errors:
        for message in errors:
            flash(message, "danger")
        db.session.rollback()
    else:
        db.session.commit()
        flash("Profile updated.", "success")
        if password_changed:
            flash("Password updated.", "success")
        if avatar_fetched:
            flash("Using your Last.fm profile picture. Change the Profile image URL field to use a custom avatar.", "info")
        _refresh_personal_sources(current_user)
    return redirect(url_for("main.settings", tab="profile"))
