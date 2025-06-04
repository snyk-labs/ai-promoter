import time
import hmac
import hashlib
from flask import current_app


def verify_slack_request(
    body_bytes, timestamp_header, signature_header, signing_secret
):
    """Verifies the Slack request signature."""
    if not timestamp_header or not signature_header or not signing_secret:
        current_app.logger.warning(
            "Slack signature verification failed: Missing header or secret."
        )
        return False

    try:
        timestamp = int(timestamp_header)
    except ValueError:
        current_app.logger.warning(
            "Slack signature verification failed: Invalid timestamp format."
        )
        return False

    if abs(time.time() - timestamp) > 60 * 5:  # 5 minutes
        current_app.logger.warning(
            "Slack signature verification failed: Timestamp too old."
        )
        return False

    sig_basestring = f"v0:{timestamp}:{body_bytes.decode('utf-8')}".encode("utf-8")
    secret_bytes = signing_secret.encode("utf-8")

    my_signature = (
        "v0=" + hmac.new(secret_bytes, sig_basestring, hashlib.sha256).hexdigest()
    )

    if not hmac.compare_digest(my_signature, signature_header):
        current_app.logger.warning(
            f"Slack signature verification failed: Signature mismatch. Expected: {my_signature}, Got: {signature_header}"
        )
        return False

    current_app.logger.info("Slack signature verification successful.")
    return True
