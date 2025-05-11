import os

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