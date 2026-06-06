"""add wizard_completed and lidarr_server_id to users

Revision ID: 20260607_04
Revises: 20260607_03
Create Date: 2026-06-07 00:03:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '20260607_04'
down_revision = '20260607_03'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("users")}

    with op.batch_alter_table('users', schema=None) as batch_op:
        if 'wizard_completed' not in existing_columns:
            batch_op.add_column(
                sa.Column('wizard_completed', sa.Boolean(), nullable=False, server_default='0')
            )
        if 'lidarr_server_id' not in existing_columns:
            batch_op.add_column(
                sa.Column('lidarr_server_id', sa.Integer(), nullable=True)
            )


def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("users")}

    with op.batch_alter_table('users', schema=None) as batch_op:
        if 'lidarr_server_id' in existing_columns:
            batch_op.drop_column('lidarr_server_id')
        if 'wizard_completed' in existing_columns:
            batch_op.drop_column('wizard_completed')
