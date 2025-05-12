import logging
import os
import sys
from datetime import datetime
import click

# Configure logging to output to STDOUT with a more detailed format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from flask import Flask, g, session
from celery import Celery # Import Celery class
from celery import Task as CeleryTask

from extensions import db, login_manager, migrate
from models import User
from cli import init_db, list_routes, create_admin
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
    celery_app = Celery(app.name, task_cls=FlaskTask, include=['tasks.content', 'tasks.promote'])
    celery_app.config_from_object(app.config["CELERY"]) # Load from CELERY dict in Flask config
    celery_app.set_default() # Make this the default Celery app for @shared_task
    app.extensions["celery"] = celery_app
    return celery_app

def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Load configuration from config.py
    app.config.from_object(Config)

    celery_instance = celery_init_app(app) # Initialize Celery and get the instance
    # Note: celery_instance is now the one to use if needed elsewhere in create_app scope,
    # or access via app.extensions["celery"]

    # Add template context processors
    @app.context_processor
    def inject_now():
        return {'now': datetime.utcnow()}

    # Add template helpers
    app.jinja_env.globals.update(
        getPlatformColor=get_platform_color,
        getPlatformIcon=get_platform_icon
    )

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

    # Add company configuration
    app.config["COMPANY_NAME"] = os.environ.get("COMPANY_NAME", "Your Company")
    app.config["UTM_PARAMS"] = os.environ.get("UTM_PARAMS", "")

    # Add Okta configuration to app config
    app.config["OKTA_ENABLED"] = OKTA_ENABLED

    # Add Firecrawl configuration
    firecrawl_api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not firecrawl_api_key:
        app.logger.warning("FIRECRAWL_API_KEY not set - content scraping will be disabled")
    app.config["FIRECRAWL_API_KEY"] = firecrawl_api_key

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

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
    app.register_blueprint(api_bp, url_prefix='/api')  # API routes
    app.register_blueprint(auth_bp, url_prefix='/auth')  # Auth routes
    app.register_blueprint(admin_bp, url_prefix='/admin')  # Admin routes

    # Register Okta blueprint if enabled
    if app.config["OKTA_ENABLED"]:
        app.register_blueprint(okta_auth_bp)
        app.logger.info("Okta SSO integration enabled")
    else:
        app.logger.info("Okta SSO integration disabled")

    # Register CLI commands
    app.cli.add_command(init_db)
    app.cli.add_command(list_routes)
    app.cli.add_command(create_admin)

    @app.cli.command("worker")
    @click.option('--loglevel', default='info', help='Log level (debug/info/warning/error)')
    def worker(loglevel):
        """Run the Celery worker."""
        from make_celery import celery
        celery.worker_main(['worker', f'--loglevel={loglevel}'])

    @app.before_request
    def before_request():
        g.user = getattr(session, 'user', None)

    return app


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5001)
