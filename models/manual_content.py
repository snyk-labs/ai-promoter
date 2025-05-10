from datetime import datetime
from extensions import db

class ManualContent(db.Model):
    """Model for manually added content by admins."""
    __tablename__ = 'manual_content'

    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    content_type = db.Column(db.String(50), nullable=False)  # 'article', 'video', 'podcast', 'asset'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    created_by = db.relationship('User', backref=db.backref('manual_content', lazy=True))

    def __repr__(self):
        return f'<ManualContent {self.url}>' 