import logging
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from flask import current_app

# Application-specific imports
from models.user import User  # For checking admin status
from services.content_service import create_content_item, DuplicateContentError

# tasks.content.scrape_content_task is not directly called here, but by create_content_item

logger = logging.getLogger(__name__)

# Define a callback_id for the modal
CREATE_CONTENT_MODAL_CALLBACK_ID = "create_content_modal_submit"


def _get_slack_client():
    """Helper function to get an initialized Slack WebClient."""
    slack_token = current_app.config.get("SLACK_BOT_TOKEN")
    if not slack_token:
        logger.error("SLACK_BOT_TOKEN is not configured.")
        raise ValueError("SLACK_BOT_TOKEN is not configured.")
    return WebClient(token=slack_token)


def _get_user_and_check_admin(slack_user_id: str):
    """
    Retrieves a user by their Slack ID and checks if they are an admin.
    Returns the User object if admin, None otherwise.
    """
    if not slack_user_id:
        logger.warning("No Slack user ID provided for admin check.")
        return None

    # Assuming User model has a 'slack_id' field and 'is_admin' property/field.
    # Adjust query if your User model stores Slack IDs differently.
    user = User.query.filter_by(slack_id=slack_user_id).first()
    if not user:
        logger.warning(f"No application user found for Slack ID: {slack_user_id}")
        return None

    if not user.is_admin:
        logger.warning(
            f"User {user.email} (Slack ID: {slack_user_id}) is not an admin."
        )
        return None

    logger.info(f"Admin user {user.email} (Slack ID: {slack_user_id}) verified.")
    return user


def handle_create_content_command(payload: dict):
    """Handles the /create-content slash command."""
    try:
        client = _get_slack_client()
        trigger_id = payload.get("trigger_id")
        slack_user_id = payload.get("user_id")
        channel_id = payload.get("channel_id")  # For ephemeral messages

        if not trigger_id or not slack_user_id or not channel_id:
            logger.error(
                f"Missing trigger_id, user_id, or channel_id in /create-content payload: {payload}"
            )
            return  # Slack will show a generic error

        app_user = _get_user_and_check_admin(slack_user_id)
        if not app_user:
            client.chat_postEphemeral(
                channel=channel_id,
                user=slack_user_id,
                text="Sorry, you don't have permission to use this command.",
            )
            return

        modal_view = {
            "type": "modal",
            "callback_id": CREATE_CONTENT_MODAL_CALLBACK_ID,
            "title": {"type": "plain_text", "text": "Create New Content"},
            "submit": {"type": "plain_text", "text": "Submit"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "url_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "content_url",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "https://example.com/article",
                        },
                    },
                    "label": {"type": "plain_text", "text": "Content URL *"},
                },
                {
                    "type": "input",
                    "block_id": "context_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "content_context",
                        "multiline": True,
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Optional context about why this content is important or relevant.",
                        },
                    },
                    "label": {"type": "plain_text", "text": "Context"},
                    "optional": True,
                },
                {
                    "type": "input",
                    "block_id": "copy_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "content_copy",
                        "multiline": True,
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Suggested copy for sharing (e.g., social media post). {url} will be replaced.",
                        },
                    },
                    "label": {"type": "plain_text", "text": "Suggested Copy"},
                    "optional": True,
                },
                {
                    "type": "input",
                    "block_id": "utm_campaign_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "content_utm_campaign",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "e.g., spring_promo_2024",
                        },
                    },
                    "label": {"type": "plain_text", "text": "UTM Campaign"},
                    "optional": True,
                },
            ],
        }
        client.views_open(trigger_id=trigger_id, view=modal_view)
        logger.info(
            f"Create content modal opened for user {slack_user_id} by /create-content command."
        )

    except ValueError as ve:  # Handles _get_slack_client config error
        logger.error(f"Configuration error handling /create-content: {ve}")
    except SlackApiError as e:
        logger.error(f"Slack API error handling /create-content: {e.response['error']}")
    except Exception as e:
        logger.exception(f"Unexpected error handling /create-content: {e}")

    return  # Always return, Slack expects a 200 OK for command ack.


def handle_create_content_view_submission(payload: dict):
    """Handles the submission of the create content modal."""
    try:
        slack_user_id = payload.get("user", {}).get("id")

        app_user = _get_user_and_check_admin(slack_user_id)
        if not app_user:
            # This case should ideally not happen if modal is only opened for admins.
            # If it does, we can't easily send an ephemeral message to the closed modal context.
            # A DM might be an option, or just log.
            logger.error(
                f"Content creation modal submitted by non-admin or unknown Slack ID: {slack_user_id}. Payload: {payload}"
            )
            # Potentially send DM if critical, for now, just log.
            # send_slack_dm(slack_user_id, "There was an issue processing your content submission. You may not have the required permissions.")
            return {"response_action": "clear"}  # Clear the modal

        view_state = payload.get("view", {}).get("state", {}).get("values", {})

        # Extract values - Slack nests them under block_id and action_id
        url = view_state.get("url_block", {}).get("content_url", {}).get("value")
        context = (
            view_state.get("context_block", {}).get("content_context", {}).get("value")
        )
        copy = view_state.get("copy_block", {}).get("content_copy", {}).get("value")
        utm_campaign = (
            view_state.get("utm_campaign_block", {})
            .get("content_utm_campaign", {})
            .get("value")
        )

        if not url:
            # This error should be sent as a response action to update the modal with an error
            logger.warning(
                f"Content creation modal submitted with no URL by Slack ID: {slack_user_id}"
            )
            # This is a validation error on the modal itself.
            # Slack expects this in a specific format if you want to display errors in the modal.
            # For input validation errors, the response should be a 200 OK with a body like:
            # {"response_action": "errors", "errors": {"url_block": "URL is a required field."}}
            return {
                "response_action": "errors",
                "errors": {
                    "url_block": "URL is a required field. Please enter a valid URL."
                },
            }

        try:
            content, task = create_content_item(
                url=url,
                context=context,
                copy=copy,
                utm_campaign=utm_campaign,
                submitted_by_id=app_user.id,
                slack_user_id=slack_user_id,
            )
            message = f"✅ Content for URL <{content.url}|{content.title if content.title != 'Processing...' else content.url}> is being processed (Task ID: {task.id}). I'll notify you when it's ready!"
            send_slack_dm(slack_user_id, message)
            logger.info(
                f"Content creation process initiated from Slack modal for URL: {url} by user: {app_user.email} (Slack ID: {slack_user_id})"
            )

        except DuplicateContentError as dce:
            logger.warning(
                f"Duplicate content submission from Slack modal for URL: {url} by user: {app_user.email}. Error: {dce}"
            )
            # Option 1: Update the modal with an error (if possible, might need different response_action)
            # Option 2: Send a DM
            send_slack_dm(
                slack_user_id,
                f"⚠️ This URL has already been added: <{url}|{url}>. {str(dce)}",
            )
            # If we want to display this in the modal directly, it's tricky after initial submission ack.
            # Usually, for business logic errors post-submission, a DM or message is better.
            # For now, we assume the modal closes on initial 200 OK.
            # If we want to keep the modal open and show this, it's more complex.
        except Exception as e:
            logger.exception(
                f"Failed to create content from Slack modal for URL {url} by user {app_user.email}. Error: {e}"
            )
            send_slack_dm(
                slack_user_id,
                f"❌ Sorry, there was an error creating content for <{url}|{url}>. Please try again or contact an admin. Error: {str(e)}",
            )

    except ValueError as ve:  # Handles _get_slack_client config error
        logger.error(f"Configuration error handling content view submission: {ve}")
        # Cannot easily DM user here if client failed to init.
    except SlackApiError as e:
        logger.error(
            f"Slack API error handling content view submission: {e.response['error']}"
        )
        # If Slack API fails, DM might also fail.
    except Exception as e:
        logger.exception(f"Unexpected error handling content view submission: {e}")
        # Attempt to DM if possible, otherwise just log.
        if slack_user_id:  # Check if we have slack_user_id before trying to DM
            try:
                _get_slack_client()  # re-check client just in case it was the error source
                send_slack_dm(
                    slack_user_id,
                    "An unexpected error occurred while processing your request. Please contact an administrator.",
                )
            except Exception:  # nosemgrep
                pass  # nosemgrep # If DM fails, we've already logged the main exception.

    # A 200 OK response with an empty body closes the modal.
    # If you need to update the modal (e.g., show a success message within it) or open a new one,
    # you'd use a different response_action.
    # For now, we'll send a DM and close the modal.
    return  # Return None, Flask will make it a 200 OK. Or can return specific action.
    # For example, to explicitly close: return {"response_action": "clear"}
    # To update the modal: return {"response_action": "update", "view": updated_view_json}
    # To push a new modal: return {"response_action": "push", "view": new_view_json}


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

    try:
        client = _get_slack_client()  # Use the helper
    except ValueError:
        return False  # SLACK_BOT_TOKEN not configured

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
                f"Error inviting {log_identifier} to Slack channel {channel_id}: {e.response['error']}"
            )  # Log the specific Slack error
            return False
    except Exception as e:  # Catch any other unexpected errors
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
    try:
        client = _get_slack_client()  # Use the helper
    except ValueError:
        return False  # SLACK_BOT_TOKEN not configured

    if not user_slack_id:
        logger.error("Slack user ID not provided. Cannot send DM.")
        return False

    try:
        logger.info(f"Sending DM to Slack user ID: {user_slack_id}")
        client.chat_postMessage(channel=user_slack_id, text=message_text, blocks=blocks)
        logger.info(f"Successfully sent DM to Slack user ID: {user_slack_id}.")
        return True
    except SlackApiError as e:
        error_code = e.response.get("error")
        logger.error(
            f"Slack API error sending DM to {user_slack_id}: {error_code} - {e.response.get('needed', '')} - {e.response.get('provided', '')}"
        )
        return False
    except Exception as e:  # Catch any other unexpected errors
        logger.error(
            f"An unexpected error occurred while sending DM to {user_slack_id}: {e}"
        )
        return False
