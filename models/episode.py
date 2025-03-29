"""
Episode model for podcast episodes.
"""

from datetime import datetime
from extensions import db


class Episode(db.Model):
    __tablename__ = "episodes"

    id = db.Column(db.Integer, primary_key=True)
    episode_number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    player_url = db.Column(db.String(500), nullable=False)
    image_url = db.Column(db.String(500), nullable=True)  # New field for episode image
    publish_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"<Episode {self.episode_number}: {self.title}>"
