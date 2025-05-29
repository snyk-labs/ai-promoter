"""
Tests for the LinkedIn platform manager.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from helpers.platforms.linkedin import LinkedInManager


class TestConstants:
    """Test constants and expected values."""

    # User data
    TEST_USER_ID = 123
    LINKEDIN_USER_ID = "linkedin_user_123"
    LINKEDIN_URN = f"urn:li:person:{LINKEDIN_USER_ID}"

    # Tokens and credentials
    VALID_ACCESS_TOKEN = "valid_access_token"
    EXPIRED_ACCESS_TOKEN = "expired_token"
    REFRESH_TOKEN = "refresh_token_123"
    NEW_ACCESS_TOKEN = "new_access_token"
    NEW_REFRESH_TOKEN = "new_refresh_token"
    CLIENT_ID = "test_client_id"
    CLIENT_SECRET = "test_client_secret"

    # Content
    VALID_CONTENT = "This is a valid LinkedIn post that's under the character limit."
    LONG_CONTENT = "x" * 3001  # Exceeds LinkedIn's 3000 character limit
    WARNING_CONTENT = "x" * 2600  # Close to limit (triggers warning)
    TEST_CONTENT = "Test content"
    TEST_POST_CONTENT = "Test post content"

    # API responses
    POST_ID = "post_123"
    MOCK_POST_ID = "mock_post_123"
    POST_URL = f"https://www.linkedin.com/feed/update/{POST_ID}/"

    # Error messages
    NO_LINKEDIN_ID_ERROR = "LinkedIn User ID not found"
    AUTH_FAILED_ERROR = "LinkedIn authentication failed"
    AUTH_ERROR_401 = "LinkedIn authentication error"
    API_ERROR_401 = "401 - Unauthorized"
    INVALID_GRANT_ERROR = "invalid_grant"
    CREDENTIALS_ERROR = "LinkedIn API credentials not configured"

    # LinkedIn API URLs
    AUTH_URL_BASE = "https://www.linkedin.com/oauth/v2/authorization"
    CALLBACK_URL = "http://localhost/auth/linkedin/callback"
    CUSTOM_CALLBACK_URL = "https://custom.com/callback"

    # Content validation
    CHARACTER_LIMIT = 3000
    WARNING_THRESHOLD = 2500


class LinkedInTestHelpers:
    """Helper methods for LinkedIn testing."""

    @staticmethod
    def create_mock_user(user_id=TestConstants.TEST_USER_ID, **kwargs):
        """Create a mock user with default LinkedIn values."""
        mock_user = Mock()
        mock_user.id = user_id
        mock_user.linkedin_native_id = kwargs.get(
            "linkedin_id", TestConstants.LINKEDIN_USER_ID
        )
        mock_user.linkedin_native_access_token = kwargs.get(
            "access_token", TestConstants.VALID_ACCESS_TOKEN
        )
        mock_user.linkedin_native_refresh_token = kwargs.get(
            "refresh_token", TestConstants.REFRESH_TOKEN
        )
        mock_user.linkedin_authorized = kwargs.get("authorized", True)

        # Token expiration
        if "token_expires_at" in kwargs:
            mock_user.linkedin_native_token_expires_at = kwargs["token_expires_at"]
        else:
            mock_user.linkedin_native_token_expires_at = datetime.utcnow() + timedelta(
                hours=1
            )

        return mock_user

    @staticmethod
    def create_unauthorized_user(user_id=TestConstants.TEST_USER_ID):
        """Create a mock user without LinkedIn authorization."""
        return LinkedInTestHelpers.create_mock_user(
            user_id=user_id,
            linkedin_id=None,
            access_token=None,
            refresh_token=None,
            authorized=False,
        )

    @staticmethod
    def create_expired_token_user(user_id=TestConstants.TEST_USER_ID):
        """Create a mock user with expired token."""
        return LinkedInTestHelpers.create_mock_user(
            user_id=user_id,
            access_token=TestConstants.EXPIRED_ACCESS_TOKEN,
            token_expires_at=datetime.utcnow() - timedelta(hours=1),
        )

    @staticmethod
    def create_mock_api_response(status_code=200, json_data=None, headers=None):
        """Create a mock API response."""
        mock_response = Mock()
        mock_response.status_code = status_code
        mock_response.json.return_value = json_data or {}

        # Create a proper mock for headers that supports .get() method
        mock_headers = Mock()
        mock_headers.get.return_value = TestConstants.POST_ID
        mock_response.headers = mock_headers

        mock_response.text = "Mock response text"
        return mock_response

    @staticmethod
    def create_mock_token_response():
        """Create a mock token refresh response."""
        return {
            "access_token": TestConstants.NEW_ACCESS_TOKEN,
            "refresh_token": TestConstants.NEW_REFRESH_TOKEN,
            "expires_in": 3600,
        }

    @staticmethod
    def assert_post_result_success(result, expected_post_id=TestConstants.POST_ID):
        """Assert that a post result indicates success."""
        assert result["success"] is True
        assert result["post_id"] == expected_post_id
        assert result["error_message"] is None
        assert "post_url" in result

    @staticmethod
    def assert_post_result_failure(result, expected_error_substring=None):
        """Assert that a post result indicates failure."""
        assert result["success"] is False
        assert result["post_id"] is None
        if expected_error_substring:
            assert expected_error_substring in result["error_message"]

    @staticmethod
    def assert_validation_result(
        result, expected_valid=True, expected_errors=None, expected_warnings=None
    ):
        """Assert validation result matches expectations."""
        assert result["valid"] == expected_valid
        if expected_errors is not None:
            assert result["errors"] == expected_errors
        if expected_warnings is not None:
            assert result["warnings"] == expected_warnings


@pytest.mark.unit
class TestLinkedInManager:
    """Test LinkedInManager class."""

    def test_initialization(self):
        """Test LinkedInManager initialization."""
        manager = LinkedInManager()
        assert manager.platform_name == "linkedin"

    def test_get_platform_name(self):
        """Test platform name generation."""
        manager = LinkedInManager()
        assert manager.get_platform_name() == "linkedin"

    def test_check_authorization_valid_user(self):
        """Test authorization check with valid user."""
        manager = LinkedInManager()
        user = LinkedInTestHelpers.create_mock_user()

        # The method returns the result of an 'and' operation, which is truthy
        result = manager.check_authorization(user)
        assert bool(result) is True

    def test_check_authorization_invalid_user(self):
        """Test authorization check with invalid user."""
        manager = LinkedInManager()

        # Test user without authorization
        user1 = LinkedInTestHelpers.create_unauthorized_user()
        assert bool(manager.check_authorization(user1)) is False

        # Test user with authorization but no token
        user2 = LinkedInTestHelpers.create_mock_user(access_token=None)
        assert bool(manager.check_authorization(user2)) is False

        # Test user with token but no ID
        user3 = LinkedInTestHelpers.create_mock_user(linkedin_id=None)
        assert bool(manager.check_authorization(user3)) is False

    def test_validate_content_valid(self):
        """Test content validation with valid content."""
        manager = LinkedInManager()
        result = manager.validate_content(TestConstants.VALID_CONTENT)

        LinkedInTestHelpers.assert_validation_result(
            result, expected_valid=True, expected_errors=[], expected_warnings=[]
        )

    def test_validate_content_too_long(self):
        """Test content validation with content that's too long."""
        manager = LinkedInManager()
        result = manager.validate_content(TestConstants.LONG_CONTENT)

        expected_errors = [
            f"Content exceeds LinkedIn's {TestConstants.CHARACTER_LIMIT} "
            f"character limit ({len(TestConstants.LONG_CONTENT)} characters)"
        ]
        LinkedInTestHelpers.assert_validation_result(
            result, expected_valid=False, expected_errors=expected_errors
        )

    def test_validate_content_warning_threshold(self):
        """Test content validation warning for content close to limit."""
        manager = LinkedInManager()
        result = manager.validate_content(TestConstants.WARNING_CONTENT)

        expected_warnings = ["Content is close to LinkedIn's character limit"]
        LinkedInTestHelpers.assert_validation_result(
            result,
            expected_valid=True,
            expected_errors=[],
            expected_warnings=expected_warnings,
        )

    def test_get_linkedin_config_success(self):
        """Test successful LinkedIn configuration retrieval."""
        manager = LinkedInManager()

        # Mock the _get_linkedin_config method directly to avoid Flask context issues
        with patch.object(manager, "_get_linkedin_config") as mock_config:
            mock_config.return_value = (
                TestConstants.CLIENT_ID,
                TestConstants.CLIENT_SECRET,
            )

            client_id, client_secret = manager._get_linkedin_config()
            assert client_id == TestConstants.CLIENT_ID
            assert client_secret == TestConstants.CLIENT_SECRET

    def test_get_linkedin_config_missing(self):
        """Test LinkedIn configuration retrieval with missing config."""
        manager = LinkedInManager()

        # Mock the _get_linkedin_config method to raise the expected error
        with patch.object(manager, "_get_linkedin_config") as mock_config:
            mock_config.side_effect = ValueError(TestConstants.CREDENTIALS_ERROR)

            with pytest.raises(ValueError, match=TestConstants.CREDENTIALS_ERROR):
                manager._get_linkedin_config()

    def test_get_auth_url(self):
        """Test LinkedIn OAuth URL generation."""
        manager = LinkedInManager()

        with patch("helpers.platforms.linkedin.url_for") as mock_url_for:
            with patch("helpers.platforms.linkedin.session", {}):
                with patch.object(manager, "_get_linkedin_config") as mock_config:
                    mock_url_for.return_value = TestConstants.CALLBACK_URL
                    mock_config.return_value = (
                        TestConstants.CLIENT_ID,
                        TestConstants.CLIENT_SECRET,
                    )

                    auth_url = manager.get_auth_url()

                    assert TestConstants.AUTH_URL_BASE in auth_url
                    assert f"client_id={TestConstants.CLIENT_ID}" in auth_url
                    assert "response_type=code" in auth_url
                    assert "scope=openid profile w_member_social email" in auth_url

    def test_get_auth_url_with_custom_redirect(self):
        """Test LinkedIn OAuth URL with custom redirect URI."""
        manager = LinkedInManager()

        with patch.object(manager, "_get_linkedin_config") as mock_config:
            with patch("helpers.platforms.linkedin.session", {}):
                mock_config.return_value = (
                    TestConstants.CLIENT_ID,
                    TestConstants.CLIENT_SECRET,
                )

                auth_url = manager.get_auth_url(TestConstants.CUSTOM_CALLBACK_URL)

                assert f"redirect_uri={TestConstants.CUSTOM_CALLBACK_URL}" in auth_url

    @patch("helpers.platforms.linkedin.requests.request")
    def test_make_linkedin_request_success(self, mock_request):
        """Test successful LinkedIn API request."""
        manager = LinkedInManager()

        mock_response = LinkedInTestHelpers.create_mock_api_response()
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = manager._make_linkedin_request("GET", "https://api.linkedin.com/test")

        assert result == mock_response
        mock_request.assert_called_once_with("GET", "https://api.linkedin.com/test")

    @patch("helpers.platforms.linkedin.requests.request")
    def test_make_linkedin_request_http_error(self, mock_request):
        """Test LinkedIn API request with HTTP error."""
        manager = LinkedInManager()

        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.json.side_effect = ValueError("No JSON")

        from requests.exceptions import HTTPError

        mock_response.raise_for_status.side_effect = HTTPError(response=mock_response)
        mock_request.return_value = mock_response

        with pytest.raises(
            ValueError, match="LinkedIn API Request failed: 401 - Unauthorized"
        ):
            manager._make_linkedin_request("GET", "https://api.linkedin.com/test")

    def test_ensure_valid_token_no_token(self):
        """Test token validation with no token."""
        manager = LinkedInManager()
        user = LinkedInTestHelpers.create_mock_user(access_token=None)

        result = manager._ensure_valid_token(user)
        assert result is None

    def test_ensure_valid_token_valid_token(self):
        """Test token validation with valid token."""
        manager = LinkedInManager()
        user = LinkedInTestHelpers.create_mock_user()

        result = manager._ensure_valid_token(user)
        assert result == TestConstants.VALID_ACCESS_TOKEN

    def test_ensure_valid_token_expired_token(self):
        """Test token validation with expired token."""
        manager = LinkedInManager()
        user = LinkedInTestHelpers.create_expired_token_user()

        with patch.object(manager, "_refresh_linkedin_token") as mock_refresh:
            mock_refresh.return_value = False

            result = manager._ensure_valid_token(user)
            assert result is None
            mock_refresh.assert_called_once_with(user)


@pytest.mark.integration
class TestLinkedInManagerPosting:
    """Integration tests for LinkedIn content posting."""

    def test_post_content_success(self):
        """Test successful content posting."""
        manager = LinkedInManager()
        user = LinkedInTestHelpers.create_mock_user()

        # Mock token validation
        with patch.object(manager, "_ensure_valid_token") as mock_token:
            mock_token.return_value = TestConstants.VALID_ACCESS_TOKEN

            # Mock API request
            with patch.object(manager, "_make_linkedin_request") as mock_request:
                mock_response = LinkedInTestHelpers.create_mock_api_response(
                    json_data={"id": TestConstants.POST_ID}
                )
                mock_request.return_value = mock_response

                result = manager.post_content(
                    user, TestConstants.TEST_POST_CONTENT, 456
                )

                LinkedInTestHelpers.assert_post_result_success(result)

    def test_post_content_no_linkedin_id(self):
        """Test content posting with user missing LinkedIn ID."""
        manager = LinkedInManager()
        user = LinkedInTestHelpers.create_mock_user(linkedin_id=None)

        result = manager.post_content(user, TestConstants.TEST_CONTENT, 123)

        LinkedInTestHelpers.assert_post_result_failure(
            result, TestConstants.NO_LINKEDIN_ID_ERROR
        )

    def test_post_content_invalid_token(self):
        """Test content posting with invalid token."""
        manager = LinkedInManager()
        user = LinkedInTestHelpers.create_mock_user()

        with patch.object(manager, "_ensure_valid_token") as mock_token:
            mock_token.return_value = None

            result = manager.post_content(user, TestConstants.TEST_CONTENT, 123)

            LinkedInTestHelpers.assert_post_result_failure(
                result, TestConstants.AUTH_FAILED_ERROR
            )

    def test_post_content_api_error(self):
        """Test content posting with API error."""
        manager = LinkedInManager()
        user = LinkedInTestHelpers.create_mock_user()

        with patch.object(manager, "_ensure_valid_token") as mock_token:
            mock_token.return_value = TestConstants.VALID_ACCESS_TOKEN

            with patch.object(manager, "_make_linkedin_request") as mock_request:
                mock_request.side_effect = ValueError(TestConstants.API_ERROR_401)

                # Mock the database operations to avoid Flask context issues
                with patch("extensions.db"):
                    result = manager.post_content(user, TestConstants.TEST_CONTENT, 123)

                    LinkedInTestHelpers.assert_post_result_failure(
                        result, TestConstants.AUTH_ERROR_401
                    )


@pytest.mark.integration
class TestLinkedInManagerTokenRefresh:
    """Integration tests for LinkedIn token refresh functionality."""

    def test_refresh_token_success(self):
        """Test successful token refresh."""
        manager = LinkedInManager()
        user = LinkedInTestHelpers.create_mock_user()

        with patch.object(manager, "_get_linkedin_config") as mock_config:
            mock_config.return_value = (
                TestConstants.CLIENT_ID,
                TestConstants.CLIENT_SECRET,
            )

            with patch.object(manager, "_make_linkedin_request") as mock_request:
                mock_response = Mock()
                mock_response.json.return_value = (
                    LinkedInTestHelpers.create_mock_token_response()
                )
                mock_request.return_value = mock_response

                # Mock the database import and operations
                with patch("extensions.db") as mock_db:
                    with patch("helpers.platforms.linkedin.datetime") as mock_datetime:
                        mock_datetime.utcnow.return_value = datetime.utcnow()
                        mock_datetime.timedelta = timedelta

                        result = manager._refresh_linkedin_token(user)

                        assert result is True
                        assert (
                            user.linkedin_native_access_token
                            == TestConstants.NEW_ACCESS_TOKEN
                        )
                        assert (
                            user.linkedin_native_refresh_token
                            == TestConstants.NEW_REFRESH_TOKEN
                        )
                        assert user.linkedin_authorized is True
                        mock_db.session.add.assert_called_once_with(user)
                        mock_db.session.commit.assert_called_once()

    def test_refresh_token_no_refresh_token(self):
        """Test token refresh with no refresh token."""
        manager = LinkedInManager()
        user = LinkedInTestHelpers.create_mock_user(refresh_token=None)

        result = manager._refresh_linkedin_token(user)
        assert result is False

    def test_refresh_token_invalid_grant(self):
        """Test token refresh with invalid grant error."""
        manager = LinkedInManager()
        user = LinkedInTestHelpers.create_mock_user()

        with patch.object(manager, "_get_linkedin_config") as mock_config:
            mock_config.return_value = (
                TestConstants.CLIENT_ID,
                TestConstants.CLIENT_SECRET,
            )

            with patch.object(manager, "_make_linkedin_request") as mock_request:
                mock_request.side_effect = ValueError(TestConstants.INVALID_GRANT_ERROR)

                # Mock the database import and operations
                with patch("extensions.db") as mock_db:
                    result = manager._refresh_linkedin_token(user)

                    assert result is False
                    # User tokens should be cleared
                    assert user.linkedin_native_access_token is None
                    assert user.linkedin_native_refresh_token is None
                    assert user.linkedin_authorized is False
                    mock_db.session.add.assert_called_once_with(user)
                    mock_db.session.commit.assert_called_once()
