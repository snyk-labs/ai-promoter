from celery import shared_task  # Import shared_task
from services.content_processor import ContentProcessor
from models.content import Content
from extensions import db

# from flask import current_app # current_app should be available due to FlaskTask
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


# Decorate with our app instance to use FlaskTask
@shared_task(bind=True, ignore_result=False, max_retries=5, default_retry_delay=60)
def scrape_content_task(self, content_id: int, url: str):
    """
    Scrape content from a URL and update the Content record with scraped data.
    Uses exponential backoff for retries.

    Args:
        content_id: The ID of the Content record to update
        url: The URL of the content to scrape
    """
    try:
        # ContentProcessor will fetch the content item by ID
        processor = ContentProcessor()

        logger.info(f"Processing URL for content_id {content_id}: {url}")

        # process_url now takes content_id and url, and handles the update internally
        updated_content = processor.process_url(content_id=content_id, url=url)

        if not updated_content:
            # This will be caught by the generic exception handler below and retried.
            # Ensure process_url raises an exception on failure for retry logic to work.
            raise Exception(
                f"Failed to process content from URL {url} for content_id {content_id}"
            )

        logger.info(
            f"Successfully processed and updated content {content_id} from URL {url}"
        )
        return content_id

    except Exception as e:
        logger.error(
            f"Error scraping content_id {content_id} (URL: {url}): {str(e)}. Retry {self.request.retries + 1}/{self.max_retries}."
        )
        retry_delay = self.default_retry_delay * (2**self.request.retries)
        raise self.retry(exc=e, countdown=retry_delay)
