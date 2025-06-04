from datetime import datetime, timedelta, timezone
from celery import shared_task
from celery.utils.log import get_task_logger
from flask import current_app, render_template
from models import User, Content
from extensions import db, redis_client
from flask_mail import Message
from extensions import mail
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = get_task_logger(__name__)


@shared_task(name="tasks.notifications.initiate_posts")
def initiate_posts():
    """
    Periodic task that runs three times per day to notify users about new content.
    Checks for content added since the last run and sends emails/Slack messages to users.
    """
    logger.info("Initiating posts task...")

    email_count = 0
    slack_count = 0
    final_status_message = "Task completed."

    try:
        last_run = redis_client.get("last_content_notification_run")
        if last_run:
            last_run = datetime.fromisoformat(last_run)
        else:
            last_run = datetime.now() - timedelta(hours=24)
        logger.debug(f"Checking for content since: {last_run}")

        new_content = Content.query.filter(Content.created_at > last_run).all()
        # new_content = Content.query.all() # this is just for testing
        logger.info(f"Found {len(new_content)} new content items.")

        if not new_content:
            final_status_message = "No new content to notify about."
        else:
            users = User.query.filter(User.linkedin_authorized == True).all()
            logger.info(f"Found {len(users)} users to notify.")

            if not users:
                final_status_message = (
                    "New content found, but no users with LinkedIn auth to notify."
                )
            else:
                content_summary = []
                for item in new_content:
                    promote_url = f"{current_app.config['BASE_URL']}/?promote={item.id}"
                    description = item.excerpt or (
                        item.scraped_content[:200] + "..."
                        if item.scraped_content
                        else ""
                    )
                    content_summary.append(
                        {
                            "id": item.id,
                            "title": item.title,
                            "url": item.url,
                            "description": description,
                            "image_url": item.image_url,
                            "promote_url": promote_url,
                        }
                    )

                for user in users:
                    try:
                        # Only send emails if EMAIL_ENABLED is True
                        if current_app.config.get("EMAIL_ENABLED", False):
                            # Prepare email content using the new template
                            # For the template context, ensure `now` and `company_name` are available if used in the template footer.
                            # `now` can be datetime.now(). `company_name` from current_app.config or a default.
                            email_html_content = render_template(
                                "email/new_content_notification.html",
                                user=user,
                                content_summary=content_summary,
                                now=datetime.now(),  # Pass current time for template
                                company_name=current_app.config.get(
                                    "COMPANY_NAME", "Your Company"
                                ),  # Pass company name
                            )

                            msg = Message(
                                subject="New Content Available to Share!",
                                sender=current_app.config["MAIL_DEFAULT_SENDER"],
                                recipients=[user.email],
                                html=email_html_content,  # Use rendered HTML
                            )
                            mail.send(msg)
                            email_count += 1
                            logger.debug(f"Email sent to {user.email} using template.")
                        else:
                            logger.info(
                                "Email sending is disabled (EMAIL_ENABLED is False)"
                            )
                    except Exception as e:
                        logger.error(
                            f"Failed to send email to {user.email}: {e}", exc_info=True
                        )

                if current_app.config.get("SLACK_NOTIFICATIONS_ENABLED"):
                    slack_token = current_app.config.get("SLACK_BOT_TOKEN")
                    default_channel_id = current_app.config.get(
                        "SLACK_DEFAULT_CHANNEL_ID"
                    )
                    if slack_token and default_channel_id:
                        try:
                            client = WebClient(token=slack_token)
                            MAX_ITEMS_PER_MESSAGE = 15  # Max items to include in a single Slack message to avoid block limits

                            # Calculate the number of chunks needed
                            num_chunks = (
                                len(content_summary) + MAX_ITEMS_PER_MESSAGE - 1
                            ) // MAX_ITEMS_PER_MESSAGE
                            if (
                                num_chunks == 0
                            ):  # Handle case with no content to prevent issues with range(0)
                                num_chunks = 1

                            for i in range(num_chunks):
                                start_index = i * MAX_ITEMS_PER_MESSAGE
                                end_index = start_index + MAX_ITEMS_PER_MESSAGE
                                chunk_content_summary = content_summary[
                                    start_index:end_index
                                ]

                                if (
                                    not chunk_content_summary
                                ):  # Skip if a chunk is empty (e.g. if content_summary was empty initially)
                                    if (
                                        len(content_summary) == 0 and i == 0
                                    ):  # Special handling for the no new content case, to avoid spamming logs for empty chunks if content_summary was empty to begin with
                                        pass  # will be handled by the general "No new content" message logic
                                    else:
                                        logger.info(
                                            f"Skipping empty chunk {i+1}/{num_chunks}."
                                        )
                                    continue

                                header_text = render_template(
                                    "slack/notification_header.txt",
                                    num_items=len(chunk_content_summary),
                                    company_name=current_app.config.get(
                                        "COMPANY_NAME", ""
                                    ),
                                    current_chunk=i + 1,
                                    total_chunks=num_chunks,
                                )

                                blocks = [
                                    {
                                        "type": "header",
                                        "text": {
                                            "type": "plain_text",
                                            "text": f"📢 New Content Ready for Promotion! {f'(Part {i+1}/{num_chunks})' if num_chunks > 1 else ''}",
                                            "emoji": True,
                                        },
                                    },
                                    {
                                        "type": "section",
                                        "text": {"type": "mrkdwn", "text": header_text},
                                    },
                                    {"type": "divider"},
                                ]

                                for item_summary in chunk_content_summary:
                                    item_text = render_template(
                                        "slack/notification_content_item.txt",
                                        item=item_summary,
                                    )
                                    blocks.extend(
                                        [
                                            {
                                                "type": "section",
                                                "text": {
                                                    "type": "mrkdwn",
                                                    "text": item_text,
                                                },
                                            },
                                            {
                                                "type": "actions",
                                                "elements": [
                                                    {
                                                        "type": "button",
                                                        "text": {
                                                            "type": "plain_text",
                                                            "text": "Promote This 🚀",
                                                            "emoji": True,
                                                        },
                                                        "url": item_summary[
                                                            "promote_url"
                                                        ],
                                                        "style": "primary",
                                                    }
                                                ],
                                            },
                                            {"type": "divider"},
                                        ]
                                    )
                                # Remove the last divider if it's the end of the message to save space, unless it's the only thing
                                if (
                                    blocks
                                    and blocks[-1]["type"] == "divider"
                                    and len(blocks) > 3
                                ):
                                    blocks.pop()

                                fallback_text = f"New content available to share! ({len(chunk_content_summary)} items{f' - Part {i+1}/{num_chunks}' if num_chunks > 1 else ''})"
                                client.chat_postMessage(
                                    channel=default_channel_id,
                                    text=fallback_text,  # Fallback for notifications
                                    blocks=blocks,
                                )
                                slack_count += 1
                                logger.info(
                                    f"Slack notification (Part {i+1}/{num_chunks}) sent to channel {default_channel_id} using templates."
                                )
                        except SlackApiError as e:
                            logger.error(
                                f"Slack API Error: {e.response['error']}", exc_info=True
                            )
                        except Exception as e:
                            logger.error(
                                f"Error sending Slack notification: {e}", exc_info=True
                            )
                    else:
                        logger.warning(
                            "Slack notifications enabled but token/channel_id not configured."
                        )

                final_status_message = f"Processed. Emails sent: {email_count}. Slack messages: {slack_count} (sent in {num_chunks if 'num_chunks' in locals() and num_chunks > 0 and len(content_summary) > 0 else (1 if len(content_summary) == 0 else 0)} part(s))."

        redis_client.set("last_content_notification_run", datetime.now().isoformat())
        logger.info("Updated last_content_notification_run.")

    except Exception as e:
        logger.error(f"Unhandled exception in initiate_posts: {e}", exc_info=True)
        final_status_message = f"Task failed with exception: {e}"
        raise  # Re-raise so Celery marks it as failed
    finally:
        logger.info(f"Initiate_posts task finished. Status: {final_status_message}")

    return final_status_message


@shared_task(name="tasks.notifications.send_one_off_content_notification")
def send_one_off_content_notification(content_id: int):
    """
    Sends a one-off Slack notification for a specific piece of content.
    Triggered by an admin from the dashboard.
    """
    logger.info(f"Starting one-off Slack notification for content_id: {content_id}")

    try:
        content = db.session.get(Content, content_id)
        if not content:
            logger.error(
                f"Content with ID {content_id} not found. Cannot send notification."
            )
            return "Content not found."

        if not current_app.config.get("SLACK_NOTIFICATIONS_ENABLED"):
            logger.warning(
                "Slack notifications are disabled. Skipping one-off notification."
            )
            return "Slack notifications disabled."

        slack_token = current_app.config.get("SLACK_BOT_TOKEN")
        default_channel_id = current_app.config.get("SLACK_DEFAULT_CHANNEL_ID")

        if not slack_token or not default_channel_id:
            logger.error(
                "Slack token or default channel ID is not configured. Cannot send notification."
            )
            return "Slack configuration missing."

        client = WebClient(token=slack_token)

        # Construct the promotion URL (assuming your app runs at BASE_URL)
        base_url = current_app.config.get("BASE_URL", "http://localhost:5001")
        promote_url = f"{base_url}/?promote={content.id}"
        content_url = content.url  # Direct URL of the content

        # Prepare excerpt (truncate if necessary, similar to initiate_posts)
        excerpt = content.excerpt or (
            content.scraped_content[:200] + "..."
            if content.scraped_content
            else "No excerpt available."
        )

        message_text = (
            f"📢 *Action Requested: Promote Content!*\n\n"
            f"An admin has requested that the following content be promoted by all users:\n\n"
            f"*<{content_url}|{content.title}>*\n"
            f"_{excerpt}_\n\n"
            f"Please consider sharing this content with your networks. Thank you!"
        )

        try:
            client.chat_postMessage(
                channel=default_channel_id,
                text=message_text,  # Text field is required, can be a fallback
                blocks=[
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": message_text},
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Promote This 🚀",
                                    "emoji": True,
                                },
                                "url": promote_url,
                                "style": "primary",
                            }
                        ],
                    },
                ],
            )
            logger.info(
                f"Successfully sent one-off Slack notification for content_id: {content_id} to channel {default_channel_id}."
            )
            return f"Notification sent for content ID {content_id}."
        except SlackApiError as e:
            logger.error(
                f"Slack API Error sending one-off notification for content_id {content_id}: {e.response['error']}",
                exc_info=True,
            )
            return f"Slack API error: {e.response['error']}."
        except Exception as e:
            logger.error(
                f"Error sending one-off Slack notification for content_id {content_id}: {e}",
                exc_info=True,
            )
            return f"Failed to send Slack message: {e}."

    except Exception as e:
        logger.error(
            f"Unhandled exception in send_one_off_content_notification for content_id {content_id}: {e}",
            exc_info=True,
        )
        # Do not re-raise, as this is a one-off notification. Log and return status.
        return f"Task failed with unhandled exception: {e}."
