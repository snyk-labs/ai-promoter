"""
LinkedIn Native Integration Helper Module

This module provides functions for interacting with the LinkedIn API
directly for authentication and social media posting.
"""

import os
from flask import current_app, url_for, session
import requests
import logging
import secrets  # For CSRF token generation
from datetime import datetime, timedelta, timezone

# Set up logging
logger = logging.getLogger(__name__)

LINKEDIN_AUTHORIZATION_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_ACCESS_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
# LINKEDIN_REVOKE_TOKEN_URL = "https://www.linkedin.com/oauth/v2/revoke" # This constant is unused
LINKEDIN_API_BASE_URL = "https://api.linkedin.com/v2"


def _make_linkedin_request(method, url, log_context="LinkedIn API Request", **kwargs):
    """
    Internal helper to make requests to the LinkedIn API and handle common errors.
    Raises ValueError for request exceptions or HTTP errors.
    """
    try:
        response = requests.request(method, url, **kwargs)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        return response
    except requests.exceptions.HTTPError as http_err:
        # Attempt to get more detailed error from response if possible
        error_detail = http_err.response.text
        try:
            json_response = http_err.response.json()
            if "message" in json_response:
                error_detail = json_response["message"]
            elif "error_description" in json_response:  # OAuth errors often use this
                error_detail = json_response["error_description"]
        except ValueError:  # response was not JSON
            pass
        logger.error(
            f"HTTP error during {log_context}: {http_err.response.status_code} - {error_detail}"
        )
        raise ValueError(
            f"{log_context} failed: {http_err.response.status_code} - {error_detail}"
        ) from http_err
    except requests.exceptions.RequestException as req_err:
        logger.error(f"Request exception during {log_context}: {str(req_err)}")
        raise ValueError(f"{log_context} request failed: {str(req_err)}") from req_err


def get_linkedin_config():
    """Retrieve LinkedIn configuration from the app."""
    client_id = current_app.config.get("LINKEDIN_CLIENT_ID")
    client_secret = current_app.config.get("LINKEDIN_CLIENT_SECRET")
    if not client_id or not client_secret:
        logger.error("LINKEDIN_CLIENT_ID or LINKEDIN_CLIENT_SECRET not configured.")
        raise ValueError("LinkedIn API credentials not configured.")
    return client_id, client_secret


def generate_linkedin_auth_url():
    """
    Generates the LinkedIn authorization URL with necessary parameters.
    Requests 'openid', 'profile', 'w_member_social', and 'email' scopes.
    Stores a CSRF token in the session.
    """
    client_id, _ = get_linkedin_config()
    redirect_uri = url_for("auth.linkedin_callback", _external=True)
    scopes = "openid profile w_member_social email"
    csrf_token = secrets.token_urlsafe(16)
    session["linkedin_oauth_csrf_token"] = csrf_token
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": csrf_token,
        "scope": scopes,
    }
    auth_url = f"{LINKEDIN_AUTHORIZATION_URL}?" + "&".join(
        [f"{k}={v}" for k, v in params.items()]
    )
    logger.info(f"Generated LinkedIn Auth URL: {auth_url}")
    return auth_url


def exchange_code_for_token(code, state):
    """
    Exchanges the authorization code for an access token and refresh token.
    Verifies the CSRF token.
    """
    session_csrf_token = session.pop("linkedin_oauth_csrf_token", None)
    if not session_csrf_token or session_csrf_token != state:
        logger.error("LinkedIn OAuth CSRF token mismatch.")
        raise ValueError("CSRF token mismatch. Authorization denied.")

    client_id, client_secret = get_linkedin_config()
    redirect_uri = url_for("auth.linkedin_callback", _external=True)
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    response = _make_linkedin_request(
        "POST",
        LINKEDIN_ACCESS_TOKEN_URL,
        data=payload,
        log_context="LinkedIn Token Exchange",
    )
    token_data = response.json()
    logger.info("Successfully exchanged code for LinkedIn token.")
    return token_data


def revoke_linkedin_token(access_token):
    """
    Revokes the given LinkedIn access token.
    """
    client_id, client_secret = get_linkedin_config()
    payload = {
        "token": access_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        # LinkedIn uses a POST to the /accessToken endpoint for revocation.
        # This call might return 200 OK on success, or an error.
        # We don't raise an error from this function itself if LinkedIn API call fails,
        # as local cleanup should proceed. The error is logged by _make_linkedin_request.
        _make_linkedin_request(
            "POST",
            LINKEDIN_ACCESS_TOKEN_URL,
            data=payload,
            headers=headers,
            log_context="LinkedIn Token Revocation",
        )
        logger.info("LinkedIn token revocation request sent successfully.")
        return True
    except ValueError:  # Catch error raised by _make_linkedin_request
        logger.warning(
            "LinkedIn token revocation request failed at API level, but proceeding with local cleanup."
        )
        return False  # Indicate API revocation failed but allow local logic to continue


def get_linkedin_user_profile(access_token):
    """
    Fetches basic profile information of the authenticated user.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    user_info_url = f"{LINKEDIN_API_BASE_URL}/userinfo"

    response = _make_linkedin_request(
        "GET", user_info_url, headers=headers, log_context="Get LinkedIn User Profile"
    )
    profile_data = response.json()
    logger.info(
        f"Successfully fetched LinkedIn user profile: {profile_data.get('sub')}"
    )
    return profile_data


def ensure_valid_token(user):
    """
    Ensures the user has a valid (non-expired) LinkedIn access token.
    Attempts to refresh the token if it's missing, expired, or nearing expiry.
    Raises ValueError if a valid token cannot be obtained/refreshed.
    Returns the valid access token string.
    """
    token_is_valid = False
    if user.linkedin_native_access_token and user.linkedin_native_token_expires_at:
        # Check if token is valid for at least 5 more minutes
        if datetime.now() < user.linkedin_native_token_expires_at - timedelta(
            minutes=5
        ):
            token_is_valid = True

    if not token_is_valid:
        logger.info(
            f"LinkedIn access token for user {user.id} requires refresh. Attempting."
        )
        if not refresh_linkedin_token(
            user
        ):  # refresh_linkedin_token updates user & commits
            logger.error(f"Failed to refresh LinkedIn token for user {user.id}.")
            # Clear potentially stale authorization status if refresh fails critically
            user.linkedin_authorized = (
                False  # Reflect that we couldn't get a working token
            )
            from extensions import db

            db.session.commit()
            raise ValueError(
                "LinkedIn token is invalid and refresh failed. Please re-authenticate."
            )
        logger.info(f"LinkedIn token refreshed successfully for user {user.id}.")

    if not user.linkedin_native_access_token:
        # This should be caught by the refresh logic, but as a safeguard:
        logger.error(
            f"User {user.id} does not have a native LinkedIn access token after validation/refresh attempt."
        )
        raise ValueError("LinkedIn access token not available. Please re-authenticate.")

    return user.linkedin_native_access_token


def _handle_invalid_grant(user, log_context="LinkedIn Token Refresh"):
    """
    Handles the 'invalid_grant' error by clearing LinkedIn tokens and authorization.
    This typically means the refresh token is no longer valid and re-authentication is required.
    """
    logger.warning(
        f"{log_context} for user {user.id} failed with invalid_grant. Clearing tokens and auth status."
    )
    user.linkedin_native_access_token = None
    user.linkedin_native_refresh_token = None
    user.linkedin_native_token_expires_at = None
    user.linkedin_authorized = False  # User needs to re-authenticate
    from extensions import db  # Local import to avoid circular dependency

    db.session.add(user)
    db.session.commit()


def refresh_linkedin_token(user):
    """
    Refreshes the LinkedIn access token using the refresh token.
    Stores the new access token, refresh token (if changed), and expiry.
    Returns True if successful, 'invalid_grant' if refresh failed due to invalid grant,
    and False otherwise.
    """
    if not user.linkedin_native_refresh_token:
        logger.warning(f"User {user.id} has no LinkedIn refresh token. Cannot refresh.")
        return False

    client_id, client_secret = get_linkedin_config()
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": user.linkedin_native_refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    try:
        response = _make_linkedin_request(
            "POST",
            LINKEDIN_ACCESS_TOKEN_URL,
            data=payload,
            log_context="LinkedIn Token Refresh",
        )
        token_data = response.json()

        new_access_token = token_data.get("access_token")
        new_refresh_token = token_data.get(
            "refresh_token"
        )  # LinkedIn might return a new refresh token
        expires_in = token_data.get("expires_in")  # in seconds
        # Also comes with: scope, token_type, refresh_token_expires_in (long lived)

        if not new_access_token:
            logger.error(
                f"LinkedIn token refresh for user {user.id} did not return a new access token."
            )
            # This case might not be 'invalid_grant' but a different API issue.
            # For now, treat as a generic failure for refresh.
            return False

        user.linkedin_native_access_token = new_access_token
        if new_refresh_token:  # Only update if a new one is provided
            user.linkedin_native_refresh_token = new_refresh_token
        user.linkedin_native_token_expires_at = datetime.now() + timedelta(
            seconds=expires_in
        )
        user.linkedin_authorized = True  # Re-affirm authorization

        from extensions import db  # Local import to avoid circular dependency

        db.session.add(user)
        db.session.commit()
        logger.info(f"Successfully refreshed LinkedIn token for user {user.id}.")
        return True
    except ValueError as e:
        # _make_linkedin_request raises ValueError, check its string content for details
        # OAuth errors usually include 'error_description' in the response.
        # 'invalid_grant' is a specific error_description indicating the refresh token is bad.
        if "invalid_grant" in str(e).lower():
            _handle_invalid_grant(
                user, log_context="LinkedIn Token Refresh via invalid_grant"
            )
            return "invalid_grant"  # Specific return for invalid grant
        else:
            logger.error(
                f"ValueError during LinkedIn token refresh for user {user.id}: {str(e)}"
            )
            # For other ValueErrors (e.g., network issues, unexpected API response format),
            # we don't necessarily clear tokens, as it might be a temporary issue.
            # The token remains as it was, and will be retried later or fail upon use.
            return False
    except Exception as e:
        logger.exception(
            f"Unexpected exception during LinkedIn token refresh for user {user.id}: {str(e)}"
        )
        return False


def post_to_linkedin_native(user, content_text):
    """
    Posts content to LinkedIn on behalf of the user using the native API.
    Ensures token is valid before posting.
    """
    if not user.linkedin_native_id:
        logger.error(
            f"User {user.id} does not have a LinkedIn native ID (person URN). Cannot post."
        )
        raise ValueError("LinkedIn User ID not found. Please re-authenticate.")

    access_token = ensure_valid_token(
        user
    )  # This will raise ValueError if token cannot be validated/refreshed

    author_urn = f"urn:li:person:{user.linkedin_native_id}"
    post_payload = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": content_text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    ugc_posts_url = f"{LINKEDIN_API_BASE_URL}/ugcPosts"

    try:
        logger.info(
            f"Attempting to post to LinkedIn for user {user.id} (URN: {author_urn})."
        )
        response = _make_linkedin_request(
            "POST",
            ugc_posts_url,
            headers=headers,
            json=post_payload,
            log_context="Post to LinkedIn",
        )

        post_id = response.headers.get("X-Restli-Id") or response.json().get("id")
        logger.info(
            f"Successfully posted to LinkedIn for user {user.id}. Post ID: {post_id}"
        )
        post_url = (
            f"https://www.linkedin.com/feed/update/{post_id}/" if post_id else None
        )

        return {"status": "success", "id": post_id, "url": post_url}

    except ValueError as e:
        err_str = str(e).lower()
        if "401" in err_str or "unauthorized" in err_str or "invalid token" in err_str:
            logger.warning(
                f"LinkedIn authentication error during post for user {user.id}. Clearing tokens post ensure_valid_token."
            )
            user.linkedin_native_access_token = None
            user.linkedin_native_refresh_token = None
            user.linkedin_native_token_expires_at = None
            user.linkedin_authorized = False
            from extensions import db

            db.session.add(user)
            db.session.commit()
            raise ValueError(
                f"LinkedIn authentication error. Please re-connect your LinkedIn account. ({str(e)})"
            ) from e
        elif "403" in err_str or "forbidden" in err_str:
            raise ValueError(
                f"LinkedIn posting failed (403 Forbidden). Check app permissions or content. ({str(e)})"
            ) from e
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error posting to LinkedIn for user {user.id}: {str(e)}"
        )
        raise ValueError(
            f"An unexpected error occurred while posting to LinkedIn: {str(e)}"
        ) from e


# ... (ensure_valid_token will be added in the next step)
