"""
LinkedIn Platform Manager

This module handles LinkedIn-specific operations including posting,
authorization, and platform-specific features.
"""

import os
import logging
from typing import Dict, Any, Optional
from flask import current_app, url_for, session
import requests
import secrets
from datetime import datetime, timedelta, timezone

from .base import BasePlatformManager

logger = logging.getLogger(__name__)

# LinkedIn API constants
LINKEDIN_AUTHORIZATION_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_ACCESS_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_API_BASE_URL = "https://api.linkedin.com/v2"


class LinkedInManager(BasePlatformManager):
    """LinkedIn platform manager for posting and authorization."""

    def __init__(self):
        """Initialize LinkedIn manager."""
        self.platform_name = "linkedin"

    def post_content(self, user, content: str, content_id: int) -> Dict[str, Any]:
        """
        Post content to LinkedIn on behalf of the user.

        Args:
            user: User object with LinkedIn authorization
            content: The content to post
            content_id: ID of the content item being posted

        Returns:
            Dict containing posting result
        """
        try:
            # Validate user has LinkedIn authorization
            if not user.linkedin_native_id:
                return {
                    "success": False,
                    "error_message": "LinkedIn User ID not found. Please re-authenticate.",
                    "post_id": None,
                    "platform_response": None,
                }

            # Ensure token is valid
            access_token = self._ensure_valid_token(user)
            if not access_token:
                return {
                    "success": False,
                    "error_message": "LinkedIn authentication failed. Please re-connect your account.",
                    "post_id": None,
                    "platform_response": None,
                }

            # Prepare post payload
            author_urn = f"urn:li:person:{user.linkedin_native_id}"
            post_payload = {
                "author": author_urn,
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": content},
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

            logger.info(
                f"Attempting to post to LinkedIn for user {user.id} (URN: {author_urn})."
            )

            response = self._make_linkedin_request(
                "POST",
                ugc_posts_url,
                headers=headers,
                json=post_payload,
                log_context="Post to LinkedIn",
            )

            post_id = response.headers.get("X-Restli-Id") or response.json().get("id")
            post_url = (
                f"https://www.linkedin.com/feed/update/{post_id}/" if post_id else None
            )

            logger.info(
                f"Successfully posted to LinkedIn for user {user.id}. Post ID: {post_id}"
            )

            return {
                "success": True,
                "post_id": post_id,
                "post_url": post_url,
                "error_message": None,
                "platform_response": {"id": post_id, "url": post_url},
            }

        except ValueError as e:
            error_str = str(e).lower()
            if (
                "401" in error_str
                or "unauthorized" in error_str
                or "invalid token" in error_str
            ):
                # Clear tokens on auth error
                user.linkedin_native_access_token = None
                user.linkedin_native_refresh_token = None
                user.linkedin_native_token_expires_at = None
                user.linkedin_authorized = False

                from extensions import db

                db.session.add(user)
                db.session.commit()

                return {
                    "success": False,
                    "error_message": f"LinkedIn authentication error. Please re-connect your LinkedIn account. ({str(e)})",
                    "post_id": None,
                    "platform_response": None,
                }
            elif "403" in error_str or "forbidden" in error_str:
                return {
                    "success": False,
                    "error_message": f"LinkedIn posting failed (403 Forbidden). Check app permissions or content. ({str(e)})",
                    "post_id": None,
                    "platform_response": None,
                }
            else:
                return {
                    "success": False,
                    "error_message": str(e),
                    "post_id": None,
                    "platform_response": None,
                }
        except Exception as e:
            logger.error(
                f"Unexpected error posting to LinkedIn for user {user.id}: {str(e)}"
            )
            return {
                "success": False,
                "error_message": f"An unexpected error occurred while posting to LinkedIn: {str(e)}",
                "post_id": None,
                "platform_response": None,
            }

    def check_authorization(self, user) -> bool:
        """Check if user is authorized for LinkedIn."""
        return (
            user.linkedin_authorized
            and user.linkedin_native_access_token
            and user.linkedin_native_id
        )

    def get_auth_url(self, redirect_uri: Optional[str] = None) -> str:
        """Get LinkedIn OAuth authorization URL."""
        client_id, _ = self._get_linkedin_config()

        if not redirect_uri:
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

    def validate_content(self, content: str) -> Dict[str, Any]:
        """Validate content for LinkedIn-specific requirements."""
        errors = []
        warnings = []

        # Check length (3000 character limit)
        if len(content) > 3000:
            errors.append(
                f"Content exceeds LinkedIn's 3000 character limit ({len(content)} characters)"
            )

        # Check for potential issues
        if len(content) > 2500:
            warnings.append("Content is close to LinkedIn's character limit")

        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    def _ensure_valid_token(self, user):
        """Ensure user has a valid LinkedIn access token."""
        if not user.linkedin_native_access_token:
            logger.warning(f"User {user.id} has no LinkedIn access token.")
            return None

        # Check if token is expired
        if (
            user.linkedin_native_token_expires_at
            and user.linkedin_native_token_expires_at <= datetime.now()
        ):
            logger.info(
                f"LinkedIn token for user {user.id} is expired. Attempting refresh."
            )
            if self._refresh_linkedin_token(user):
                return user.linkedin_native_access_token
            else:
                return None

        return user.linkedin_native_access_token

    def _refresh_linkedin_token(self, user) -> bool:
        """Refresh the LinkedIn access token using the refresh token."""
        if not user.linkedin_native_refresh_token:
            logger.warning(
                f"User {user.id} has no LinkedIn refresh token. Cannot refresh."
            )
            return False

        client_id, client_secret = self._get_linkedin_config()
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": user.linkedin_native_refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }

        try:
            response = self._make_linkedin_request(
                "POST",
                LINKEDIN_ACCESS_TOKEN_URL,
                data=payload,
                log_context="LinkedIn Token Refresh",
            )
            token_data = response.json()

            new_access_token = token_data.get("access_token")
            new_refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in")

            if not new_access_token:
                logger.error(
                    f"LinkedIn token refresh for user {user.id} did not return a new access token."
                )
                return False

            user.linkedin_native_access_token = new_access_token
            if new_refresh_token:
                user.linkedin_native_refresh_token = new_refresh_token
            user.linkedin_native_token_expires_at = datetime.now() + timedelta(
                seconds=expires_in
            )
            user.linkedin_authorized = True

            from extensions import db

            db.session.add(user)
            db.session.commit()

            logger.info(f"Successfully refreshed LinkedIn token for user {user.id}.")
            return True

        except ValueError as e:
            error_str = str(e).lower()
            if "invalid_grant" in error_str:
                logger.warning(
                    f"LinkedIn refresh token for user {user.id} is invalid. User needs to re-authenticate."
                )
                user.linkedin_native_access_token = None
                user.linkedin_native_refresh_token = None
                user.linkedin_native_token_expires_at = None
                user.linkedin_authorized = False

                from extensions import db

                db.session.add(user)
                db.session.commit()
            else:
                logger.error(
                    f"LinkedIn token refresh failed for user {user.id}: {str(e)}"
                )
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error refreshing LinkedIn token for user {user.id}: {str(e)}"
            )
            return False

    def _get_linkedin_config(self):
        """Retrieve LinkedIn configuration from the app."""
        client_id = current_app.config.get("LINKEDIN_CLIENT_ID")
        client_secret = current_app.config.get("LINKEDIN_CLIENT_SECRET")
        if not client_id or not client_secret:
            logger.error("LINKEDIN_CLIENT_ID or LINKEDIN_CLIENT_SECRET not configured.")
            raise ValueError("LinkedIn API credentials not configured.")
        return client_id, client_secret

    def _make_linkedin_request(
        self, method, url, log_context="LinkedIn API Request", **kwargs
    ):
        """Make requests to the LinkedIn API and handle common errors."""
        try:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as http_err:
            # Get detailed error from response
            error_detail = http_err.response.text
            try:
                json_response = http_err.response.json()
                if "message" in json_response:
                    error_detail = json_response["message"]
                elif "error_description" in json_response:
                    error_detail = json_response["error_description"]
            except ValueError:
                pass

            logger.error(
                f"HTTP error during {log_context}: {http_err.response.status_code} - {error_detail}"
            )
            raise ValueError(
                f"{log_context} failed: {http_err.response.status_code} - {error_detail}"
            ) from http_err
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Request exception during {log_context}: {str(req_err)}")
            raise ValueError(
                f"{log_context} request failed: {str(req_err)}"
            ) from req_err
