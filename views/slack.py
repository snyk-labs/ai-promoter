from flask import Blueprint, request, jsonify, current_app
import json
from urllib.parse import parse_qs  # For parsing slash command payloads if needed

from helpers.slack import verify_slack_request

# Import the specific handlers from the service layer
from services.slack_service import (
    handle_create_content_command,
    handle_create_content_view_submission,
    CREATE_CONTENT_MODAL_CALLBACK_ID,  # Import callback_id for view submissions
)

bp = Blueprint("slack", __name__, url_prefix="/slack")


@bp.route("/events", methods=["POST"])
def slack_events():
    """
    Handles incoming Slack events, including slash commands and view submissions.
    """
    raw_body_bytes = request.get_data()
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")
    slack_signing_secret = current_app.config.get("SLACK_SIGNING_SECRET")

    if not slack_signing_secret:
        current_app.logger.error(
            "CRITICAL: SLACK_SIGNING_SECRET is not configured. Rejecting request."
        )
        return (
            jsonify({"error": "Server configuration error for Slack integration"}),
            500,
        )

    # Verify the request signature for all incoming event types except initial url_verification
    # For slash commands, the body is form-urlencoded, not JSON, so decode differently for signature generation
    # For interactive payloads (like view_submission), it's often `payload={...}` in form data.

    try:
        # Attempt to parse as JSON first (common for Events API, some interactions)
        data = json.loads(raw_body_bytes.decode("utf-8"))
    except json.JSONDecodeError:
        # If not JSON, it might be form-urlencoded (slash commands, interactive components)
        try:
            # Slack sends slash commands as application/x-www-form-urlencoded
            # Slack sends view_submissions typically as payload={"type":"view_submission", ...}
            decoded_body = raw_body_bytes.decode("utf-8")
            parsed_data = parse_qs(decoded_body)
            if "payload" in parsed_data:
                # This is an interactive component (e.g., modal submission)
                data = json.loads(parsed_data["payload"][0])
            else:
                # This is likely a slash command, keep it as parsed_data (dictionary of lists)
                # The verify_slack_request helper expects raw_body_bytes for basestring construction
                data = {
                    key: value[0] if len(value) == 1 else value
                    for key, value in parsed_data.items()
                }
        except Exception as e:
            current_app.logger.error(
                f"Error parsing non-JSON request body: {e}. Body: {raw_body_bytes.decode('utf-8')[:200]}"
            )
            return jsonify({"error": "Error processing request body"}), 400

    # URL verification is a special case and doesn't need signature verification here, handle first.
    if data.get("type") == "url_verification":
        challenge = data.get("challenge")
        current_app.logger.info(
            f"Responding to Slack URL verification challenge: {challenge}"
        )
        return jsonify({"challenge": challenge})

    # Now, verify the signature for all other requests.
    # The verify_slack_request function expects raw_body_bytes for basestring construction, which is correct.
    if not verify_slack_request(
        raw_body_bytes, timestamp, signature, slack_signing_secret
    ):
        current_app.logger.warning(
            "Slack request verification failed. Rejecting request."
        )
        return jsonify({"error": "Request verification failed"}), 403

    current_app.logger.info(
        f"Received and verified Slack payload. Data: {str(data)[:500]}"
    )  # Log snippet

    # --- Payload Routing ---
    # Check if it's a slash command payload
    # Slash commands come with a `command` field.
    if "command" in data:
        command = data.get("command")
        current_app.logger.info(f"Received slash command: {command}")
        if command == "/create-content":
            handle_create_content_command(data)  # Pass the parsed command payload
            return "", 200  # Acknowledge command immediately
        else:
            current_app.logger.warning(f"Received unknown slash command: {command}")
            return (
                jsonify({"text": f"Unknown command: {command}"}),
                200,
            )  # Send ephemeral message

    # Check if it's an interactive payload (e.g., view_submission)
    # Interactive payloads have a `type` field like `view_submission` or `block_actions`
    interaction_type = data.get("type")
    if interaction_type == "view_submission":
        callback_id = data.get("view", {}).get("callback_id")
        current_app.logger.info(
            f"Received view_submission with callback_id: {callback_id}"
        )
        if callback_id == CREATE_CONTENT_MODAL_CALLBACK_ID:
            # For view submissions, Slack expects a response that can modify the modal (e.g., show errors)
            # or close it. The handler function should return this response (or None/empty for just ack-and-close).
            response_action = handle_create_content_view_submission(data)
            if response_action:
                return jsonify(response_action), 200
            return "", 200  # Acknowledge and close modal by default
        else:
            current_app.logger.warning(
                f"Received view_submission with unhandled callback_id: {callback_id}"
            )
            return "", 200  # Acknowledge

    elif interaction_type == "block_actions":
        current_app.logger.info(f"Received block_actions payload: {str(data)[:500]}")
        # Add block_actions handlers here if needed in the future
        return "", 200  # Acknowledge

    # Fallback for other event types if not handled by specific logic above
    # (e.g., events from the Events API like `app_mention` if you subscribe to them)
    event_type = data.get("type")  # This might be the outer type like 'event_callback'
    if event_type == "event_callback":
        inner_event = data.get("event", {})
        inner_event_type = inner_event.get("type")
        current_app.logger.info(
            f"Received event_callback. Inner event type: {inner_event_type}"
        )
        # from services.slack import slack_service # If you have a generic event handler
        # slack_service.handle_event(data)
        return jsonify({"status": "event_callback received"}), 200

    current_app.logger.warning(
        f"Received unhandled Slack payload type or structure. Initial data keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}"
    )
    return jsonify({"status": "unhandled payload"}), 200
