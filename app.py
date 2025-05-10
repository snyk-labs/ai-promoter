import logging
import os
import sys

# Configure logging to output to STDOUT with a more detailed format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from flask import Flask
from flask_migrate import Migrate

from extensions import db, login_manager
from models import User
from cli import init_db, sync_podcast, sync_blog, sync_youtube, list_routes, create_admin
from helpers.okta import OKTA_ENABLED, validate_okta_config

# Import blueprints from views package
from views.main import bp as main_bp
from views.api import bp as api_bp
from views.auth import bp as auth_bp
from views.okta_auth import bp as okta_auth_bp
from views.admin import bp as admin_bp


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Database Configuration
    # Use DATABASE_URL environment variable if available
    # Otherwise, fall back to default SQLite for development
    database_url = os.environ.get("DATABASE_URL")

    if database_url:
        # If DATABASE_URL is provided, use it directly
        if database_url.startswith("postgres://"):
            # Handle potential 'postgres://' format that Heroku might provide
            database_url = database_url.replace("postgres://", "postgresql://", 1)
            app.config["SQLALCHEMY_DATABASE_URI"] = database_url
            app.logger.info(
                f"Using PostgreSQL database from environment: {database_url.split('@')[0]}@..."
            )
        elif database_url.startswith("sqlite:///"):
            # Handle SQLite URLs in DATABASE_URL
            app.config["SQLALCHEMY_DATABASE_URI"] = database_url
            app.logger.info(f"Using custom SQLite database: {database_url}")
        else:
            # Handle other database types
            app.config["SQLALCHEMY_DATABASE_URI"] = database_url
            app.logger.info(
                f"Using database from environment: {database_url.split(':')[0]}"
            )
    else:
        # Fall back to default SQLite for development
        basedir = os.path.abspath(os.path.dirname(__file__))
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(
            basedir, "promoter.db"
        )
        app.logger.info("Using default SQLite database for development")

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Set secret key for session management
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-key-please-change")

    # Add Okta configuration to app config
    app.config["OKTA_ENABLED"] = OKTA_ENABLED

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)

    # Initialize Flask-Migrate
    migrate = Migrate(app, db)

    # Validate Okta configuration
    with app.app_context():
        try:
            validate_okta_config()
        except ValueError as e:
            app.logger.warning(f"Okta configuration error: {str(e)}")
            app.config["OKTA_ENABLED"] = False

    # User loader for Flask-Login
    @login_manager.user_loader
    def load_user(id):
        """Load user by ID."""
        return db.session.get(User, int(id))

    # Register blueprints
    app.register_blueprint(main_bp)  # Main routes
    app.register_blueprint(api_bp)  # API routes
    app.register_blueprint(auth_bp)  # Auth routes
    app.register_blueprint(admin_bp)  # Admin routes

    # Register Okta blueprint if enabled
    if app.config["OKTA_ENABLED"]:
        app.register_blueprint(okta_auth_bp)
        app.logger.info("Okta SSO integration enabled")
    else:
        app.logger.info("Okta SSO integration disabled")

    # Register CLI commands
    app.cli.add_command(sync_podcast)
    app.cli.add_command(init_db)
    app.cli.add_command(sync_blog)
    app.cli.add_command(sync_youtube)
    app.cli.add_command(list_routes)
    app.cli.add_command(create_admin)

    return app


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
    app.run(debug=True)
