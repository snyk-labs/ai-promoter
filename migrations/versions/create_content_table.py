"""Create unified content table

Revision ID: create_content_table
Revises: dd6e188ecf40
Create Date: 2025-05-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'create_content_table'
down_revision = 'dd6e188ecf40'
branch_labels = None
depends_on = None


def upgrade():
    # Create new content table
    op.create_table(
        'content',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('content_type', sa.String(length=50), nullable=False),
        sa.Column('scraped_content', sa.Text(), nullable=True),
        sa.Column('excerpt', sa.Text(), nullable=True),
        sa.Column('image_url', sa.String(length=500), nullable=True),
        sa.Column('author', sa.String(length=100), nullable=True),
        sa.Column('publish_date', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('source', sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('url')
    )

    # Drop old content tables
    op.drop_table('posts')
    op.drop_table('videos')
    op.drop_table('episodes')


def downgrade():
    # Recreate old content tables
    op.create_table(
        'posts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('excerpt', sa.Text(), nullable=True),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('image_url', sa.String(length=500), nullable=True),
        sa.Column('author', sa.String(length=100), nullable=True),
        sa.Column('publish_date', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('source', sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'videos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('video_id', sa.String(length=20), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('excerpt', sa.Text(), nullable=True),
        sa.Column('thumbnail_url', sa.String(length=500), nullable=True),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('channel_name', sa.String(length=100), nullable=True),
        sa.Column('channel_id', sa.String(length=50), nullable=True),
        sa.Column('publish_date', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('duration', sa.String(length=20), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('video_id')
    )

    op.create_table(
        'episodes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('episode_number', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('player_url', sa.String(length=500), nullable=False),
        sa.Column('image_url', sa.String(length=500), nullable=True),
        sa.Column('publish_date', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Drop new content table
    op.drop_table('content') 