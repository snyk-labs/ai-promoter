"""Merge heads

Revision ID: e0fba490788c
Revises: 963e028232ac, create_content_table
Create Date: 2025-05-10 12:20:52.954001

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e0fba490788c'
down_revision = ('963e028232ac', 'create_content_table')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
