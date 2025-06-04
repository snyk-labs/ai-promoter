import logging
import os
import sys
from datetime import datetime, timezone
import click
from urllib.parse import urlparse

# import pytest # pytest is no longer directly used here

from judoscale.flask import Judoscale
from judoscale.celery import judoscale_celery

# Configure logging to output to STDOUT with a more detailed format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from flask import Flask, g, session
from celery import Celery  # Import Celery class
from celery import Task as CeleryTask

from extensions import db, login_manager, migrate, mail, redis_client
from models import User
from cli import (
    init_db,
    create_admin,
    beat_command,
    trigger_posts_command,
    trigger_fetch_content_command,
    test_command,
    lint_command,
)
from helpers.okta import OKTA_ENABLED, validate_okta_config
from helpers.template_helpers import get_platform_color, get_platform_icon
from config import Config

# celery_app.py is now just a target for CLI, no instance imported from there.

# Import blueprints from views package
from views.main import bp as main_bp
from views.api import bp as api_bp
from views.auth import bp as auth_bp
from views.okta_auth import bp as okta_auth_bp
from views.admin import bp as admin_bp

# Our Judoscale global instance
judoscale = Judoscale()


def celery_init_app(app: Flask) -> Celery:
    """Create and configure a new Celery instance, integrated with Flask."""

    class FlaskTask(CeleryTask):
        def __call__(self, *args: object, **kwargs: object) -> object:
            with app.app_context():
                return self.run(*args, **kwargs)

    # Create the Celery app instance here
    # It will use app.name and be configured with FlaskTask as default task class
    # Tasks should be in an 'include' list for the worker to find if not using full autodiscovery.
    # Common practice is to have tasks in a 'tasks.py' or a 'tasks' package.
    # If your tasks are in 'tasks/content.py', Celery needs to be able to import 'tasks.content'.
    celery_app = Celery(
        app.name,
        task_cls=FlaskTask,
        include=[
            "tasks.content",
            "tasks.promote",
            "tasks.notifications",
            "tasks.fetch_content",
        ],
    )
    celery_app.config_from_object(
        app.config["CELERY"]
    )  # Load from CELERY dict in Flask config
    celery_app.set_default()  # Make this the default Celery app for @shared_task
    app.extensions["celery"] = celery_app

    return celery_app


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Load configuration from config.py
    app.config.from_object(Config)

    celery_instance = celery_init_app(app)  # Initialize Celery and get the instance
    # Note: celery_instance is now the one to use if needed elsewhere in create_app scope,
    # or access via app.extensions["celery"]

    # Initialize Judoscale (for autoscaling our Heroku dynos based on load)
    judoscale.init_app(app)
    # Initialize Judoscale for Celery (for autoscaling our Heroku dynos based on load)
    judoscale_celery(celery_instance, extra_config=app.config["JUDOSCALE"])

    # Add template context processors
    @app.context_processor
    def inject_now():
        return {"now": datetime.now()}

    # Add template helpers
    app.jinja_env.globals.update(
        getPlatformColor=get_platform_color, getPlatformIcon=get_platform_icon
    )

    # Database Configuration
    # Configuration is now loaded from Config object.
    # Log the database being used based on the loaded configuration.
    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not db_uri:
        app.logger.warning("SQLALCHEMY_DATABASE_URI is not configured.")
    elif "postgres" in db_uri:  # Covers postgresql and postgres
        # Avoid logging sensitive parts of the URI if present
        uri_to_log = db_uri.split("@")[-1] if "@" in db_uri else db_uri
        app.logger.info(f"Using PostgreSQL database: {uri_to_log}")
    elif "sqlite" in db_uri:
        app.logger.info(f"Using SQLite database: {db_uri}")
    else:
        # For other database types, log the scheme
        uri_scheme = db_uri.split(":")[0] if ":" in db_uri else "Unknown"
        app.logger.info(f"Using {uri_scheme} database.")

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    # Configure Flask-Mail
    mail.init_app(app)

    # Configure Redis
    redis_client.init_app(app)
    app.redis_client = redis_client

    # Celery also uses this REDIS_URL via app.config["CELERY"].
    redis_url_from_app_config = app.config.get("REDIS_URL")
    app.logger.info(f"Application intends to use Redis at: {redis_url_from_app_config}")

    # Validate Okta configuration (ensure it runs after app.config is fully set)
    with app.app_context():
        try:
            validate_okta_config()
        except ValueError as e:
            app.logger.warning(f"Okta configuration error: {str(e)}")
            app.config["OKTA_ENABLED"] = False

    # User loader for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID."""
        return db.session.get(User, int(user_id))

    # Register blueprints
    app.register_blueprint(main_bp)  # Main routes
    app.register_blueprint(api_bp, url_prefix="/api")  # API routes
    app.register_blueprint(auth_bp, url_prefix="/auth")  # Auth routes
    app.register_blueprint(admin_bp, url_prefix="/admin")  # Admin routes

    # Register Okta blueprint if enabled
    if app.config["OKTA_ENABLED"]:
        app.register_blueprint(okta_auth_bp)
        app.logger.info("Okta SSO integration enabled")
    else:
        app.logger.info("Okta SSO integration disabled")

    # Register CLI commands
    app.cli.add_command(init_db)
    app.cli.add_command(create_admin)
    app.cli.add_command(beat_command)
    app.cli.add_command(trigger_posts_command)
    app.cli.add_command(trigger_fetch_content_command)
    app.cli.add_command(test_command)
    app.cli.add_command(lint_command)

    @app.cli.command("worker")
    @click.option(
        "--loglevel", default="info", help="Log level (debug/info/warning/error)"
    )
    def worker(loglevel):
        """Run the Celery worker."""
        from make_celery import celery

        celery.worker_main(["worker", f"--loglevel={loglevel}"])

    @app.before_request
    def before_request():
        g.user = getattr(session, "user", None)

    return app


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
    app.run(debug=True, host="0.0.0.0", port=5001)
