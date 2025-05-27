from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_mail import Mail
import redis
import ssl # Added for ssl.CERT_NONE
# We will import the helper from app.py
# from urllib.parse import urlparse 

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
mail = Mail()

class RedisClient:
    def __init__(self):
        self.client = None

    def init_app(self, app):
        # from app import _get_safe_redis_url_for_logging # Removed import

        redis_url = app.config.get("REDIS_URL")
        redis_kwargs = app.config.get("REDIS_CONNECTION_KWARGS", {}).copy() # Get from config
        # Ensure decode_responses is True if not provided or overridden by config
        redis_kwargs.setdefault("decode_responses", True)

        # safe_log_url = _get_safe_redis_url_for_logging(redis_url) # Use the helper # Removed usage

        if not redis_url:
            app.logger.warning(f"RedisClient: REDIS_URL is not configured. Client will not be initialized.") # Updated log
            self.client = None
            return

        app.logger.info(f"RedisClient: Attempting to connect using REDIS_URL: {redis_url} with options: {redis_kwargs}") # Updated log

        try:
            # kwargs = {"decode_responses": True} # Old kwargs initialization
            # if redis_url.startswith("rediss://"): # Logic moved to config.py
                # For rediss://, disable SSL certificate verification for simplicity in environments
                # like Heroku where local CA certs might not be set up.
                # This is less secure for untrusted networks but common for managed services.
                # kwargs['ssl_cert_reqs'] = ssl.CERT_NONE # Logic moved to config.py
                # app.logger.info("RedisClient: rediss:// detected, using ssl_cert_reqs=ssl.CERT_NONE.") # Logic moved to config.py

            self.client = redis.from_url(redis_url, **redis_kwargs) # Use new redis_kwargs
            self.client.ping()  # Verify connection by pinging
            app.logger.info(f"RedisClient: Successfully connected to Redis at {redis_url} and received PONG.") # Use redis_url directly

        except redis.exceptions.ConnectionError as e:
            app.logger.error(f"RedisClient: Failed to connect to Redis at '{redis_url}'. ConnectionError: {e}") # Use redis_url directly
            self.client = None  # Ensure client is None on connection failure
        except Exception as e:
            app.logger.error(f"RedisClient: An unexpected error occurred while connecting to Redis at '{redis_url}': {e}") # Use redis_url directly
            self.client = None  # Ensure client is None on other failures

    def get(self, key):
        if not self.client:
            # app.logger.error("RedisClient.get called but client is not initialized.") # Avoid excessive logging
            return None
        return self.client.get(key)

    def set(self, key, value):
        if not self.client:
            # app.logger.error("RedisClient.set called but client is not initialized.") # Avoid excessive logging
            return None
        return self.client.set(key, value)

redis_client = RedisClient()

login_manager.login_view = "auth.login"  # Specify the login view endpoint
login_manager.login_message_category = "info"
