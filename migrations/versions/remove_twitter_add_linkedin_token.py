"""Remove Twitter field and add LinkedIn token

Revision ID: remove_twitter_add_linkedin_token
Revises: dd6e188ecf40
Create Date: 2024-03-19 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "remove_twitter_add_linkedin_token"
down_revision = "dd6e188ecf40"
branch_labels = None
depends_on = None


def upgrade():
    # Add linkedin_token column
    op.add_column('users', sa.Column('linkedin_token', sa.Text(), nullable=True))
    
    # Drop x_authorized column
    op.drop_column('users', 'x_authorized')


def downgrade():
    # Add back x_authorized column
    op.add_column('users', sa.Column('x_authorized', sa.Boolean(), nullable=False, server_default='0'))
    
    # Drop linkedin_token column
    op.drop_column('users', 'linkedin_token') 