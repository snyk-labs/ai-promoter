from celery import shared_task  # Import shared_task
from services.content_processor import ContentProcessor
from models.content import Content
from extensions import db

# from flask import current_app # current_app should be available due to FlaskTask
import logging

# Import for Slack DM, will be used inside the task
# from services.slack_service import send_slack_dm # Delayed import to avoid circularity

logger = logging.getLogger(__name__)


# Decorate with our app instance to use FlaskTask
@shared_task(bind=True, ignore_result=False, max_retries=5, default_retry_delay=60)
def scrape_content_task(
    self, content_id: int, url: str, slack_user_id: str | None = None
):
    """
    Scrape content from a URL and update the Content record with scraped data.
    Notifies the Slack user via DM upon completion or final failure if slack_user_id is provided.
    Uses exponential backoff for retries.

    Args:
        content_id: The ID of the Content record to update
        url: The URL of the content to scrape
        slack_user_id: Optional Slack ID of the user who initiated the request.
    """
    # Moved import here to avoid potential circular dependencies
    from services.slack_service import send_slack_dm

    try:
        # ContentProcessor will fetch the content item by ID
        processor = ContentProcessor()

        logger.info(
            f"Processing URL for content_id {content_id}: {url}. Slack user: {slack_user_id}"
        )

        # process_url now takes content_id and url, and handles the update internally
        updated_content = processor.process_url(content_id=content_id, url=url)

        if not updated_content:
            # This will be caught by the generic exception handler below and retried.
            # Ensure process_url raises an exception on failure for retry logic to work.
            raise Exception(
                f"Failed to process content from URL {url} for content_id {content_id} (processor returned None)"
            )

        logger.info(
            f"Successfully processed and updated content {content_id} from URL {url}"
        )

        if slack_user_id and updated_content:
            try:
                # Fetch the latest content title as it might have been updated from "Processing..."
                content_item = db.session.get(Content, content_id)
                title = content_item.title if content_item else url
                message = f"✅ Great news! The content you submitted for <{url}|{title}> has been successfully processed and is now ready.\nContent ID: {content_id}"
                send_slack_dm(slack_user_id, message)
                logger.info(
                    f"Sent success DM to Slack user {slack_user_id} for content {content_id}"
                )
            except Exception as dm_exc:
                logger.error(
                    f"Failed to send success DM to Slack user {slack_user_id} for content {content_id}: {dm_exc}"
                )
        return content_id

    except Exception as e:
        logger.error(
            f"Error scraping content_id {content_id} (URL: {url}): {str(e)}. Retry {self.request.retries + 1}/{self.max_retries}."
        )

        is_last_retry = self.request.retries + 1 >= self.max_retries

        if slack_user_id and is_last_retry:
            try:
                message = f"⚠️ Apologies, but we encountered an issue while processing the content from <{url}|{url}> after multiple retries. Please try submitting it again later or contact an administrator if the problem persists.\nError: {str(e)}"
                send_slack_dm(slack_user_id, message)
                logger.info(
                    f"Sent failure DM to Slack user {slack_user_id} for content {content_id} after max retries."
                )
            except Exception as dm_exc:
                logger.error(
                    f"Failed to send failure DM to Slack user {slack_user_id} for content {content_id}: {dm_exc}"
                )

        retry_delay = self.default_retry_delay * (2**self.request.retries)
        raise self.retry(exc=e, countdown=retry_delay)
