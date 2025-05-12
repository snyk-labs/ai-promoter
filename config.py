import os
from datetime import timedelta

class Config:
    """Base configuration class."""
    
    # Flask configuration
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-please-change")
    
    # Company configuration
    COMPANY_NAME = os.environ.get("COMPANY_NAME", "Your Company")
    UTM_PARAMS = os.environ.get("UTM_PARAMS", "")
    DASHBOARD_BANNER = os.environ.get("DASHBOARD_BANNER", "")
    
    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///promoter.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Celery Configuration Dictionary
    # Following the pattern from https://flask.palletsprojects.com/en/stable/patterns/celery/
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    CELERY = dict(
        broker_url=REDIS_URL,
        result_backend=REDIS_URL,
        task_ignore_result=True, # Default, can be overridden per task
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
        task_track_started=True,
        task_time_limit=3600,  # 1 hour
        worker_max_tasks_per_child=200,
        worker_prefetch_multiplier=1,
        broker_connection_retry_on_startup=True 
    )
    
    # Okta configuration
    OKTA_ENABLED = os.environ.get("OKTA_ENABLED", "false").lower() == "true"
    OKTA_CLIENT_ID = os.environ.get("OKTA_CLIENT_ID")
    OKTA_CLIENT_SECRET = os.environ.get("OKTA_CLIENT_SECRET")
    OKTA_ISSUER = os.environ.get("OKTA_ISSUER")
    OKTA_REDIRECT_URI = os.environ.get("OKTA_REDIRECT_URI")
    
    # API Keys
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    ARCADE_API_KEY = os.environ.get("ARCADE_API_KEY")
    FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY")
    
    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(days=7) 