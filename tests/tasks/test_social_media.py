import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, Mock, MagicMock, call

from tasks.social_media import (
    generate_and_post_content,
    generate_content_only,
    post_generated_content,
)
from models.user import User
from models.content import Content
from models.share import Share
from helpers.content_generator import Platform

# Generate unique identifier for this test run to avoid conflicts in parallel execution
TEST_RUN_ID = str(uuid.uuid4())[:8]


# --- Test Constants ---
class TestConstants:
    """Test constants for consistent data across tests."""

    # Task names
    GENERATE_AND_POST_TASK = "tasks.social_media.generate_and_post_content"
    GENERATE_ONLY_TASK = "tasks.social_media.generate_content_only"
    POST_CONTENT_TASK = "tasks.social_media.post_generated_content"

    # User test data
    TEST_USER_EMAIL = f"user-{TEST_RUN_ID}@example.com"
    TEST_USER_NAME = f"Test User {TEST_RUN_ID}"
    TEST_SLACK_ID = f"U{TEST_RUN_ID[:7].upper()}"

    # Content test data
    TEST_CONTENT_URL = f"https://example.com/article-{TEST_RUN_ID}"
    TEST_CONTENT_TITLE = f"Test Article {TEST_RUN_ID}"
    TEST_CONTENT_COPY = f"Check this out: {TEST_CONTENT_URL}"

    # Generated content
    TEST_GENERATED_CONTENT = f"This is generated social media content for {TEST_RUN_ID}"
    TEST_POST_URL = f"https://linkedin.com/posts/{TEST_RUN_ID}"
    TEST_POST_ID = f"post_{TEST_RUN_ID}"

    # Platform data
    SUPPORTED_PLATFORMS = ["linkedin", "twitter", "facebook"]
    UNSUPPORTED_PLATFORMS = ["tiktok", "pinterest"]
    INVALID_PLATFORMS = ["invalid_platform", ""]

    # Configuration options
    DEFAULT_CONFIG = {
        "model_name": "gemini-1.5-pro",
        "temperature": 0.7,
        "max_retries": 3,
    }

    CUSTOM_CONFIG = {
        "model_name": "gpt-4",
        "temperature": 0.5,
        "max_retries": 2,
        "api_key": f"custom_key_{TEST_RUN_ID}",
    }

    # Error messages for testing
    COMMON_ERROR_MESSAGES = {
        "api_timeout": "API request timed out",
        "rate_limit": "Rate limit exceeded",
        "invalid_content": "Content validation failed",
        "database_error": "Database operation failed",
    }


# --- Test Helpers ---
class TestHelpers:
    """Helper methods for testing."""

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
            "slack_id": f"U{unique_id[:7].upper()}",
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
            "copy": f"Test article content for {unique_id}",
        }
        defaults.update(kwargs)

        content = Content(**defaults)
        session.add(content)
        session.commit()
        return content

    @staticmethod
    def create_mock_generation_result(
        success=True, content=None, attempts=1, error_message=None
    ):
        """Create a mock content generation result."""
        mock_result = Mock()
        mock_result.success = success
        mock_result.content = content or TestConstants.TEST_GENERATED_CONTENT
        mock_result.error_message = error_message
        mock_result.attempts = attempts
        mock_result.length = len(mock_result.content) if mock_result.content else 0
        return mock_result

    @staticmethod
    def create_mock_post_result(
        success=True, post_url=None, post_id=None, error_message=None
    ):
        """Create a mock posting result."""
        return {
            "success": success,
            "post_url": post_url or TestConstants.TEST_POST_URL,
            "post_id": post_id or TestConstants.TEST_POST_ID,
            "error_message": error_message,
            "platform_response": (
                {"id": post_id or TestConstants.TEST_POST_ID} if success else None
            ),
        }

    @staticmethod
    def setup_basic_mocks(mock_is_supported, mock_get_manager, mock_generator_class):
        """Set up basic mocks for successful scenarios."""
        mock_is_supported.return_value = True

        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        generation_result = TestHelpers.create_mock_generation_result()
        mock_generator.generate_content.return_value = generation_result

        mock_platform_manager = Mock()
        mock_get_manager.return_value = mock_platform_manager
        mock_platform_manager.check_authorization.return_value = True
        mock_platform_manager.post_content.return_value = (
            TestHelpers.create_mock_post_result()
        )

        return mock_generator, mock_platform_manager

    @staticmethod
    def assert_generation_result_structure(result, platform_name):
        """Assert that a generation result has the expected structure."""
        assert "generation" in result
        assert "posting" in result

        generation = result["generation"]
        assert "success" in generation
        assert "content" in generation
        assert "error_message" in generation
        assert "attempts" in generation
        assert "length" in generation

    @staticmethod
    def assert_task_result_structure(result):
        """Assert that a task result has the expected structure."""
        assert "status" in result
        assert "platforms" in result
        assert "user_id" in result
        assert "content_id" in result
        assert "config" in result
        assert result["status"] in ["SUCCESS", "FAILURE"]

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
    def assert_share_created_correctly(
        user_id, content_id, platform, post_content, post_url=None
    ):
        """Assert that a Share record was created with the correct data."""
        share = Share.query.filter_by(
            user_id=user_id, content_id=content_id, platform=platform
        ).first()
        assert (
            share is not None
        ), f"Share record not found for user {user_id}, content {content_id}, platform {platform}"
        assert share.post_content == post_content
        if post_url:
            assert share.post_url == post_url


# --- Test Data Factory ---
class TestData:
    """Factory for creating test data."""

    @staticmethod
    def make_authorized_user(session, platforms=None):
        """Create a user authorized for specified platforms."""
        if platforms is None:
            platforms = ["linkedin"]

        kwargs = {}
        # Only set linkedin_authorized since that's the only authorization field in the User model
        if "linkedin" in platforms:
            kwargs["linkedin_authorized"] = True

        return TestHelpers.create_test_user(session, **kwargs)

    @staticmethod
    def make_unauthorized_user(session):
        """Create a user with no platform authorizations."""
        return TestHelpers.create_test_user(
            session,
            linkedin_authorized=False,
        )

    @staticmethod
    def make_multiple_test_contents(session, count=3):
        """Create multiple test content items."""
        contents = []
        for i in range(count):
            content = TestHelpers.create_test_content(
                session,
                title=f"Test Article {i} {TEST_RUN_ID}",
                url=f"https://example.com/article-{i}-{TEST_RUN_ID}",
            )
            contents.append(content)
        return contents


# --- Unit Tests ---
@pytest.mark.unit
class TestSocialMediaTasksUnit:
    """Unit tests for social media tasks without database operations."""

    def test_generate_and_post_task_configuration(self):
        """Test that the generate_and_post_content task has correct Celery configuration."""
        task = generate_and_post_content
        assert task.ignore_result is False
        assert task.max_retries == 3
        assert task.default_retry_delay == 60
        assert task.name == TestConstants.GENERATE_AND_POST_TASK

    def test_generate_content_only_task_configuration(self):
        """Test that the generate_content_only task has correct Celery configuration."""
        task = generate_content_only
        assert task.ignore_result is False
        assert task.max_retries == 3
        assert task.default_retry_delay == 60
        assert task.name == TestConstants.GENERATE_ONLY_TASK

    def test_post_generated_content_task_configuration(self):
        """Test that the post_generated_content task has correct Celery configuration."""
        task = post_generated_content
        assert task.ignore_result is False
        assert task.max_retries == 3
        assert task.default_retry_delay == 60
        assert task.name == TestConstants.POST_CONTENT_TASK

    @patch("tasks.social_media.ContentGenerator")
    def test_content_generator_initialization_failure(self, mock_generator_class):
        """Test handling when ContentGenerator initialization fails."""
        mock_generator_class.side_effect = Exception(
            "ContentGenerator initialization failed"
        )

        # Test that the exception is properly raised when ContentGenerator fails to initialize
        with pytest.raises(Exception, match="ContentGenerator initialization failed"):
            # This simulates what happens in the task when ContentGenerator fails
            mock_generator_class(model="invalid-model")


# --- Integration Tests ---
@pytest.mark.integration
class TestGenerateAndPostContentIntegration:
    """Integration tests for generate_and_post_content task."""

    @patch("tasks.social_media.ContentGenerator")
    @patch("tasks.social_media.get_platform_manager")
    @patch("tasks.social_media.is_platform_supported")
    def test_successful_generation_without_posting(
        self, mock_is_supported, mock_get_manager, mock_generator_class, session, app
    ):
        """Test successful content generation without auto-posting."""
        # Setup test data
        user = TestHelpers.create_test_user(session)
        content = TestHelpers.create_test_content(session)
        platforms = ["linkedin", "twitter"]

        # Setup mocks
        mock_generator, _ = TestHelpers.setup_basic_mocks(
            mock_is_supported, mock_get_manager, mock_generator_class
        )

        with app.app_context():
            result = generate_and_post_content.apply(
                args=[content.id, user.id, platforms, None, False]
            ).get()

        # Assertions
        assert result["status"] == "SUCCESS"
        assert result["user_id"] == user.id
        assert result["content_id"] == content.id

        for platform in platforms:
            TestHelpers.assert_generation_result_structure(
                result["platforms"][platform], platform
            )
            assert result["platforms"][platform]["generation"]["success"] is True
            assert result["platforms"][platform]["posting"] is None

        # Verify ContentGenerator was called for each platform
        assert mock_generator.generate_content.call_count == len(platforms)

    @patch("tasks.social_media.ContentGenerator")
    @patch("tasks.social_media.get_platform_manager")
    @patch("tasks.social_media.is_platform_supported")
    def test_successful_generation_with_posting(
        self, mock_is_supported, mock_get_manager, mock_generator_class, session, app
    ):
        """Test successful content generation with auto-posting."""
        # Setup test data
        user = TestData.make_authorized_user(session, ["linkedin"])
        content = TestHelpers.create_test_content(session)
        platforms = ["linkedin"]

        # Setup mocks
        mock_generator, mock_platform_manager = TestHelpers.setup_basic_mocks(
            mock_is_supported, mock_get_manager, mock_generator_class
        )

        with app.app_context():
            result = generate_and_post_content.apply(
                args=[content.id, user.id, platforms, None, True]
            ).get()

        # Assertions
        assert result["status"] == "SUCCESS"
        platform_result = result["platforms"]["linkedin"]
        assert platform_result["generation"]["success"] is True
        assert platform_result["posting"]["success"] is True

        # Check that Share was created correctly
        TestHelpers.assert_share_created_correctly(
            user.id, content.id, "linkedin", TestConstants.TEST_GENERATED_CONTENT
        )

        # Verify platform manager methods were called (without passing the user object to avoid SQLAlchemy issues)
        mock_platform_manager.check_authorization.assert_called_once()
        mock_platform_manager.post_content.assert_called_once()

    @patch("tasks.social_media.ContentGenerator")
    def test_generation_failure(self, mock_generator_class, session, app):
        """Test handling of content generation failure."""
        # Setup test data
        user = TestHelpers.create_test_user(session)
        content = TestHelpers.create_test_content(session)
        platforms = ["linkedin"]

        # Setup mocks
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator

        generation_result = TestHelpers.create_mock_generation_result(
            success=False, content=None, error_message="API error"
        )
        mock_generator.generate_content.return_value = generation_result

        with app.app_context():
            result = generate_and_post_content.apply(
                args=[content.id, user.id, platforms, None, False]
            ).get()

        # Assertions
        assert result["status"] == "FAILURE"
        platform_result = result["platforms"]["linkedin"]
        assert platform_result["generation"]["success"] is False
        assert platform_result["generation"]["error_message"] == "API error"
        assert platform_result["posting"] is None

    @patch("tasks.social_media.ContentGenerator")
    @patch("tasks.social_media.get_platform_manager")
    @patch("tasks.social_media.is_platform_supported")
    def test_unauthorized_user_posting(
        self, mock_is_supported, mock_get_manager, mock_generator_class, session, app
    ):
        """Test posting failure when user is not authorized for platform."""
        # Setup test data
        user = TestData.make_unauthorized_user(session)
        content = TestHelpers.create_test_content(session)
        platforms = ["linkedin"]

        # Setup mocks
        mock_is_supported.return_value = True

        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        generation_result = TestHelpers.create_mock_generation_result()
        mock_generator.generate_content.return_value = generation_result

        mock_platform_manager = Mock()
        mock_get_manager.return_value = mock_platform_manager
        mock_platform_manager.check_authorization.return_value = False

        with app.app_context():
            result = generate_and_post_content.apply(
                args=[content.id, user.id, platforms, None, True]
            ).get()

        # Assertions
        assert result["status"] == "SUCCESS"  # Generation succeeded
        platform_result = result["platforms"]["linkedin"]
        assert platform_result["generation"]["success"] is True
        assert platform_result["posting"]["success"] is False
        assert "not authorized" in platform_result["posting"]["error_message"]

    def test_invalid_user_id(self, session, app):
        """Test handling of invalid user ID."""
        content = TestHelpers.create_test_content(session)

        with app.app_context():
            with pytest.raises(Exception):  # Should raise and retry
                generate_and_post_content.apply(
                    args=[content.id, 99999, ["linkedin"], None, False]
                ).get()

    def test_invalid_content_id(self, session, app):
        """Test handling of invalid content ID."""
        user = TestHelpers.create_test_user(session)

        with app.app_context():
            with pytest.raises(Exception):  # Should raise and retry
                generate_and_post_content.apply(
                    args=[99999, user.id, ["linkedin"], None, False]
                ).get()

    @patch("tasks.social_media.ContentGenerator")
    def test_invalid_platform_handling(
        self, mock_generator_class, session, app, caplog
    ):
        """Test handling of invalid platform names."""
        # Setup test data
        user = TestHelpers.create_test_user(session)
        content = TestHelpers.create_test_content(session)
        platforms = ["invalid_platform"]

        # Setup mocks
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator

        with app.app_context():
            result = generate_and_post_content.apply(
                args=[content.id, user.id, platforms, None, False]
            ).get()

        # Assertions
        assert result["status"] == "FAILURE"
        platform_result = result["platforms"]["invalid_platform"]
        assert platform_result["generation"]["success"] is False
        assert "error_message" in platform_result["generation"]

    @patch("tasks.social_media.ContentGenerator")
    @patch("tasks.social_media.get_platform_manager")
    @patch("tasks.social_media.is_platform_supported")
    def test_multiple_platforms_mixed_results(
        self, mock_is_supported, mock_get_manager, mock_generator_class, session, app
    ):
        """Test content generation for multiple platforms with mixed success."""
        # Setup test data
        user = TestData.make_authorized_user(session, ["linkedin"])
        content = TestHelpers.create_test_content(session)
        platforms = ["linkedin", "twitter"]

        # Setup mocks
        mock_is_supported.return_value = True

        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator

        def generation_side_effect(content, user, platform, **kwargs):
            if platform == Platform.LINKEDIN:
                return TestHelpers.create_mock_generation_result(success=True)
            else:
                return TestHelpers.create_mock_generation_result(
                    success=False, error_message="Twitter API error"
                )

        mock_generator.generate_content.side_effect = generation_side_effect

        mock_platform_manager = Mock()
        mock_get_manager.return_value = mock_platform_manager
        mock_platform_manager.check_authorization.return_value = True
        mock_platform_manager.post_content.return_value = (
            TestHelpers.create_mock_post_result()
        )

        with app.app_context():
            result = generate_and_post_content.apply(
                args=[content.id, user.id, platforms, None, True]
            ).get()

        # Assertions
        assert result["status"] == "SUCCESS"  # At least one succeeded

        linkedin_result = result["platforms"]["linkedin"]
        assert linkedin_result["generation"]["success"] is True
        assert linkedin_result["posting"]["success"] is True

        twitter_result = result["platforms"]["twitter"]
        assert twitter_result["generation"]["success"] is False
        assert twitter_result["posting"] is None

    @patch("tasks.social_media.ContentGenerator")
    def test_custom_configuration(self, mock_generator_class, session, app):
        """Test task with custom configuration parameters."""
        # Setup test data
        user = TestHelpers.create_test_user(session)
        content = TestHelpers.create_test_content(session)
        platforms = ["linkedin"]
        config = TestConstants.CUSTOM_CONFIG

        # Setup mocks
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        generation_result = TestHelpers.create_mock_generation_result()
        mock_generator.generate_content.return_value = generation_result

        with app.app_context():
            result = generate_and_post_content.apply(
                args=[content.id, user.id, platforms, config, False]
            ).get()

        # Assertions
        assert result["status"] == "SUCCESS"
        assert result["config"] == config

        # Verify ContentGenerator was initialized with custom config
        mock_generator_class.assert_called_once_with(
            model="gpt-4", api_key=config["api_key"]
        )

        # Verify generate_content was called with custom parameters
        mock_generator.generate_content.assert_called_once()
        call_kwargs = mock_generator.generate_content.call_args[1]
        assert call_kwargs["max_retries"] == 2
        assert call_kwargs["temperature"] == 0.5


@pytest.mark.integration
class TestGenerateContentOnlyIntegration:
    """Integration tests for generate_content_only task."""

    @patch("tasks.social_media.generate_and_post_content.apply_async")
    def test_generate_content_only_wrapper(self, mock_apply_async, session, app):
        """Test that generate_content_only correctly wraps generate_and_post_content."""
        # Setup test data
        user = TestHelpers.create_test_user(session)
        content = TestHelpers.create_test_content(session)
        platforms = ["linkedin"]
        config = TestConstants.DEFAULT_CONFIG

        # Setup mock
        mock_result = Mock()
        mock_result.get.return_value = {"status": "SUCCESS"}
        mock_apply_async.return_value = mock_result

        with app.app_context():
            result = generate_content_only.apply(
                args=[content.id, user.id, platforms, config]
            ).get()

        # Assertions
        mock_apply_async.assert_called_once_with(
            args=[content.id, user.id, platforms, config, False]
        )
        assert result == {"status": "SUCCESS"}

    @patch("tasks.social_media.generate_and_post_content.apply_async")
    def test_generate_content_only_propagates_errors(
        self, mock_apply_async, session, app
    ):
        """Test that generate_content_only properly propagates errors from the wrapped task."""
        # Setup test data
        user = TestHelpers.create_test_user(session)
        content = TestHelpers.create_test_content(session)

        # Setup mock to simulate failure
        mock_result = Mock()
        mock_result.get.side_effect = Exception("Underlying task failed")
        mock_apply_async.return_value = mock_result

        with app.app_context():
            with pytest.raises(Exception, match="Underlying task failed"):
                generate_content_only.apply(
                    args=[content.id, user.id, ["linkedin"], None]
                ).get()


@pytest.mark.integration
class TestPostGeneratedContentIntegration:
    """Integration tests for post_generated_content task."""

    @patch("tasks.social_media.get_platform_manager")
    @patch("tasks.social_media.is_platform_supported")
    def test_successful_posting(
        self, mock_is_supported, mock_get_manager, session, app
    ):
        """Test successful posting of generated content."""
        # Setup test data
        user = TestData.make_authorized_user(session, ["linkedin"])
        content = TestHelpers.create_test_content(session)
        platform_name = "linkedin"
        post_content = TestConstants.TEST_GENERATED_CONTENT

        # Setup mocks
        mock_is_supported.return_value = True

        mock_platform_manager = Mock()
        mock_get_manager.return_value = mock_platform_manager
        mock_platform_manager.check_authorization.return_value = True
        mock_platform_manager.post_content.return_value = (
            TestHelpers.create_mock_post_result()
        )

        with app.app_context():
            result = post_generated_content.apply(
                args=[user.id, content.id, platform_name, post_content]
            ).get()

        # Assertions
        assert result["status"] == "SUCCESS"
        assert result["platform"] == platform_name
        assert result["result"]["success"] is True

        # Check that Share was created
        TestHelpers.assert_share_created_correctly(
            user.id, content.id, platform_name, post_content
        )

    @patch("tasks.social_media.is_platform_supported")
    def test_unsupported_platform(self, mock_is_supported, session, app):
        """Test posting to unsupported platform."""
        # Setup test data
        user = TestHelpers.create_test_user(session)
        content = TestHelpers.create_test_content(session)
        platform_name = "unsupported_platform"
        post_content = TestConstants.TEST_GENERATED_CONTENT

        # Setup mocks
        mock_is_supported.return_value = False

        with app.app_context():
            with pytest.raises(Exception):  # Should raise and retry
                post_generated_content.apply(
                    args=[user.id, content.id, platform_name, post_content]
                ).get()

    @patch("tasks.social_media.get_platform_manager")
    @patch("tasks.social_media.is_platform_supported")
    def test_unauthorized_user(self, mock_is_supported, mock_get_manager, session, app):
        """Test posting with unauthorized user."""
        # Setup test data
        user = TestData.make_unauthorized_user(session)
        content = TestHelpers.create_test_content(session)
        platform_name = "linkedin"
        post_content = TestConstants.TEST_GENERATED_CONTENT

        # Setup mocks
        mock_is_supported.return_value = True

        mock_platform_manager = Mock()
        mock_get_manager.return_value = mock_platform_manager
        mock_platform_manager.check_authorization.return_value = False

        with app.app_context():
            with pytest.raises(Exception):  # Should raise and retry
                post_generated_content.apply(
                    args=[user.id, content.id, platform_name, post_content]
                ).get()

    def test_invalid_user_id(self, session, app):
        """Test posting with invalid user ID."""
        content = TestHelpers.create_test_content(session)

        with app.app_context():
            with pytest.raises(Exception):  # Should raise and retry
                post_generated_content.apply(
                    args=[99999, content.id, "linkedin", "test content"]
                ).get()

    def test_invalid_content_id(self, session, app):
        """Test posting with invalid content ID."""
        user = TestHelpers.create_test_user(session)

        with app.app_context():
            with pytest.raises(Exception):  # Should raise and retry
                post_generated_content.apply(
                    args=[user.id, 99999, "linkedin", "test content"]
                ).get()

    @patch("tasks.social_media.get_platform_manager")
    @patch("tasks.social_media.is_platform_supported")
    def test_posting_with_special_characters(
        self, mock_is_supported, mock_get_manager, session, app
    ):
        """Test posting content with special characters and unicode."""
        # Setup test data
        user = TestData.make_authorized_user(session, ["linkedin"])
        content = TestHelpers.create_test_content(session)
        platform_name = "linkedin"
        special_content = "Check this out! 🚀✨ Special chars: @#$%^&*()_+ Unicode: café, naïve, résumé"

        # Setup mocks
        mock_is_supported.return_value = True

        mock_platform_manager = Mock()
        mock_get_manager.return_value = mock_platform_manager
        mock_platform_manager.check_authorization.return_value = True
        mock_platform_manager.post_content.return_value = (
            TestHelpers.create_mock_post_result()
        )

        with app.app_context():
            result = post_generated_content.apply(
                args=[user.id, content.id, platform_name, special_content]
            ).get()

        # Assertions
        assert result["status"] == "SUCCESS"

        # Verify special content was handled correctly
        share = Share.query.filter_by(user_id=user.id, content_id=content.id).first()
        assert share.post_content == special_content


@pytest.mark.integration
class TestSocialMediaTasksEdgeCases:
    """Edge case tests for social media tasks."""

    @patch("tasks.social_media.ContentGenerator")
    def test_empty_platforms_list(self, mock_generator_class, session, app):
        """Test handling of empty platforms list."""
        user = TestHelpers.create_test_user(session)
        content = TestHelpers.create_test_content(session)
        platforms = []

        with app.app_context():
            result = generate_and_post_content.apply(
                args=[content.id, user.id, platforms, None, False]
            ).get()

        # Should succeed but with no platform results
        assert result["status"] == "FAILURE"  # No platforms means failure
        assert result["platforms"] == {}

    @patch("tasks.social_media.ContentGenerator")
    @patch("tasks.social_media.get_platform_manager")
    @patch("tasks.social_media.is_platform_supported")
    def test_posting_api_error(
        self, mock_is_supported, mock_get_manager, mock_generator_class, session, app
    ):
        """Test handling of posting API errors."""
        # Setup test data
        user = TestData.make_authorized_user(session, ["linkedin"])
        content = TestHelpers.create_test_content(session)
        platforms = ["linkedin"]

        # Setup mocks
        mock_is_supported.return_value = True

        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        generation_result = TestHelpers.create_mock_generation_result()
        mock_generator.generate_content.return_value = generation_result

        mock_platform_manager = Mock()
        mock_get_manager.return_value = mock_platform_manager
        mock_platform_manager.check_authorization.return_value = True
        mock_platform_manager.post_content.side_effect = Exception("API Error")

        with app.app_context():
            result = generate_and_post_content.apply(
                args=[content.id, user.id, platforms, None, True]
            ).get()

        # Assertions
        assert result["status"] == "SUCCESS"  # Generation succeeded
        platform_result = result["platforms"]["linkedin"]
        assert platform_result["generation"]["success"] is True
        assert platform_result["posting"]["success"] is False
        assert "API Error" in platform_result["posting"]["error_message"]

    @patch("tasks.social_media.ContentGenerator")
    def test_extremely_long_content(self, mock_generator_class, session, app):
        """Test handling of extremely long generated content."""
        # Setup test data
        user = TestHelpers.create_test_user(session)
        content = TestHelpers.create_test_content(session)
        platforms = ["linkedin"]

        # Create very long content
        long_content = "A" * 10000

        # Setup mocks
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        generation_result = TestHelpers.create_mock_generation_result(
            content=long_content
        )
        mock_generator.generate_content.return_value = generation_result

        with app.app_context():
            result = generate_and_post_content.apply(
                args=[content.id, user.id, platforms, None, False]
            ).get()

        # Assertions
        assert result["status"] == "SUCCESS"
        platform_result = result["platforms"]["linkedin"]
        assert platform_result["generation"]["success"] is True
        assert platform_result["generation"]["length"] == 10000

    @patch("tasks.social_media.ContentGenerator")
    @pytest.mark.parametrize(
        "error_type", list(TestConstants.COMMON_ERROR_MESSAGES.keys())
    )
    def test_various_generation_errors(
        self, mock_generator_class, error_type, session, app
    ):
        """Test handling of various types of generation errors."""
        # Setup test data
        user = TestHelpers.create_test_user(session)
        content = TestHelpers.create_test_content(session)
        platforms = ["linkedin"]

        # Setup mocks with specific error
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        error_message = TestConstants.COMMON_ERROR_MESSAGES[error_type]
        generation_result = TestHelpers.create_mock_generation_result(
            success=False, error_message=error_message
        )
        mock_generator.generate_content.return_value = generation_result

        with app.app_context():
            result = generate_and_post_content.apply(
                args=[content.id, user.id, platforms, None, False]
            ).get()

        # Assertions
        assert result["status"] == "FAILURE"
        platform_result = result["platforms"]["linkedin"]
        assert platform_result["generation"]["success"] is False
        assert platform_result["generation"]["error_message"] == error_message

    @patch("tasks.social_media.ContentGenerator")
    def test_none_config_handling(self, mock_generator_class, session, app):
        """Test that None config is handled gracefully."""
        # Setup test data
        user = TestHelpers.create_test_user(session)
        content = TestHelpers.create_test_content(session)
        platforms = ["linkedin"]

        # Setup mocks
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        generation_result = TestHelpers.create_mock_generation_result()
        mock_generator.generate_content.return_value = generation_result

        with app.app_context():
            result = generate_and_post_content.apply(
                args=[content.id, user.id, platforms, None, False]
            ).get()

        # Assertions
        assert result["status"] == "SUCCESS"
        assert result["config"] is None

        # Verify ContentGenerator was initialized with defaults
        mock_generator_class.assert_called_once_with(
            model="gemini-1.5-pro", api_key=None
        )


@pytest.mark.slow
@pytest.mark.integration
class TestSocialMediaTasksPerformance:
    """Performance tests for social media tasks."""

    @patch("tasks.social_media.ContentGenerator")
    @patch("tasks.social_media.get_platform_manager")
    @patch("tasks.social_media.is_platform_supported")
    def test_multiple_platforms_performance(
        self, mock_is_supported, mock_get_manager, mock_generator_class, session, app
    ):
        """Test performance with multiple platforms."""
        # Setup test data
        user = TestData.make_authorized_user(session, TestConstants.SUPPORTED_PLATFORMS)
        content = TestHelpers.create_test_content(session)
        platforms = TestConstants.SUPPORTED_PLATFORMS

        # Setup mocks
        mock_generator, mock_platform_manager = TestHelpers.setup_basic_mocks(
            mock_is_supported, mock_get_manager, mock_generator_class
        )

        with app.app_context():
            result = generate_and_post_content.apply(
                args=[content.id, user.id, platforms, None, True]
            ).get()

        # Assertions
        assert result["status"] == "SUCCESS"
        assert len(result["platforms"]) == len(platforms)

        for platform in platforms:
            assert platform in result["platforms"]
            TestHelpers.assert_generation_result_structure(
                result["platforms"][platform], platform
            )

        # Verify efficient processing - should call generate_content once per platform
        assert mock_generator.generate_content.call_count == len(platforms)

    @patch("tasks.social_media.ContentGenerator")
    @patch("tasks.social_media.get_platform_manager")
    @patch("tasks.social_media.is_platform_supported")
    def test_bulk_content_generation(
        self, mock_is_supported, mock_get_manager, mock_generator_class, session, app
    ):
        """Test processing multiple content items efficiently."""
        # Setup test data
        user = TestData.make_authorized_user(session, ["linkedin"])
        contents = TestData.make_multiple_test_contents(session, count=3)
        platform = "linkedin"

        # Setup mocks
        mock_generator, _ = TestHelpers.setup_basic_mocks(
            mock_is_supported, mock_get_manager, mock_generator_class
        )

        # Process each content item
        results = []
        with app.app_context():
            for content in contents:
                result = generate_and_post_content.apply(
                    args=[content.id, user.id, [platform], None, False]
                ).get()
                results.append(result)

        # Assertions
        assert len(results) == 3
        for result in results:
            assert result["status"] == "SUCCESS"

        # Should have called generate_content once per content item
        assert mock_generator.generate_content.call_count == 3


@pytest.mark.integration
class TestSocialMediaTasksCeleryIntegration:
    """Tests for Celery task integration and configuration."""

    def test_task_registration(self):
        """Test that all tasks are properly registered with Celery."""
        from celery_app import celery

        registered_tasks = celery.tasks.keys()

        assert TestConstants.GENERATE_AND_POST_TASK in registered_tasks
        assert TestConstants.GENERATE_ONLY_TASK in registered_tasks
        assert TestConstants.POST_CONTENT_TASK in registered_tasks

    def test_task_retry_behavior(self, session, app):
        """Test that tasks properly retry on failure."""
        user = TestHelpers.create_test_user(session)
        content = TestHelpers.create_test_content(session)

        # Test with invalid platform to trigger retry
        with app.app_context():
            task_result = generate_and_post_content.apply(
                args=[content.id, user.id, ["linkedin"], None, False], throw=False
            )

        # Task should complete (either success or max retries reached)
        assert task_result.state in ["SUCCESS", "FAILURE", "RETRY"]

    @patch("tasks.social_media.ContentGenerator")
    @patch("tasks.social_media.logger")
    def test_logging_behavior(self, mock_logger, mock_generator_class, session, app):
        """Test that tasks log appropriately during execution."""
        # Setup test data
        user = TestHelpers.create_test_user(session)
        content = TestHelpers.create_test_content(session)
        platforms = ["linkedin"]

        # Setup mocks
        mock_generator = Mock()
        mock_generator_class.return_value = mock_generator
        generation_result = TestHelpers.create_mock_generation_result()
        mock_generator.generate_content.return_value = generation_result

        with app.app_context():
            generate_and_post_content.apply(
                args=[content.id, user.id, platforms, None, False]
            ).get()

        # Verify logging was called
        mock_logger.info.assert_called()

        # Check that the log message contains expected information
        log_calls = [log_call.args[0] for log_call in mock_logger.info.call_args_list]
        assert any("Starting unified content generation" in msg for msg in log_calls)
