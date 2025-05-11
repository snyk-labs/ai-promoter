"""Add updated_at column to content table

Revision ID: c362adca1754
Revises: 40777968a2bf
Create Date: 2025-05-11 14:54:51.338000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime


# revision identifiers, used by Alembic.
revision = 'c362adca1754'
down_revision = '40777968a2bf'
branch_labels = None
depends_on = None


def upgrade():
    # Add updated_at column with default value
    with op.batch_alter_table('content', schema=None) as batch_op:
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')))


def downgrade():
    # Remove updated_at column
    with op.batch_alter_table('content', schema=None) as batch_op:
        batch_op.drop_column('updated_at')
