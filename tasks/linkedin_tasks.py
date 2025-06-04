from celery import shared_task
from flask import current_app  # For accessing app config
from datetime import datetime, timedelta, timezone
import logging

from models import User  # Assuming User model is in models.py or models/user.py
from helpers.linkedin_native import refresh_linkedin_token
from services.slack_service import send_slack_dm  # Import the Slack DM helper
from extensions import (
    db,
)  # For db.session within the task if needed, though refresh_token handles its own commit

logger = logging.getLogger(__name__)


@shared_task(name="tasks.linkedin.refresh_expiring_tokens", ignore_result=True)
def refresh_expiring_linkedin_tokens():
    """
    Periodically refreshes LinkedIn access tokens that are about to expire.
    Only processes users who have LinkedIn integration enabled and have refresh tokens.
    """
    now = datetime.now()
    expiration_threshold = now + timedelta(
        days=7
    )  # Tokens expiring within the next 7 days
    # A shorter threshold (e.g., 1-2 days) might be more practical to avoid unnecessary API calls
    # if tokens are typically much longer-lived, but 7 days is a safe starting point.

    # Query for users with native LinkedIn tokens that are expiring soon
    # and have a refresh token.
    users_to_refresh = User.query.filter(
        User.linkedin_native_refresh_token.isnot(None),
        User.linkedin_native_token_expires_at.isnot(None),
        User.linkedin_native_token_expires_at < expiration_threshold,
    ).all()

    if not users_to_refresh:
        logger.info(
            "No LinkedIn tokens found that are expiring soon and need refreshing."
        )
        return

    logger.info(
        f"Found {len(users_to_refresh)} LinkedIn token(s) to attempt refreshing."
    )
    successful_refreshes = 0
    failed_refreshes = 0

    for user in users_to_refresh:
        logger.info(
            f"Attempting to refresh LinkedIn token for user ID: {user.id} (Email: {user.email})"
        )
        try:
            # The refresh_linkedin_token function now returns True, False, or 'invalid_grant'
            refresh_result = refresh_linkedin_token(user)

            if refresh_result is True:
                logger.info(
                    f"Successfully refreshed LinkedIn token for user ID: {user.id}"
                )
                successful_refreshes += 1
            elif refresh_result == "invalid_grant":
                logger.warning(
                    f"LinkedIn token for user ID: {user.id} is invalid (invalid_grant) and requires re-authentication."
                )
                failed_refreshes += 1
                if user.slack_id:
                    try:
                        base_url = current_app.config.get("BASE_URL", "").rstrip("/")
                        profile_url = f"{base_url}/auth/profile"
                        dm_text = (
                            f"Hi there! We tried to refresh your LinkedIn connection for AI Promoter, "
                            f"but it looks like your authorization has expired or been revoked. "
                            f"Please reconnect your LinkedIn account by visiting your profile page: {profile_url}"
                        )
                        send_slack_dm(user.slack_id, dm_text)
                        logger.info(
                            f"Sent Slack DM to user {user.id} ({user.slack_id}) about LinkedIn re-authentication."
                        )
                    except Exception as slack_err:
                        logger.error(
                            f"Failed to send Slack DM to user {user.id} ({user.slack_id}): {str(slack_err)}"
                        )
                else:
                    logger.warning(
                        f"User {user.id} requires LinkedIn re-authentication but has no Slack ID for notification."
                    )

            else:  # refresh_result is False (generic error)
                # refresh_linkedin_token logs its own errors, but we can add context here
                logger.warning(
                    f"Failed to refresh LinkedIn token for user ID: {user.id}. Check previous logs for details. Will retry later if applicable."
                )
                failed_refreshes += 1
        except Exception as e:
            # Catch any unexpected errors during the refresh attempt for a specific user
            logger.error(
                f"Unexpected error while trying to refresh token for user ID {user.id}: {str(e)}"
            )
            failed_refreshes += 1
            # Continue to the next user

    logger.info(
        f"LinkedIn token refresh task completed. Successful: {successful_refreshes}, Failed: {failed_refreshes}."
    )
