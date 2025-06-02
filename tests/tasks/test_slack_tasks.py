import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, Mock, MagicMock
from celery.exceptions import Retry

from tasks.slack_tasks import send_slack_invitation_task, slack_get_user_id
from models.user import User
from slack_sdk.errors import SlackApiError

# Generate unique identifier for this test run to avoid conflicts in parallel execution
TEST_RUN_ID = str(uuid.uuid4())[:8]


# --- Test Constants ---
class TestConstants:
    """Test constants for consistent data across tests."""

    # Task names
    INVITATION_TASK_NAME = "tasks.slack_tasks.send_slack_invitation_task"
    GET_USER_ID_TASK_NAME = "tasks.slack_tasks.slack_get_user_id"

    # User test data
    TEST_USER_EMAIL = f"user-{TEST_RUN_ID}@example.com"
    TEST_USER_NAME = f"Test User {TEST_RUN_ID}"
    TEST_SLACK_ID = f"U{TEST_RUN_ID[:7].upper()}"
    TEST_OKTA_ID = f"okta_user_{TEST_RUN_ID}"

    # Slack configuration
    TEST_SLACK_TOKEN = f"xoxb-test-token-{TEST_RUN_ID}"
    TEST_CHANNEL_ID = f"C{TEST_RUN_ID[:7].upper()}"

    # Slack API responses
    @staticmethod
    def get_slack_user_lookup_success(user_id=None):
        """Generate a unique Slack user lookup response."""
        unique_id = str(uuid.uuid4())[:8]
        slack_id = f"U{unique_id[:7].upper()}"
        return {
            "ok": True,
            "user": {
                "id": slack_id,
                "name": "testuser",
                "real_name": TestConstants.TEST_USER_NAME,
                "profile": {"email": TestConstants.TEST_USER_EMAIL},
            },
        }

    # Legacy constant for backward compatibility
    SLACK_USER_LOOKUP_SUCCESS = {
        "ok": True,
        "user": {
            "id": TEST_SLACK_ID,
            "name": "testuser",
            "real_name": TEST_USER_NAME,
            "profile": {"email": TEST_USER_EMAIL},
        },
    }

    # Slack API error codes
    SLACK_ERROR_CODES = {
        "users_not_found": "users_not_found",
        "missing_scope": "missing_scope",
        "invalid_auth": "invalid_auth",
        "account_inactive": "account_inactive",
    }

    # Task configuration defaults
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_DELAY = 300  # send_slack_invitation_task
    GET_USER_ID_RETRY_DELAY = 180  # slack_get_user_id


# --- Test Messages ---
class TestMessages:
    """Expected log messages and error strings."""

    USER_NOT_FOUND = "not found. Cannot"
    NO_SLACK_ID = "does not have a slack_id. Skipping"
    NO_CHANNEL_CONFIG = "SLACK_DEFAULT_CHANNEL_ID is not configured"
    NO_TOKEN_CONFIG = "SLACK_BOT_TOKEN is not configured"
    NO_EMAIL = "has no email. Cannot get Slack ID"
    ALREADY_HAS_SLACK_ID = "already has a slack_id"
    SLACK_USER_NOT_FOUND = "not found on Slack"
    MISSING_PERMISSIONS = "due to missing permissions"
    INVITATION_COMPLETED = "Slack invitation process completed"
    INVITATION_FAILED = "Slack invitation failed"
    STORED_SLACK_ID = "Successfully stored slack_id"


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
            "slack_id": None,
        }
        defaults.update(kwargs)

        user = User(**defaults)
        session.add(user)
        session.commit()
        return user

    @staticmethod
    def create_user_with_slack_id(session, **kwargs):
        """Create a test user with Slack ID."""
        unique_id = str(uuid.uuid4())[:8]
        slack_id = f"U{unique_id[:7].upper()}"
        kwargs.setdefault("slack_id", slack_id)
        return TestHelpers.create_test_user(session, **kwargs)

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
    def mock_slack_api_error(error_code):
        """Create a mock SlackApiError with specified error code."""
        error = SlackApiError("Test error", response={"error": error_code})
        return error

    @staticmethod
    def mock_flask_config(**overrides):
        """Mock Flask current_app.config with test values."""
        config = {
            "SLACK_BOT_TOKEN": TestConstants.TEST_SLACK_TOKEN,
            "SLACK_DEFAULT_CHANNEL_ID": TestConstants.TEST_CHANNEL_ID,
        }
        config.update(overrides)
        return config


# --- Unit Tests ---
@pytest.mark.unit
class TestSlackTasksUnit:
    """Unit tests for Slack tasks without external dependencies."""

    def test_send_invitation_task_configuration(self):
        """Test that send_slack_invitation_task has correct Celery configuration."""
        task = send_slack_invitation_task
        assert task.max_retries == TestConstants.DEFAULT_MAX_RETRIES
        assert task.default_retry_delay == TestConstants.DEFAULT_RETRY_DELAY

    def test_get_user_id_task_configuration(self):
        """Test that slack_get_user_id has correct Celery configuration."""
        task = slack_get_user_id
        assert task.max_retries == TestConstants.DEFAULT_MAX_RETRIES
        assert task.default_retry_delay == TestConstants.GET_USER_ID_RETRY_DELAY

    def test_task_registration(self):
        """Test that tasks are properly registered with Celery."""
        for task in [send_slack_invitation_task, slack_get_user_id]:
            assert hasattr(task, "apply")
            assert hasattr(task, "delay")
            assert hasattr(task, "apply_async")


# --- Integration Tests ---
@pytest.mark.integration
class TestSlackTasksIntegration:
    """Integration tests with database operations and service calls."""

    @patch("services.slack_service.invite_user_to_channel")
    @patch("tasks.slack_tasks.current_app")
    def test_send_invitation_user_not_found(
        self, mock_current_app, mock_invite, session, app
    ):
        """Test send invitation when user is not found."""
        mock_current_app.config = TestHelpers.mock_flask_config()

        with app.app_context():
            result = send_slack_invitation_task.apply(args=[999])

        assert result.successful()
        mock_invite.assert_not_called()

    @patch("services.slack_service.invite_user_to_channel")
    @patch("tasks.slack_tasks.current_app")
    def test_send_invitation_no_slack_id(
        self, mock_current_app, mock_invite, session, app, caplog
    ):
        """Test send invitation when user has no slack_id."""
        user = TestHelpers.create_test_user(session, slack_id=None)
        mock_current_app.config = TestHelpers.mock_flask_config()

        with app.app_context():
            result = send_slack_invitation_task.apply(args=[user.id])

        assert result.successful()
        TestHelpers.assert_log_contains(caplog, "WARNING", TestMessages.NO_SLACK_ID)
        mock_invite.assert_not_called()

    @patch("services.slack_service.invite_user_to_channel")
    @patch("tasks.slack_tasks.current_app")
    def test_send_invitation_config_errors(
        self, mock_current_app, mock_invite, session, app, caplog
    ):
        """Test send invitation with various configuration errors."""
        user = TestHelpers.create_user_with_slack_id(session)

        # Test missing channel config
        mock_current_app.config = TestHelpers.mock_flask_config(
            SLACK_DEFAULT_CHANNEL_ID=None
        )
        with app.app_context():
            result = send_slack_invitation_task.apply(args=[user.id])

        assert result.successful()
        TestHelpers.assert_log_contains(caplog, "ERROR", TestMessages.NO_CHANNEL_CONFIG)
        mock_invite.assert_not_called()

    @patch("services.slack_service.invite_user_to_channel")
    @patch("tasks.slack_tasks.current_app")
    def test_send_invitation_success_and_failure(
        self, mock_current_app, mock_invite, session, app, caplog
    ):
        """Test both successful and failed invitation scenarios."""
        user = TestHelpers.create_user_with_slack_id(session)
        mock_current_app.config = TestHelpers.mock_flask_config()

        # Test success
        mock_invite.return_value = True
        with app.app_context():
            result = send_slack_invitation_task.apply(args=[user.id])

        assert result.successful()
        TestHelpers.assert_log_contains(caplog, "INFO", "Slack invitation")

        # Test service failure
        caplog.clear()
        mock_invite.return_value = False
        with app.app_context():
            result = send_slack_invitation_task.apply(args=[user.id])

        assert result.successful()
        TestHelpers.assert_log_contains(
            caplog, "WARNING", TestMessages.INVITATION_FAILED
        )

    @patch("tasks.slack_tasks.current_app")
    def test_get_user_id_validation_errors(
        self, mock_current_app, session, app, caplog
    ):
        """Test slack_get_user_id validation error scenarios."""
        mock_current_app.config = TestHelpers.mock_flask_config()

        # Test user not found
        with app.app_context():
            result = slack_get_user_id.apply(args=[999])
        assert result.successful()
        TestHelpers.assert_log_contains(caplog, "ERROR", TestMessages.USER_NOT_FOUND)

        # Test no email
        caplog.clear()
        user = TestHelpers.create_test_user(session)
        user.email = ""
        session.commit()

        with app.app_context():
            result = slack_get_user_id.apply(args=[user.id])
        assert result.successful()
        TestHelpers.assert_log_contains(caplog, "ERROR", TestMessages.NO_EMAIL)

        # Test already has slack_id
        caplog.clear()
        user_with_slack = TestHelpers.create_user_with_slack_id(session)
        with app.app_context():
            result = slack_get_user_id.apply(args=[user_with_slack.id])
        assert result.successful()
        TestHelpers.assert_log_contains(
            caplog, "INFO", TestMessages.ALREADY_HAS_SLACK_ID
        )

    @patch("tasks.slack_tasks.current_app")
    def test_get_user_id_no_token_config(self, mock_current_app, session, app):
        """Test slack_get_user_id when SLACK_BOT_TOKEN is not configured."""
        user = TestHelpers.create_test_user(session, slack_id=None)
        mock_current_app.config = TestHelpers.mock_flask_config(SLACK_BOT_TOKEN=None)

        with app.app_context():
            result = slack_get_user_id.apply(args=[user.id])

        assert not result.successful()
        assert "SLACK_BOT_TOKEN not configured" in str(result.traceback)

    @patch("tasks.slack_tasks.WebClient")
    @patch("tasks.slack_tasks.current_app")
    def test_get_user_id_slack_api_scenarios(
        self, mock_current_app, mock_web_client, session, app, caplog
    ):
        """Test various Slack API response scenarios."""
        user = TestHelpers.create_test_user(session, slack_id=None)
        mock_current_app.config = TestHelpers.mock_flask_config()
        mock_client = Mock()
        mock_web_client.return_value = mock_client

        # Test successful lookup - generate unique response
        mock_client.users_lookupByEmail.return_value = (
            TestConstants.get_slack_user_lookup_success()
        )
        with app.app_context():
            result = slack_get_user_id.apply(args=[user.id])
        assert result.successful()
        TestHelpers.assert_log_contains(caplog, "INFO", "slack_id")

        # Test user not found
        caplog.clear()
        user2 = TestHelpers.create_test_user(session, slack_id=None)
        mock_client.users_lookupByEmail.side_effect = TestHelpers.mock_slack_api_error(
            TestConstants.SLACK_ERROR_CODES["users_not_found"]
        )
        with app.app_context():
            result = slack_get_user_id.apply(args=[user2.id])
        assert result.successful()
        TestHelpers.assert_log_contains(
            caplog, "WARNING", TestMessages.SLACK_USER_NOT_FOUND
        )


# --- Error Handling Tests ---
@pytest.mark.integration
class TestSlackTasksErrorHandling:
    """Tests for error handling and retry scenarios."""

    @patch("services.slack_service.invite_user_to_channel")
    @patch("tasks.slack_tasks.current_app")
    def test_send_invitation_exception_retries(
        self, mock_current_app, mock_invite, session, app
    ):
        """Test that exceptions in send_slack_invitation_task trigger retries."""
        user = TestHelpers.create_user_with_slack_id(session)
        mock_current_app.config = TestHelpers.mock_flask_config()
        mock_invite.side_effect = Exception("Service error")

        with app.app_context():
            result = send_slack_invitation_task.apply(args=[user.id])

        # Task should fail due to retry exhaustion
        assert not result.successful()

    @patch("tasks.slack_tasks.WebClient")
    @patch("tasks.slack_tasks.current_app")
    def test_get_user_id_retry_scenarios(
        self, mock_current_app, mock_web_client, session, app
    ):
        """Test various error scenarios that should trigger retries."""
        user = TestHelpers.create_test_user(session, slack_id=None)
        mock_current_app.config = TestHelpers.mock_flask_config()
        mock_client = Mock()
        mock_web_client.return_value = mock_client

        # Test missing scope error (should retry)
        mock_client.users_lookupByEmail.side_effect = TestHelpers.mock_slack_api_error(
            TestConstants.SLACK_ERROR_CODES["missing_scope"]
        )
        with app.app_context():
            result = slack_get_user_id.apply(args=[user.id])
        assert not result.successful()

        # Test invalid auth error (should retry)
        mock_client.users_lookupByEmail.side_effect = TestHelpers.mock_slack_api_error(
            TestConstants.SLACK_ERROR_CODES["invalid_auth"]
        )
        with app.app_context():
            result = slack_get_user_id.apply(args=[user.id])
        assert not result.successful()

        # Test unexpected error (should retry)
        mock_client.users_lookupByEmail.side_effect = Exception("Unexpected error")
        with app.app_context():
            result = slack_get_user_id.apply(args=[user.id])
        assert not result.successful()


# --- Performance Tests ---
@pytest.mark.slow
@pytest.mark.integration
class TestSlackTasksPerformance:
    """Performance and scalability tests."""

    @patch("services.slack_service.invite_user_to_channel")
    @patch("tasks.slack_tasks.current_app")
    def test_send_invitation_multiple_users(
        self, mock_current_app, mock_invite, session, app
    ):
        """Test invitation task can handle multiple sequential calls efficiently."""
        users = [TestHelpers.create_user_with_slack_id(session) for _ in range(10)]
        mock_current_app.config = TestHelpers.mock_flask_config()
        mock_invite.return_value = True

        with app.app_context():
            results = []
            for user in users:
                result = send_slack_invitation_task.apply(args=[user.id])
                results.append(result)

        assert all(result.successful() for result in results)
        assert mock_invite.call_count == len(users)

    @patch("tasks.slack_tasks.WebClient")
    @patch("tasks.slack_tasks.current_app")
    def test_get_user_id_bulk_processing(
        self, mock_current_app, mock_web_client, session, app
    ):
        """Test Slack user ID lookup can handle multiple users efficiently."""
        users = [TestHelpers.create_test_user(session, slack_id=None) for _ in range(5)]
        mock_current_app.config = TestHelpers.mock_flask_config()

        # Mock Slack API client - return unique response for each call
        mock_client = Mock()
        mock_client.users_lookupByEmail.side_effect = [
            TestConstants.get_slack_user_lookup_success() for _ in range(len(users))
        ]
        mock_web_client.return_value = mock_client

        with app.app_context():
            results = []
            for user in users:
                result = slack_get_user_id.apply(args=[user.id])
                results.append(result)

        assert all(result.successful() for result in results)
        assert all(result.result == user.id for result, user in zip(results, users))
        assert mock_client.users_lookupByEmail.call_count == len(users)

    @patch("tasks.slack_tasks.WebClient")
    @patch("services.slack_service.invite_user_to_channel")
    @patch("tasks.slack_tasks.current_app")
    def test_task_chaining_workflow(
        self, mock_current_app, mock_invite, mock_web_client, session, app
    ):
        """Test complete workflow: get Slack ID -> send invitation."""
        user = TestHelpers.create_test_user(session, slack_id=None)
        mock_current_app.config = TestHelpers.mock_flask_config()

        # Mock successful Slack user lookup - generate unique response
        mock_client = Mock()
        mock_client.users_lookupByEmail.return_value = (
            TestConstants.get_slack_user_lookup_success()
        )
        mock_web_client.return_value = mock_client
        mock_invite.return_value = True

        with app.app_context():
            # Step 1: Get Slack user ID
            user_id_result = slack_get_user_id.apply(args=[user.id])
            assert user_id_result.successful()

            # Step 2: Send invitation using the same user ID
            invitation_result = send_slack_invitation_task.apply(
                args=[user_id_result.result]
            )
            assert invitation_result.successful()

        mock_invite.assert_called_once()
