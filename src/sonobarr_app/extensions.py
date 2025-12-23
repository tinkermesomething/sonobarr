from __future__ import annotations

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

from authlib.integrations.flask_client import OAuth

db = SQLAlchemy()
login_manager = LoginManager()
socketio = SocketIO()
csrf = CSRFProtect()
migrate = Migrate()

oidc = OAuth()