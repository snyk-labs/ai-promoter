import pytest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, Mock, MagicMock, call

from tasks.notifications import initiate_posts, send_one_off_content_notification
from models.user import User
from models.content import Content
from flask_mail import Message

# Generate unique identifier for this test run to avoid conflicts in parallel execution
TEST_RUN_ID = str(uuid.uuid4())[:8]


# --- Test Constants ---
class TestConstants:
    """Test constants for consistent data across tests."""

    # Task names
    INITIATE_POSTS_TASK_NAME = "tasks.notifications.initiate_posts"
    ONE_OFF_NOTIFICATION_TASK_NAME = (
        "tasks.notifications.send_one_off_content_notification"
    )

    # User test data
    TEST_USER_EMAIL = f"user-{TEST_RUN_ID}@example.com"
    TEST_USER_NAME = f"Test User {TEST_RUN_ID}"
    TEST_SLACK_ID = f"U{TEST_RUN_ID[:7].upper()}"

    # Content test data
    TEST_CONTENT_URL = f"https://example.com/article-{TEST_RUN_ID}"
    TEST_CONTENT_TITLE = f"Test Article {TEST_RUN_ID}"
    TEST_CONTENT_EXCERPT = f"This is a test excerpt for {TEST_RUN_ID}"
    TEST_SCRAPED_CONTENT = f"This is scraped content for testing {TEST_RUN_ID}. " * 10

    # Configuration
    TEST_BASE_URL = "https://test.example.com"
    TEST_COMPANY_NAME = "Test Company"
    TEST_SLACK_TOKEN = f"xoxb-test-token-{TEST_RUN_ID}"
    TEST_SLACK_CHANNEL_ID = f"C{TEST_RUN_ID[:7].upper()}"
    TEST_MAIL_SENDER = f"noreply-{TEST_RUN_ID}@example.com"

    # Redis cache keys
    LAST_RUN_REDIS_KEY = "last_content_notification_run"

    # Expected email subject
    EXPECTED_EMAIL_SUBJECT = "New Content Available to Share!"

    # Slack constants
    MAX_ITEMS_PER_MESSAGE = 15


# --- Test Helpers ---
class TestHelpers:
    """Helper methods for testing."""

    @staticmethod
    def utc_now():
        """Get current UTC time avoiding deprecation warnings."""
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def create_test_user(session, linkedin_authorized=True, **kwargs):
        """Create a test user with sensible defaults."""
        unique_id = str(uuid.uuid4())[:8]
        defaults = {
            "email": f"user-{unique_id}@example.com",
            "name": f"Test User {unique_id}",
            "is_admin": False,
            "auth_type": "password",
            "linkedin_authorized": linkedin_authorized,
            "slack_id": f"U{unique_id[:7].upper()}",
        }
        defaults.update(kwargs)

        user = User(**defaults)
        session.add(user)
        session.commit()
        return user

    @staticmethod
    def create_test_content(session, created_at=None, **kwargs):
        """Create test content with sensible defaults."""
        unique_id = str(uuid.uuid4())[:8]
        defaults = {
            "url": f"https://example.com/article-{unique_id}",
            "title": f"Test Article {unique_id}",
            "excerpt": f"Test excerpt for {unique_id}",
            "scraped_content": f"Scraped content for testing {unique_id}. " * 10,
            "image_url": f"https://example.com/image-{unique_id}.jpg",
            "created_at": created_at or TestHelpers.utc_now(),
        }
        defaults.update(kwargs)

        content = Content(**defaults)
        session.add(content)
        session.commit()
        return content

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
    def create_mock_app_config(**overrides):
        """Create a mock app config with sensible defaults."""
        defaults = {
            "BASE_URL": TestConstants.TEST_BASE_URL,
            "COMPANY_NAME": TestConstants.TEST_COMPANY_NAME,
            "EMAIL_ENABLED": True,
            "MAIL_DEFAULT_SENDER": TestConstants.TEST_MAIL_SENDER,
            "SLACK_NOTIFICATIONS_ENABLED": True,
            "SLACK_BOT_TOKEN": TestConstants.TEST_SLACK_TOKEN,
            "SLACK_DEFAULT_CHANNEL_ID": TestConstants.TEST_SLACK_CHANNEL_ID,
        }
        defaults.update(overrides)
        return defaults

    @staticmethod
    def setup_notification_mocks():
        """Set up standard mocks for notification tests."""
        mocks = {
            "redis": Mock(),
            "render_template": Mock(return_value="Rendered template content"),
            "mail": Mock(),
            "webclient": Mock(),
            "slack_client": Mock(),
        }
        mocks["webclient"].return_value = mocks["slack_client"]
        mocks["redis"].get.return_value = None
        mocks["redis"].set.return_value = True
        return mocks

    @staticmethod
    def assert_email_sent_correctly(mock_mail_send, user_email, expected_subject=None):
        """Assert that email was sent with correct parameters."""
        mock_mail_send.assert_called_once()
        sent_message = mock_mail_send.call_args[0][0]
        assert isinstance(
            sent_message, Message
        ), "Should send a Flask-Mail Message object"

        expected_subject = expected_subject or TestConstants.EXPECTED_EMAIL_SUBJECT
        assert (
            sent_message.subject == expected_subject
        ), f"Email subject should be '{expected_subject}'"
        assert (
            user_email in sent_message.recipients
        ), f"Email should be sent to {user_email}"
        assert (
            sent_message.sender == TestConstants.TEST_MAIL_SENDER
        ), "Email should have correct sender"
        assert sent_message.html is not None, "Email should have HTML content"

    @staticmethod
    def assert_slack_message_sent_correctly(
        mock_slack_client, channel_id, expected_content_count=None
    ):
        """Assert that Slack message was sent with correct parameters."""
        mock_slack_client.chat_postMessage.assert_called_once()
        call_kwargs = mock_slack_client.chat_postMessage.call_args[1]

        assert (
            call_kwargs["channel"] == channel_id
        ), f"Slack message should be sent to channel {channel_id}"
        assert "text" in call_kwargs, "Slack message should have fallback text"
        assert "blocks" in call_kwargs, "Slack message should have block structure"
        assert (
            len(call_kwargs["blocks"]) > 0
        ), "Slack message should have at least one block"


# --- Fixtures ---
@pytest.fixture
def notification_mocks():
    """Fixture providing standard notification mocks."""
    return TestHelpers.setup_notification_mocks()


@pytest.fixture
def sample_users(session):
    """Fixture providing sample users for testing."""
    return [
        TestHelpers.create_test_user(session, linkedin_authorized=True),
        TestHelpers.create_test_user(session, linkedin_authorized=True),
        TestHelpers.create_test_user(session, linkedin_authorized=False),
    ]


@pytest.fixture
def sample_content(session):
    """Fixture providing sample content for testing."""
    return [
        TestHelpers.create_test_content(session),
        TestHelpers.create_test_content(session, excerpt=None),
        TestHelpers.create_test_content(session, excerpt=None, scraped_content=None),
    ]


# --- Unit Tests ---
@pytest.mark.unit
class TestNotificationTasksUnit:
    """Unit tests for notification tasks without database operations."""

    def test_initiate_posts_task_configuration(self):
        """Test that the initiate_posts task has correct Celery configuration."""
        task = initiate_posts
        assert task.name == TestConstants.INITIATE_POSTS_TASK_NAME

    def test_send_one_off_notification_task_configuration(self):
        """Test that the send_one_off_content_notification task has correct Celery configuration."""
        task = send_one_off_content_notification
        assert task.name == TestConstants.ONE_OFF_NOTIFICATION_TASK_NAME

    @patch("tasks.notifications.redis_client")
    @patch("tasks.notifications.Content.query")
    @patch("tasks.notifications.User.query")
    @patch("tasks.notifications.logger")
    def test_no_new_content_found(
        self, mock_logger, mock_user_query, mock_content_query, mock_redis, app
    ):
        """Test behavior when no new content is found."""
        mock_redis.get.return_value = None
        mock_content_query.filter.return_value.all.return_value = []

        with app.app_context():
            result = initiate_posts.apply()

        assert (
            result.successful()
        ), "Task should complete successfully when no content found"
        assert "No new content to notify about." in result.result
        mock_logger.info.assert_any_call("Found 0 new content items.")

    @patch("tasks.notifications.redis_client")
    @patch("tasks.notifications.Content.query")
    @patch("tasks.notifications.User.query")
    @patch("tasks.notifications.logger")
    def test_no_authorized_users_found(
        self, mock_logger, mock_user_query, mock_content_query, mock_redis, app
    ):
        """Test behavior when content exists but no authorized users found."""
        mock_redis.get.return_value = None
        mock_content_query.filter.return_value.all.return_value = [Mock()]
        mock_user_query.filter.return_value.all.return_value = []

        with app.app_context():
            result = initiate_posts.apply()

        assert (
            result.successful()
        ), "Task should complete successfully when no authorized users found"
        assert "no users with LinkedIn auth to notify" in result.result

    @patch("tasks.notifications.db.session.get")
    def test_send_one_off_notification_content_not_found(self, mock_db_get, app):
        """Test one-off notification when content is not found."""
        mock_db_get.return_value = None  # Content not found

        with app.app_context():
            result = send_one_off_content_notification.apply(args=[999])

        assert (
            result.successful()
        ), "Task should complete successfully even when content not found"
        assert result.result == "Content not found."

    @patch("tasks.notifications.redis_client")
    @patch("tasks.notifications.Content.query")
    @patch("tasks.notifications.User.query")
    @patch("tasks.notifications.logger")
    def test_redis_cache_hit_with_recent_run(
        self, mock_logger, mock_user_query, mock_content_query, mock_redis, app
    ):
        """Test behavior when Redis cache shows a recent run."""
        recent_time = TestHelpers.utc_now() - timedelta(minutes=30)
        mock_redis.get.return_value = recent_time.isoformat()
        mock_content_query.filter.return_value.all.return_value = []

        with app.app_context():
            result = initiate_posts.apply()

        assert result.successful()
        # Verify the filter was called with the cached time
        mock_content_query.filter.assert_called_once()


# --- Integration Tests ---
@pytest.mark.integration
class TestNotificationTasksIntegration:
    """Integration tests with real database operations."""

    def test_successful_notification_with_content_and_users(
        self, session, app, notification_mocks
    ):
        """Test successful notification when content and users exist."""
        # Setup data
        TestHelpers.create_test_user(session, linkedin_authorized=True)
        TestHelpers.create_test_content(session)
        app.config.update(TestHelpers.create_mock_app_config())

        with app.app_context():
            with patch("tasks.notifications.redis_client", notification_mocks["redis"]):
                with patch(
                    "tasks.notifications.render_template",
                    notification_mocks["render_template"],
                ):
                    with patch("tasks.notifications.mail", notification_mocks["mail"]):
                        with patch(
                            "tasks.notifications.WebClient",
                            notification_mocks["webclient"],
                        ):
                            result = initiate_posts.apply()

        assert (
            result.successful()
        ), f"Task should complete successfully, got: {result.result}"
        assert "Emails sent: 1" in result.result
        assert "Slack messages: 1" in result.result

        # Verify components were called
        notification_mocks["mail"].send.assert_called_once()
        notification_mocks["slack_client"].chat_postMessage.assert_called_once()
        notification_mocks["redis"].set.assert_called_with(
            TestConstants.LAST_RUN_REDIS_KEY,
            notification_mocks["redis"].set.call_args[0][1],
        )

    def test_content_filtering_by_date(self, session, app, notification_mocks):
        """Test that only content created after last run is processed."""
        last_run = TestHelpers.utc_now() - timedelta(hours=12)
        notification_mocks["redis"].get.return_value = last_run.isoformat()

        # Create content before and after last run
        TestHelpers.create_test_content(
            session, created_at=last_run - timedelta(hours=1)
        )
        TestHelpers.create_test_content(
            session, created_at=last_run + timedelta(hours=1)
        )
        TestHelpers.create_test_user(session, linkedin_authorized=True)

        app.config.update(TestHelpers.create_mock_app_config())

        with app.app_context():
            with patch("tasks.notifications.redis_client", notification_mocks["redis"]):
                with patch(
                    "tasks.notifications.render_template",
                    notification_mocks["render_template"],
                ):
                    with patch("tasks.notifications.mail", notification_mocks["mail"]):
                        with patch(
                            "tasks.notifications.WebClient",
                            notification_mocks["webclient"],
                        ):
                            result = initiate_posts.apply()

        assert result.successful()
        # Should only process the new content (verified through template calls)
        assert notification_mocks["render_template"].called

    def test_email_disabled_configuration(
        self, session, app, notification_mocks, caplog
    ):
        """Test behavior when email is disabled in configuration."""
        TestHelpers.create_test_user(session, linkedin_authorized=True)
        TestHelpers.create_test_content(session)

        config = TestHelpers.create_mock_app_config(EMAIL_ENABLED=False)
        app.config.update(config)

        with app.app_context():
            with patch("tasks.notifications.redis_client", notification_mocks["redis"]):
                with patch(
                    "tasks.notifications.render_template",
                    notification_mocks["render_template"],
                ):
                    with patch("tasks.notifications.mail", notification_mocks["mail"]):
                        with patch(
                            "tasks.notifications.WebClient",
                            notification_mocks["webclient"],
                        ):
                            result = initiate_posts.apply()

        assert result.successful()
        notification_mocks["mail"].send.assert_not_called()
        TestHelpers.assert_log_contains(caplog, "INFO", "Email sending is disabled")

    def test_slack_disabled_configuration(self, session, app, notification_mocks):
        """Test behavior when Slack notifications are disabled."""
        TestHelpers.create_test_user(session, linkedin_authorized=True)
        TestHelpers.create_test_content(session)

        config = TestHelpers.create_mock_app_config(
            SLACK_NOTIFICATIONS_ENABLED=False, EMAIL_ENABLED=False
        )
        app.config.update(config)

        with app.app_context():
            with patch("tasks.notifications.redis_client", notification_mocks["redis"]):
                with patch(
                    "tasks.notifications.render_template",
                    notification_mocks["render_template"],
                ):
                    with patch("tasks.notifications.mail", notification_mocks["mail"]):
                        with patch(
                            "tasks.notifications.WebClient",
                            notification_mocks["webclient"],
                        ):
                            result = initiate_posts.apply()

        assert result.successful()
        notification_mocks["webclient"].assert_not_called()

    def test_send_one_off_notification_success(self, session, app, notification_mocks):
        """Test successful one-off notification sending."""
        content = TestHelpers.create_test_content(session)
        app.config.update(TestHelpers.create_mock_app_config())

        with app.app_context():
            with patch(
                "tasks.notifications.WebClient", notification_mocks["webclient"]
            ):
                result = send_one_off_content_notification.apply(args=[content.id])

        assert result.successful()
        assert f"Notification sent for content ID {content.id}" in result.result

        call_kwargs = notification_mocks["slack_client"].chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == TestConstants.TEST_SLACK_CHANNEL_ID
        assert content.title in call_kwargs["text"]

    def test_send_one_off_notification_slack_disabled(self, session, app):
        """Test one-off notification when Slack is disabled."""
        content = TestHelpers.create_test_content(session)
        app.config.update(
            TestHelpers.create_mock_app_config(SLACK_NOTIFICATIONS_ENABLED=False)
        )

        with app.app_context():
            result = send_one_off_content_notification.apply(args=[content.id])

        assert result.successful()
        assert result.result == "Slack notifications disabled."

    def test_multiple_users_notification(
        self, sample_users, sample_content, app, notification_mocks
    ):
        """Test notification sending to multiple users."""
        linkedin_users = [user for user in sample_users if user.linkedin_authorized]
        app.config.update(TestHelpers.create_mock_app_config())

        with app.app_context():
            with patch("tasks.notifications.redis_client", notification_mocks["redis"]):
                with patch(
                    "tasks.notifications.render_template",
                    notification_mocks["render_template"],
                ):
                    with patch("tasks.notifications.mail", notification_mocks["mail"]):
                        with patch(
                            "tasks.notifications.WebClient",
                            notification_mocks["webclient"],
                        ):
                            result = initiate_posts.apply()

        assert result.successful()
        expected_emails = len(linkedin_users)
        assert f"Emails sent: {expected_emails}" in result.result
        assert notification_mocks["mail"].send.call_count == expected_emails


# --- Error Handling Tests ---
@pytest.mark.integration
class TestNotificationTasksErrorHandling:
    """Test error handling and edge cases."""

    def test_email_sending_failure(self, session, app, notification_mocks, caplog):
        """Test handling of email sending failures."""
        TestHelpers.create_test_user(session, linkedin_authorized=True)
        TestHelpers.create_test_content(session)

        notification_mocks["mail"].send.side_effect = Exception("SMTP Error")
        config = TestHelpers.create_mock_app_config(SLACK_NOTIFICATIONS_ENABLED=False)
        app.config.update(config)

        with app.app_context():
            with patch("tasks.notifications.redis_client", notification_mocks["redis"]):
                with patch(
                    "tasks.notifications.render_template",
                    notification_mocks["render_template"],
                ):
                    with patch("tasks.notifications.mail", notification_mocks["mail"]):
                        with patch(
                            "tasks.notifications.WebClient",
                            notification_mocks["webclient"],
                        ):
                            result = initiate_posts.apply()

        assert result.successful(), "Task should handle email failures gracefully"
        TestHelpers.assert_log_contains(caplog, "ERROR", "Failed to send email")

    def test_slack_api_error(self, session, app, notification_mocks, caplog):
        """Test handling of Slack API errors."""
        from slack_sdk.errors import SlackApiError

        TestHelpers.create_test_user(session, linkedin_authorized=True)
        TestHelpers.create_test_content(session)

        notification_mocks["slack_client"].chat_postMessage.side_effect = SlackApiError(
            message="Invalid channel", response={"error": "channel_not_found"}
        )

        config = TestHelpers.create_mock_app_config(EMAIL_ENABLED=False)
        app.config.update(config)

        with app.app_context():
            with patch("tasks.notifications.redis_client", notification_mocks["redis"]):
                with patch(
                    "tasks.notifications.render_template",
                    notification_mocks["render_template"],
                ):
                    with patch("tasks.notifications.mail", notification_mocks["mail"]):
                        with patch(
                            "tasks.notifications.WebClient",
                            notification_mocks["webclient"],
                        ):
                            result = initiate_posts.apply()

        assert result.successful(), "Task should handle Slack API errors gracefully"
        TestHelpers.assert_log_contains(caplog, "ERROR", "Slack API Error")

    def test_send_one_off_slack_configuration_missing(
        self, session, app, notification_mocks
    ):
        """Test one-off notification when Slack configuration is missing."""
        content = TestHelpers.create_test_content(session)

        config = TestHelpers.create_mock_app_config(
            SLACK_BOT_TOKEN=None, SLACK_DEFAULT_CHANNEL_ID=None
        )
        app.config.update(config)

        with app.app_context():
            with patch(
                "tasks.notifications.WebClient", notification_mocks["webclient"]
            ):
                result = send_one_off_content_notification.apply(args=[content.id])

        assert result.successful()
        assert result.result == "Slack configuration missing."

    def test_database_query_exception(self, app, notification_mocks):
        """Test handling of database query failures."""
        with app.app_context():
            with patch("tasks.notifications.redis_client", notification_mocks["redis"]):
                with patch("tasks.notifications.Content.query") as mock_content_query:
                    mock_content_query.filter.side_effect = Exception("Database error")

                    result = initiate_posts.apply()
                    assert (
                        result.failed()
                    ), "Task should fail when database errors occur"

    def test_template_rendering_failure(self, session, app, notification_mocks, caplog):
        """Test handling of template rendering failures."""
        TestHelpers.create_test_user(session, linkedin_authorized=True)
        TestHelpers.create_test_content(session)

        notification_mocks["render_template"].side_effect = Exception("Template error")
        app.config.update(TestHelpers.create_mock_app_config())

        with app.app_context():
            with patch("tasks.notifications.redis_client", notification_mocks["redis"]):
                with patch(
                    "tasks.notifications.render_template",
                    notification_mocks["render_template"],
                ):
                    with patch("tasks.notifications.mail", notification_mocks["mail"]):
                        with patch(
                            "tasks.notifications.WebClient",
                            notification_mocks["webclient"],
                        ):
                            result = initiate_posts.apply()

        assert result.successful(), "Task should handle template errors gracefully"
        TestHelpers.assert_log_contains(caplog, "ERROR", "Failed to send email")

    def test_redis_connection_failure(self, session, app, caplog):
        """Test handling of Redis connection failures."""
        TestHelpers.create_test_user(session, linkedin_authorized=True)
        TestHelpers.create_test_content(session)

        with app.app_context():
            with patch("tasks.notifications.redis_client") as mock_redis:
                mock_redis.get.side_effect = Exception("Redis connection error")

                result = initiate_posts.apply()
                assert result.failed(), "Task should fail when Redis is unavailable"

    def test_slack_configuration_warning(
        self, session, app, notification_mocks, caplog
    ):
        """Test warning when Slack is enabled but not properly configured."""
        TestHelpers.create_test_user(session, linkedin_authorized=True)
        TestHelpers.create_test_content(session)

        config = TestHelpers.create_mock_app_config(
            EMAIL_ENABLED=False, SLACK_BOT_TOKEN=None  # Missing token
        )
        app.config.update(config)

        with app.app_context():
            with patch("tasks.notifications.redis_client", notification_mocks["redis"]):
                with patch(
                    "tasks.notifications.render_template",
                    notification_mocks["render_template"],
                ):
                    with patch("tasks.notifications.mail", notification_mocks["mail"]):
                        with patch(
                            "tasks.notifications.WebClient",
                            notification_mocks["webclient"],
                        ):
                            result = initiate_posts.apply()

        assert result.successful()
        TestHelpers.assert_log_contains(
            caplog, "WARNING", "token/channel_id not configured"
        )


# --- Content Processing Tests ---
@pytest.mark.integration
class TestNotificationContentProcessing:
    """Test content processing and formatting in notifications."""

    def test_content_with_excerpt(self, session, app, notification_mocks):
        """Test content processing when excerpt is available."""
        TestHelpers.create_test_user(session, linkedin_authorized=True)
        TestHelpers.create_test_content(
            session,
            excerpt=TestConstants.TEST_CONTENT_EXCERPT,
            scraped_content=TestConstants.TEST_SCRAPED_CONTENT,
        )

        app.config.update(TestHelpers.create_mock_app_config())

        with app.app_context():
            with patch("tasks.notifications.redis_client", notification_mocks["redis"]):
                with patch(
                    "tasks.notifications.render_template",
                    notification_mocks["render_template"],
                ):
                    with patch("tasks.notifications.mail", notification_mocks["mail"]):
                        with patch(
                            "tasks.notifications.WebClient",
                            notification_mocks["webclient"],
                        ):
                            result = initiate_posts.apply()

        assert result.successful()

        # Verify that render_template was called with content_summary containing excerpt
        render_calls = notification_mocks["render_template"].call_args_list
        email_template_call = [
            template_call
            for template_call in render_calls
            if "email/" in template_call[0][0]
        ][0]
        content_summary = email_template_call[1]["content_summary"]
        assert content_summary[0]["description"] == TestConstants.TEST_CONTENT_EXCERPT

    def test_content_without_excerpt_uses_scraped_content(
        self, session, app, notification_mocks
    ):
        """Test content processing when excerpt is not available but scraped content is."""
        TestHelpers.create_test_user(session, linkedin_authorized=True)
        TestHelpers.create_test_content(
            session, excerpt=None, scraped_content=TestConstants.TEST_SCRAPED_CONTENT
        )

        app.config.update(TestHelpers.create_mock_app_config())

        with app.app_context():
            with patch("tasks.notifications.redis_client", notification_mocks["redis"]):
                with patch(
                    "tasks.notifications.render_template",
                    notification_mocks["render_template"],
                ):
                    with patch("tasks.notifications.mail", notification_mocks["mail"]):
                        with patch(
                            "tasks.notifications.WebClient",
                            notification_mocks["webclient"],
                        ):
                            result = initiate_posts.apply()

        assert result.successful()

        # Verify that render_template was called with truncated scraped content
        render_calls = notification_mocks["render_template"].call_args_list
        email_template_call = [
            template_call
            for template_call in render_calls
            if "email/" in template_call[0][0]
        ][0]
        content_summary = email_template_call[1]["content_summary"]
        assert len(content_summary[0]["description"]) <= 203  # 200 chars + "..."

    def test_content_with_no_description_content(
        self, session, app, notification_mocks
    ):
        """Test content processing when neither excerpt nor scraped_content is available."""
        TestHelpers.create_test_user(session, linkedin_authorized=True)
        TestHelpers.create_test_content(session, excerpt=None, scraped_content=None)

        app.config.update(TestHelpers.create_mock_app_config())

        with app.app_context():
            with patch("tasks.notifications.redis_client", notification_mocks["redis"]):
                with patch(
                    "tasks.notifications.render_template",
                    notification_mocks["render_template"],
                ):
                    with patch("tasks.notifications.mail", notification_mocks["mail"]):
                        with patch(
                            "tasks.notifications.WebClient",
                            notification_mocks["webclient"],
                        ):
                            result = initiate_posts.apply()

        assert result.successful()

        # Verify that render_template was called with empty description
        render_calls = notification_mocks["render_template"].call_args_list
        email_template_call = [
            template_call
            for template_call in render_calls
            if "email/" in template_call[0][0]
        ][0]
        content_summary = email_template_call[1]["content_summary"]
        assert content_summary[0]["description"] == ""

    def test_promote_url_generation(self, session, app, notification_mocks):
        """Test that promote URLs are generated correctly."""
        TestHelpers.create_test_user(session, linkedin_authorized=True)
        content = TestHelpers.create_test_content(session)

        app.config.update(TestHelpers.create_mock_app_config())

        with app.app_context():
            with patch("tasks.notifications.redis_client", notification_mocks["redis"]):
                with patch(
                    "tasks.notifications.render_template",
                    notification_mocks["render_template"],
                ):
                    with patch("tasks.notifications.mail", notification_mocks["mail"]):
                        with patch(
                            "tasks.notifications.WebClient",
                            notification_mocks["webclient"],
                        ):
                            result = initiate_posts.apply()

        assert result.successful()

        # Verify promote URL in content_summary
        render_calls = notification_mocks["render_template"].call_args_list
        email_template_call = [
            template_call
            for template_call in render_calls
            if "email/" in template_call[0][0]
        ][0]
        content_summary = email_template_call[1]["content_summary"]
        expected_promote_url = f"{TestConstants.TEST_BASE_URL}/?promote={content.id}"
        assert content_summary[0]["promote_url"] == expected_promote_url

    def test_one_off_notification_content_processing(
        self, session, app, notification_mocks
    ):
        """Test content processing in one-off notifications."""
        # Test with content that has no excerpt or scraped content
        content = TestHelpers.create_test_content(
            session, excerpt=None, scraped_content=None
        )
        app.config.update(TestHelpers.create_mock_app_config())

        with app.app_context():
            with patch(
                "tasks.notifications.WebClient", notification_mocks["webclient"]
            ):
                result = send_one_off_content_notification.apply(args=[content.id])

        assert result.successful()

        # Verify the fallback text is used
        call_kwargs = notification_mocks["slack_client"].chat_postMessage.call_args[1]
        assert "No excerpt available." in call_kwargs["text"]


# --- Performance Tests ---
@pytest.mark.slow
@pytest.mark.integration
class TestNotificationTasksPerformance:
    """Performance and scalability tests."""

    def test_bulk_content_processing(self, session, app, notification_mocks):
        """Test processing multiple content items efficiently."""
        # Create multiple users and content items
        for _ in range(5):
            TestHelpers.create_test_user(session, linkedin_authorized=True)
        for _ in range(10):
            TestHelpers.create_test_content(session)

        app.config.update(TestHelpers.create_mock_app_config())

        with app.app_context():
            with patch("tasks.notifications.redis_client", notification_mocks["redis"]):
                with patch(
                    "tasks.notifications.render_template",
                    notification_mocks["render_template"],
                ):
                    with patch("tasks.notifications.mail", notification_mocks["mail"]):
                        with patch(
                            "tasks.notifications.WebClient",
                            notification_mocks["webclient"],
                        ):
                            result = initiate_posts.apply()

        assert result.successful()
        assert "Emails sent: 5" in result.result
        assert "Slack messages: 1" in result.result

    def test_slack_message_chunking(self, session, app, notification_mocks):
        """Test that large content sets are properly chunked for Slack."""
        # Create content that would exceed Slack block limits
        TestHelpers.create_test_user(session, linkedin_authorized=True)
        for _ in range(TestConstants.MAX_ITEMS_PER_MESSAGE + 5):  # More than limit
            TestHelpers.create_test_content(session)

        config = TestHelpers.create_mock_app_config(EMAIL_ENABLED=False)
        app.config.update(config)

        with app.app_context():
            with patch("tasks.notifications.redis_client", notification_mocks["redis"]):
                with patch(
                    "tasks.notifications.render_template",
                    notification_mocks["render_template"],
                ):
                    with patch("tasks.notifications.mail", notification_mocks["mail"]):
                        with patch(
                            "tasks.notifications.WebClient",
                            notification_mocks["webclient"],
                        ):
                            result = initiate_posts.apply()

        assert result.successful()
        # Should send multiple Slack messages due to chunking
        assert notification_mocks["slack_client"].chat_postMessage.call_count >= 2
        assert "sent in 2 part(s)" in result.result

    def test_empty_chunk_handling(self, session, app, notification_mocks, caplog):
        """Test handling of empty chunks in Slack message processing."""
        TestHelpers.create_test_user(session, linkedin_authorized=True)
        # Create exactly the limit number of items to test boundary conditions
        for _ in range(TestConstants.MAX_ITEMS_PER_MESSAGE):
            TestHelpers.create_test_content(session)

        config = TestHelpers.create_mock_app_config(EMAIL_ENABLED=False)
        app.config.update(config)

        with app.app_context():
            with patch("tasks.notifications.redis_client", notification_mocks["redis"]):
                with patch(
                    "tasks.notifications.render_template",
                    notification_mocks["render_template"],
                ):
                    with patch("tasks.notifications.mail", notification_mocks["mail"]):
                        with patch(
                            "tasks.notifications.WebClient",
                            notification_mocks["webclient"],
                        ):
                            result = initiate_posts.apply()

        assert result.successful()
        # Should send exactly one message with all items
        assert notification_mocks["slack_client"].chat_postMessage.call_count == 1


# --- Template Integration Tests ---
@pytest.mark.integration
class TestNotificationTemplateIntegration:
    """Test integration with email and Slack templates."""

    def test_email_template_rendering(self, session, app, notification_mocks):
        """Test that email templates are rendered with correct context."""
        user = TestHelpers.create_test_user(session, linkedin_authorized=True)
        TestHelpers.create_test_content(session)

        app.config.update(TestHelpers.create_mock_app_config())

        with app.app_context():
            with patch("tasks.notifications.redis_client", notification_mocks["redis"]):
                with patch(
                    "tasks.notifications.render_template",
                    notification_mocks["render_template"],
                ):
                    with patch("tasks.notifications.mail", notification_mocks["mail"]):
                        with patch(
                            "tasks.notifications.WebClient",
                            notification_mocks["webclient"],
                        ):
                            result = initiate_posts.apply()

        assert result.successful()

        # Verify email template was called with correct context
        email_template_calls = [
            template_call
            for template_call in notification_mocks["render_template"].call_args_list
            if template_call[0][0] == "email/new_content_notification.html"
        ]
        assert (
            len(email_template_calls) == 1
        ), "Email template should be rendered once per user"

        template_context = email_template_calls[0][1]
        assert template_context["user"] == user
        assert "content_summary" in template_context
        assert "now" in template_context
        assert template_context["company_name"] == TestConstants.TEST_COMPANY_NAME

    def test_slack_template_rendering(self, session, app, notification_mocks):
        """Test that Slack templates are rendered correctly."""
        TestHelpers.create_test_user(session, linkedin_authorized=True)
        TestHelpers.create_test_content(session)

        config = TestHelpers.create_mock_app_config(EMAIL_ENABLED=False)
        app.config.update(config)

        with app.app_context():
            with patch("tasks.notifications.redis_client", notification_mocks["redis"]):
                with patch(
                    "tasks.notifications.render_template",
                    notification_mocks["render_template"],
                ):
                    with patch("tasks.notifications.mail", notification_mocks["mail"]):
                        with patch(
                            "tasks.notifications.WebClient",
                            notification_mocks["webclient"],
                        ):
                            result = initiate_posts.apply()

        assert result.successful()

        # Verify Slack templates were called
        slack_header_calls = [
            template_call
            for template_call in notification_mocks["render_template"].call_args_list
            if template_call[0][0] == "slack/notification_header.txt"
        ]
        slack_item_calls = [
            template_call
            for template_call in notification_mocks["render_template"].call_args_list
            if template_call[0][0] == "slack/notification_content_item.txt"
        ]

        assert (
            len(slack_header_calls) == 1
        ), "Slack header template should be rendered once per chunk"
        assert (
            len(slack_item_calls) == 1
        ), "Slack item template should be rendered once per content item"

    def test_template_context_completeness(self, session, app, notification_mocks):
        """Test that all required template context variables are provided."""
        TestHelpers.create_test_user(session, linkedin_authorized=True)
        TestHelpers.create_test_content(session)

        app.config.update(TestHelpers.create_mock_app_config())

        with app.app_context():
            with patch("tasks.notifications.redis_client", notification_mocks["redis"]):
                with patch(
                    "tasks.notifications.render_template",
                    notification_mocks["render_template"],
                ):
                    with patch("tasks.notifications.mail", notification_mocks["mail"]):
                        with patch(
                            "tasks.notifications.WebClient",
                            notification_mocks["webclient"],
                        ):
                            result = initiate_posts.apply()

        assert result.successful()

        # Check email template context
        email_calls = [
            template_call
            for template_call in notification_mocks["render_template"].call_args_list
            if "email/" in template_call[0][0]
        ]
        if email_calls:
            email_context = email_calls[0][1]
            required_keys = ["user", "content_summary", "now", "company_name"]
            for key in required_keys:
                assert (
                    key in email_context
                ), f"Email template context missing required key: {key}"

        # Check Slack template contexts
        slack_header_calls = [
            template_call
            for template_call in notification_mocks["render_template"].call_args_list
            if template_call[0][0] == "slack/notification_header.txt"
        ]
        if slack_header_calls:
            header_context = slack_header_calls[0][1]
            required_keys = [
                "num_items",
                "company_name",
                "current_chunk",
                "total_chunks",
            ]
            for key in required_keys:
                assert (
                    key in header_context
                ), f"Slack header template context missing required key: {key}"
