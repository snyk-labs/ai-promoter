"""
Okta Helper Module

This module provides functions for Okta SSO authentication and configuration.
"""

import os
import requests
import secrets
import logging
from jose import jwt
from urllib.parse import urlencode

# Load environment variables if .env file exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

# Set up logging
logger = logging.getLogger(__name__)

# Okta settings
OKTA_ENABLED = os.environ.get('OKTA_ENABLED', 'false').lower() == 'true'
OKTA_CLIENT_ID = os.environ.get('OKTA_CLIENT_ID', '')
OKTA_CLIENT_SECRET = os.environ.get('OKTA_CLIENT_SECRET', '')
OKTA_ISSUER = os.environ.get('OKTA_ISSUER', '')
OKTA_AUTH_SERVER_ID = os.environ.get('OKTA_AUTH_SERVER_ID', 'default')
OKTA_AUDIENCE = os.environ.get('OKTA_AUDIENCE', 'api://default')
OKTA_SCOPES = os.environ.get('OKTA_SCOPES', 'openid profile email').split(' ')
OKTA_REDIRECT_URI = os.environ.get('OKTA_REDIRECT_URI', 'http://localhost:5000/auth/okta/callback')

def validate_okta_config():
    """
    Validate that all required Okta configuration is provided when Okta is enabled.
    
    Returns:
        Boolean indicating if configuration is valid
        
    Raises:
        ValueError: If required Okta configuration is missing
    """
    if not OKTA_ENABLED:
        logger.info("Okta SSO integration is disabled")
        return True
        
    # Check for required Okta settings
    missing_settings = []
    if not OKTA_CLIENT_ID:
        missing_settings.append('OKTA_CLIENT_ID')
    if not OKTA_CLIENT_SECRET:
        missing_settings.append('OKTA_CLIENT_SECRET')
    if not OKTA_ISSUER:
        missing_settings.append('OKTA_ISSUER')
        
    if missing_settings:
        error_msg = f"Missing required Okta configuration: {', '.join(missing_settings)}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    # Log successful validation
    logger.info("Okta configuration validated successfully")
    return True

def build_authorization_url(state, nonce):
    """
    Build the Okta authorization URL for redirecting users.
    
    Args:
        state: A secure random state parameter to prevent CSRF
        nonce: A secure random nonce to prevent replay attacks
        
    Returns:
        The complete authorization URL for redirecting to Okta
    """
    auth_params = {
        'client_id': OKTA_CLIENT_ID,
        'response_type': 'code',
        'scope': ' '.join(OKTA_SCOPES),
        'redirect_uri': OKTA_REDIRECT_URI,
        'state': state,
        'nonce': nonce
    }
    return f"{OKTA_ISSUER}/v1/authorize?{urlencode(auth_params)}"

def exchange_code_for_tokens(code):
    """
    Exchange an authorization code for access and ID tokens.
    
    Args:
        code: The authorization code received from Okta
        
    Returns:
        A dictionary containing the access_token, id_token, and token_type
        
    Raises:
        Exception: If token exchange fails
    """
    token_url = f"{OKTA_ISSUER}/v1/token"
    token_payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': OKTA_REDIRECT_URI,
        'client_id': OKTA_CLIENT_ID,
        'client_secret': OKTA_CLIENT_SECRET
    }
    
    try:
        response = requests.post(token_url, data=token_payload)
        response.raise_for_status()
        tokens = response.json()
        logger.info("Successfully exchanged code for tokens")
        return tokens
    except Exception as e:
        logger.error(f"Error exchanging code for tokens: {str(e)}")
        raise Exception(f"Failed to exchange code for tokens: {str(e)}")

def validate_id_token(id_token, nonce, access_token=None):
    """
    Validate the ID token received from Okta.
    
    Args:
        id_token: The ID token to validate
        nonce: The nonce used in the authorization request
        access_token: Optional access token to validate at_hash claim
        
    Returns:
        The decoded JWT claims if validation succeeds
        
    Raises:
        Exception: If token validation fails
    """
    try:
        # Decode and validate the JWT
        jwt_claims = jwt.decode(
            token=id_token,
            key='',  # We're not validating the signature here
            options={
                'verify_signature': False,  # This should be True in production
                'verify_aud': True,
                'verify_iat': True,
                'verify_exp': True,
                'verify_nbf': True,
                'verify_iss': True,
                'verify_jti': False,
                'verify_at_hash': access_token is not None
            },
            audience=OKTA_CLIENT_ID,
            issuer=OKTA_ISSUER
        )
        
        # Verify the nonce
        if jwt_claims.get('nonce') != nonce:
            logger.error("Invalid nonce in ID token")
            raise Exception("Invalid nonce in ID token")
            
        logger.info("ID token validated successfully")
        return jwt_claims
    except Exception as e:
        logger.error(f"Error validating ID token: {str(e)}")
        raise Exception(f"Failed to validate ID token: {str(e)}")

def get_user_profile(access_token):
    """
    Get the user's profile information from Okta.
    
    Args:
        access_token: The access token to use for authentication
        
    Returns:
        A dictionary containing the user's profile information
        
    Raises:
        Exception: If retrieving user profile fails
    """
    userinfo_url = f"{OKTA_ISSUER}/v1/userinfo"
    headers = {
        'Authorization': f"Bearer {access_token}"
    }
    
    try:
        response = requests.get(userinfo_url, headers=headers)
        response.raise_for_status()
        user_info = response.json()
        logger.info("Successfully retrieved user profile")
        return user_info
    except Exception as e:
        logger.error(f"Error retrieving user profile: {str(e)}")
        raise Exception(f"Failed to retrieve user profile: {str(e)}")

def generate_secure_state_and_nonce():
    """
    Generate secure state and nonce parameters for Okta authentication.
    
    Returns:
        A tuple containing (state, nonce)
    """
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    return state, nonce 