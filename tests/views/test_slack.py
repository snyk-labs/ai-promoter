import pytest
from flask import Flask, jsonify, current_app

# Import the blueprint to be tested
from views.slack import bp


@pytest.fixture
def app_with_slack_bp():
    """Fixture to create a minimal Flask app with the slack_bp registered."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(bp)
    return app


@pytest.fixture
def client(app_with_slack_bp):
    """Fixture to get a test client for the app."""
    return app_with_slack_bp.test_client()


# --- Unit Tests for Slack Blueprint ---
@pytest.mark.unit
@pytest.mark.slack
class TestSlackBlueprintUnit:
    def test_slack_blueprint_exists(self, app_with_slack_bp):
        """Test that the slack blueprint is registered."""
        assert "slack" in app_with_slack_bp.blueprints
        assert app_with_slack_bp.blueprints["slack"].name == "slack"
        assert app_with_slack_bp.blueprints["slack"].url_prefix == "/slack"


# --- Integration Tests for /slack/events Endpoint ---
@pytest.mark.integration
@pytest.mark.slack
class TestSlackEventsEndpoint:
    def test_url_verification(self, client):
        """Test the Slack URL verification challenge."""
        challenge_token = "test_challenge_token"
        response = client.post(
            "/slack/events",
            json={"type": "url_verification", "challenge": challenge_token},
        )
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data["challenge"] == challenge_token

    def test_event_callback_ok(self, client, caplog):
        """Test a generic event callback is acknowledged."""
        response = client.post(
            "/slack/events",
            json={
                "type": "event_callback",
                "event": {
                    "type": "app_mention",
                    "user": "U123ABC",
                    "text": "Hello bot",
                    "ts": "1629876543.000100",
                    "channel": "C123XYZ",
                    "event_ts": "1629876543.000100",
                },
            },
        )
        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data["status"] == "ok"
        # Check if the event was logged
        assert "Received Slack event of type 'event_callback'" in caplog.text

    def test_invalid_json_payload(self, client):
        """Test handling of an invalid JSON payload."""
        response = client.post(
            "/slack/events", data="not json", content_type="application/json"
        )
        assert response.status_code == 400
        json_data = response.get_json()
        assert "error" in json_data
        assert json_data["error"] == "Invalid JSON payload"

    def test_empty_json_payload(self, client):
        """Test handling of an empty JSON payload."""
        response = client.post("/slack/events", json={})
        assert (
            response.status_code == 400
        )  # Based on current implementation requiring data
        json_data = response.get_json()
        assert "error" in json_data
        # Update: The code was changed to return 400 if data is empty (not None as initially in my mental model)
        # Current code: `if not data:` which means an empty dict `{}` is falsy in this context of providing data
        # So, it should be caught by the `if not data:` check
        # Let's ensure the error message matches.
        assert json_data["error"] == "No data provided"

    def test_missing_type_in_payload(self, client, caplog):
        """Test handling of a payload missing the 'type' field."""
        response = client.post(
            "/slack/events", json={"challenge": "some_challenge_without_type"}
        )
        assert (
            response.status_code == 200
        )  # Currently, it will log and return ok, not a specific error for missing type if not url_verification
        json_data = response.get_json()
        assert json_data["status"] == "ok"
        assert (
            "Received Slack event of type 'None'" in caplog.text
        )  # Event type will be None
