"""
Content model for all types of content (articles, videos, podcasts, etc.).
"""

from datetime import datetime
from extensions import db
from models.user import User
from models.share import Share


class Content(db.Model):
    __tablename__ = "content"

    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.Text, nullable=False, unique=True)
    title = db.Column(db.Text, nullable=False)
    scraped_content = db.Column(db.Text, nullable=True)  # Raw markdown content from Firecrawl
    excerpt = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.Text, nullable=True)
    publish_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    context = db.Column(db.Text, nullable=True)  # Additional context for social media posts
    submitted_by_id = db.Column(db.Integer, db.ForeignKey('users.id', name='fk_content_submitted_by_id_users'), nullable=True)
    submitted_by = db.relationship('User', backref=db.backref('submitted_content', lazy=True))
    
    # Relationship with Share model using back_populates
    shares = db.relationship('Share', back_populates='content', lazy='dynamic', cascade='all, delete-orphan')

    @property
    def share_count(self):
        """Get the total number of shares for this content."""
        return self.shares.count()

    @property
    def platform_share_counts(self):
        """Get share counts broken down by platform for this content."""
        from sqlalchemy import func
        return db.session.query(
            Share.platform,
            func.count(Share.id).label('count')
        ).filter_by(content_id=self.id).group_by(Share.platform).all()

    def __repr__(self):
        return f"<Content {self.id}: {self.title}>"

    def delete(self):
        """Delete the content item from the database."""
        db.session.delete(self)
        db.session.commit() 