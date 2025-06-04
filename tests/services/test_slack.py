import pytest
from unittest.mock import patch, MagicMock
from flask import Flask

# Import the service to be tested
from services.slack import SlackService, slack_service  # Assuming a global instance


@pytest.fixture
def app_context():
    """Fixture to provide a Flask app context for tests that need it (e.g., logging)."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    # Mock essential config values if the service tries to access them during init or methods
    app.config["SLACK_BOT_TOKEN"] = "test_token"
    app.config["SLACK_SIGNING_SECRET"] = "test_secret"
    with app.app_context():
        yield app


# --- Unit Tests for SlackService ---
@pytest.mark.unit
@pytest.mark.slack
class TestSlackServiceUnit:

    def test_service_initialization(self, app_context):
        """Test that the SlackService can be initialized."""
        # The global slack_service is already initialized when imported.
        # This test mainly checks if it exists and is an instance of SlackService.
        assert slack_service is not None
        assert isinstance(slack_service, SlackService)
        # If a client is initialized in __init__ (currently commented out):
        # assert slack_service.client is not None
        # assert slack_service.slack_bot_token == 'test_token'

    def test_handle_event_generic(self, app_context, caplog):
        """Test the generic event handling logs correctly."""
        sample_payload = {
            "type": "event_callback",
            "event": {
                "type": "app_mention",
                "user": "U123",
                "text": "Hi there",
                "channel": "C456",
            },
        }
        result = slack_service.handle_event(sample_payload)
        assert result == {"status": "event received by service"}
        assert (
            "SlackService received event. Outer type: 'event_callback', Inner type: 'app_mention'"
            in caplog.text
        )

    def test_handle_app_mention(self, app_context, caplog):
        """Test the app_mention event handler logs correctly."""
        # This currently just logs, no complex logic or external calls yet.
        app_mention_payload = {
            "type": "app_mention",
            "user": "UUSER123",
            "text": "Hello @BotName, how are you?",
            "channel": "CCHANNEL789",
            "ts": "1600000000.000000",
        }
        # Note: handle_event would normally dispatch this.
        # We are testing the specific handler directly for unit testing purposes.
        slack_service.handle_app_mention(app_mention_payload)
        assert "App mention from user UUSER123 in channel CCHANNEL789" in caplog.text

    def test_handle_message_normal(self, app_context, caplog):
        """Test the message event handler logs correctly for a normal user message."""
        message_payload = {
            "type": "message",
            "user": "UUSER456",
            "text": "Just a regular message.",
            "channel": "CCHANNELABC",
            "ts": "1600000001.000000",
        }
        slack_service.handle_message(message_payload)
        assert (
            "Message from user UUSER456 in channel CCHANNELABC: Just a regular message."
            in caplog.text
        )

    def test_handle_message_bot_message_subtype(self, app_context, caplog):
        """Test that bot messages (subtype) are ignored by handle_message."""
        bot_message_payload = {
            "type": "message",
            "subtype": "bot_message",
            "bot_id": "BBOTID789",
            "text": "I am a bot.",
            "channel": "CCHANNELDEF",
            "ts": "1600000002.000000",
        }
        slack_service.handle_message(bot_message_payload)
        # Ensure no logging for processing bot messages beyond initial checks
        assert (
            "Message from user" not in caplog.text
        )  # Should not log processing for bot messages

    def test_handle_message_with_bot_id(self, app_context, caplog):
        """Test that messages with a bot_id are ignored by handle_message."""
        bot_id_message_payload = {
            "type": "message",
            "bot_id": "BBOTIDXYZ",  # Presence of bot_id field
            "user": "UUSER789",  # Can still have a user, but bot_id indicates bot origin
            "text": "Automated message.",
            "channel": "CCHANNELGHI",
            "ts": "1600000003.000000",
        }
        slack_service.handle_message(bot_id_message_payload)
        assert (
            "Message from user" not in caplog.text
        )  # Should not log processing for bot messages

    # Example for when post_message is implemented (currently commented out in service)
    # @patch('services.slack.WebClient') # Mock the WebClient
    # def test_post_message_success(self, MockWebClient, app_context, caplog):
    #     """Test successfully posting a message to Slack."""
    #     mock_client_instance = MockWebClient.return_value
    #     mock_client_instance.chat_postMessage.return_value = {
    #         'ok': True,
    #         'ts': '1234567890.098765',
    #         'channel': 'C123CHAN',
    #         'message': {'text': 'Test message'}
    #     }

    #     # Re-initialize service or mock its client if it's set in __init__
    #     # For the global instance, we might need to temporarily replace its client
    #     # current_app.config['SLACK_BOT_TOKEN'] = 'a_valid_token' # Ensure token is set
    #     # test_service = SlackService() # Or directly patch slack_service.client

    #     # If using the global slack_service, and client is initialized in its __init__:
    #     original_client = slack_service.client
    #     slack_service.client = mock_client_instance # Temporarily replace with mock

    #     channel_id = "C123CHAN"
    #     text = "Test message"
    #     response = slack_service.post_message(channel_id, text)

    #     assert response is not None
    #     assert response['ok'] is True
    #     mock_client_instance.chat_postMessage.assert_called_once_with(channel=channel_id, text=text)
    #     assert f"Message posted to {channel_id}" in caplog.text

    #     slack_service.client = original_client # Restore original client

    # @patch('services.slack.WebClient')
    # def test_post_message_failure(self, MockWebClient, app_context, caplog):
    #     """Test handling of an error when posting a message to Slack."""
    #     mock_client_instance = MockWebClient.return_value
    #     mock_client_instance.chat_postMessage.side_effect = SlackApiError(
    #         message="API Error",
    #         response={'ok': False, 'error': 'test_error'}
    #     )

    #     original_client = slack_service.client
    #     slack_service.client = mock_client_instance

    #     channel_id = "CERRORCHAN"
    #     text = "This will fail"
    #     response = slack_service.post_message(channel_id, text)

    #     assert response is None
    #     mock_client_instance.chat_postMessage.assert_called_once_with(channel=channel_id, text=text)
    #     assert f"Error posting message to Slack channel {channel_id}: test_error" in caplog.text

    #     slack_service.client = original_client
