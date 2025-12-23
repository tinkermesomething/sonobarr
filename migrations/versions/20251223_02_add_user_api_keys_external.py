"""Add per-user external API keys (Last.fm, YouTube, LLM)

Moves external API key configuration from global environment variables
to per-user database columns, enabling personalized API access.

Revision ID: 20251223_02
Revises: 20251222_01
Create Date: 2025-12-23 17:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "20251223_02"
down_revision = "20251222_01"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("users")}

    with op.batch_alter_table("users", schema=None) as batch_op:
        # Last.fm API credentials
        if "lastfm_api_key" not in existing_columns:
            batch_op.add_column(
                sa.Column("lastfm_api_key", sa.String(length=255), nullable=True)
            )
        if "lastfm_api_secret" not in existing_columns:
            batch_op.add_column(
                sa.Column("lastfm_api_secret", sa.String(length=255), nullable=True)
            )

        # YouTube API key
        if "youtube_api_key" not in existing_columns:
            batch_op.add_column(
                sa.Column("youtube_api_key", sa.String(length=255), nullable=True)
            )

        # OpenAI/LLM API settings
        if "openai_api_key" not in existing_columns:
            batch_op.add_column(
                sa.Column("openai_api_key", sa.String(length=512), nullable=True)
            )
        if "openai_model" not in existing_columns:
            batch_op.add_column(
                sa.Column("openai_model", sa.String(length=128), nullable=True)
            )
        if "openai_api_base" not in existing_columns:
            batch_op.add_column(
                sa.Column("openai_api_base", sa.String(length=512), nullable=True)
            )
        if "openai_extra_headers" not in existing_columns:
            batch_op.add_column(
                sa.Column("openai_extra_headers", sa.Text(), nullable=True)
            )
        if "openai_max_seed_artists" not in existing_columns:
            batch_op.add_column(
                sa.Column("openai_max_seed_artists", sa.Integer(), nullable=True)
            )


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("users")}

    with op.batch_alter_table("users", schema=None) as batch_op:
        if "lastfm_api_key" in existing_columns:
            batch_op.drop_column("lastfm_api_key")
        if "lastfm_api_secret" in existing_columns:
            batch_op.drop_column("lastfm_api_secret")
        if "youtube_api_key" in existing_columns:
            batch_op.drop_column("youtube_api_key")
        if "openai_api_key" in existing_columns:
            batch_op.drop_column("openai_api_key")
        if "openai_model" in existing_columns:
            batch_op.drop_column("openai_model")
        if "openai_api_base" in existing_columns:
            batch_op.drop_column("openai_api_base")
        if "openai_extra_headers" in existing_columns:
            batch_op.drop_column("openai_extra_headers")
        if "openai_max_seed_artists" in existing_columns:
            batch_op.drop_column("openai_max_seed_artists")
