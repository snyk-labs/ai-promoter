"""
Tests for the LinkedIn Native integration helper module.

This test suite provides comprehensive coverage for the LinkedIn Native API integration,
including OAuth flow, token management, and content posting functionality.

Test Organization:
- Unit tests: Individual function testing with mocked dependencies
- Integration tests: Multi-component interaction testing
- Slow tests: Complex workflow simulation and end-to-end scenarios

Coverage includes:
- All public functions in helpers/linkedin_native.py
- Error handling and edge cases
- Security validation (CSRF tokens, token cleanup)
- OAuth flow simulation
- Token refresh and expiration handling
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta, timezone
import requests
from flask import session, url_for

from helpers.linkedin_native import (
    _make_linkedin_request,
    get_linkedin_config,
    generate_linkedin_auth_url,
    exchange_code_for_token,
    revoke_linkedin_token,
    get_linkedin_user_profile,
    ensure_valid_token,
    _handle_invalid_grant,
    refresh_linkedin_token,
    post_to_linkedin_native,
    LINKEDIN_AUTHORIZATION_URL,
    LINKEDIN_ACCESS_TOKEN_URL,
    LINKEDIN_API_BASE_URL,
)


class TestConstants:
    """Test constants for better maintainability."""

    # API URLs
    TEST_API_URL = "https://api.linkedin.com/test"
    CALLBACK_URL = "http://localhost/auth/linkedin/callback"

    # HTTP Status Codes
    HTTP_OK = 200
    HTTP_BAD_REQUEST = 400
    HTTP_UNAUTHORIZED = 401
    HTTP_FORBIDDEN = 403
    HTTP_INTERNAL_ERROR = 500

    # Test Post IDs
    POST_ID_123 = "post_123"
    JSON_POST_ID_123 = "json_post_123"


class TestMessages:
    """Expected messages and error strings for testing."""

    LINKEDIN_CONFIG_ERROR = "LinkedIn API credentials not configured."
    CSRF_TOKEN_MISMATCH = "CSRF token mismatch. Authorization denied."
    INVALID_TOKEN_ERROR = (
        "LinkedIn token is invalid and refresh failed. Please re-authenticate."
    )
    NO_ACCESS_TOKEN_ERROR = (
        "LinkedIn access token not available. Please re-authenticate."
    )
    NO_LINKEDIN_ID_ERROR = "LinkedIn User ID not found. Please re-authenticate."
    AUTH_ERROR_MESSAGE = (
        "LinkedIn authentication error. Please re-connect your LinkedIn account."
    )
    FORBIDDEN_ERROR_MESSAGE = (
        "LinkedIn posting failed (403 Forbidden). Check app permissions or content."
    )


class TestData:
    """Test data and fixtures."""

    VALID_CLIENT_ID = "test_client_id"
    VALID_CLIENT_SECRET = "test_client_secret"
    VALID_ACCESS_TOKEN = "test_access_token"
    VALID_REFRESH_TOKEN = "test_refresh_token"
    VALID_CODE = "test_auth_code"
    VALID_STATE = "test_csrf_token"
    LINKEDIN_USER_ID = "test_linkedin_id"

    SAMPLE_TOKEN_RESPONSE = {
        "access_token": "new_access_token",
        "refresh_token": "new_refresh_token",
        "expires_in": 3600,
        "token_type": "Bearer",
        "scope": "openid profile w_member_social email",
    }

    SAMPLE_USER_PROFILE = {
        "sub": "test_linkedin_id",
        "name": "Test User",
        "email": "test@example.com",
        "picture": "https://example.com/picture.jpg",
    }

    SAMPLE_POST_CONTENT = "This is a test LinkedIn post content."


class LinkedInNativeTestHelpers:
    """Helper methods for LinkedIn native tests."""

    @staticmethod
    def utc_now():
        """Get current UTC time using timezone-aware datetime to avoid deprecation warnings."""
        return datetime.now(timezone.utc)

    @staticmethod
    def utc_now_naive():
        """Get current UTC time as naive datetime for compatibility with existing module code."""
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def create_mock_user(
        linkedin_native_id=TestData.LINKEDIN_USER_ID,
        access_token=TestData.VALID_ACCESS_TOKEN,
        refresh_token=TestData.VALID_REFRESH_TOKEN,
        token_expires_at=None,
        linkedin_authorized=True,
    ):
        """Create a mock user with LinkedIn credentials."""
        user = Mock()
        user.id = 1
        user.linkedin_native_id = linkedin_native_id
        user.linkedin_native_access_token = access_token
        user.linkedin_native_refresh_token = refresh_token
        user.linkedin_native_token_expires_at = token_expires_at or (
            LinkedInNativeTestHelpers.utc_now_naive() + timedelta(hours=1)
        )
        user.linkedin_authorized = linkedin_authorized
        return user

    @staticmethod
    def create_mock_response(status_code=200, json_data=None, headers=None):
        """Create a mock HTTP response."""
        response = Mock()
        response.status_code = status_code
        response.json.return_value = json_data or {}
        response.headers = headers or {}
        response.text = str(json_data) if json_data else ""
        return response

    @staticmethod
    def assert_user_tokens_cleared(user):
        """Assert that all LinkedIn tokens and authorization are cleared."""
        assert user.linkedin_native_access_token is None
        assert user.linkedin_native_refresh_token is None
        assert user.linkedin_native_token_expires_at is None
        assert user.linkedin_authorized is False

    @staticmethod
    def assert_successful_post_result(result, expected_post_id):
        """Assert that a post result indicates success with the expected post ID."""
        assert result["status"] == "success"
        assert result["id"] == expected_post_id
        assert (
            result["url"] == f"https://www.linkedin.com/feed/update/{expected_post_id}/"
        )


@pytest.mark.unit
class TestMakeLinkedInRequest:
    """Test _make_linkedin_request helper function."""

    @patch("helpers.linkedin_native.requests.request")
    def test_successful_request(self, mock_request):
        """Test successful LinkedIn API request."""
        mock_response = LinkedInNativeTestHelpers.create_mock_response(
            status_code=TestConstants.HTTP_OK, json_data={"success": True}
        )
        mock_request.return_value = mock_response

        result = _make_linkedin_request("GET", TestConstants.TEST_API_URL)

        assert result == mock_response
        mock_request.assert_called_once_with("GET", TestConstants.TEST_API_URL)

    @patch("helpers.linkedin_native.requests.request")
    def test_http_error_with_json_message(self, mock_request):
        """Test HTTP error with JSON error message."""
        mock_response = Mock()
        mock_response.status_code = TestConstants.HTTP_BAD_REQUEST
        mock_response.json.return_value = {"message": "Invalid request"}
        mock_response.text = '{"message": "Invalid request"}'

        http_error = requests.exceptions.HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = http_error
        mock_request.return_value = mock_response

        with pytest.raises(
            ValueError, match="LinkedIn API Request failed: 400 - Invalid request"
        ):
            _make_linkedin_request("GET", TestConstants.TEST_API_URL)

    @patch("helpers.linkedin_native.requests.request")
    def test_http_error_with_oauth_error_description(self, mock_request):
        """Test HTTP error with OAuth error_description."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error_description": "Invalid token"}
        mock_response.text = '{"error_description": "Invalid token"}'

        http_error = requests.exceptions.HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = http_error
        mock_request.return_value = mock_response

        with pytest.raises(
            ValueError, match="LinkedIn API Request failed: 401 - Invalid token"
        ):
            _make_linkedin_request("GET", "https://api.linkedin.com/test")

    @patch("helpers.linkedin_native.requests.request")
    def test_http_error_without_json(self, mock_request):
        """Test HTTP error without JSON response."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.side_effect = ValueError("Not JSON")
        mock_response.text = "Internal Server Error"

        http_error = requests.exceptions.HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = http_error
        mock_request.return_value = mock_response

        with pytest.raises(
            ValueError, match="LinkedIn API Request failed: 500 - Internal Server Error"
        ):
            _make_linkedin_request("GET", "https://api.linkedin.com/test")

    @patch("helpers.linkedin_native.requests.request")
    def test_request_exception(self, mock_request):
        """Test general request exception."""
        mock_request.side_effect = requests.exceptions.ConnectionError(
            "Connection failed"
        )

        with pytest.raises(
            ValueError, match="LinkedIn API Request request failed: Connection failed"
        ):
            _make_linkedin_request("GET", "https://api.linkedin.com/test")

    @patch("helpers.linkedin_native.requests.request")
    def test_custom_log_context(self, mock_request):
        """Test custom log context in error messages."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"message": "Bad request"}
        mock_response.text = '{"message": "Bad request"}'

        http_error = requests.exceptions.HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = http_error
        mock_request.return_value = mock_response

        with pytest.raises(
            ValueError, match="Custom Context failed: 400 - Bad request"
        ):
            _make_linkedin_request(
                "GET", "https://api.linkedin.com/test", log_context="Custom Context"
            )


@pytest.mark.unit
class TestGetLinkedInConfig:
    """Test get_linkedin_config function."""

    def test_valid_config(self, app):
        """Test retrieving valid LinkedIn configuration."""
        with app.app_context():
            app.config["LINKEDIN_CLIENT_ID"] = TestData.VALID_CLIENT_ID
            app.config["LINKEDIN_CLIENT_SECRET"] = TestData.VALID_CLIENT_SECRET

            client_id, client_secret = get_linkedin_config()

            assert client_id == TestData.VALID_CLIENT_ID
            assert client_secret == TestData.VALID_CLIENT_SECRET

    def test_missing_client_id(self, app):
        """Test error when client ID is missing."""
        with app.app_context():
            app.config.pop("LINKEDIN_CLIENT_ID", None)
            app.config["LINKEDIN_CLIENT_SECRET"] = TestData.VALID_CLIENT_SECRET

            with pytest.raises(ValueError, match=TestMessages.LINKEDIN_CONFIG_ERROR):
                get_linkedin_config()

    def test_missing_client_secret(self, app):
        """Test error when client secret is missing."""
        with app.app_context():
            app.config["LINKEDIN_CLIENT_ID"] = TestData.VALID_CLIENT_ID
            app.config.pop("LINKEDIN_CLIENT_SECRET", None)

            with pytest.raises(ValueError, match=TestMessages.LINKEDIN_CONFIG_ERROR):
                get_linkedin_config()

    def test_empty_credentials(self, app):
        """Test error when credentials are empty strings."""
        with app.app_context():
            app.config["LINKEDIN_CLIENT_ID"] = ""
            app.config["LINKEDIN_CLIENT_SECRET"] = ""

            with pytest.raises(ValueError, match=TestMessages.LINKEDIN_CONFIG_ERROR):
                get_linkedin_config()


@pytest.mark.unit
class TestGenerateLinkedInAuthUrl:
    """Test generate_linkedin_auth_url function."""

    @patch("helpers.linkedin_native.get_linkedin_config")
    @patch("helpers.linkedin_native.url_for")
    @patch("helpers.linkedin_native.secrets.token_urlsafe")
    def test_generate_auth_url(self, mock_token, mock_url_for, mock_config, app):
        """Test generating LinkedIn authorization URL."""
        with app.app_context():
            mock_config.return_value = (
                TestData.VALID_CLIENT_ID,
                TestData.VALID_CLIENT_SECRET,
            )
            mock_url_for.return_value = TestConstants.CALLBACK_URL
            mock_token.return_value = TestData.VALID_STATE

            with app.test_request_context():
                auth_url = generate_linkedin_auth_url()

                # Verify CSRF token is stored in session
                assert session.get("linkedin_oauth_csrf_token") == TestData.VALID_STATE

            # Verify URL contains expected parameters
            assert LINKEDIN_AUTHORIZATION_URL in auth_url
            assert f"client_id={TestData.VALID_CLIENT_ID}" in auth_url
            assert f"state={TestData.VALID_STATE}" in auth_url
            assert "scope=openid profile w_member_social email" in auth_url
            assert "response_type=code" in auth_url
            assert f"redirect_uri={TestConstants.CALLBACK_URL}" in auth_url


@pytest.mark.unit
class TestExchangeCodeForToken:
    """Test exchange_code_for_token function."""

    @patch("helpers.linkedin_native._make_linkedin_request")
    @patch("helpers.linkedin_native.get_linkedin_config")
    @patch("helpers.linkedin_native.url_for")
    def test_successful_token_exchange(
        self, mock_url_for, mock_config, mock_request, app
    ):
        """Test successful authorization code exchange."""
        with app.app_context():
            mock_config.return_value = (
                TestData.VALID_CLIENT_ID,
                TestData.VALID_CLIENT_SECRET,
            )
            mock_url_for.return_value = TestConstants.CALLBACK_URL
            mock_response = LinkedInNativeTestHelpers.create_mock_response(
                json_data=TestData.SAMPLE_TOKEN_RESPONSE
            )
            mock_request.return_value = mock_response

            with app.test_request_context():
                session["linkedin_oauth_csrf_token"] = TestData.VALID_STATE

                result = exchange_code_for_token(
                    TestData.VALID_CODE, TestData.VALID_STATE
                )

            assert result == TestData.SAMPLE_TOKEN_RESPONSE
            assert "linkedin_oauth_csrf_token" not in session

    def test_csrf_token_mismatch(self, app):
        """Test CSRF token mismatch error."""
        with app.app_context():
            with app.test_request_context():
                session["linkedin_oauth_csrf_token"] = "different_token"

                with pytest.raises(ValueError, match=TestMessages.CSRF_TOKEN_MISMATCH):
                    exchange_code_for_token(TestData.VALID_CODE, TestData.VALID_STATE)

    def test_missing_csrf_token(self, app):
        """Test missing CSRF token error."""
        with app.app_context():
            with app.test_request_context():
                with pytest.raises(ValueError, match=TestMessages.CSRF_TOKEN_MISMATCH):
                    exchange_code_for_token(TestData.VALID_CODE, TestData.VALID_STATE)


@pytest.mark.unit
class TestRevokeLinkedInToken:
    """Test revoke_linkedin_token function."""

    @patch("helpers.linkedin_native._make_linkedin_request")
    @patch("helpers.linkedin_native.get_linkedin_config")
    def test_successful_token_revocation(self, mock_config, mock_request):
        """Test successful token revocation."""
        mock_config.return_value = (
            TestData.VALID_CLIENT_ID,
            TestData.VALID_CLIENT_SECRET,
        )
        mock_response = LinkedInNativeTestHelpers.create_mock_response()
        mock_request.return_value = mock_response

        result = revoke_linkedin_token(TestData.VALID_ACCESS_TOKEN)

        assert result is True
        mock_request.assert_called_once()

    @patch("helpers.linkedin_native._make_linkedin_request")
    @patch("helpers.linkedin_native.get_linkedin_config")
    def test_failed_token_revocation(self, mock_config, mock_request):
        """Test failed token revocation (API error)."""
        mock_config.return_value = (
            TestData.VALID_CLIENT_ID,
            TestData.VALID_CLIENT_SECRET,
        )
        mock_request.side_effect = ValueError("API Error")

        result = revoke_linkedin_token(TestData.VALID_ACCESS_TOKEN)

        assert result is False


@pytest.mark.unit
class TestGetLinkedInUserProfile:
    """Test get_linkedin_user_profile function."""

    @patch("helpers.linkedin_native._make_linkedin_request")
    def test_successful_profile_fetch(self, mock_request):
        """Test successful user profile retrieval."""
        mock_response = LinkedInNativeTestHelpers.create_mock_response(
            json_data=TestData.SAMPLE_USER_PROFILE
        )
        mock_request.return_value = mock_response

        result = get_linkedin_user_profile(TestData.VALID_ACCESS_TOKEN)

        assert result == TestData.SAMPLE_USER_PROFILE
        mock_request.assert_called_once_with(
            "GET",
            f"{LINKEDIN_API_BASE_URL}/userinfo",
            headers={"Authorization": f"Bearer {TestData.VALID_ACCESS_TOKEN}"},
            log_context="Get LinkedIn User Profile",
        )


@pytest.mark.unit
class TestEnsureValidToken:
    """Test ensure_valid_token function."""

    def test_valid_token_not_expired(self):
        """Test with valid, non-expired token."""
        user = LinkedInNativeTestHelpers.create_mock_user(
            token_expires_at=LinkedInNativeTestHelpers.utc_now_naive()
            + timedelta(hours=1)
        )

        result = ensure_valid_token(user)

        assert result == TestData.VALID_ACCESS_TOKEN

    def test_token_near_expiry_triggers_refresh(self):
        """Test that token near expiry triggers refresh."""
        user = LinkedInNativeTestHelpers.create_mock_user(
            token_expires_at=LinkedInNativeTestHelpers.utc_now_naive()
            + timedelta(minutes=2)
        )

        with patch("helpers.linkedin_native.refresh_linkedin_token") as mock_refresh:
            mock_refresh.return_value = True

            result = ensure_valid_token(user)

            assert result == TestData.VALID_ACCESS_TOKEN
            mock_refresh.assert_called_once_with(user)

    def test_missing_token_triggers_refresh(self):
        """Test that missing token triggers refresh."""
        user = LinkedInNativeTestHelpers.create_mock_user(access_token=None)

        with patch("helpers.linkedin_native.refresh_linkedin_token") as mock_refresh:
            mock_refresh.return_value = True

            # Simulate the refresh updating the user's token
            def refresh_side_effect(user_obj):
                user_obj.linkedin_native_access_token = TestData.VALID_ACCESS_TOKEN
                return True

            mock_refresh.side_effect = refresh_side_effect

            result = ensure_valid_token(user)

            assert result == TestData.VALID_ACCESS_TOKEN
            mock_refresh.assert_called_once_with(user)

    @patch("helpers.linkedin_native.refresh_linkedin_token")
    @patch("extensions.db")
    def test_refresh_failure_raises_error(self, mock_db, mock_refresh):
        """Test that refresh failure raises appropriate error."""
        user = LinkedInNativeTestHelpers.create_mock_user(access_token=None)
        mock_refresh.return_value = False

        with pytest.raises(ValueError, match=TestMessages.INVALID_TOKEN_ERROR):
            ensure_valid_token(user)

        assert user.linkedin_authorized is False
        mock_db.session.commit.assert_called_once()

    def test_no_access_token_after_refresh_raises_error(self):
        """Test error when no access token exists after refresh."""
        user = LinkedInNativeTestHelpers.create_mock_user(access_token=None)

        with patch("helpers.linkedin_native.refresh_linkedin_token") as mock_refresh:
            mock_refresh.return_value = True
            user.linkedin_native_access_token = None  # Still None after refresh

            with pytest.raises(ValueError, match=TestMessages.NO_ACCESS_TOKEN_ERROR):
                ensure_valid_token(user)


@pytest.mark.unit
class TestHandleInvalidGrant:
    """Test _handle_invalid_grant function."""

    @patch("extensions.db")
    def test_handle_invalid_grant(self, mock_db):
        """Test handling of invalid grant error."""
        user = LinkedInNativeTestHelpers.create_mock_user()

        _handle_invalid_grant(user, "Test Context")

        LinkedInNativeTestHelpers.assert_user_tokens_cleared(user)
        mock_db.session.add.assert_called_once_with(user)
        mock_db.session.commit.assert_called_once()


@pytest.mark.unit
class TestRefreshLinkedInToken:
    """Test refresh_linkedin_token function."""

    @patch("helpers.linkedin_native._make_linkedin_request")
    @patch("helpers.linkedin_native.get_linkedin_config")
    @patch("extensions.db")
    def test_successful_token_refresh(self, mock_db, mock_config, mock_request):
        """Test successful token refresh."""
        user = LinkedInNativeTestHelpers.create_mock_user()
        mock_config.return_value = (
            TestData.VALID_CLIENT_ID,
            TestData.VALID_CLIENT_SECRET,
        )
        mock_response = LinkedInNativeTestHelpers.create_mock_response(
            json_data=TestData.SAMPLE_TOKEN_RESPONSE
        )
        mock_request.return_value = mock_response

        result = refresh_linkedin_token(user)

        assert result is True
        assert user.linkedin_native_access_token == "new_access_token"
        assert user.linkedin_native_refresh_token == "new_refresh_token"
        assert user.linkedin_authorized is True
        mock_db.session.add.assert_called_once_with(user)
        mock_db.session.commit.assert_called_once()

    def test_no_refresh_token(self):
        """Test refresh with no refresh token."""
        user = LinkedInNativeTestHelpers.create_mock_user(refresh_token=None)

        result = refresh_linkedin_token(user)

        assert result is False

    @patch("helpers.linkedin_native._make_linkedin_request")
    @patch("helpers.linkedin_native.get_linkedin_config")
    def test_refresh_returns_no_access_token(self, mock_config, mock_request):
        """Test refresh when response doesn't contain access token."""
        user = LinkedInNativeTestHelpers.create_mock_user()
        mock_config.return_value = (
            TestData.VALID_CLIENT_ID,
            TestData.VALID_CLIENT_SECRET,
        )
        mock_response = LinkedInNativeTestHelpers.create_mock_response(
            json_data={"expires_in": 3600}  # Missing access_token
        )
        mock_request.return_value = mock_response

        result = refresh_linkedin_token(user)

        assert result is False

    @patch("helpers.linkedin_native._make_linkedin_request")
    @patch("helpers.linkedin_native.get_linkedin_config")
    @patch("helpers.linkedin_native._handle_invalid_grant")
    def test_invalid_grant_error(self, mock_handle_invalid, mock_config, mock_request):
        """Test handling of invalid_grant error during refresh."""
        user = LinkedInNativeTestHelpers.create_mock_user()
        mock_config.return_value = (
            TestData.VALID_CLIENT_ID,
            TestData.VALID_CLIENT_SECRET,
        )
        mock_request.side_effect = ValueError("invalid_grant error")

        result = refresh_linkedin_token(user)

        assert result == "invalid_grant"
        mock_handle_invalid.assert_called_once_with(
            user, log_context="LinkedIn Token Refresh via invalid_grant"
        )

    @patch("helpers.linkedin_native._make_linkedin_request")
    @patch("helpers.linkedin_native.get_linkedin_config")
    def test_other_value_error(self, mock_config, mock_request):
        """Test handling of other ValueError during refresh."""
        user = LinkedInNativeTestHelpers.create_mock_user()
        mock_config.return_value = (
            TestData.VALID_CLIENT_ID,
            TestData.VALID_CLIENT_SECRET,
        )
        mock_request.side_effect = ValueError("Network error")

        result = refresh_linkedin_token(user)

        assert result is False

    @patch("helpers.linkedin_native._make_linkedin_request")
    @patch("helpers.linkedin_native.get_linkedin_config")
    def test_unexpected_exception(self, mock_config, mock_request):
        """Test handling of unexpected exception during refresh."""
        user = LinkedInNativeTestHelpers.create_mock_user()
        mock_config.return_value = (
            TestData.VALID_CLIENT_ID,
            TestData.VALID_CLIENT_SECRET,
        )
        mock_request.side_effect = Exception("Unexpected error")

        result = refresh_linkedin_token(user)

        assert result is False


@pytest.mark.integration
class TestPostToLinkedInNative:
    """Test post_to_linkedin_native function."""

    @patch("helpers.linkedin_native._make_linkedin_request")
    @patch("helpers.linkedin_native.ensure_valid_token")
    def test_successful_post(self, mock_ensure_token, mock_request):
        """Test successful LinkedIn post."""
        user = LinkedInNativeTestHelpers.create_mock_user()
        mock_ensure_token.return_value = TestData.VALID_ACCESS_TOKEN
        mock_response = LinkedInNativeTestHelpers.create_mock_response(
            json_data={"id": TestConstants.POST_ID_123},
            headers={"X-Restli-Id": TestConstants.POST_ID_123},
        )
        mock_request.return_value = mock_response

        result = post_to_linkedin_native(user, TestData.SAMPLE_POST_CONTENT)

        LinkedInNativeTestHelpers.assert_successful_post_result(
            result, TestConstants.POST_ID_123
        )

        # Verify request payload
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        assert call_args[0][0] == "POST"
        assert call_args[0][1] == f"{LINKEDIN_API_BASE_URL}/ugcPosts"
        assert (
            call_args[1]["json"]["author"]
            == f"urn:li:person:{TestData.LINKEDIN_USER_ID}"
        )
        assert (
            call_args[1]["json"]["specificContent"]["com.linkedin.ugc.ShareContent"][
                "shareCommentary"
            ]["text"]
            == TestData.SAMPLE_POST_CONTENT
        )

    def test_no_linkedin_id_error(self):
        """Test error when user has no LinkedIn ID."""
        user = LinkedInNativeTestHelpers.create_mock_user(linkedin_native_id=None)

        with pytest.raises(ValueError, match=TestMessages.NO_LINKEDIN_ID_ERROR):
            post_to_linkedin_native(user, TestData.SAMPLE_POST_CONTENT)

    @patch("helpers.linkedin_native._make_linkedin_request")
    @patch("helpers.linkedin_native.ensure_valid_token")
    @patch("extensions.db")
    def test_authentication_error_clears_tokens(
        self, mock_db, mock_ensure_token, mock_request
    ):
        """Test that authentication errors clear user tokens."""
        user = LinkedInNativeTestHelpers.create_mock_user()
        mock_ensure_token.return_value = TestData.VALID_ACCESS_TOKEN
        mock_request.side_effect = ValueError("401 Unauthorized")

        with pytest.raises(ValueError, match=TestMessages.AUTH_ERROR_MESSAGE):
            post_to_linkedin_native(user, TestData.SAMPLE_POST_CONTENT)

        LinkedInNativeTestHelpers.assert_user_tokens_cleared(user)
        mock_db.session.add.assert_called_once_with(user)
        mock_db.session.commit.assert_called_once()

    @patch("helpers.linkedin_native._make_linkedin_request")
    @patch("helpers.linkedin_native.ensure_valid_token")
    def test_forbidden_error(self, mock_ensure_token, mock_request):
        """Test handling of 403 Forbidden error."""
        user = LinkedInNativeTestHelpers.create_mock_user()
        mock_ensure_token.return_value = TestData.VALID_ACCESS_TOKEN
        mock_request.side_effect = ValueError("403 Forbidden")

        with pytest.raises(
            ValueError,
            match=r"LinkedIn posting failed \(403 Forbidden\)\. Check app permissions or content\.",
        ):
            post_to_linkedin_native(user, TestData.SAMPLE_POST_CONTENT)

    @patch("helpers.linkedin_native._make_linkedin_request")
    @patch("helpers.linkedin_native.ensure_valid_token")
    def test_unexpected_error(self, mock_ensure_token, mock_request):
        """Test handling of unexpected errors."""
        user = LinkedInNativeTestHelpers.create_mock_user()
        mock_ensure_token.return_value = TestData.VALID_ACCESS_TOKEN
        mock_request.side_effect = Exception("Unexpected error")

        with pytest.raises(
            ValueError, match="An unexpected error occurred while posting to LinkedIn"
        ):
            post_to_linkedin_native(user, TestData.SAMPLE_POST_CONTENT)

    @patch("helpers.linkedin_native._make_linkedin_request")
    @patch("helpers.linkedin_native.ensure_valid_token")
    def test_post_id_from_json_response(self, mock_ensure_token, mock_request):
        """Test getting post ID from JSON response when header is missing."""
        user = LinkedInNativeTestHelpers.create_mock_user()
        mock_ensure_token.return_value = TestData.VALID_ACCESS_TOKEN
        mock_response = LinkedInNativeTestHelpers.create_mock_response(
            json_data={"id": TestConstants.JSON_POST_ID_123},
            headers={},  # No X-Restli-Id header
        )
        mock_request.return_value = mock_response

        result = post_to_linkedin_native(user, TestData.SAMPLE_POST_CONTENT)

        LinkedInNativeTestHelpers.assert_successful_post_result(
            result, TestConstants.JSON_POST_ID_123
        )


@pytest.mark.slow
class TestLinkedInNativeIntegration:
    """Integration tests for LinkedIn Native functionality."""

    @patch("helpers.linkedin_native._make_linkedin_request")
    @patch("helpers.linkedin_native.get_linkedin_config")
    def test_full_oauth_flow_simulation(self, mock_config, mock_request, app):
        """Test simulation of complete OAuth flow."""
        mock_config.return_value = (
            TestData.VALID_CLIENT_ID,
            TestData.VALID_CLIENT_SECRET,
        )

        # Mock token exchange response
        token_response = LinkedInNativeTestHelpers.create_mock_response(
            json_data=TestData.SAMPLE_TOKEN_RESPONSE
        )

        # Mock profile response
        profile_response = LinkedInNativeTestHelpers.create_mock_response(
            json_data=TestData.SAMPLE_USER_PROFILE
        )

        mock_request.side_effect = [token_response, profile_response]

        with app.app_context():
            with app.test_request_context():
                # Step 1: Generate auth URL
                session["linkedin_oauth_csrf_token"] = TestData.VALID_STATE

                # Step 2: Exchange code for token
                token_data = exchange_code_for_token(
                    TestData.VALID_CODE, TestData.VALID_STATE
                )
                assert token_data == TestData.SAMPLE_TOKEN_RESPONSE

                # Step 3: Get user profile
                profile_data = get_linkedin_user_profile(token_data["access_token"])
                assert profile_data == TestData.SAMPLE_USER_PROFILE

    @patch("helpers.linkedin_native._make_linkedin_request")
    @patch("helpers.linkedin_native.get_linkedin_config")
    @patch("extensions.db")
    def test_token_refresh_and_post_flow(self, mock_db, mock_config, mock_request):
        """Test token refresh followed by posting."""
        user = LinkedInNativeTestHelpers.create_mock_user(
            token_expires_at=LinkedInNativeTestHelpers.utc_now_naive()
            - timedelta(minutes=1)  # Expired
        )
        mock_config.return_value = (
            TestData.VALID_CLIENT_ID,
            TestData.VALID_CLIENT_SECRET,
        )

        # Mock refresh response
        refresh_response = LinkedInNativeTestHelpers.create_mock_response(
            json_data=TestData.SAMPLE_TOKEN_RESPONSE
        )

        # Mock post response
        post_response = LinkedInNativeTestHelpers.create_mock_response(
            json_data={"id": TestConstants.POST_ID_123},
            headers={"X-Restli-Id": TestConstants.POST_ID_123},
        )

        mock_request.side_effect = [refresh_response, post_response]

        # This should trigger token refresh and then post
        result = post_to_linkedin_native(user, TestData.SAMPLE_POST_CONTENT)

        LinkedInNativeTestHelpers.assert_successful_post_result(
            result, TestConstants.POST_ID_123
        )

        # Verify token was refreshed
        assert user.linkedin_native_access_token == "new_access_token"
        assert user.linkedin_native_refresh_token == "new_refresh_token"
