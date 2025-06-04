import pytest
from flask import Flask
import time
import hmac
import hashlib
import json
from urllib.parse import urlencode
from unittest.mock import patch

from views.slack import bp
from services.slack_service import CREATE_CONTENT_MODAL_CALLBACK_ID

TEST_SLACK_SIGNING_SECRET = "test_secret_1234567890abcdef1234567890abcdef"


@pytest.fixture
def app_with_slack_bp():
    """Fixture to create a minimal Flask app with the slack_bp registered."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SLACK_SIGNING_SECRET"] = TEST_SLACK_SIGNING_SECRET
    app.config["SLACK_BOT_TOKEN"] = "test_bot_token_for_views"
    app.register_blueprint(bp)
    return app


@pytest.fixture
def client(app_with_slack_bp):
    return app_with_slack_bp.test_client()


def generate_slack_signature(timestamp, payload_body_str, secret):
    """Helper to generate a valid Slack signature."""
    if not isinstance(payload_body_str, str):
        raise ValueError("payload_body_str must be a string for signature generation.")

    sig_basestring = f"v0:{timestamp}:{payload_body_str}".encode("utf-8")
    secret_bytes = secret.encode("utf-8")
    my_signature = (
        "v0=" + hmac.new(secret_bytes, sig_basestring, hashlib.sha256).hexdigest()
    )
    return my_signature


@pytest.mark.unit
@pytest.mark.slack
class TestSlackBlueprintUnit:
    def test_slack_blueprint_exists(self, app_with_slack_bp):
        assert "slack" in app_with_slack_bp.blueprints
        assert app_with_slack_bp.blueprints["slack"].name == "slack"
        assert app_with_slack_bp.blueprints["slack"].url_prefix == "/slack"


@pytest.mark.integration
@pytest.mark.slack
class TestSlackEventsEndpoint:
    def test_url_verification(self, client):
        """Test the Slack URL verification challenge (does not require signature)."""
        challenge_token = "test_challenge_token"
        response = client.post(
            "/slack/events",
            json={"type": "url_verification", "challenge": challenge_token},
        )
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data["challenge"] == challenge_token

    @patch("views.slack.verify_slack_request", return_value=True)
    def test_event_callback_with_valid_signature(self, mock_verify, client, caplog):
        payload = {
            "type": "event_callback",
            "event": {
                "type": "app_mention",
                "user": "U123ABC",
                "text": "Hello bot",
                "ts": "1629876543.000100",
                "channel": "C123XYZ",
                "event_ts": "1629876543.000100",
            },
        }
        payload_str = json.dumps(payload, separators=(",", ":"))
        timestamp = str(int(time.time()))
        signature = generate_slack_signature(
            timestamp, payload_str, TEST_SLACK_SIGNING_SECRET
        )

        response = client.post(
            "/slack/events",
            data=payload_str,
            content_type="application/json",
            headers={
                "X-Slack-Request-Timestamp": timestamp,
                "X-Slack-Signature": signature,
            },
        )
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data["status"] == "event_callback received"
        assert "Received and verified Slack payload." in caplog.text
        assert "Received event_callback. Inner event type: app_mention" in caplog.text

    def test_event_callback_with_invalid_signature(self, client, caplog):
        payload = {"type": "event_callback", "event": {"type": "app_mention"}}
        payload_str = json.dumps(payload, separators=(",", ":"))
        timestamp = str(int(time.time()))
        invalid_signature = "v0=invalid_signature_does_not_match"

        response = client.post(
            "/slack/events",
            data=payload_str,
            content_type="application/json",
            headers={
                "X-Slack-Request-Timestamp": timestamp,
                "X-Slack-Signature": invalid_signature,
            },
        )
        assert response.status_code == 403
        json_data = response.get_json()
        assert json_data["error"] == "Request verification failed"
        assert "Slack signature verification failed: Signature mismatch" in caplog.text

    def test_event_callback_with_old_timestamp(self, client, caplog):
        payload = {"type": "event_callback", "event": {"type": "app_mention"}}
        payload_str = json.dumps(payload, separators=(",", ":"))
        old_timestamp = str(
            int(time.time()) - (60 * 6)
        )  # Timestamp more than 5 minutes old
        signature = generate_slack_signature(
            old_timestamp, payload_str, TEST_SLACK_SIGNING_SECRET
        )

        response = client.post(
            "/slack/events",
            data=payload_str,
            content_type="application/json",
            headers={
                "X-Slack-Request-Timestamp": old_timestamp,
                "X-Slack-Signature": signature,
            },
        )
        assert response.status_code == 403
        json_data = response.get_json()
        assert json_data["error"] == "Request verification failed"
        assert "Slack signature verification failed: Timestamp too old." in caplog.text

    def test_event_callback_missing_timestamp_header(self, client, caplog):
        payload = {"type": "event_callback", "event": {"type": "app_mention"}}
        payload_str = json.dumps(payload, separators=(",", ":"))
        timestamp = str(int(time.time()))
        signature = generate_slack_signature(
            timestamp, payload_str, TEST_SLACK_SIGNING_SECRET
        )

        response = client.post(
            "/slack/events",
            data=payload_str,
            content_type="application/json",
            headers={
                "X-Slack-Signature": signature  # Missing 'X-Slack-Request-Timestamp'
            },
        )
        assert response.status_code == 403
        json_data = response.get_json()
        assert json_data["error"] == "Request verification failed"
        assert "Slack request verification failed. Rejecting request." in caplog.text

    def test_event_callback_missing_signature_header(self, client, caplog):
        payload = {"type": "event_callback", "event": {"type": "app_mention"}}
        payload_str = json.dumps(payload, separators=(",", ":"))
        timestamp = str(int(time.time()))

        response = client.post(
            "/slack/events",
            data=payload_str,
            content_type="application/json",
            headers={
                "X-Slack-Request-Timestamp": timestamp  # Missing 'X-Slack-Signature'
            },
        )
        assert response.status_code == 403
        json_data = response.get_json()
        assert json_data["error"] == "Request verification failed"
        assert "Slack request verification failed. Rejecting request." in caplog.text

    def test_event_callback_no_signing_secret_configured(
        self, client, caplog, app_with_slack_bp
    ):
        """Test behavior when SLACK_SIGNING_SECRET is not configured in the app."""
        original_secret = app_with_slack_bp.config.pop("SLACK_SIGNING_SECRET", None)

        payload = {"type": "event_callback", "event": {"type": "app_mention"}}
        payload_str = json.dumps(payload, separators=(",", ":"))
        timestamp = str(int(time.time()))
        irrelevant_signature = "v0=irrelevant_because_secret_is_missing"

        try:
            response = client.post(
                "/slack/events",
                data=payload_str,
                content_type="application/json",
                headers={
                    "X-Slack-Request-Timestamp": timestamp,
                    "X-Slack-Signature": irrelevant_signature,
                },
            )
            assert response.status_code == 500
            json_data = response.get_json()
            assert (
                json_data["error"] == "Server configuration error for Slack integration"
            )
            assert (
                "CRITICAL: SLACK_SIGNING_SECRET is not configured. Rejecting request."
                in caplog.text
            )
        finally:
            if original_secret:
                app_with_slack_bp.config["SLACK_SIGNING_SECRET"] = original_secret

    @patch("views.slack.verify_slack_request", return_value=True)
    def test_invalid_json_payload(self, mock_verify_request, client, caplog):
        """Test handling of an invalid JSON payload when signature is mocked as valid."""
        raw_data = "not json {{{{ badly formatted"
        timestamp = str(int(time.time()))
        signature = "v0=mocked_signature_for_bad_json"

        response = client.post(
            "/slack/events",
            data=raw_data,
            headers={
                "X-Slack-Request-Timestamp": timestamp,
                "X-Slack-Signature": signature,
            },
        )
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data["status"] == "unhandled payload"
        assert "Error parsing non-JSON request body" not in caplog.text
        assert "Received unhandled Slack payload type or structure" in caplog.text

    @patch("views.slack.verify_slack_request", return_value=True)
    def test_empty_json_payload_with_valid_signature(self, mock_verify, client, caplog):
        payload_str = "{}"
        timestamp = str(int(time.time()))
        signature = generate_slack_signature(
            timestamp, payload_str, TEST_SLACK_SIGNING_SECRET
        )

        response = client.post(
            "/slack/events",
            data=payload_str,
            content_type="application/json",
            headers={
                "X-Slack-Request-Timestamp": timestamp,
                "X-Slack-Signature": signature,
            },
        )
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data["status"] == "unhandled payload"
        assert "Received unhandled Slack payload type or structure" in caplog.text

    @patch("views.slack.verify_slack_request", return_value=True)
    def test_missing_type_in_payload_with_valid_signature(
        self, mock_verify, client, caplog
    ):
        payload = {"challenge": "some_challenge_without_type"}
        payload_str = json.dumps(payload)
        timestamp = str(int(time.time()))
        signature = generate_slack_signature(
            timestamp, payload_str, TEST_SLACK_SIGNING_SECRET
        )

        response = client.post(
            "/slack/events",
            data=payload_str,
            content_type="application/json",
            headers={
                "X-Slack-Request-Timestamp": timestamp,
                "X-Slack-Signature": signature,
            },
        )
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data["status"] == "unhandled payload"
        assert "Received unhandled Slack payload type or structure" in caplog.text

    @patch("views.slack.handle_create_content_command")
    @patch("views.slack.verify_slack_request", return_value=True)
    def test_slash_command_create_content_routing(
        self, mock_verify_request, mock_handle_command, client, caplog
    ):
        command_payload = {
            "command": "/create-content",
            "text": "some params",
            "user_id": "UUSER123",
            "channel_id": "CCHAN123",
            "trigger_id": "trigger123",
        }
        raw_body_str = urlencode(command_payload)
        timestamp = str(int(time.time()))
        signature = "v0=mock_signature_for_test"

        response = client.post(
            "/slack/events",
            data=raw_body_str,
            content_type="application/x-www-form-urlencoded",
            headers={
                "X-Slack-Request-Timestamp": timestamp,
                "X-Slack-Signature": signature,
            },
        )
        assert response.status_code == 200
        mock_verify_request.assert_called_once()
        expected_parsed_payload_single_values = {
            k: v for k, v in command_payload.items()
        }

        mock_handle_command.assert_called_once_with(
            expected_parsed_payload_single_values
        )
        assert "Received slash command: /create-content" in caplog.text

    @patch("views.slack.handle_create_content_view_submission")
    @patch("views.slack.verify_slack_request", return_value=True)
    def test_view_submission_create_content_routing(
        self, mock_verify_request, mock_handle_submission, client, caplog
    ):
        mock_handle_submission.return_value = None

        view_submission_payload_dict = {
            "type": "view_submission",
            "user": {"id": "UUSER123"},
            "view": {
                "id": "VVIEW123",
                "type": "modal",
                "callback_id": CREATE_CONTENT_MODAL_CALLBACK_ID,
                "state": {
                    "values": {
                        "url_block": {"content_url": {"value": "http://example.com"}}
                    }
                },
            },
        }
        raw_body_str = urlencode({"payload": json.dumps(view_submission_payload_dict)})
        timestamp = str(int(time.time()))
        signature = "v0=mock_signature_for_test"

        response = client.post(
            "/slack/events",
            data=raw_body_str,
            content_type="application/x-www-form-urlencoded",
            headers={
                "X-Slack-Request-Timestamp": timestamp,
                "X-Slack-Signature": signature,
            },
        )
        assert response.status_code == 200
        assert response.data == b""
        mock_verify_request.assert_called_once()
        mock_handle_submission.assert_called_once_with(view_submission_payload_dict)
        assert (
            f"Received view_submission with callback_id: {CREATE_CONTENT_MODAL_CALLBACK_ID}"
            in caplog.text
        )

    @patch("views.slack.handle_create_content_view_submission")
    @patch("views.slack.verify_slack_request", return_value=True)
    def test_view_submission_with_response_action(
        self, mock_verify_request, mock_handle_submission, client, caplog
    ):
        error_response_action = {
            "response_action": "errors",
            "errors": {"url_block": "URL is required."},
        }
        mock_handle_submission.return_value = error_response_action

        view_submission_payload_dict = {
            "type": "view_submission",
            "user": {"id": "UUSER123"},
            "view": {
                "callback_id": CREATE_CONTENT_MODAL_CALLBACK_ID,
                "state": {"values": {}},
            },
        }
        raw_body_str = urlencode({"payload": json.dumps(view_submission_payload_dict)})
        timestamp = str(int(time.time()))
        signature = "v0=mock_signature_for_test"

        response = client.post(
            "/slack/events",
            data=raw_body_str,
            content_type="application/x-www-form-urlencoded",
            headers={
                "X-Slack-Request-Timestamp": timestamp,
                "X-Slack-Signature": signature,
            },
        )
        assert response.status_code == 200
        assert response.json == error_response_action
        mock_handle_submission.assert_called_once_with(view_submission_payload_dict)

    @patch("views.slack.handle_create_content_command")
    @patch("views.slack.verify_slack_request", return_value=True)
    def test_unknown_slash_command(
        self, mock_verify_request, mock_handle_known_command, client, caplog
    ):
        command_payload = {
            "command": "/unknown",
            "user_id": "U123",
            "channel_id": "C123",
            "trigger_id": "t123",
        }
        raw_body_str = urlencode(command_payload)
        timestamp = str(int(time.time()))
        signature = "v0=mock_signature_for_test"

        response = client.post(
            "/slack/events",
            data=raw_body_str,
            content_type="application/x-www-form-urlencoded",
            headers={
                "X-Slack-Request-Timestamp": timestamp,
                "X-Slack-Signature": signature,
            },
        )
        assert response.status_code == 200
        assert response.json == {"text": "Unknown command: /unknown"}
        mock_handle_known_command.assert_not_called()
        assert "Received unknown slash command: /unknown" in caplog.text

    @patch("views.slack.handle_create_content_view_submission")
    @patch("views.slack.verify_slack_request", return_value=True)
    def test_unhandled_view_submission_callback_id(
        self, mock_verify_request, mock_handle_known_submission, client, caplog
    ):
        view_submission_payload_dict = {
            "type": "view_submission",
            "user": {"id": "UUSER123"},
            "view": {"callback_id": "unhandled_callback_id", "state": {"values": {}}},
        }
        raw_body_str = urlencode({"payload": json.dumps(view_submission_payload_dict)})
        timestamp = str(int(time.time()))
        signature = "v0=mock_signature_for_test"

        response = client.post(
            "/slack/events",
            data=raw_body_str,
            content_type="application/x-www-form-urlencoded",
            headers={
                "X-Slack-Request-Timestamp": timestamp,
                "X-Slack-Signature": signature,
            },
        )
        assert response.status_code == 200
        assert response.data == b""
        mock_handle_known_submission.assert_not_called()
        assert (
            "Received view_submission with unhandled callback_id: unhandled_callback_id"
            in caplog.text
        )
