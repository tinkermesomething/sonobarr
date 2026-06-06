"""drop unused auto_approve_artist_requests column

Revision ID: 20260607_01
Revises: 20251223_02
Create Date: 2026-06-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '20260607_01'
down_revision = '20251223_02'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("users")}

    with op.batch_alter_table('users', schema=None) as batch_op:
        if "auto_approve_artist_requests" in existing_columns:
            batch_op.drop_column('auto_approve_artist_requests')


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("users")}

    with op.batch_alter_table('users', schema=None) as batch_op:
        if "auto_approve_artist_requests" not in existing_columns:
            batch_op.add_column(
                sa.Column('auto_approve_artist_requests', sa.Boolean(), nullable=False, server_default='0')
            )
