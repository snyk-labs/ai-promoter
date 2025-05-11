"""Initial database setup

Revision ID: dd6e188ecf40
Revises:
Create Date: 2024-03-19 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "dd6e188ecf40"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=128), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("auth_type", sa.String(length=20), nullable=False),
        sa.Column("okta_id", sa.String(length=100), nullable=True),
        sa.Column("linkedin_authorized", sa.Boolean(), nullable=False),
        sa.Column("linkedin_token", sa.Text(), nullable=True),
        sa.Column("autonomous_mode", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("okta_id"),
    )

    # Create content table
    op.create_table(
        "content",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("publish_date", sa.DateTime(), nullable=True),
        sa.Column("author", sa.String(length=100), nullable=True),
        sa.Column("submitted_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["submitted_by_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("content")
    op.drop_table("users")
