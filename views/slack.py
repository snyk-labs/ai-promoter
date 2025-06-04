from flask import Blueprint, request, jsonify, current_app
import os

bp = Blueprint("slack", __name__, url_prefix="/slack")


@bp.route("/events", methods=["POST"])
def slack_events():
    """
    Handles incoming Slack events.
    """
    try:
        data = request.json
    except Exception as e:
        current_app.logger.error(f"Error parsing JSON: {e}")
        return jsonify({"error": "Invalid JSON payload"}), 400

    if not data:
        current_app.logger.warning("Received empty JSON data in /slack/events")
        return jsonify({"error": "No data provided"}), 400

    event_type = data.get("type")

    if event_type == "url_verification":
        challenge = data.get("challenge")
        current_app.logger.info(
            f"Responding to Slack URL verification challenge: {challenge}"
        )
        return jsonify({"challenge": challenge})

    # TODO: Implement Slack request signature verification for security.
    # This is crucial for ensuring requests are genuinely from Slack.
    # Example placeholder:
    # slack_signing_secret = current_app.config.get('SLACK_SIGNING_SECRET')
    # if not verify_slack_request(request.get_data(as_text=True),
    #                             request.headers.get('X-Slack-Request-Timestamp'),
    #                             request.headers.get('X-Slack-Signature'),
    #                             slack_signing_secret):
    #     current_app.logger.warning("Slack request verification failed.")
    #     return jsonify({"error": "Request verification failed"}), 403

    current_app.logger.info(f"Received Slack event of type '{event_type}': {data}")

    # Delegate to the SlackService for processing
    # We'll import and call the service here once it's more fleshed out.
    # For now, we're just acknowledging the event.
    # from services.slack import slack_service
    # slack_service.handle_event(data)

    return jsonify({"status": "ok"}), 200


# Example helper for signature verification (to be completed and placed appropriately)
# def verify_slack_request(body, timestamp, signature, signing_secret):
#     import hmac
#     import hashlib
#     if abs(time.time() - int(timestamp)) > 60 * 5: # 5 minutes
#         return False # Timestamp too old
#     sig_basestring = f"v0:{timestamp}:{body}".encode('utf-8')
#     my_signature = 'v0=' + hmac.new(
#         signing_secret.encode('utf-8'),
#         sig_basestring,
#         hashlib.sha256
#     ).hexdigest()
#     return hmac.compare_digest(my_signature, signature)
