import logging
from celery import shared_task, chain
from flask import current_app

# Import Slack SDK components - these are fine at module level
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Removed model and db imports from here to break circular dependency

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def send_slack_invitation_task(self, user_id_from_chain: int):
    """
    Celery task to send a Slack invitation to a new user.
    Receives user_id from the preceding task in a chain.
    """
    # Moved imports inside the task function
    from models import User
    from extensions import db
    from services.slack_service import invite_user_to_channel

    logger.info(
        f"Starting Slack invitation task for user_id: {user_id_from_chain} (received from chain)"
    )
    try:
        user = db.session.get(User, user_id_from_chain)
        if not user:
            logger.error(
                f"User with ID {user_id_from_chain} not found. Cannot send Slack invitation."
            )
            return

        if not user.slack_id:
            logger.warning(
                f"User {user.email} (ID: {user_id_from_chain}) does not have a slack_id. Skipping Slack invitation."
            )
            return

        channel_id = current_app.config.get("SLACK_DEFAULT_CHANNEL_ID")
        if not channel_id:
            logger.error(
                "SLACK_DEFAULT_CHANNEL_ID is not configured. Cannot send Slack invitation."
            )
            return

        logger.info(
            f"Attempting to send Slack invitation to user: {user.email} (Slack ID: {user.slack_id}) for channel: {channel_id}"
        )
        success = invite_user_to_channel(
            slack_user_id=user.slack_id,
            channel_id=channel_id,
            user_email_for_logging=user.email,
        )

        if success:
            logger.info(f"Slack invitation process completed for user {user.email}.")
        else:
            logger.warning(
                f"Slack invitation failed for user {user.email}. Task may retry if attempts left and an exception was raised by the service."
            )

    except Exception as e:
        logger.error(
            f"Error in send_slack_invitation_task for user_id {user_id_from_chain}: {e}",
            exc_info=True,
        )
        self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=180)
def slack_get_user_id(self, user_id: int):
    """
    Celery task to fetch a user's Slack ID using their email and update the User model.
    Returns user_id on successful completion to be passed to the next task in a chain.
    """
    # Moved imports inside the task function
    from models import User
    from extensions import db

    logger.info(f"Starting task to get Slack ID for user_id: {user_id}")

    try:
        user = db.session.get(User, user_id)
        if not user:
            logger.error(f"User with ID {user_id} not found. Cannot get Slack ID.")
            return user_id

        if not user.email:
            logger.error(f"User with ID {user_id} has no email. Cannot get Slack ID.")
            return user_id

        if user.slack_id:
            logger.info(
                f"User {user.email} (ID: {user_id}) already has a slack_id: {user.slack_id}. Skipping lookup."
            )
            return user_id

        slack_token = current_app.config.get("SLACK_BOT_TOKEN")
        if not slack_token:
            logger.error("SLACK_BOT_TOKEN is not configured. Cannot get Slack ID.")
            raise ValueError("SLACK_BOT_TOKEN not configured")

        client = WebClient(token=slack_token)
        logger.info(f"Looking up Slack user ID for email: {user.email}")

        slack_user_api_response = client.users_lookupByEmail(email=user.email)
        found_slack_user_id = slack_user_api_response["user"]["id"]

        logger.info(
            f"Found Slack user ID: {found_slack_user_id} for email: {user.email}"
        )
        user.slack_id = found_slack_user_id
        db.session.commit()
        logger.info(
            f"Successfully stored slack_id {found_slack_user_id} for user {user.email} (ID: {user_id})."
        )
        return user_id

    except SlackApiError as e:
        error_code = e.response.get("error")
        if error_code == "users_not_found":
            logger.warning(
                f"Slack user with email {user.email} (ID: {user_id}) not found on Slack. Error: {e}"
            )
            return user_id
        elif error_code == "missing_scope":
            logger.error(
                f"Slack API error for user {user.email} (ID: {user_id}) due to missing permissions: {e}. Required scope: users:read.email"
            )
            self.retry(exc=e)
        else:
            logger.error(
                f"Slack API error for user {user.email} (ID: {user_id}): {e}",
                exc_info=True,
            )
            self.retry(exc=e)
    except Exception as e:
        logger.error(
            f"Unexpected error in slack_get_user_id for user_id {user_id}: {e}",
            exc_info=True,
        )
        db.session.rollback()
        self.retry(exc=e)

    return user_id


def create_tasks_init_py():
    """
    Helper to ensure tasks/__init__.py exists.
    """
    pass  # Handled by edit_file for tasks/slack_tasks.py directly
