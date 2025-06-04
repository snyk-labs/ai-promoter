from flask import Blueprint, request, jsonify, current_app
import json
from helpers.slack import verify_slack_request

bp = Blueprint("slack", __name__, url_prefix="/slack")


@bp.route("/events", methods=["POST"])
def slack_events():
    """
    Handles incoming Slack events.
    """
    raw_body_bytes = request.get_data()

    try:
        data = json.loads(raw_body_bytes.decode("utf-8"))
    except json.JSONDecodeError as e:
        current_app.logger.error(f"Error parsing JSON from raw body: {e}")
        return jsonify({"error": "Invalid JSON payload"}), 400
    except Exception as e:
        current_app.logger.error(f"Unexpected error processing request body: {e}")
        return jsonify({"error": "Error processing request body"}), 400

    event_type = data.get("type")

    # Handle URL verification first, as it does not require signature verification
    if event_type == "url_verification":
        challenge = data.get("challenge")
        current_app.logger.info(
            f"Responding to Slack URL verification challenge: {challenge}"
        )
        return jsonify({"challenge": challenge})

    # For all other event types, verify the signature first
    slack_signing_secret = current_app.config.get("SLACK_SIGNING_SECRET")
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")

    if not slack_signing_secret:
        current_app.logger.error(
            "CRITICAL: SLACK_SIGNING_SECRET is not configured. Rejecting request."
        )
        return (
            jsonify({"error": "Server configuration error for Slack integration"}),
            500,
        )  # Fail closed
    elif not verify_slack_request(
        raw_body_bytes, timestamp, signature, slack_signing_secret
    ):
        current_app.logger.warning(
            "Slack request verification failed. Rejecting request."
        )
        return jsonify({"error": "Request verification failed"}), 403
    # If secret exists and verification passed, we can proceed

    # Now that signature (if applicable) is verified, check if the data payload is empty
    # This handles cases like an empty JSON object {} which is valid JSON but might not be a valid event
    if not data:
        current_app.logger.warning(
            "Received empty JSON data (e.g., '{}') after signature verification."
        )
        return jsonify({"error": "No data provided or malformed JSON"}), 400

    current_app.logger.info(
        f"Received and verified Slack event of type '{event_type}': {data}"
    )

    # Delegate to the SlackService for processing
    # from services.slack import slack_service
    # slack_service.handle_event(data)
    return jsonify({"status": "ok"}), 200
