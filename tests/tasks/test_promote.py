import pytest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, Mock, MagicMock

from tasks.promote import generate_content_task, post_to_linkedin_task
from models.user import User
from models.content import Content
from models.share import Share
from helpers.content_generator import Platform, GenerationResult

# Generate unique identifier for this test run to avoid conflicts in parallel execution
TEST_RUN_ID = str(uuid.uuid4())[:8]


# --- Test Constants ---
class TestConstants:
    """Test constants for consistent data across tests."""

    # Task names
    GENERATE_TASK_NAME = "tasks.promote.generate_content_task"
    LINKEDIN_TASK_NAME = "tasks.promote.post_to_linkedin_task"

    # User test data
    TEST_USER_EMAIL = f"user-{TEST_RUN_ID}@example.com"
    TEST_USER_NAME = f"Test User {TEST_RUN_ID}"
    TEST_SLACK_ID = f"U{TEST_RUN_ID[:7].upper()}"

    # Content test data
    TEST_CONTENT_URL = f"https://example.com/article-{TEST_RUN_ID}"
    TEST_CONTENT_TITLE = f"Test Article {TEST_RUN_ID}"
    TEST_CONTENT_COPY = f"Check out this article: {TEST_CONTENT_URL}"
    TEST_GENERATED_CONTENT = f"AI generated content for {TEST_RUN_ID}"

    # Platform data
    SUPPORTED_PLATFORMS = ["linkedin", "twitter", "facebook"]
    UNSUPPORTED_PLATFORM = "unsupported_platform"

    # LinkedIn data
    TEST_ACCESS_TOKEN = f"access_token_{TEST_RUN_ID}"
    TEST_POST_URL = f"https://linkedin.com/post/{TEST_RUN_ID}"

    # Configuration
    TEST_CONFIG = {
        "model_name": "gemini-1.5-pro",
        "max_retries": 3,
        "temperature": 0.7,
        "api_key": f"test_api_key_{TEST_RUN_ID}",
    }

    # Error messages
    USER_NOT_FOUND_ERROR = "User with ID {user_id} not found."
    CONTENT_NOT_FOUND_ERROR = "Content with ID {content_id} not found."
    USER_NOT_AUTHORIZED_ERROR = "User is not authorized for LinkedIn posting. Please connect/re-connect your LinkedIn account."


# --- Test Helpers ---
class TestHelpers:
    """Helper methods for testing."""

    @staticmethod
    def utc_now():
        """Get current UTC time avoiding deprecation warnings."""
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def create_test_user(session, **kwargs):
        """Create a test user with sensible defaults."""
        unique_id = str(uuid.uuid4())[:8]
        defaults = {
            "email": f"user-{unique_id}@example.com",
            "name": f"Test User {unique_id}",
            "is_admin": False,
            "auth_type": "password",
            "linkedin_authorized": True,
            "linkedin_native_access_token": f"access_token_{unique_id}",
            "linkedin_native_refresh_token": f"refresh_token_{unique_id}",
            "linkedin_native_token_expires_at": TestHelpers.utc_now()
            + timedelta(days=30),
            "slack_id": f"U{unique_id[:7].upper()}",
            "autonomous_mode": False,
        }
        defaults.update(kwargs)

        user = User(**defaults)
        session.add(user)
        session.commit()
        return user

    @staticmethod
    def create_test_content(session, **kwargs):
        """Create test content with sensible defaults."""
        unique_id = str(uuid.uuid4())[:8]
        defaults = {
            "url": f"https://example.com/article-{unique_id}",
            "title": f"Test Article {unique_id}",
            "copy": None,  # Default to no copy so AI generation is triggered
        }
        defaults.update(kwargs)

        content = Content(**defaults)
        session.add(content)
        session.commit()
        return content

    @staticmethod
    def create_mock_generation_result(success=True, content=None, error=None):
        """Create a mock GenerationResult object."""
        result = Mock(spec=GenerationResult)
        result.success = success
        result.content = content or TestConstants.TEST_GENERATED_CONTENT
        result.length = len(result.content) if result.content else 0
        result.attempts = 1
        result.error_message = error
        return result

    @staticmethod
    def assert_log_contains(caplog, level, message_fragment):
        """Assert that logs contain a specific message at the specified level."""
        log_messages = [
            record.message
            for record in caplog.records
            if record.levelname == level.upper()
        ]
        assert any(
            message_fragment in msg for msg in log_messages
        ), f"Expected log message containing '{message_fragment}' at {level} level. Found: {log_messages}"

    @staticmethod
    def assert_generation_result_structure(result, platforms=None):
        """Assert the structure of a content generation task result."""
        platforms = platforms or ["linkedin"]

        assert "platforms" in result
        assert "warnings" in result
        assert "user_authorizations" in result
        assert "content_id" in result
        assert "user_id" in result
        assert "config" in result

        for platform in platforms:
            assert platform in result["platforms"]
            platform_result = result["platforms"][platform]
            assert "success" in platform_result
            assert "source" in platform_result

            if platform_result["success"]:
                assert "content" in platform_result
                assert "length" in platform_result
                assert "attempts" in platform_result
            else:
                assert "error" in platform_result


# --- Unit Tests ---
@pytest.mark.unit
class TestGenerateContentTaskUnit:
    """Unit tests for generate_content_task without database operations."""

    def test_task_configuration(self):
        """Test that the task has correct Celery configuration."""
        task = generate_content_task
        assert task.ignore_result is False
        assert task.max_retries == 3
        assert task.default_retry_delay == 60

    @patch("tasks.promote.Content.query")
    @patch("tasks.promote.User.query")
    def test_content_not_found(self, mock_user_query, mock_content_query, app):
        """Test behavior when content is not found."""
        mock_content_query.get.return_value = None
        mock_user_query.get.return_value = Mock()

        with app.app_context():
            result = generate_content_task.apply(args=[999, 1])
            assert not result.successful()
            assert "Content with ID 999 not found" in str(result.result)

    @patch("tasks.promote.Content.query")
    @patch("tasks.promote.User.query")
    def test_user_not_found(self, mock_user_query, mock_content_query, app):
        """Test behavior when user is not found."""
        mock_content_query.get.return_value = Mock()
        mock_user_query.get.return_value = None

        with app.app_context():
            result = generate_content_task.apply(args=[1, 999])
            assert not result.successful()
            assert "User with ID 999 not found" in str(result.result)

    @patch("tasks.promote.Content.query")
    @patch("tasks.promote.User.query")
    @patch("tasks.promote.ContentGenerator")
    @patch("tasks.promote.get_platform_manager")
    @patch("tasks.promote.is_platform_supported")
    def test_user_provided_copy_flow(
        self,
        mock_is_supported,
        mock_get_manager,
        mock_generator_class,
        mock_user_query,
        mock_content_query,
        app,
    ):
        """Test generation when user provides custom copy."""
        # Setup mocks
        mock_content = Mock()
        mock_content.copy = "User provided content"
        mock_content.url = "https://example.com/test"
        mock_user = Mock()
        mock_content_query.get.return_value = mock_content
        mock_user_query.get.return_value = mock_user

        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        mock_config = Mock()
        mock_config.max_length = 300
        mock_generator.get_platform_config.return_value = mock_config

        mock_is_supported.return_value = True
        mock_platform_manager = Mock()
        mock_platform_manager.check_authorization.return_value = True
        mock_get_manager.return_value = mock_platform_manager

        with app.app_context():
            result = generate_content_task.apply(args=[1, 1, ["linkedin"]])

        assert result.successful()
        result_data = result.result
        TestHelpers.assert_generation_result_structure(result_data)

        # Should use user-provided copy with URL appended
        assert (
            "User provided content" in result_data["platforms"]["linkedin"]["content"]
        )
        assert result_data["platforms"]["linkedin"]["source"] == "user_provided"

    @patch("tasks.promote.Content.query")
    @patch("tasks.promote.User.query")
    @patch("tasks.promote.ContentGenerator")
    @patch("tasks.promote.get_platform_manager")
    @patch("tasks.promote.is_platform_supported")
    def test_ai_generation_success(
        self,
        mock_is_supported,
        mock_get_manager,
        mock_generator_class,
        mock_user_query,
        mock_content_query,
        app,
    ):
        """Test successful AI content generation."""
        # Setup mocks
        mock_content = Mock()
        mock_content.copy = None  # No user copy, trigger AI generation
        mock_user = Mock()
        mock_content_query.get.return_value = mock_content
        mock_user_query.get.return_value = mock_user

        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        mock_result = TestHelpers.create_mock_generation_result(success=True)
        mock_generator.generate_content.return_value = mock_result

        mock_is_supported.return_value = True
        mock_platform_manager = Mock()
        mock_platform_manager.check_authorization.return_value = True
        mock_get_manager.return_value = mock_platform_manager

        with app.app_context():
            result = generate_content_task.apply(args=[1, 1, ["linkedin"]])

        assert result.successful()
        result_data = result.result
        TestHelpers.assert_generation_result_structure(result_data)

        assert result_data["platforms"]["linkedin"]["success"] is True
        assert result_data["platforms"]["linkedin"]["source"] == "ai_generated"
        assert (
            result_data["platforms"]["linkedin"]["content"]
            == TestConstants.TEST_GENERATED_CONTENT
        )

    @patch("tasks.promote.Content.query")
    @patch("tasks.promote.User.query")
    @patch("tasks.promote.ContentGenerator")
    def test_unsupported_platform(
        self, mock_generator_class, mock_user_query, mock_content_query, app
    ):
        """Test handling of unsupported platforms."""
        mock_content = Mock()
        mock_content.copy = None
        mock_user = Mock()
        mock_content_query.get.return_value = mock_content
        mock_user_query.get.return_value = mock_user

        # Mock the ContentGenerator to avoid GEMINI_API_KEY requirement
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator

        with app.app_context():
            result = generate_content_task.apply(args=[1, 1, ["invalid_platform"]])

        assert result.successful()
        result_data = result.result

        assert "invalid_platform" in result_data["platforms"]
        assert result_data["platforms"]["invalid_platform"]["success"] is False
        assert (
            "Unsupported platform"
            in result_data["platforms"]["invalid_platform"]["error"]
        )


@pytest.mark.unit
class TestPostToLinkedInTaskUnit:
    """Unit tests for post_to_linkedin_task without database operations."""

    def test_task_configuration(self):
        """Test that the task has correct Celery configuration."""
        task = post_to_linkedin_task
        assert task.ignore_result is False
        assert task.max_retries == 3
        assert task.default_retry_delay == 60

    @patch("tasks.promote.User.query")
    @patch("tasks.promote.Content.query")
    def test_user_not_found(self, mock_content_query, mock_user_query, app):
        """Test behavior when user is not found."""
        mock_user_query.get.return_value = None
        mock_content_query.get.return_value = Mock()

        with app.app_context():
            result = post_to_linkedin_task.apply(args=[999, 1, "test content"])
            assert not result.successful()
            assert "User with ID 999 not found" in str(result.result)

    @patch("tasks.promote.User.query")
    @patch("tasks.promote.Content.query")
    def test_content_not_found(self, mock_content_query, mock_user_query, app):
        """Test behavior when content is not found."""
        mock_user_query.get.return_value = Mock()
        mock_content_query.get.return_value = None

        with app.app_context():
            result = post_to_linkedin_task.apply(args=[1, 999, "test content"])
            assert not result.successful()
            assert "Content with ID 999 not found" in str(result.result)

    @patch("tasks.promote.User.query")
    @patch("tasks.promote.Content.query")
    @patch("tasks.promote.get_platform_manager")
    def test_user_not_authorized(
        self, mock_get_manager, mock_content_query, mock_user_query, app
    ):
        """Test behavior when user is not authorized for LinkedIn."""
        mock_user = Mock()
        mock_content = Mock()
        mock_user_query.get.return_value = mock_user
        mock_content_query.get.return_value = mock_content

        mock_platform_manager = Mock()
        mock_platform_manager.check_authorization.return_value = False
        mock_get_manager.return_value = mock_platform_manager

        with app.app_context():
            result = post_to_linkedin_task.apply(args=[1, 1, "test content"])
            assert not result.successful()
            assert "User is not authorized for LinkedIn posting" in str(result.result)

    @patch("tasks.promote.User.query")
    @patch("tasks.promote.Content.query")
    @patch("tasks.promote.get_platform_manager")
    @patch("tasks.promote.db.session")
    def test_successful_post(
        self, mock_session, mock_get_manager, mock_content_query, mock_user_query, app
    ):
        """Test successful LinkedIn posting."""
        mock_user = Mock()
        mock_user.id = 1
        mock_content = Mock()
        mock_content.id = 1
        mock_user_query.get.return_value = mock_user
        mock_content_query.get.return_value = mock_content

        mock_platform_manager = Mock()
        mock_platform_manager.check_authorization.return_value = True
        mock_platform_manager.post_content.return_value = {
            "success": True,
            "post_url": TestConstants.TEST_POST_URL,
        }
        mock_get_manager.return_value = mock_platform_manager

        with app.app_context():
            result = post_to_linkedin_task.apply(args=[1, 1, "test content"])

        assert result.successful()
        result_data = result.result
        assert result_data["status"] == "SUCCESS"
        assert result_data["message"] == "Posted to LinkedIn successfully!"
        assert result_data["post_url"] == TestConstants.TEST_POST_URL

    @patch("tasks.promote.User.query")
    @patch("tasks.promote.Content.query")
    @patch("tasks.promote.get_platform_manager")
    @patch("tasks.promote.send_slack_dm")
    @patch("tasks.promote.current_app")
    def test_auth_error_with_slack_notification(
        self,
        mock_current_app,
        mock_send_slack_dm,
        mock_get_manager,
        mock_content_query,
        mock_user_query,
        app,
    ):
        """Test auth error handling with Slack notification."""
        mock_user = Mock()
        mock_user.id = 1
        mock_user.slack_id = TestConstants.TEST_SLACK_ID
        mock_content = Mock()
        mock_content.id = 1
        mock_user_query.get.return_value = mock_user
        mock_content_query.get.return_value = mock_content

        mock_platform_manager = Mock()
        mock_platform_manager.check_authorization.return_value = True
        mock_platform_manager.post_content.return_value = {
            "success": False,
            "error_message": "401 Unauthorized - token expired",
        }
        mock_get_manager.return_value = mock_platform_manager

        # Use regular Mock for current_app config
        mock_current_app.config = {"BASE_URL": "https://test.example.com"}

        with app.app_context():
            result = post_to_linkedin_task.apply(args=[1, 1, "test content"])
            assert not result.successful()
            assert "401 Unauthorized - token expired" in str(result.result)

        # Should send Slack DM for auth error
        mock_send_slack_dm.assert_called_once()


# --- Integration Tests ---
@pytest.mark.integration
class TestGenerateContentTaskIntegration:
    """Integration tests for generate_content_task with real database operations."""

    @patch("tasks.promote.ContentGenerator")
    @patch("tasks.promote.get_platform_manager")
    @patch("tasks.promote.is_platform_supported")
    def test_full_flow_user_provided_copy(
        self, mock_is_supported, mock_get_manager, mock_generator_class, session, app
    ):
        """Test complete flow with user-provided copy."""
        user = TestHelpers.create_test_user(session)
        content = TestHelpers.create_test_content(session, copy="User provided content")

        # Setup mocks
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        mock_config = Mock()
        mock_config.max_length = 300
        mock_generator.get_platform_config.return_value = mock_config

        mock_is_supported.return_value = True
        mock_platform_manager = Mock()
        mock_platform_manager.check_authorization.return_value = True
        mock_get_manager.return_value = mock_platform_manager

        with app.app_context():
            result = generate_content_task.apply(
                args=[content.id, user.id, ["linkedin"], TestConstants.TEST_CONFIG]
            )

        assert result.successful()
        result_data = result.result
        TestHelpers.assert_generation_result_structure(result_data)

        assert result_data["content_id"] == content.id
        assert result_data["user_id"] == user.id
        # Content may have URL appended, so check it contains the original
        assert (
            "User provided content" in result_data["platforms"]["linkedin"]["content"]
        )
        assert result_data["platforms"]["linkedin"]["source"] == "user_provided"

    @patch("tasks.promote.ContentGenerator")
    @patch("tasks.promote.get_platform_manager")
    @patch("tasks.promote.is_platform_supported")
    def test_full_flow_ai_generation(
        self, mock_is_supported, mock_get_manager, mock_generator_class, session, app
    ):
        """Test complete flow with AI generation."""
        user = TestHelpers.create_test_user(session)
        content = TestHelpers.create_test_content(session)  # No copy provided

        # Setup mocks
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        mock_result = TestHelpers.create_mock_generation_result(success=True)
        mock_generator.generate_content.return_value = mock_result

        mock_is_supported.return_value = True
        mock_platform_manager = Mock()
        mock_platform_manager.check_authorization.return_value = True
        mock_get_manager.return_value = mock_platform_manager

        with app.app_context():
            result = generate_content_task.apply(args=[content.id, user.id])

        assert result.successful()
        result_data = result.result
        TestHelpers.assert_generation_result_structure(result_data)

        assert result_data["platforms"]["linkedin"]["success"] is True
        assert result_data["platforms"]["linkedin"]["source"] == "ai_generated"

    @patch("tasks.promote.ContentGenerator")
    @patch("tasks.promote.get_platform_manager")
    @patch("tasks.promote.is_platform_supported")
    def test_multiple_platforms(
        self, mock_is_supported, mock_get_manager, mock_generator_class, session, app
    ):
        """Test generation for multiple platforms."""
        user = TestHelpers.create_test_user(session)
        content = TestHelpers.create_test_content(session)

        # Setup mocks
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        mock_result = TestHelpers.create_mock_generation_result(success=True)
        mock_generator.generate_content.return_value = mock_result

        mock_is_supported.return_value = True
        mock_platform_manager = Mock()
        mock_platform_manager.check_authorization.return_value = True
        mock_get_manager.return_value = mock_platform_manager

        platforms = ["linkedin", "twitter"]
        with app.app_context():
            result = generate_content_task.apply(args=[content.id, user.id, platforms])

        assert result.successful()
        result_data = result.result
        TestHelpers.assert_generation_result_structure(result_data, platforms)

        for platform in platforms:
            assert result_data["platforms"][platform]["success"] is True

    @patch("tasks.promote.ContentGenerator")
    @patch("tasks.promote.get_platform_manager")
    @patch("tasks.promote.is_platform_supported")
    def test_generation_failure(
        self,
        mock_is_supported,
        mock_get_manager,
        mock_generator_class,
        session,
        app,
        caplog,
    ):
        """Test handling of generation failures."""
        user = TestHelpers.create_test_user(session)
        content = TestHelpers.create_test_content(session)

        # Setup mocks
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        mock_result = TestHelpers.create_mock_generation_result(
            success=False, error="API rate limit exceeded"
        )
        mock_generator.generate_content.return_value = mock_result

        mock_is_supported.return_value = True
        mock_platform_manager = Mock()
        mock_platform_manager.check_authorization.return_value = True
        mock_get_manager.return_value = mock_platform_manager

        with app.app_context():
            result = generate_content_task.apply(args=[content.id, user.id])

        assert result.successful()
        result_data = result.result

        assert result_data["platforms"]["linkedin"]["success"] is False
        assert (
            "API rate limit exceeded" in result_data["platforms"]["linkedin"]["error"]
        )
        TestHelpers.assert_log_contains(caplog, "ERROR", "Failed to generate")


@pytest.mark.integration
class TestPostToLinkedInTaskIntegration:
    """Integration tests for post_to_linkedin_task with real database operations."""

    @patch("tasks.promote.get_platform_manager")
    def test_successful_posting_with_share_creation(
        self, mock_get_manager, session, app
    ):
        """Test successful posting with Share record creation."""
        user = TestHelpers.create_test_user(session)
        content = TestHelpers.create_test_content(session)

        mock_platform_manager = Mock()
        mock_platform_manager.check_authorization.return_value = True
        mock_platform_manager.post_content.return_value = {
            "success": True,
            "post_url": TestConstants.TEST_POST_URL,
        }
        mock_get_manager.return_value = mock_platform_manager

        with app.app_context():
            result = post_to_linkedin_task.apply(
                args=[user.id, content.id, "test content"]
            )

        assert result.successful()
        result_data = result.result
        assert result_data["status"] == "SUCCESS"
        assert result_data["post_url"] == TestConstants.TEST_POST_URL

        # Verify Share record was created
        share = Share.query.filter_by(
            user_id=user.id, content_id=content.id, platform="linkedin"
        ).first()
        assert share is not None
        assert share.post_content == "test content"
        assert share.post_url == TestConstants.TEST_POST_URL

    @patch("tasks.promote.get_platform_manager")
    def test_unauthorized_user(self, mock_get_manager, session, app):
        """Test posting with unauthorized user."""
        user = TestHelpers.create_test_user(session, linkedin_authorized=False)
        content = TestHelpers.create_test_content(session)

        mock_platform_manager = Mock()
        mock_platform_manager.check_authorization.return_value = False
        mock_get_manager.return_value = mock_platform_manager

        with app.app_context():
            result = post_to_linkedin_task.apply(
                args=[user.id, content.id, "test content"]
            )
            assert not result.successful()
            assert "User is not authorized for LinkedIn posting" in str(result.result)

    @patch("tasks.promote.get_platform_manager")
    @patch("tasks.promote.send_slack_dm")
    @patch("tasks.promote.current_app")
    def test_token_expired_slack_notification(
        self,
        mock_current_app,
        mock_send_slack_dm,
        mock_get_manager,
        session,
        app,
        caplog,
    ):
        """Test Slack notification when LinkedIn token expires."""
        user = TestHelpers.create_test_user(session)
        content = TestHelpers.create_test_content(session)

        mock_platform_manager = Mock()
        mock_platform_manager.check_authorization.return_value = True
        mock_platform_manager.post_content.return_value = {
            "success": False,
            "error_message": "401 Unauthorized - token expired",
        }
        mock_get_manager.return_value = mock_platform_manager

        # Use regular Mock for current_app config
        mock_current_app.config = {"BASE_URL": "https://test.example.com"}

        with app.app_context():
            result = post_to_linkedin_task.apply(
                args=[user.id, content.id, "test content"]
            )
            assert not result.successful()
            assert "401 Unauthorized - token expired" in str(result.result)

        # Verify Slack DM was sent
        mock_send_slack_dm.assert_called_once()
        TestHelpers.assert_log_contains(caplog, "INFO", "Sent Slack DM to user")

    @patch("tasks.promote.get_platform_manager")
    def test_posting_failure(self, mock_get_manager, session, app):
        """Test handling of posting failures."""
        user = TestHelpers.create_test_user(session)
        content = TestHelpers.create_test_content(session)

        mock_platform_manager = Mock()
        mock_platform_manager.check_authorization.return_value = True
        mock_platform_manager.post_content.return_value = {
            "success": False,
            "error_message": "Network error",
        }
        mock_get_manager.return_value = mock_platform_manager

        with app.app_context():
            result = post_to_linkedin_task.apply(
                args=[user.id, content.id, "test content"]
            )
            assert not result.successful()
            assert "Network error" in str(result.result)


# --- Error Handling Tests ---
@pytest.mark.integration
class TestPromoteTasksErrorHandling:
    """Tests for error handling in promote tasks."""

    def test_generate_content_task_database_error(self, session, app):
        """Test generate_content_task handles database errors."""
        # Create invalid IDs that don't exist
        with app.app_context():
            result = generate_content_task.apply(args=[999, 999])
            assert not result.successful()

    def test_post_to_linkedin_task_database_error(self, session, app):
        """Test post_to_linkedin_task handles database errors."""
        # Create invalid IDs that don't exist
        with app.app_context():
            result = post_to_linkedin_task.apply(args=[999, 999, "test content"])
            assert not result.successful()

    @patch("tasks.promote.ContentGenerator")
    def test_generate_content_task_exception_retry(
        self, mock_generator_class, session, app
    ):
        """Test that generate_content_task retries on exceptions."""
        user = TestHelpers.create_test_user(session)
        content = TestHelpers.create_test_content(session)

        mock_generator_class.side_effect = Exception("Unexpected error")

        with app.app_context():
            # The task should retry and eventually fail
            result = generate_content_task.apply(args=[content.id, user.id])

        assert not result.successful()

    @patch("tasks.promote.get_platform_manager")
    def test_post_to_linkedin_task_network_retry(self, mock_get_manager, session, app):
        """Test that post_to_linkedin_task retries on network errors."""
        user = TestHelpers.create_test_user(session)
        content = TestHelpers.create_test_content(session)

        mock_platform_manager = Mock()
        mock_platform_manager.check_authorization.return_value = True
        mock_platform_manager.post_content.side_effect = Exception("Network timeout")
        mock_get_manager.return_value = mock_platform_manager

        with app.app_context():
            # The task should retry and eventually fail
            result = post_to_linkedin_task.apply(
                args=[user.id, content.id, "test content"]
            )

        assert not result.successful()


# --- Performance Tests ---
@pytest.mark.slow
@pytest.mark.integration
class TestPromoteTasksPerformance:
    """Performance tests for promote tasks."""

    @patch("tasks.promote.ContentGenerator")
    @patch("tasks.promote.get_platform_manager")
    @patch("tasks.promote.is_platform_supported")
    def test_generate_content_multiple_platforms_performance(
        self, mock_is_supported, mock_get_manager, mock_generator_class, session, app
    ):
        """Test performance with multiple platforms."""
        user = TestHelpers.create_test_user(session)
        content = TestHelpers.create_test_content(session)

        # Setup mocks
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        mock_result = TestHelpers.create_mock_generation_result(success=True)
        mock_generator.generate_content.return_value = mock_result

        mock_is_supported.return_value = True
        mock_platform_manager = Mock()
        mock_platform_manager.check_authorization.return_value = True
        mock_get_manager.return_value = mock_platform_manager

        platforms = ["linkedin", "twitter", "facebook"]

        with app.app_context():
            result = generate_content_task.apply(args=[content.id, user.id, platforms])

        assert result.successful()
        result_data = result.result

        # Verify all platforms were processed
        for platform in platforms:
            assert platform in result_data["platforms"]
            assert result_data["platforms"][platform]["success"] is True


# --- Celery Integration Tests ---
@pytest.mark.integration
class TestPromoteTasksCeleryIntegration:
    """Tests for Celery-specific functionality."""

    def test_generate_content_task_registration(self):
        """Test that generate_content_task is properly registered with Celery."""
        task = generate_content_task
        assert task.name == "tasks.promote.generate_content_task"
        assert hasattr(task, "apply")
        assert hasattr(task, "delay")
        assert hasattr(task, "apply_async")

    def test_post_to_linkedin_task_registration(self):
        """Test that post_to_linkedin_task is properly registered with Celery."""
        task = post_to_linkedin_task
        assert task.name == "tasks.promote.post_to_linkedin_task"
        assert hasattr(task, "apply")
        assert hasattr(task, "delay")
        assert hasattr(task, "apply_async")

    def test_task_retry_configuration(self):
        """Test that tasks have appropriate retry configuration."""
        generate_task = generate_content_task
        linkedin_task = post_to_linkedin_task

        assert generate_task.max_retries == 3
        assert generate_task.default_retry_delay == 60
        assert linkedin_task.max_retries == 3
        assert linkedin_task.default_retry_delay == 60
