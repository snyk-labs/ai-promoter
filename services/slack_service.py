import logging
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from flask import current_app

# Removed db and User model imports as slack_id is now passed in directly
# and its storage is handled by a dedicated Celery task.

logger = logging.getLogger(__name__)


def invite_user_to_channel(
    slack_user_id: str, channel_id: str, user_email_for_logging: str = None
):
    """
    Invites a user to a Slack channel using their Slack User ID.

    Args:
        slack_user_id: The Slack User ID of the user to invite.
        channel_id: The ID of the Slack channel to invite the user to.
        user_email_for_logging: (Optional) The user's email, for richer logging.

    Returns:
        True if the invitation was sent successfully or user already in channel, False otherwise.
    """
    log_identifier = f"user with Slack ID {slack_user_id}"
    if user_email_for_logging:
        log_identifier += f" ({user_email_for_logging})"

    slack_token = current_app.config.get("SLACK_BOT_TOKEN")
    if not slack_token:
        logger.error(
            f"SLACK_BOT_TOKEN is not configured. Cannot invite {log_identifier}."
        )
        return False
    if not channel_id:
        logger.error(
            f"Slack channel ID is not provided. Cannot invite {log_identifier}."
        )
        return False
    if not slack_user_id:
        logger.error(
            f"Slack user ID is not provided. Cannot invite to channel {channel_id}."
        )
        return False

    client = WebClient(token=slack_token)

    try:
        logger.info(f"Inviting {log_identifier} to channel {channel_id}")
        client.conversations_invite(channel=channel_id, users=slack_user_id)
        logger.info(
            f"Successfully sent Slack invitation to {log_identifier} for channel {channel_id}."
        )
        return True
    except SlackApiError as e:
        error_code = e.response.get("error")
        if error_code == "already_in_channel":
            logger.info(f"{log_identifier} is already in channel {channel_id}.")
            return True
        # user_not_found is less likely here if slack_user_id is valid, but good to keep.
        elif error_code == "user_not_found" or error_code == "users_not_found":
            logger.warning(
                f"Slack user with ID {slack_user_id} not found by Slack. Cannot invite to channel {channel_id}. Error: {e}"
            )
            return False
        elif error_code == "channel_not_found":
            logger.error(
                f"Slack channel {channel_id} not found. Cannot invite {log_identifier}. Error: {e}"
            )
            return False
        elif error_code == "not_in_channel":
            logger.error(
                f"The bot is not in channel {channel_id}. Cannot invite {log_identifier}. Error: {e}"
            )
            return False
        elif error_code == "ekm_access_denied" or error_code == "missing_scope":
            logger.error(
                f"Slack API error for {log_identifier} due to missing permissions or EKM access: {e}. Required scopes might be missing (e.g., channels:manage, groups:write, chat:write)."
            )
            return False
        else:
            logger.error(
                f"Error inviting {log_identifier} to Slack channel {channel_id}: {e}"
            )
            return False
    except Exception as e:
        logger.error(
            f"An unexpected error occurred while inviting {log_identifier} to Slack channel {channel_id}: {e}"
        )
        return False


def send_slack_dm(user_slack_id: str, message_text: str, blocks: list = None):
    """
    Sends a direct message to a Slack user.

    Args:
        user_slack_id: The Slack User ID of the recipient.
        message_text: The fallback text for the message.
        blocks: Optional list of Slack blocks for richer formatting.

    Returns:
        True if the message was sent successfully, False otherwise.
    """
    slack_token = current_app.config.get("SLACK_BOT_TOKEN")
    if not slack_token:
        logger.error("SLACK_BOT_TOKEN is not configured. Cannot send DM.")
        return False
    if not user_slack_id:
        logger.error("Slack user ID not provided. Cannot send DM.")
        return False

    client = WebClient(token=slack_token)
    try:
        logger.info(f"Sending DM to Slack user ID: {user_slack_id}")
        client.chat_postMessage(channel=user_slack_id, text=message_text, blocks=blocks)
        logger.info(f"Successfully sent DM to Slack user ID: {user_slack_id}.")
        return True
    except SlackApiError as e:
        error_code = e.response.get("error")
        # Common errors: user_not_found, channel_not_found (if ID is wrong type), restricted_action
        logger.error(
            f"Slack API error sending DM to {user_slack_id}: {error_code} - {e.response.get('needed', '')} - {e.response.get('provided', '')}"
        )
        return False
    except Exception as e:
        logger.error(
            f"An unexpected error occurred while sending DM to {user_slack_id}: {e}"
        )
        return False
