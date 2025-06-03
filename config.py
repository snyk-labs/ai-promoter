import os
from datetime import timedelta
from celery.schedules import crontab
import logging
import ssl

config_logger = logging.getLogger(__name__)


class Config:
    """Base configuration class."""

    # Flask configuration
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-please-change")

    # Company configuration
    COMPANY_NAME = os.environ.get("COMPANY_NAME", "Your Company")
    UTM_PARAMS = os.environ.get("UTM_PARAMS", "")
    DASHBOARD_BANNER = os.environ.get("DASHBOARD_BANNER", "")
    BASE_URL = os.environ.get("BASE_URL", "http://localhost:5001")
    COMPANY_PRIVACY_NOTICE = os.environ.get("COMPANY_PRIVACY_NOTICE", "")

    # Content feeds configuration
    raw_content_feeds = os.environ.get("CONTENT_FEEDS")
    if raw_content_feeds:
        if "|" in raw_content_feeds:
            CONTENT_FEEDS = raw_content_feeds.split("|")
        else:
            CONTENT_FEEDS = [raw_content_feeds]
    else:
        CONTENT_FEEDS = []

    # Database configuration
    # Construct default SQLite path relative to this config file's directory
    _DEFAULT_SQLITE_PATH = os.path.join(
        os.path.abspath(os.path.dirname(__file__)), "promoter.db"
    )
    _DEFAULT_SQLALCHEMY_DATABASE_URI = "sqlite:///" + _DEFAULT_SQLITE_PATH

    database_url_env = os.environ.get("DATABASE_URL")
    if database_url_env:
        if database_url_env.startswith("postgres://"):
            # Handle Heroku-style 'postgres://' prefix
            SQLALCHEMY_DATABASE_URI = database_url_env.replace(
                "postgres://", "postgresql://", 1
            )
        else:
            # Covers 'postgresql://', 'sqlite:///', and other SQLAlchemy-compatible URIs
            SQLALCHEMY_DATABASE_URI = database_url_env
    else:
        SQLALCHEMY_DATABASE_URI = _DEFAULT_SQLALCHEMY_DATABASE_URI

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Celery Configuration Dictionary
    # Following the pattern from https://flask.palletsprojects.com/en/stable/patterns/celery/
    REDIS_URL_DEFAULT = "redis://localhost:6379/0"  # Define a default
    REDIS_URL = os.environ.get("REDIS_URL", REDIS_URL_DEFAULT)

    # Prepare Redis connection kwargs for direct Redis client use (e.g., Flask-Redis)
    REDIS_CONNECTION_KWARGS = {"decode_responses": True}
    if REDIS_URL and REDIS_URL.startswith("rediss://"):
        # For direct Redis client connections
        REDIS_CONNECTION_KWARGS["ssl_cert_reqs"] = ssl.CERT_NONE
        # Modify REDIS_URL to include ssl_cert_reqs parameter for Celery
        if "?" not in REDIS_URL:
            REDIS_URL += "?ssl_cert_reqs=none"
        else:
            REDIS_URL += "&ssl_cert_reqs=none"

    # SSL options for Celery broker and backend if using rediss://
    CELERY_BROKER_SSL_CONFIG = None
    CELERY_BACKEND_SSL_CONFIG = {}  # Default to empty dict for backend settings
    if REDIS_URL and REDIS_URL.startswith("rediss://"):
        common_ssl_params = {"ssl_cert_reqs": ssl.CERT_NONE}
        CELERY_BROKER_SSL_CONFIG = common_ssl_params
        CELERY_BACKEND_SSL_CONFIG = common_ssl_params

    CELERY = dict(
        broker_url=REDIS_URL,  # Use the potentially modified REDIS_URL
        result_backend=REDIS_URL,  # Use the potentially modified REDIS_URL
        # Use Redis-specific SSL settings
        broker_use_ssl=CELERY_BROKER_SSL_CONFIG,
        redis_backend_settings=CELERY_BACKEND_SSL_CONFIG,
        task_ignore_result=True,  # Default, can be overridden per task
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="US/Eastern",
        enable_utc=True,
        task_track_started=True,
        task_time_limit=3600,  # 1 hour
        worker_max_tasks_per_child=200,
        worker_prefetch_multiplier=1,
        broker_connection_retry_on_startup=True,
        beat_schedule={
            "initiate-posts-friday": {
                "task": "tasks.notifications.initiate_posts",
                "schedule": crontab(hour=9, minute=0, day_of_week="friday"),
            },
            "fetch-content-hourly": {
                "task": "tasks.fetch_content.fetch_content_task",
                "schedule": crontab(
                    minute=0, hour="*"
                ),  # Runs at the start of every hour
            },
            "refresh-linkedin-tokens-daily": {
                "task": "tasks.linkedin.refresh_expiring_tokens",
                "schedule": crontab(hour=3, minute=0),
            },
        },
    )

    # Okta configuration
    OKTA_ENABLED = os.environ.get("OKTA_ENABLED", "false").lower() == "true"
    OKTA_CLIENT_ID = os.environ.get("OKTA_CLIENT_ID")
    OKTA_CLIENT_SECRET = os.environ.get("OKTA_CLIENT_SECRET")
    OKTA_ISSUER = os.environ.get("OKTA_ISSUER")
    OKTA_REDIRECT_URI = os.environ.get("OKTA_REDIRECT_URI")

    # API Keys
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY")

    # LinkedIn Configuration (Native LinkedIn only)
    LINKEDIN_CLIENT_ID = os.environ.get("LINKEDIN_CLIENT_ID")
    LINKEDIN_CLIENT_SECRET = os.environ.get("LINKEDIN_CLIENT_SECRET")

    # LinkedIn keys are required for LinkedIn integration (except during testing)
    TESTING = os.environ.get("TESTING", "false").lower() == "true"
    if not TESTING:
        if not LINKEDIN_CLIENT_ID:
            raise ValueError("LINKEDIN_CLIENT_ID is required for LinkedIn integration")
        if not LINKEDIN_CLIENT_SECRET:
            raise ValueError(
                "LINKEDIN_CLIENT_SECRET is required for LinkedIn integration"
            )

    # Mail configuration
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() in ["true", "on", "1"]
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@example.com")
    EMAIL_ENABLED = os.environ.get("EMAIL_ENABLED", "false").lower() == "true"

    # Slack Configuration
    SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
    SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")
    SLACK_DEFAULT_CHANNEL_ID = os.environ.get("SLACK_DEFAULT_CHANNEL_ID")
    SLACK_NOTIFICATIONS_ENABLED = (
        os.environ.get("SLACK_NOTIFICATIONS_ENABLED", "false").lower() == "true"
    )

    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # Settings for Judoscale (for autoscaling our Heroku dynos based on load)
    JUDOSCALE = {"LOG_LEVEL": "DEBUG"}


# Log information about the configured REDIS_URL
# This runs when the config module is first imported.
# Ensure this is placed *after* the Config class definition.
if hasattr(Config, "REDIS_URL") and Config.REDIS_URL:
    config_logger.info(f"Configuration: REDIS_URL is set to: {Config.REDIS_URL}")
    if "localhost" in Config.REDIS_URL or "127.0.0.1" in Config.REDIS_URL:
        config_logger.info("Configuration: REDIS_URL appears to be a local instance.")
    elif Config.REDIS_URL.startswith("rediss://"):
        config_logger.info(
            "Configuration: REDIS_URL appears to be a secure (rediss://) instance."
        )
else:
    # This case should not be reached if REDIS_URL_DEFAULT is a non-empty string.
    config_logger.warning(
        "Configuration: REDIS_URL is not defined or is empty, even after considering defaults."
    )
