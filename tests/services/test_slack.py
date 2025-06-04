import pytest
from unittest.mock import patch, MagicMock
from flask import Flask, current_app
from slack_sdk.errors import SlackApiError

# Import the service to be tested
from services.slack import SlackService, slack_service  # Assuming a global instance

# Functions/classes to test from the actual service file
from services.slack_service import (
    _get_slack_client,
    _get_user_and_check_admin,
    handle_create_content_command,
    handle_create_content_view_submission,
    CREATE_CONTENT_MODAL_CALLBACK_ID,
)

# Potentially needed from other parts of your app for mocking
from services.content_service import DuplicateContentError  # For error handling tests


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


# Mock User class for _get_user_and_check_admin tests
class MockUser:
    def __init__(self, id, email, slack_id, is_admin):
        self.id = id
        self.email = email
        self.slack_id = slack_id
        self.is_admin = is_admin


# Mock Content object for testing return values from create_content_item
class MockContent:
    def __init__(self, id, url, title="Processing..."):
        self.id = id
        self.url = url
        self.title = title


# Mock Celery Task AsyncResult
class MockAsyncResult:
    def __init__(self, id):
        self.id = id


@pytest.mark.unit
@pytest.mark.slack
class TestSlackServiceHelpers:
    """Tests for helper functions in slack_service.py"""

    def test_get_slack_client_success(self, app_context):
        """Test _get_slack_client returns a WebClient with a token."""
        with patch("services.slack_service.WebClient") as MockWebClient:
            client = _get_slack_client()
            MockWebClient.assert_called_once_with(token="test_token")
            assert client is not None

    def test_get_slack_client_no_token(self, app_context):
        """Test _get_slack_client raises ValueError if token is missing."""
        current_app.config["SLACK_BOT_TOKEN"] = None
        with pytest.raises(ValueError, match="SLACK_BOT_TOKEN is not configured."):
            _get_slack_client()

    @patch("services.slack_service.User.query")
    def test_get_user_and_check_admin_is_admin(self, mock_user_query, app_context):
        """Test _get_user_and_check_admin returns user if admin."""
        admin_user = MockUser(
            id=1, email="admin@example.com", slack_id="UADMIN123", is_admin=True
        )
        mock_user_query.filter_by.return_value.first.return_value = admin_user

        user = _get_user_and_check_admin("UADMIN123")
        assert user == admin_user
        mock_user_query.filter_by.assert_called_once_with(slack_id="UADMIN123")

    @patch("services.slack_service.User.query")
    def test_get_user_and_check_admin_not_admin(self, mock_user_query, app_context):
        """Test _get_user_and_check_admin returns None if not admin."""
        non_admin_user = MockUser(
            id=2, email="user@example.com", slack_id="UUSER456", is_admin=False
        )
        mock_user_query.filter_by.return_value.first.return_value = non_admin_user

        user = _get_user_and_check_admin("UUSER456")
        assert user is None

    @patch("services.slack_service.User.query")
    def test_get_user_and_check_admin_no_user_found(self, mock_user_query, app_context):
        """Test _get_user_and_check_admin returns None if no user found."""
        mock_user_query.filter_by.return_value.first.return_value = None
        user = _get_user_and_check_admin("UUNKNOWN")
        assert user is None

    def test_get_user_and_check_admin_no_slack_id(self, app_context):
        """Test _get_user_and_check_admin returns None if no slack_id provided."""
        user = _get_user_and_check_admin(None)
        assert user is None


@pytest.mark.unit
@pytest.mark.slack
class TestHandleCreateContentCommand:
    """Tests for handle_create_content_command in slack_service.py"""

    @patch("services.slack_service._get_user_and_check_admin")
    @patch("services.slack_service._get_slack_client")
    def test_success_opens_modal(self, mock_get_client, mock_check_admin, app_context):
        mock_slack_web_client = MagicMock()
        mock_get_client.return_value = mock_slack_web_client
        admin_user = MockUser(
            id=1, email="admin@example.com", slack_id="UADMIN123", is_admin=True
        )
        mock_check_admin.return_value = admin_user

        payload = {
            "trigger_id": "test_trigger",
            "user_id": "UADMIN123",
            "channel_id": "C123",
        }
        handle_create_content_command(payload)

        mock_check_admin.assert_called_once_with("UADMIN123")
        mock_slack_web_client.views_open.assert_called_once()
        args, kwargs = mock_slack_web_client.views_open.call_args
        assert kwargs["trigger_id"] == "test_trigger"
        assert kwargs["view"]["type"] == "modal"
        assert kwargs["view"]["callback_id"] == CREATE_CONTENT_MODAL_CALLBACK_ID

    @patch("services.slack_service._get_user_and_check_admin")
    @patch("services.slack_service._get_slack_client")
    def test_non_admin_gets_ephemeral_message(
        self, mock_get_client, mock_check_admin, app_context
    ):
        mock_slack_web_client = MagicMock()
        mock_get_client.return_value = mock_slack_web_client
        mock_check_admin.return_value = None  # Non-admin

        payload = {
            "trigger_id": "test_trigger",
            "user_id": "UUSER456",
            "channel_id": "C123",
        }
        handle_create_content_command(payload)

        mock_check_admin.assert_called_once_with("UUSER456")
        mock_slack_web_client.chat_postEphemeral.assert_called_once_with(
            channel="C123",
            user="UUSER456",
            text="Sorry, you don't have permission to use this command.",
        )
        mock_slack_web_client.views_open.assert_not_called()

    @patch(
        "services.slack_service._get_slack_client",
        side_effect=ValueError("Config error"),
    )
    def test_slack_client_value_error(self, mock_get_client, app_context, caplog):
        payload = {
            "trigger_id": "test_trigger",
            "user_id": "UADMIN123",
            "channel_id": "C123",
        }
        handle_create_content_command(payload)
        assert (
            "Configuration error handling /create-content: Config error" in caplog.text
        )

    @patch("services.slack_service._get_user_and_check_admin")
    @patch("services.slack_service._get_slack_client")
    def test_slack_api_error_on_views_open(
        self, mock_get_client, mock_check_admin, app_context, caplog
    ):
        mock_slack_web_client = MagicMock()
        mock_slack_web_client.views_open.side_effect = SlackApiError(
            "API Error", {"ok": False, "error": "test_api_error"}
        )
        mock_get_client.return_value = mock_slack_web_client
        admin_user = MockUser(
            id=1, email="admin@example.com", slack_id="UADMIN123", is_admin=True
        )
        mock_check_admin.return_value = admin_user

        payload = {
            "trigger_id": "test_trigger",
            "user_id": "UADMIN123",
            "channel_id": "C123",
        }
        handle_create_content_command(payload)
        assert "Slack API error handling /create-content: test_api_error" in caplog.text


@pytest.mark.unit
@pytest.mark.slack
class TestHandleCreateContentViewSubmission:
    """Tests for handle_create_content_view_submission in slack_service.py"""

    @patch("services.slack_service.send_slack_dm")
    @patch("services.slack_service.create_content_item")
    @patch("services.slack_service._get_user_and_check_admin")
    @patch("services.slack_service._get_slack_client")
    def test_success_creates_content_sends_dm(
        self,
        mock_get_client,
        mock_check_admin,
        mock_create_item,
        mock_send_dm,
        app_context,
    ):
        mock_slack_web_client = MagicMock()
        mock_get_client.return_value = mock_slack_web_client
        admin_user = MockUser(
            id=1, email="admin@example.com", slack_id="UADMIN123", is_admin=True
        )
        mock_check_admin.return_value = admin_user

        mock_content_obj = MockContent(id=101, url="http://new.url")
        mock_task_obj = MockAsyncResult(id="task_123")
        mock_create_item.return_value = (mock_content_obj, mock_task_obj)

        payload = {
            "user": {"id": "UADMIN123"},
            "view": {
                "state": {
                    "values": {
                        "url_block": {"content_url": {"value": "http://new.url"}},
                        "context_block": {"content_context": {"value": "Test context"}},
                        "copy_block": {"content_copy": {"value": "Test copy"}},
                        "utm_campaign_block": {
                            "content_utm_campaign": {"value": "test_utm"}
                        },
                    }
                }
            },
        }
        response = handle_create_content_view_submission(payload)

        mock_check_admin.assert_called_once_with("UADMIN123")
        mock_create_item.assert_called_once_with(
            url="http://new.url",
            context="Test context",
            copy="Test copy",
            utm_campaign="test_utm",
            submitted_by_id=admin_user.id,
        )
        mock_send_dm.assert_called_once()
        dm_text_arg = mock_send_dm.call_args[0][1]  # second argument is message_text
        assert (
            "Content for URL <http://new.url|http://new.url> is being processed"
            in dm_text_arg
        )
        assert "Task ID: task_123" in dm_text_arg
        assert response is None  # Default response closes modal

    @patch("services.slack_service.send_slack_dm")
    @patch("services.slack_service.create_content_item")
    @patch("services.slack_service._get_user_and_check_admin")
    @patch("services.slack_service._get_slack_client")
    def test_missing_url_returns_validation_error(
        self,
        mock_get_client,
        mock_check_admin,
        mock_create_item,
        mock_send_dm,
        app_context,
    ):
        mock_slack_web_client = MagicMock()
        mock_get_client.return_value = mock_slack_web_client
        admin_user = MockUser(
            id=1, email="admin@example.com", slack_id="UADMIN123", is_admin=True
        )
        mock_check_admin.return_value = admin_user

        payload = {  # Missing URL
            "user": {"id": "UADMIN123"},
            "view": {"state": {"values": {}}},
        }
        response = handle_create_content_view_submission(payload)

        assert response == {
            "response_action": "errors",
            "errors": {
                "url_block": "URL is a required field. Please enter a valid URL."
            },
        }
        mock_create_item.assert_not_called()
        mock_send_dm.assert_not_called()

    @patch("services.slack_service.send_slack_dm")
    @patch(
        "services.slack_service.create_content_item",
        side_effect=DuplicateContentError("URL exists"),
    )
    @patch("services.slack_service._get_user_and_check_admin")
    @patch("services.slack_service._get_slack_client")
    def test_duplicate_content_error_sends_dm(
        self,
        mock_get_client,
        mock_check_admin,
        mock_create_item,
        mock_send_dm,
        app_context,
    ):
        mock_slack_web_client = MagicMock()
        mock_get_client.return_value = mock_slack_web_client
        admin_user = MockUser(
            id=1, email="admin@example.com", slack_id="UADMIN123", is_admin=True
        )
        mock_check_admin.return_value = admin_user

        payload = {
            "user": {"id": "UADMIN123"},
            "view": {
                "state": {
                    "values": {
                        "url_block": {"content_url": {"value": "http://duplicate.url"}}
                    }
                }
            },
        }
        response = handle_create_content_view_submission(payload)

        mock_send_dm.assert_called_once()
        dm_text_arg = mock_send_dm.call_args[0][1]
        assert (
            "This URL has already been added: <http://duplicate.url|http://duplicate.url>"
            in dm_text_arg
        )
        assert response is None

    @patch("services.slack_service.send_slack_dm")
    @patch(
        "services.slack_service.create_content_item", side_effect=Exception("DB error")
    )
    @patch("services.slack_service._get_user_and_check_admin")
    @patch("services.slack_service._get_slack_client")
    def test_general_exception_on_create_sends_dm(
        self,
        mock_get_client,
        mock_check_admin,
        mock_create_item,
        mock_send_dm,
        app_context,
    ):
        mock_slack_web_client = MagicMock()
        mock_get_client.return_value = mock_slack_web_client
        admin_user = MockUser(
            id=1, email="admin@example.com", slack_id="UADMIN123", is_admin=True
        )
        mock_check_admin.return_value = admin_user

        payload = {
            "user": {"id": "UADMIN123"},
            "view": {
                "state": {
                    "values": {
                        "url_block": {"content_url": {"value": "http://error.url"}}
                    }
                }
            },
        }
        response = handle_create_content_view_submission(payload)

        mock_send_dm.assert_called_once()
        dm_text_arg = mock_send_dm.call_args[0][1]
        assert (
            "Sorry, there was an error creating content for <http://error.url|http://error.url>"
            in dm_text_arg
        )
        assert "Error: DB error" in dm_text_arg
        assert response is None

    @patch("services.slack_service._get_user_and_check_admin")
    @patch("services.slack_service._get_slack_client")
    def test_submission_by_non_admin_logs_clears_modal(
        self, mock_get_client, mock_check_admin, app_context, caplog
    ):
        mock_slack_web_client = (
            MagicMock()
        )  # Not strictly needed as no client calls if admin check fails early
        mock_get_client.return_value = mock_slack_web_client
        mock_check_admin.return_value = None  # Simulate non-admin / user not found

        payload = {
            "user": {"id": "UNOTADMIN"},
            "view": {
                "state": {
                    "values": {
                        "url_block": {"content_url": {"value": "http://sneaky.url"}}
                    }
                }
            },
        }
        response = handle_create_content_view_submission(payload)

        assert (
            "Content creation modal submitted by non-admin or unknown Slack ID: UNOTADMIN"
            in caplog.text
        )
        assert response == {"response_action": "clear"}
