"""
Post model for blog posts.
"""

from datetime import datetime
from extensions import db


class Post(db.Model):
    __tablename__ = "posts"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    excerpt = db.Column(db.Text, nullable=True)
    url = db.Column(db.String(500), nullable=False)
    image_url = db.Column(db.String(500), nullable=True)  # New field for blog image
    author = db.Column(db.String(100), nullable=True)
    publish_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    source = db.Column(db.String(100), nullable=True)  # To track the blog source

    def __repr__(self):
        return f"<Post {self.id}: {self.title}>"
