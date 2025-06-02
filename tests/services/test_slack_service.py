import pytest
import uuid
from unittest.mock import patch, MagicMock
from slack_sdk.errors import SlackApiError

from services.slack_service import invite_user_to_channel, send_slack_dm

# Generate unique identifier for this test run to avoid conflicts in parallel execution
TEST_RUN_ID = str(uuid.uuid4())[:8]


# --- Test Data and Constants ---
class TestConstants:
    """Test constants for consistent data across tests."""

    # Core test identifiers
    TEST_SLACK_USER_ID = f"U{TEST_RUN_ID[:7].upper()}"
    TEST_CHANNEL_ID = f"C{TEST_RUN_ID[:7].upper()}"
    TEST_USER_EMAIL = f"user-{TEST_RUN_ID}@example.com"
    TEST_MESSAGE_TEXT = f"Test message for {TEST_RUN_ID}"
    TEST_SLACK_BOT_TOKEN = f"xoxb-test-token-{TEST_RUN_ID}"

    # Test Slack blocks for rich messaging
    TEST_BLOCKS = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"Test block content for {TEST_RUN_ID}"},
        }
    ]

    # Slack API error codes for testing
    SLACK_ERROR_CODES = {
        "already_in_channel": "already_in_channel",
        "user_not_found": "user_not_found",
        "users_not_found": "users_not_found",
        "channel_not_found": "channel_not_found",
        "not_in_channel": "not_in_channel",
        "ekm_access_denied": "ekm_access_denied",
        "missing_scope": "missing_scope",
        "restricted_action": "restricted_action",
        "rate_limited": "rate_limited",
    }


class TestMessages:
    """Expected log messages and error strings for validation."""

    # Configuration errors
    MISSING_SLACK_TOKEN = "SLACK_BOT_TOKEN is not configured"
    MISSING_CHANNEL_ID = "Slack channel ID is not provided"
    MISSING_SLACK_USER_ID = "Slack user ID is not provided"
    MISSING_SLACK_USER_ID_DM = "Slack user ID not provided. Cannot send DM"

    # Success messages
    SUCCESSFULLY_INVITED = "Successfully sent Slack invitation"
    DM_SENT_SUCCESSFULLY = "Successfully sent DM to Slack user ID"

    # Specific error conditions
    ALREADY_IN_CHANNEL = "is already in channel"
    USER_NOT_FOUND = "Slack user with ID"
    CHANNEL_NOT_FOUND = "Slack channel"
    BOT_NOT_IN_CHANNEL = "The bot is not in channel"
    MISSING_PERMISSIONS = "Slack API error"
    UNEXPECTED_ERROR = "An unexpected error occurred"


# --- Test Utilities ---
class TestHelpers:
    """Helper methods for testing Slack service functionality."""

    @staticmethod
    def create_mock_slack_api_error(
        error_code: str, additional_response_data: dict = None
    ) -> SlackApiError:
        """
        Create a mock SlackApiError with specified error code.

        Args:
            error_code: The Slack API error code to simulate
            additional_response_data: Optional additional response data

        Returns:
            SlackApiError: Mock error object for testing
        """
        response_data = {"error": error_code}
        if additional_response_data:
            response_data.update(additional_response_data)

        mock_response = MagicMock()
        mock_response.get.side_effect = lambda key, default=None: response_data.get(
            key, default
        )

        return SlackApiError("Test error", mock_response)

    @staticmethod
    def assert_log_contains(caplog, level: str, message_fragment: str) -> None:
        """
        Assert that logs contain a specific message at the specified level.

        Args:
            caplog: pytest caplog fixture
            level: Log level to check (INFO, ERROR, etc.)
            message_fragment: Text fragment that should appear in log
        """
        log_messages = [
            record.message
            for record in caplog.records
            if record.levelname == level.upper()
        ]
        assert any(
            message_fragment in msg for msg in log_messages
        ), f"Expected log message containing '{message_fragment}' at {level} level. Found: {log_messages}"

    @staticmethod
    def assert_no_logs_contain(caplog, message_fragment: str) -> None:
        """
        Assert that no logs contain a specific message fragment.

        Args:
            caplog: pytest caplog fixture
            message_fragment: Text fragment that should NOT appear in any log
        """
        all_messages = [record.message for record in caplog.records]
        assert not any(
            message_fragment in msg for msg in all_messages
        ), f"Expected no log messages containing '{message_fragment}'. Found: {all_messages}"

    @staticmethod
    def setup_mock_slack_client(
        mock_webclient_class, success: bool = True, error_code: str = None
    ) -> MagicMock:
        """
        Setup a mock Slack WebClient with standardized behavior.

        Args:
            mock_webclient_class: Mock WebClient class to configure
            success: Whether the API calls should succeed
            error_code: Error code to simulate if success=False

        Returns:
            MagicMock: Configured mock client
        """
        mock_client = MagicMock()
        mock_webclient_class.return_value = mock_client

        if not success and error_code:
            error = TestHelpers.create_mock_slack_api_error(error_code)
            mock_client.conversations_invite.side_effect = error
            mock_client.chat_postMessage.side_effect = error

        return mock_client


# --- Unit Tests ---
@pytest.mark.unit
class TestSlackServiceHelpers:
    """Unit tests for helper functionality that doesn't require Flask app context."""

    def test_slack_api_error_creation(self):
        """Test creation of mock Slack API errors."""
        error_code = "test_error"
        additional_data = {"needed": "scope", "provided": "invalid"}

        error = TestHelpers.create_mock_slack_api_error(error_code, additional_data)

        assert error.response.get("error") == error_code
        assert error.response.get("needed") == "scope"
        assert error.response.get("provided") == "invalid"

    def test_log_assertion_helpers(self, caplog):
        """Test log assertion helper methods."""
        import logging

        logger = logging.getLogger("test")

        # Test positive assertion
        logger.info("Test message with keyword")
        TestHelpers.assert_log_contains(caplog, "INFO", "keyword")

        # Test negative assertion
        TestHelpers.assert_no_logs_contain(caplog, "nonexistent")

    def test_test_constants_uniqueness(self):
        """Test that test constants are properly unique for parallel execution."""
        # Verify that test run ID is generated and consistent
        assert TEST_RUN_ID is not None
        assert len(TEST_RUN_ID) == 8

        # Verify constants use the test run ID for uniqueness
        assert TEST_RUN_ID in TestConstants.TEST_USER_EMAIL
        assert TEST_RUN_ID in TestConstants.TEST_MESSAGE_TEXT
        assert TEST_RUN_ID[:7].upper() in TestConstants.TEST_SLACK_USER_ID
        assert TEST_RUN_ID[:7].upper() in TestConstants.TEST_CHANNEL_ID

    def test_mock_client_setup_helper(self):
        """Test the mock client setup helper functionality."""
        with patch("services.slack_service.WebClient") as mock_webclient_class:
            # Test successful setup
            mock_client = TestHelpers.setup_mock_slack_client(
                mock_webclient_class, success=True
            )
            assert mock_client is not None
            assert mock_webclient_class.return_value == mock_client

            # Test error setup
            error_client = TestHelpers.setup_mock_slack_client(
                mock_webclient_class, success=False, error_code="test_error"
            )
            assert error_client is not None


# --- Core Integration Tests ---
@pytest.mark.integration
class TestSlackServiceCore:
    """Core integration tests for Slack service functionality."""

    @pytest.mark.parametrize("include_email", [True, False])
    def test_invite_user_success(self, app, caplog, include_email):
        """Test successful user invitation to Slack channel with and without email."""
        with app.app_context():
            app.config["SLACK_BOT_TOKEN"] = TestConstants.TEST_SLACK_BOT_TOKEN

            with patch("services.slack_service.WebClient") as mock_webclient_class:
                TestHelpers.setup_mock_slack_client(mock_webclient_class, success=True)

                email = TestConstants.TEST_USER_EMAIL if include_email else None

                result = invite_user_to_channel(
                    TestConstants.TEST_SLACK_USER_ID,
                    TestConstants.TEST_CHANNEL_ID,
                    email,
                )

                assert result is True
                mock_webclient_class.assert_called_once_with(
                    token=TestConstants.TEST_SLACK_BOT_TOKEN
                )
                TestHelpers.assert_log_contains(
                    caplog, "INFO", TestMessages.SUCCESSFULLY_INVITED
                )

    def test_invite_user_already_in_channel(self, app, caplog):
        """Test invitation when user is already in the channel (should succeed)."""
        with app.app_context():
            app.config["SLACK_BOT_TOKEN"] = TestConstants.TEST_SLACK_BOT_TOKEN

            with patch("services.slack_service.WebClient") as mock_webclient_class:
                TestHelpers.setup_mock_slack_client(
                    mock_webclient_class,
                    success=False,
                    error_code=TestConstants.SLACK_ERROR_CODES["already_in_channel"],
                )

                result = invite_user_to_channel(
                    TestConstants.TEST_SLACK_USER_ID,
                    TestConstants.TEST_CHANNEL_ID,
                    TestConstants.TEST_USER_EMAIL,
                )

                assert result is True
                TestHelpers.assert_log_contains(
                    caplog, "INFO", TestMessages.ALREADY_IN_CHANNEL
                )

    @pytest.mark.parametrize("text_only", [True, False])
    def test_send_dm_success(self, app, caplog, text_only):
        """Test successful direct message sending with text only and with blocks."""
        with app.app_context():
            app.config["SLACK_BOT_TOKEN"] = TestConstants.TEST_SLACK_BOT_TOKEN

            with patch("services.slack_service.WebClient") as mock_webclient_class:
                mock_client = TestHelpers.setup_mock_slack_client(
                    mock_webclient_class, success=True
                )

                blocks = None if text_only else TestConstants.TEST_BLOCKS

                result = send_slack_dm(
                    TestConstants.TEST_SLACK_USER_ID,
                    TestConstants.TEST_MESSAGE_TEXT,
                    blocks,
                )

                assert result is True
                mock_client.chat_postMessage.assert_called_once_with(
                    channel=TestConstants.TEST_SLACK_USER_ID,
                    text=TestConstants.TEST_MESSAGE_TEXT,
                    blocks=blocks,
                )
                TestHelpers.assert_log_contains(
                    caplog, "INFO", TestMessages.DM_SENT_SUCCESSFULLY
                )


# --- Configuration and Validation Tests ---
@pytest.mark.integration
class TestSlackServiceValidation:
    """Tests for input validation and configuration handling."""

    @pytest.mark.parametrize("missing_config", ["token", "channel_id", "slack_user_id"])
    def test_invite_user_missing_config(self, app, caplog, missing_config):
        """Test invitation failure scenarios for missing configuration."""
        with app.app_context():
            # Setup based on what we're testing
            if missing_config == "token":
                # Explicitly set to None to simulate missing token
                app.config["SLACK_BOT_TOKEN"] = None
            else:
                app.config["SLACK_BOT_TOKEN"] = TestConstants.TEST_SLACK_BOT_TOKEN

            slack_user_id = (
                ""
                if missing_config == "slack_user_id"
                else TestConstants.TEST_SLACK_USER_ID
            )
            channel_id = (
                "" if missing_config == "channel_id" else TestConstants.TEST_CHANNEL_ID
            )

            result = invite_user_to_channel(
                slack_user_id, channel_id, TestConstants.TEST_USER_EMAIL
            )

            assert result is False

            # Check appropriate error message
            if missing_config == "token":
                TestHelpers.assert_log_contains(
                    caplog, "ERROR", TestMessages.MISSING_SLACK_TOKEN
                )
            elif missing_config == "channel_id":
                TestHelpers.assert_log_contains(
                    caplog, "ERROR", TestMessages.MISSING_CHANNEL_ID
                )
            elif missing_config == "slack_user_id":
                TestHelpers.assert_log_contains(
                    caplog, "ERROR", TestMessages.MISSING_SLACK_USER_ID
                )

    @pytest.mark.parametrize("missing_config", ["token", "slack_user_id"])
    def test_send_dm_missing_config(self, app, caplog, missing_config):
        """Test DM failure scenarios for missing configuration."""
        with app.app_context():
            if missing_config == "token":
                # Explicitly set to None to simulate missing token
                app.config["SLACK_BOT_TOKEN"] = None
            else:
                app.config["SLACK_BOT_TOKEN"] = TestConstants.TEST_SLACK_BOT_TOKEN

            slack_user_id = (
                ""
                if missing_config == "slack_user_id"
                else TestConstants.TEST_SLACK_USER_ID
            )

            result = send_slack_dm(slack_user_id, TestConstants.TEST_MESSAGE_TEXT)

            assert result is False

            if missing_config == "token":
                TestHelpers.assert_log_contains(
                    caplog, "ERROR", TestMessages.MISSING_SLACK_TOKEN
                )
            elif missing_config == "slack_user_id":
                TestHelpers.assert_log_contains(
                    caplog, "ERROR", TestMessages.MISSING_SLACK_USER_ID_DM
                )


# --- Error Handling Tests ---
@pytest.mark.integration
class TestSlackServiceErrorHandling:
    """Tests for various error conditions and API failures."""

    @pytest.mark.parametrize(
        "error_code,expected_result",
        [
            ("user_not_found", False),
            ("users_not_found", False),
            ("channel_not_found", False),
            ("not_in_channel", False),
            ("ekm_access_denied", False),
            ("missing_scope", False),
            ("restricted_action", False),
        ],
    )
    def test_invite_user_api_errors(self, app, error_code, expected_result, caplog):
        """Test various Slack API errors during invitation."""
        with app.app_context():
            app.config["SLACK_BOT_TOKEN"] = TestConstants.TEST_SLACK_BOT_TOKEN

            with patch("services.slack_service.WebClient") as mock_webclient_class:
                TestHelpers.setup_mock_slack_client(
                    mock_webclient_class, success=False, error_code=error_code
                )

                result = invite_user_to_channel(
                    TestConstants.TEST_SLACK_USER_ID,
                    TestConstants.TEST_CHANNEL_ID,
                    TestConstants.TEST_USER_EMAIL,
                )

                assert result is expected_result
                # Verify error is logged
                log_levels = ["WARNING", "ERROR"]
                log_found = any(
                    any(
                        "Error" in record.message or "Slack API error" in record.message
                        for record in caplog.records
                        if record.levelname == level
                    )
                    for level in log_levels
                )
                assert log_found, f"Expected error log for {error_code}"

    def test_invite_user_unknown_error(self, app, caplog):
        """Test handling of unknown Slack API errors."""
        with app.app_context():
            app.config["SLACK_BOT_TOKEN"] = TestConstants.TEST_SLACK_BOT_TOKEN

            with patch("services.slack_service.WebClient") as mock_webclient_class:
                TestHelpers.setup_mock_slack_client(
                    mock_webclient_class, success=False, error_code="unknown_error"
                )

                result = invite_user_to_channel(
                    TestConstants.TEST_SLACK_USER_ID, TestConstants.TEST_CHANNEL_ID
                )

                assert result is False
                TestHelpers.assert_log_contains(caplog, "ERROR", "Error inviting")

    @pytest.mark.parametrize(
        "function_name,args",
        [
            (
                "invite_user_to_channel",
                [TestConstants.TEST_SLACK_USER_ID, TestConstants.TEST_CHANNEL_ID],
            ),
            (
                "send_slack_dm",
                [TestConstants.TEST_SLACK_USER_ID, TestConstants.TEST_MESSAGE_TEXT],
            ),
        ],
    )
    def test_unexpected_exceptions(self, app, caplog, function_name, args):
        """Test handling of unexpected exceptions in Slack operations."""
        with app.app_context():
            app.config["SLACK_BOT_TOKEN"] = TestConstants.TEST_SLACK_BOT_TOKEN

            with patch("services.slack_service.WebClient") as mock_webclient_class:
                mock_client = MagicMock()
                mock_webclient_class.return_value = mock_client
                mock_client.conversations_invite.side_effect = Exception(
                    "Network error"
                )
                mock_client.chat_postMessage.side_effect = Exception("Network error")

                if function_name == "invite_user_to_channel":
                    result = invite_user_to_channel(*args)
                else:
                    result = send_slack_dm(*args)

                assert result is False
                TestHelpers.assert_log_contains(
                    caplog, "ERROR", TestMessages.UNEXPECTED_ERROR
                )


# --- Edge Cases and Boundary Tests ---
@pytest.mark.integration
class TestSlackServiceEdgeCases:
    """Test edge cases and boundary conditions for Slack service."""

    @pytest.mark.parametrize(
        "invalid_input,field",
        [
            (None, "slack_user_id"),
            ("", "slack_user_id"),
            ("   ", "slack_user_id"),
            ("invalid-format", "slack_user_id"),
            ("U" + "A" * 50, "slack_user_id"),  # Very long user ID
            (None, "channel_id"),
            ("", "channel_id"),
            ("   ", "channel_id"),
            ("invalid-format", "channel_id"),
            ("C" + "B" * 50, "channel_id"),  # Very long channel ID
        ],
    )
    def test_invite_user_invalid_inputs(self, app, invalid_input, field):
        """Test invitation with various invalid input formats."""
        with app.app_context():
            app.config["SLACK_BOT_TOKEN"] = TestConstants.TEST_SLACK_BOT_TOKEN

            if field == "slack_user_id":
                slack_user_id, channel_id = invalid_input, TestConstants.TEST_CHANNEL_ID
            else:
                slack_user_id, channel_id = (
                    TestConstants.TEST_SLACK_USER_ID,
                    invalid_input,
                )

            result = invite_user_to_channel(slack_user_id, channel_id)
            assert result is False

    @pytest.mark.parametrize(
        "message_text",
        [
            "",  # Empty message
            "A" * 4000,  # Very long message
            "Test with émojis 🚀💡🎉",  # Unicode content
            "Message with\nmultiple\nlines",  # Multiline content
            "Special chars: !@#$%^&*()[]{}|;:,.<>?",  # Special characters
        ],
    )
    def test_send_dm_message_variations(self, app, message_text):
        """Test DM sending with various message formats and content."""
        with app.app_context():
            app.config["SLACK_BOT_TOKEN"] = TestConstants.TEST_SLACK_BOT_TOKEN

            with patch("services.slack_service.WebClient") as mock_webclient_class:
                TestHelpers.setup_mock_slack_client(mock_webclient_class, success=True)

                result = send_slack_dm(TestConstants.TEST_SLACK_USER_ID, message_text)

                # Should succeed for all valid message formats
                assert result is True

    def test_complex_blocks_formatting(self, app):
        """Test DM sending with complex Slack block layouts."""
        with app.app_context():
            app.config["SLACK_BOT_TOKEN"] = TestConstants.TEST_SLACK_BOT_TOKEN

            complex_blocks = [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "*Complex Block Test*"},
                },
                {"type": "divider"},
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": f"Test ID: {TEST_RUN_ID}"}],
                },
            ]

            with patch("services.slack_service.WebClient") as mock_webclient_class:
                mock_client = TestHelpers.setup_mock_slack_client(
                    mock_webclient_class, success=True
                )

                result = send_slack_dm(
                    TestConstants.TEST_SLACK_USER_ID,
                    TestConstants.TEST_MESSAGE_TEXT,
                    complex_blocks,
                )

                assert result is True
                mock_client.chat_postMessage.assert_called_once_with(
                    channel=TestConstants.TEST_SLACK_USER_ID,
                    text=TestConstants.TEST_MESSAGE_TEXT,
                    blocks=complex_blocks,
                )


# --- Performance and Reliability Tests ---
@pytest.mark.slow
@pytest.mark.integration
class TestSlackServicePerformance:
    """Performance and reliability tests for Slack service under load."""

    def test_concurrent_invitations(self, app):
        """Test handling of multiple concurrent invitation attempts."""
        with app.app_context():
            app.config["SLACK_BOT_TOKEN"] = TestConstants.TEST_SLACK_BOT_TOKEN

            from concurrent.futures import ThreadPoolExecutor, as_completed

            # Use a global mock to ensure all threads see the same behavior
            with patch("services.slack_service.WebClient") as mock_webclient_class:
                mock_client = MagicMock()
                mock_webclient_class.return_value = mock_client

                def invite_user():
                    # Each thread needs its own app context with same config
                    with app.app_context():
                        app.config["SLACK_BOT_TOKEN"] = (
                            TestConstants.TEST_SLACK_BOT_TOKEN
                        )
                        unique_id = str(uuid.uuid4())[:8]
                        return invite_user_to_channel(
                            f"U{unique_id}",
                            TestConstants.TEST_CHANNEL_ID,
                            f"user-{unique_id}@example.com",
                        )

                # Execute multiple invitations concurrently
                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = [executor.submit(invite_user) for _ in range(10)]
                    results = [future.result() for future in as_completed(futures)]

                # All should succeed
                assert all(results), f"Some invitations failed: {results}"
                assert len(results) == 10

    def test_retry_behavior_simulation(self, app, caplog):
        """Test simulated retry behavior for failed requests."""
        with app.app_context():
            app.config["SLACK_BOT_TOKEN"] = TestConstants.TEST_SLACK_BOT_TOKEN

            with patch("services.slack_service.WebClient") as mock_webclient_class:
                mock_client = MagicMock()
                mock_webclient_class.return_value = mock_client

                # First call fails with rate limit, second succeeds
                mock_client.conversations_invite.side_effect = [
                    TestHelpers.create_mock_slack_api_error(
                        TestConstants.SLACK_ERROR_CODES["rate_limited"]
                    ),
                    None,  # Success on "retry"
                ]

                # First attempt should fail
                result1 = invite_user_to_channel(
                    TestConstants.TEST_SLACK_USER_ID, TestConstants.TEST_CHANNEL_ID
                )
                assert result1 is False

                # Second attempt should succeed (simulating retry)
                result2 = invite_user_to_channel(
                    TestConstants.TEST_SLACK_USER_ID, TestConstants.TEST_CHANNEL_ID
                )
                assert result2 is True

    @pytest.mark.parametrize("operation_count", [50, 100])
    def test_high_volume_operations(self, app, operation_count):
        """Test service reliability under high operation volume."""
        with app.app_context():
            app.config["SLACK_BOT_TOKEN"] = TestConstants.TEST_SLACK_BOT_TOKEN

            with patch("services.slack_service.WebClient") as mock_webclient_class:
                TestHelpers.setup_mock_slack_client(mock_webclient_class, success=True)

                success_count = 0
                for i in range(operation_count):
                    result = invite_user_to_channel(
                        f"U{i:07d}", TestConstants.TEST_CHANNEL_ID
                    )
                    if result:
                        success_count += 1

                # Should handle all operations successfully
                success_rate = success_count / operation_count
                assert (
                    success_rate >= 0.95
                ), f"Success rate {success_rate} below threshold"
