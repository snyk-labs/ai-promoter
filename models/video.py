"""
Video model for YouTube videos.
"""

from datetime import datetime
from extensions import db


class Video(db.Model):
    __tablename__ = "videos"

    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.String(20), nullable=False, unique=True)  # YouTube video ID
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)  # Full description
    excerpt = db.Column(db.Text, nullable=True)  # Shorter description for display
    thumbnail_url = db.Column(db.String(500), nullable=True)
    url = db.Column(db.String(500), nullable=False)  # YouTube video URL
    channel_name = db.Column(db.String(100), nullable=True)
    channel_id = db.Column(db.String(50), nullable=True)
    publish_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    duration = db.Column(db.String(20), nullable=True)  # Duration in ISO 8601 format

    def __repr__(self):
        return f"<Video {self.video_id}: {self.title}>"
