from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_mail import Mail
import redis

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
mail = Mail()

class RedisClient:
    def __init__(self):
        self.client = None

    def init_app(self, app):
        self.client = redis.Redis(
            host=app.config.get('REDIS_HOST', 'localhost'),
            port=app.config.get('REDIS_PORT', 6379),
            db=app.config.get('REDIS_DB', 0),
            decode_responses=True
        )

    def get(self, key):
        return self.client.get(key)

    def set(self, key, value):
        return self.client.set(key, value)

redis_client = RedisClient()

login_manager.login_view = "auth.login"  # Specify the login view endpoint
login_manager.login_message_category = "info"
