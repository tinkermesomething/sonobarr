"""add app_settings table

Revision ID: 20260607_03
Revises: 20260607_02
Create Date: 2026-06-07 00:02:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '20260607_03'
down_revision = '20260607_02'
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())
    tables = inspector.get_table_names()
    if 'app_settings' not in tables:
        op.create_table(
            'app_settings',
            sa.Column('key', sa.String(length=128), nullable=False),
            sa.Column('value', sa.Text(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint('key'),
        )


def downgrade():
    op.drop_table('app_settings')
