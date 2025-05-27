from datetime import datetime
from extensions import db


class Share(db.Model):
    """Model representing a social media share of content."""

    __tablename__ = "shares"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Foreign keys
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content_id = db.Column(
        db.Integer, db.ForeignKey("content.id", ondelete="CASCADE"), nullable=False
    )

    # Share details
    platform = db.Column(db.Text, nullable=False)  # e.g., 'linkedin', 'twitter', etc.
    post_content = db.Column(
        db.Text, nullable=False
    )  # The actual content that was posted
    post_url = db.Column(db.Text)  # URL to the post if available

    # Relationships
    user = db.relationship(
        "User",
        backref=db.backref("shares", lazy="dynamic", cascade="all, delete-orphan"),
    )
    content = db.relationship("Content", back_populates="shares")

    def __repr__(self):
        return f"<Share {self.id}: {self.platform} by {self.user.name}>"

    @classmethod
    def get_share_count(cls, content_id):
        """Get the total number of shares for a content item."""
        return cls.query.filter_by(content_id=content_id).count()

    @classmethod
    def get_platform_share_counts(cls, content_id):
        """Get share counts broken down by platform for a content item."""
        from sqlalchemy import func

        return (
            db.session.query(cls.platform, func.count(cls.id).label("count"))
            .filter_by(content_id=content_id)
            .group_by(cls.platform)
            .all()
        )
