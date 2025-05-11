"""Merge heads

Revision ID: merge_heads
Revises: ec798e612e0c, remove_twitter_add_linkedin_token
Create Date: 2024-03-19 11:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "merge_heads"
down_revision = ("ec798e612e0c", "remove_twitter_add_linkedin_token")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass 