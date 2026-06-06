from __future__ import annotations

from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class LidarrServer(db.Model):
    __tablename__ = "lidarr_servers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    url = db.Column(db.String(512), nullable=False, default="")
    api_key = db.Column(db.String(256), nullable=False, default="")
    root_folder_path = db.Column(db.String(512), nullable=True)
    quality_profile_id = db.Column(db.Integer, nullable=True)
    metadata_profile_id = db.Column(db.Integer, nullable=True)
    api_timeout = db.Column(db.Float, default=120.0, nullable=False)
    fallback_to_top_result = db.Column(db.Boolean, default=False, nullable=False)
    search_for_missing_albums = db.Column(db.Boolean, default=False, nullable=False)
    dry_run = db.Column(db.Boolean, default=False, nullable=False)
    monitor_option = db.Column(db.String(64), nullable=True)
    monitored = db.Column(db.Boolean, default=True, nullable=False)
    monitor_new_items = db.Column(db.String(64), nullable=True)
    albums_to_monitor = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    created_by = db.relationship("User", foreign_keys=[created_by_id], backref="created_servers")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LidarrServer id={self.id} name={self.name!r} active={self.is_active}>"


class AppSetting(db.Model):
    """Single key-value store for app-wide settings (replaces settings_config.json)."""
    __tablename__ = "app_settings"

    key = db.Column(db.String(128), primary_key=True)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AppSetting {self.key!r}>"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    oidc_id = db.Column(db.String(256), unique=True, nullable=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=True)
    display_name = db.Column(db.String(120), nullable=True)
    avatar_url = db.Column(db.String(512), nullable=True)
    lastfm_username = db.Column(db.String(120), nullable=True)
    listenbrainz_username = db.Column(db.String(120), nullable=True)
    # Per-user API keys (optional - fall back to global if not set)
    lastfm_api_key = db.Column(db.String(255), nullable=True)
    lastfm_api_secret = db.Column(db.String(255), nullable=True)
    youtube_api_key = db.Column(db.String(255), nullable=True)
    openai_api_key = db.Column(db.String(512), nullable=True)
    openai_api_base = db.Column(db.String(512), nullable=True)
    openai_model = db.Column(db.String(128), nullable=True)
    openai_extra_headers = db.Column(db.Text(), nullable=True)
    openai_max_seed_artists = db.Column(db.Integer(), nullable=True)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    wizard_completed = db.Column(db.Boolean, default=False, nullable=False, server_default='0')
    lidarr_server_id = db.Column(db.Integer, db.ForeignKey("lidarr_servers.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    lidarr_server = db.relationship("LidarrServer", foreign_keys=[lidarr_server_id], backref="assigned_users")

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, raw_password)

    @property
    def name(self) -> str:
        return self.display_name or self.username

    def __repr__(self) -> str:  # pragma: no cover - representation helper
        return f"<User id={self.id} username={self.username!r} admin={self.is_admin}>"


class ArtistRequest(db.Model):
    __tablename__ = "artist_requests"

    id = db.Column(db.Integer, primary_key=True)
    artist_name = db.Column(db.String(255), nullable=False, index=True)
    requested_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False)  # pending, approved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    requested_by = db.relationship("User", foreign_keys=[requested_by_id], backref="requested_artists")
    approved_by = db.relationship("User", foreign_keys=[approved_by_id], backref="approved_requests")

    def __repr__(self) -> str:  # pragma: no cover - representation helper
        return f"<ArtistRequest id={self.id} artist='{self.artist_name}' status={self.status}>"
