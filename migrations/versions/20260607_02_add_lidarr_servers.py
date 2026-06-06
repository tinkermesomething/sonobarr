"""add lidarr_servers table

Revision ID: 20260607_02
Revises: 20260607_01
Create Date: 2026-06-07 00:01:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '20260607_02'
down_revision = '20260607_01'
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())
    tables = inspector.get_table_names()
    if 'lidarr_servers' not in tables:
        op.create_table(
            'lidarr_servers',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=128), nullable=False),
            sa.Column('url', sa.String(length=512), nullable=False, server_default=''),
            sa.Column('api_key', sa.String(length=256), nullable=False, server_default=''),
            sa.Column('root_folder_path', sa.String(length=512), nullable=True),
            sa.Column('quality_profile_id', sa.Integer(), nullable=True),
            sa.Column('metadata_profile_id', sa.Integer(), nullable=True),
            sa.Column('api_timeout', sa.Float(), nullable=False, server_default='120.0'),
            sa.Column('fallback_to_top_result', sa.Boolean(), nullable=False, server_default='0'),
            sa.Column('search_for_missing_albums', sa.Boolean(), nullable=False, server_default='0'),
            sa.Column('dry_run', sa.Boolean(), nullable=False, server_default='0'),
            sa.Column('monitor_option', sa.String(length=64), nullable=True),
            sa.Column('monitored', sa.Boolean(), nullable=False, server_default='1'),
            sa.Column('monitor_new_items', sa.String(length=64), nullable=True),
            sa.Column('albums_to_monitor', sa.Text(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
            sa.Column('created_by_id', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id'),
        )


def downgrade():
    op.drop_table('lidarr_servers')
