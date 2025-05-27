"""
User model for authentication and profile information.
"""

from datetime import datetime
import bcrypt
from flask_login import UserMixin
from extensions import db
from sqlalchemy import text, event
from celery import chain

# Import the Celery task
# Ensure your Celery app is structured so this import doesn't cause circular dependencies.
# This might mean defining tasks in a way that they don't import models directly at the module level,
# or ensuring the Celery app instance is available.
from tasks.slack_tasks import send_slack_invitation_task, slack_get_user_id


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.Text, unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=True)  # Now nullable for SSO users
    name = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    bio = db.Column(db.Text, nullable=True)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)

    # Authentication source - using server_default for SQLite compatibility
    auth_type = db.Column(db.Text, nullable=False, server_default=text("'password'"))

    # Okta user identifier
    okta_id = db.Column(db.Text, nullable=True, unique=True)

    # Slack user identifier
    slack_id = db.Column(
        db.Text, nullable=True, unique=True
    )  # Slack User IDs are typically shorter, e.g. U0xxxxxxx or W0xxxxxxx

    # Arcade LinkedIn integration fields
    linkedin_authorized = db.Column(db.Boolean, default=False, nullable=False)
    linkedin_token = db.Column(db.Text, nullable=True)

    # Native LinkedIn Integration Fields
    linkedin_native_id = db.Column(
        db.Text, nullable=True, unique=True
    )  # LinkedIn User ID (sub)
    linkedin_native_access_token = db.Column(db.Text, nullable=True)
    linkedin_native_refresh_token = db.Column(db.Text, nullable=True)
    linkedin_native_token_expires_at = db.Column(db.DateTime, nullable=True)
    # Consider adding linkedin_native_refresh_token_expires_at if LinkedIn provides this and it's useful

    # Autonomous mode for automatic posting
    autonomous_mode = db.Column(db.Boolean, default=False, nullable=False)

    # Field for example social posts
    example_social_posts = db.Column(db.Text, nullable=True)

    def set_password(self, password):
        """Hash password with bcrypt using work factor 13."""
        salt = bcrypt.gensalt(rounds=13)
        self.password_hash = bcrypt.hashpw(password.encode("utf-8"), salt).decode(
            "utf-8"
        )

    def check_password(self, password):
        """Check if provided password matches the hash."""
        if not self.password_hash:
            return False
        return bcrypt.checkpw(
            password.encode("utf-8"), self.password_hash.encode("utf-8")
        )

    @classmethod
    def find_or_create_okta_user(cls, okta_id, email, name):
        """Find existing user by Okta ID or create a new one."""
        user = cls.query.filter_by(okta_id=okta_id).first()
        if user:
            return user

        # Check if a user exists with this email but no Okta ID (existing user now using SSO)
        existing_user = cls.query.filter_by(email=email).first()
        if existing_user:
            # Update existing user with Okta ID
            existing_user.okta_id = okta_id
            existing_user.auth_type = "okta"
            return existing_user

        # Create new user
        user = cls(email=email, name=name, auth_type="okta", okta_id=okta_id)
        db.session.add(user)
        db.session.commit()
        return user

    def __repr__(self):
        return f"<User {self.email}>"


# SQLAlchemy event listener for new User instances
@event.listens_for(User, "after_insert")
def after_user_created(mapper, connection, target):
    """
    After a new user is inserted, trigger a Slack invitation task.
    'target' is the User instance that was just inserted.
    """
    # We need to ensure this runs in a context where Celery tasks can be sent.
    # Flask-SQLAlchemy and Celery integration usually handles this if set up correctly.
    # The task will be responsible for handling its own app context if needed.

    # It's also important to ensure this is truly a NEW user.
    # In most simple cases, 'after_insert' on a primary model like User implies new.
    # If there are complex scenarios (like bulk inserts or specific ORM patterns)
    # that might re-trigger this, additional checks might be needed inside the listener.
    # For now, we assume 'after_insert' on User is for new creations.

    print(
        f"User {target.email} (ID: {target.id}) has been created. Queuing Slack ID lookup then invitation."
    )
    # Create a chain: slack_get_user_id runs first, then send_slack_invitation_task
    task_chain = chain(slack_get_user_id.s(target.id), send_slack_invitation_task.s())
    task_chain.apply_async()
