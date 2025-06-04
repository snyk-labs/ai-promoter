import pytest
from flask import Flask, current_app
import time
import hmac
import hashlib
import json

from helpers.slack import verify_slack_request

TEST_SLACK_SIGNING_SECRET = "test_secret_for_helpers_12345"


@pytest.fixture
def app_context():
    """Fixture to provide a minimal Flask app context for the helper tests."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    # The helper itself doesn't directly use app.config for the secret,
    # but it uses current_app.logger, so a context is needed.
    with app.app_context():
        yield app


# --- Unit Tests for verify_slack_request Helper ---
@pytest.mark.unit
@pytest.mark.slack  # Keep slack marker if we want to run all slack-related unit tests together
class TestVerifySlackRequestHelper:

    def generate_signature(self, timestamp, payload_body_str, secret):
        """Helper to generate a valid Slack signature for testing this module."""
        if not isinstance(payload_body_str, str):
            # In tests, we might pass dicts, so ensure it's stringified if body_bytes is expected as str by helper
            payload_body_str = json.dumps(payload_body_str, separators=(",", ":"))

        sig_basestring = f"v0:{timestamp}:{payload_body_str}".encode("utf-8")
        secret_bytes = secret.encode("utf-8")
        my_signature = (
            "v0=" + hmac.new(secret_bytes, sig_basestring, hashlib.sha256).hexdigest()
        )
        return my_signature

    def test_valid_signature(self, app_context, caplog):
        payload_dict = {"message": "hello"}
        payload_str = json.dumps(
            payload_dict, separators=(",", ":")
        )  # As the function expects bytes decodable to this
        payload_bytes = payload_str.encode("utf-8")
        timestamp = str(int(time.time()))
        signature = self.generate_signature(
            timestamp, payload_str, TEST_SLACK_SIGNING_SECRET
        )

        assert (
            verify_slack_request(
                payload_bytes, timestamp, signature, TEST_SLACK_SIGNING_SECRET
            )
            is True
        )
        assert "Slack signature verification successful." in caplog.text

    def test_invalid_signature_mismatch(self, app_context, caplog):
        payload_dict = {"message": "hello"}
        payload_str = json.dumps(payload_dict, separators=(",", ":"))
        payload_bytes = payload_str.encode("utf-8")
        timestamp = str(int(time.time()))
        invalid_signature = "v0=bad_signature"

        assert (
            verify_slack_request(
                payload_bytes, timestamp, invalid_signature, TEST_SLACK_SIGNING_SECRET
            )
            is False
        )
        assert "Slack signature verification failed: Signature mismatch" in caplog.text

    def test_old_timestamp(self, app_context, caplog):
        payload_dict = {"message": "hello"}
        payload_str = json.dumps(payload_dict, separators=(",", ":"))
        payload_bytes = payload_str.encode("utf-8")
        old_timestamp = str(int(time.time()) - (60 * 6))  # 6 minutes old
        signature = self.generate_signature(
            old_timestamp, payload_str, TEST_SLACK_SIGNING_SECRET
        )

        assert (
            verify_slack_request(
                payload_bytes, old_timestamp, signature, TEST_SLACK_SIGNING_SECRET
            )
            is False
        )
        assert "Slack signature verification failed: Timestamp too old." in caplog.text

    def test_missing_timestamp_header_arg(self, app_context, caplog):
        payload_bytes = b"payload"
        signature = "v0=some_sig"
        assert (
            verify_slack_request(
                payload_bytes, None, signature, TEST_SLACK_SIGNING_SECRET
            )
            is False
        )
        assert (
            "Slack signature verification failed: Missing header or secret."
            in caplog.text
        )

    def test_missing_signature_header_arg(self, app_context, caplog):
        payload_bytes = b"payload"
        timestamp = str(int(time.time()))
        assert (
            verify_slack_request(
                payload_bytes, timestamp, None, TEST_SLACK_SIGNING_SECRET
            )
            is False
        )
        assert (
            "Slack signature verification failed: Missing header or secret."
            in caplog.text
        )

    def test_missing_signing_secret_arg(self, app_context, caplog):
        payload_bytes = b"payload"
        timestamp = str(int(time.time()))
        signature = "v0=some_sig"
        assert verify_slack_request(payload_bytes, timestamp, signature, None) is False
        assert (
            "Slack signature verification failed: Missing header or secret."
            in caplog.text
        )

    def test_invalid_timestamp_format(self, app_context, caplog):
        payload_bytes = b"payload"
        timestamp = "not_an_int"
        signature = "v0=some_sig"
        assert (
            verify_slack_request(
                payload_bytes, timestamp, signature, TEST_SLACK_SIGNING_SECRET
            )
            is False
        )
        assert (
            "Slack signature verification failed: Invalid timestamp format."
            in caplog.text
        )
