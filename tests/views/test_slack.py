import pytest
from flask import Flask
import time
import hmac
import hashlib
import json

from views.slack import bp

TEST_SLACK_SIGNING_SECRET = "test_secret_1234567890abcdef1234567890abcdef"


@pytest.fixture
def app_with_slack_bp():
    """Fixture to create a minimal Flask app with the slack_bp registered."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SLACK_SIGNING_SECRET"] = TEST_SLACK_SIGNING_SECRET
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

    def test_event_callback_with_valid_signature(self, client, caplog):
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
        assert json_data["status"] == "ok"
        assert (
            "Received and verified Slack event of type 'event_callback'" in caplog.text
        )
        assert "Slack signature verification successful." in caplog.text

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
        assert (
            "Slack signature verification failed: Missing header or secret."
            in caplog.text
        )

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
        assert (
            "Slack signature verification failed: Missing header or secret."
            in caplog.text
        )

    def test_event_callback_no_signing_secret_configured(
        self, client, caplog, app_with_slack_bp
    ):
        """Test behavior when SLACK_SIGNING_SECRET is not configured in the app."""
        original_secret = app_with_slack_bp.config.pop("SLACK_SIGNING_SECRET", None)

        payload = {"type": "event_callback", "event": {"type": "app_mention"}}
        payload_str = json.dumps(payload, separators=(",", ":"))
        timestamp = str(int(time.time()))
        irrelevant_signature = "v0=irrelevant_because_secret_is_missing"

        response = client.post(
            "/slack/events",
            data=payload_str,
            content_type="application/json",
            headers={
                "X-Slack-Request-Timestamp": timestamp,
                "X-Slack-Signature": irrelevant_signature,
            },
        )
        assert response.status_code == 500  # Expect 500 Internal Server Error
        json_data = response.get_json()
        assert json_data["error"] == "Server configuration error for Slack integration"
        assert (
            "CRITICAL: SLACK_SIGNING_SECRET is not configured. Rejecting request."
            in caplog.text
        )
        # Ensure the warning about proceeding is NOT logged
        assert (
            "Proceeding with Slack event without signature verification"
            not in caplog.text
        )

        if original_secret:
            app_with_slack_bp.config["SLACK_SIGNING_SECRET"] = original_secret

    def test_invalid_json_payload(self, client):
        """Test handling of an invalid JSON payload when signature is valid."""
        raw_data = "not json {{{{ badly formatted"
        timestamp = str(int(time.time()))
        signature = generate_slack_signature(
            timestamp, raw_data, TEST_SLACK_SIGNING_SECRET
        )

        response = client.post(
            "/slack/events",
            data=raw_data,
            content_type="application/json",
            headers={
                "X-Slack-Request-Timestamp": timestamp,
                "X-Slack-Signature": signature,
            },
        )
        assert response.status_code == 400
        json_data = response.get_json()
        assert "error" in json_data
        assert json_data["error"] == "Invalid JSON payload"

    def test_empty_json_payload_with_valid_signature(self, client, caplog):
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
        assert response.status_code == 400
        json_data = response.get_json()
        assert "error" in json_data
        assert json_data["error"] == "No data provided or malformed JSON"
        assert (
            "Slack signature verification successful." in caplog.text
        )  # Verification happens before empty data check

    def test_missing_type_in_payload_with_valid_signature(self, client, caplog):
        payload = {"challenge": "some_challenge_without_type"}
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
        assert json_data["status"] == "ok"
        assert "Slack signature verification successful." in caplog.text
        assert "Received and verified Slack event of type 'None'" in caplog.text
