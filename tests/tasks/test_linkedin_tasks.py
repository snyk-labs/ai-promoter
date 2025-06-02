import pytest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, Mock

from tasks.linkedin_tasks import refresh_expiring_linkedin_tokens
from models.user import User

# Generate unique identifier for this test run to avoid conflicts in parallel execution
TEST_RUN_ID = str(uuid.uuid4())[:8]


# --- Test Constants ---
class TestConstants:
    """Test constants for consistent data across tests."""

    # Task configuration
    TASK_NAME = "tasks.linkedin.refresh_expiring_tokens"

    # User test data
    TEST_USER_EMAIL = f"user-{TEST_RUN_ID}@example.com"
    TEST_USER_NAME = f"Test User {TEST_RUN_ID}"
    TEST_SLACK_ID = f"U{TEST_RUN_ID[:7].upper()}"

    # LinkedIn credentials
    TEST_ACCESS_TOKEN = f"access_token_{TEST_RUN_ID}"
    TEST_REFRESH_TOKEN = f"refresh_token_{TEST_RUN_ID}"

    # URLs and configuration
    TEST_BASE_URL = "https://test.example.com"
    EXPECTED_PROFILE_URL = f"{TEST_BASE_URL}/auth/profile"

    # Expected Slack DM text
    EXPECTED_DM_TEXT = (
        f"Hi there! We tried to refresh your LinkedIn connection for AI Promoter, "
        f"but it looks like your authorization has expired or been revoked. "
        f"Please reconnect your LinkedIn account by visiting your profile page: {EXPECTED_PROFILE_URL}"
    )


# --- Test Helpers ---
class TestHelpers:
    """Helper methods for testing."""

    @staticmethod
    def utc_now():
        """Get current UTC time avoiding deprecation warnings."""
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def create_test_user(session, days_until_expiry=5, **kwargs):
        """Create a test user with LinkedIn integration and sensible defaults."""
        unique_id = str(uuid.uuid4())[:8]
        defaults = {
            "email": f"user-{unique_id}@example.com",
            "name": f"Test User {unique_id}",
            "is_admin": False,
            "auth_type": "password",
            "linkedin_authorized": True,
            "linkedin_native_refresh_token": f"refresh_token_{unique_id}",
            "linkedin_native_access_token": f"access_token_{unique_id}",
            "linkedin_native_token_expires_at": TestHelpers.utc_now()
            + timedelta(days=days_until_expiry),
            "slack_id": f"U{unique_id[:7].upper()}",
        }
        defaults.update(kwargs)

        user = User(**defaults)
        session.add(user)
        session.commit()
        return user

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


# --- Unit Tests ---
@pytest.mark.unit
class TestLinkedInTasksUnit:
    """Unit tests for LinkedIn tasks without database operations."""

    def test_task_configuration(self):
        """Test that the task has correct Celery configuration."""
        task = refresh_expiring_linkedin_tokens
        assert task.ignore_result is True
        assert task.name == TestConstants.TASK_NAME

    @patch("tasks.linkedin_tasks.User.query")
    @patch("tasks.linkedin_tasks.logger")
    def test_no_expiring_tokens(self, mock_logger, mock_query, app):
        """Test behavior when no tokens are expiring."""
        mock_query.filter.return_value.all.return_value = []

        with app.app_context():
            result = refresh_expiring_linkedin_tokens.apply()

        assert result.successful()
        mock_logger.info.assert_called_with(
            "No LinkedIn tokens found that are expiring soon and need refreshing."
        )

    @patch("tasks.linkedin_tasks.User.query")
    @patch("tasks.linkedin_tasks.refresh_linkedin_token")
    @patch("tasks.linkedin_tasks.logger")
    def test_successful_refresh(self, mock_logger, mock_refresh_token, mock_query, app):
        """Test successful token refresh."""
        mock_user = Mock()
        mock_user.id = 1
        mock_user.email = TestConstants.TEST_USER_EMAIL

        mock_query.filter.return_value.all.return_value = [mock_user]
        mock_refresh_token.return_value = True

        with app.app_context():
            result = refresh_expiring_linkedin_tokens.apply()

        assert result.successful()
        mock_refresh_token.assert_called_once_with(mock_user)
        assert mock_logger.info.call_count >= 2

    @patch("tasks.linkedin_tasks.User.query")
    @patch("tasks.linkedin_tasks.refresh_linkedin_token")
    @patch("tasks.linkedin_tasks.logger")
    def test_invalid_grant_handling(
        self, mock_logger, mock_refresh_token, mock_query, app
    ):
        """Test handling of invalid_grant error without Slack complications."""
        mock_user = Mock()
        mock_user.id = 1
        mock_user.slack_id = None

        mock_query.filter.return_value.all.return_value = [mock_user]
        mock_refresh_token.return_value = "invalid_grant"

        with app.app_context():
            result = refresh_expiring_linkedin_tokens.apply()

        assert result.successful()
        mock_refresh_token.assert_called_once_with(mock_user)
        assert mock_logger.warning.call_count >= 1


# --- Integration Tests ---
@pytest.mark.integration
class TestLinkedInTasksIntegration:
    """Integration tests with real database operations."""

    @patch("tasks.linkedin_tasks.refresh_linkedin_token")
    def test_no_expiring_tokens_integration(
        self, mock_refresh_token, session, app, caplog
    ):
        """Test with real database when no tokens are expiring."""
        # Create user with non-expiring token
        TestHelpers.create_test_user(session, days_until_expiry=30)

        with app.app_context():
            result = refresh_expiring_linkedin_tokens.apply()

        assert result.successful()
        TestHelpers.assert_log_contains(caplog, "INFO", "No LinkedIn tokens found")
        mock_refresh_token.assert_not_called()

    @patch("tasks.linkedin_tasks.refresh_linkedin_token")
    def test_single_user_success(self, mock_refresh_token, session, app, caplog):
        """Test successful refresh for a single user."""
        user = TestHelpers.create_test_user(session, days_until_expiry=5)
        mock_refresh_token.return_value = True

        with app.app_context():
            result = refresh_expiring_linkedin_tokens.apply()

        assert result.successful()
        mock_refresh_token.assert_called_once_with(user)
        TestHelpers.assert_log_contains(
            caplog, "INFO", "LinkedIn token(s) to attempt refreshing"
        )
        TestHelpers.assert_log_contains(
            caplog, "INFO", "Successfully refreshed LinkedIn token"
        )

    @patch("tasks.linkedin_tasks.refresh_linkedin_token")
    def test_multiple_users_mixed_results(
        self, mock_refresh_token, session, app, caplog
    ):
        """Test multiple users with different refresh outcomes."""
        user1 = TestHelpers.create_test_user(session, days_until_expiry=3)
        user2 = TestHelpers.create_test_user(session, days_until_expiry=6)
        user3 = TestHelpers.create_test_user(session, days_until_expiry=1)

        def refresh_side_effect(user):
            return {user1.id: True, user2.id: False, user3.id: "invalid_grant"}[user.id]

        mock_refresh_token.side_effect = refresh_side_effect

        with app.app_context():
            result = refresh_expiring_linkedin_tokens.apply()

        assert result.successful()
        assert mock_refresh_token.call_count == 3
        TestHelpers.assert_log_contains(caplog, "INFO", "Successful: 1, Failed: 2")

    @patch("tasks.linkedin_tasks.refresh_linkedin_token")
    @patch("tasks.linkedin_tasks.send_slack_dm")
    def test_slack_notification_on_invalid_grant(
        self, mock_send_dm, mock_refresh_token, session, app, caplog
    ):
        """Test Slack notification when refresh fails with invalid_grant."""
        _ = TestHelpers.create_test_user(session, slack_id=TestConstants.TEST_SLACK_ID)
        mock_refresh_token.return_value = "invalid_grant"
        mock_send_dm.return_value = True

        with app.app_context():
            app.config["BASE_URL"] = TestConstants.TEST_BASE_URL
            result = refresh_expiring_linkedin_tokens.apply()

        assert result.successful()
        mock_send_dm.assert_called_once_with(
            TestConstants.TEST_SLACK_ID, TestConstants.EXPECTED_DM_TEXT
        )
        TestHelpers.assert_log_contains(caplog, "WARNING", "invalid (invalid_grant)")
        TestHelpers.assert_log_contains(caplog, "INFO", "Sent Slack DM")

    @patch("tasks.linkedin_tasks.refresh_linkedin_token")
    @patch("tasks.linkedin_tasks.send_slack_dm")
    def test_invalid_grant_without_slack_id(
        self, mock_send_dm, mock_refresh_token, session, app, caplog
    ):
        """Test invalid_grant handling when user has no Slack ID."""
        _ = TestHelpers.create_test_user(session, slack_id=None)
        mock_refresh_token.return_value = "invalid_grant"

        with app.app_context():
            result = refresh_expiring_linkedin_tokens.apply()

        assert result.successful()
        mock_send_dm.assert_not_called()
        TestHelpers.assert_log_contains(caplog, "WARNING", "has no Slack ID")

    @patch("tasks.linkedin_tasks.refresh_linkedin_token")
    @patch("tasks.linkedin_tasks.send_slack_dm")
    def test_slack_dm_failure_handling(
        self, mock_send_dm, mock_refresh_token, session, app, caplog
    ):
        """Test handling when Slack DM sending fails."""
        _ = TestHelpers.create_test_user(session, slack_id=TestConstants.TEST_SLACK_ID)
        mock_refresh_token.return_value = "invalid_grant"
        mock_send_dm.side_effect = Exception("Slack API error")

        with app.app_context():
            app.config["BASE_URL"] = TestConstants.TEST_BASE_URL
            result = refresh_expiring_linkedin_tokens.apply()

        assert result.successful()
        TestHelpers.assert_log_contains(caplog, "ERROR", "Failed to send Slack DM")

    def test_filtering_logic(self, session, app):
        """Test that only appropriate users are processed."""
        # Create various user scenarios
        TestHelpers.create_test_user(session, days_until_expiry=1)  # Should process
        TestHelpers.create_test_user(session, days_until_expiry=5)  # Should process
        TestHelpers.create_test_user(session, days_until_expiry=30)  # Should skip
        TestHelpers.create_test_user(
            session, linkedin_native_refresh_token=None
        )  # Should skip

        with app.app_context():
            with patch("tasks.linkedin_tasks.refresh_linkedin_token") as mock_refresh:
                mock_refresh.return_value = True
                result = refresh_expiring_linkedin_tokens.apply()

        assert result.successful()
        assert mock_refresh.call_count == 2  # Only 2 users should be processed


# --- Error Handling Tests ---
@pytest.mark.integration
class TestLinkedInTasksErrorHandling:
    """Test error handling and edge cases."""

    @patch("tasks.linkedin_tasks.refresh_linkedin_token")
    def test_unexpected_exception_handling(
        self, mock_refresh_token, session, app, caplog
    ):
        """Test handling of unexpected exceptions during refresh."""
        TestHelpers.create_test_user(session)
        mock_refresh_token.side_effect = Exception("Unexpected error")

        with app.app_context():
            result = refresh_expiring_linkedin_tokens.apply()

        assert result.successful()
        TestHelpers.assert_log_contains(
            caplog, "ERROR", "Unexpected error while trying to refresh"
        )
        TestHelpers.assert_log_contains(caplog, "INFO", "Successful: 0, Failed: 1")

    @patch("tasks.linkedin_tasks.User.query")
    def test_database_query_exception(self, mock_query, app):
        """Test handling of database query failures."""
        mock_query.filter.side_effect = Exception("Database error")

        with app.app_context():
            result = refresh_expiring_linkedin_tokens.apply()
            assert result.failed()

    @patch("tasks.linkedin_tasks.refresh_linkedin_token")
    def test_generic_refresh_failure(self, mock_refresh_token, session, app, caplog):
        """Test handling of generic refresh failures."""
        TestHelpers.create_test_user(session)
        mock_refresh_token.return_value = False

        with app.app_context():
            result = refresh_expiring_linkedin_tokens.apply()

        assert result.successful()
        TestHelpers.assert_log_contains(
            caplog, "WARNING", "Failed to refresh LinkedIn token"
        )


# --- Performance Tests ---
@pytest.mark.slow
@pytest.mark.integration
class TestLinkedInTasksPerformance:
    """Performance and scalability tests."""

    @patch("tasks.linkedin_tasks.refresh_linkedin_token")
    def test_bulk_processing(self, mock_refresh_token, session, app):
        """Test processing multiple users efficiently."""
        users = [
            TestHelpers.create_test_user(session, days_until_expiry=i % 7 + 1)
            for i in range(10)
        ]
        mock_refresh_token.return_value = True

        with app.app_context():
            result = refresh_expiring_linkedin_tokens.apply()

        assert result.successful()
        assert mock_refresh_token.call_count == len(users)

    @patch("tasks.linkedin_tasks.refresh_linkedin_token")
    @patch("tasks.linkedin_tasks.send_slack_dm")
    def test_mixed_results_at_scale(
        self, mock_send_dm, mock_refresh_token, session, app
    ):
        """Test performance with mixed success/failure results."""
        users = []
        for i in range(20):
            unique_slack_id = (
                f"U{str(uuid.uuid4())[:7].upper()}" if i % 3 == 0 else None
            )
            user = TestHelpers.create_test_user(session, slack_id=unique_slack_id)
            users.append(user)

        def refresh_side_effect(user):
            return ["invalid_grant", True, False][user.id % 3]

        mock_refresh_token.side_effect = refresh_side_effect
        mock_send_dm.return_value = True

        with app.app_context():
            app.config["BASE_URL"] = TestConstants.TEST_BASE_URL
            result = refresh_expiring_linkedin_tokens.apply()

        assert result.successful()
        assert mock_refresh_token.call_count == len(users)


# --- Integration Tests ---
@pytest.mark.integration
class TestLinkedInTasksCeleryIntegration:
    """Test Celery-specific functionality."""

    def test_task_registration(self):
        """Test that the task is properly registered with Celery."""
        assert refresh_expiring_linkedin_tokens.name == TestConstants.TASK_NAME

    def test_task_scheduling_methods(self):
        """Test that task can be scheduled using Celery methods."""
        # Test delay() method
        result = refresh_expiring_linkedin_tokens.delay()
        assert result is not None

        # Test apply_async() method
        result = refresh_expiring_linkedin_tokens.apply_async()
        assert result is not None

    @patch("tasks.linkedin_tasks.refresh_linkedin_token")
    def test_real_user_model_integration(self, mock_refresh_token, session, app):
        """Test integration with real User model."""
        user = User(
            email=TestConstants.TEST_USER_EMAIL,
            name=TestConstants.TEST_USER_NAME,
            linkedin_authorized=True,
            linkedin_native_refresh_token=TestConstants.TEST_REFRESH_TOKEN,
            linkedin_native_access_token=TestConstants.TEST_ACCESS_TOKEN,
            linkedin_native_token_expires_at=TestHelpers.utc_now() + timedelta(days=3),
            slack_id=TestConstants.TEST_SLACK_ID,
        )
        session.add(user)
        session.commit()

        mock_refresh_token.return_value = True

        with app.app_context():
            result = refresh_expiring_linkedin_tokens.apply()

        assert result.successful()
        mock_refresh_token.assert_called_once()

        # Verify the user object passed is the real model
        called_user = mock_refresh_token.call_args[0][0]
        assert isinstance(called_user, User)
        assert called_user.id == user.id
        assert called_user.email == TestConstants.TEST_USER_EMAIL
