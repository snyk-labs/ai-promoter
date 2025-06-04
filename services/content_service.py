import logging
from models.content import Content
from extensions import db
from tasks.content import scrape_content_task

logger = logging.getLogger(__name__)


class DuplicateContentError(ValueError):
    """Custom exception for duplicate content."""

    pass


def create_content_item(
    url: str,
    context: str | None,
    copy: str | None,
    utm_campaign: str | None,
    submitted_by_id: int,
):
    """
    Core logic to create a new content item and trigger async scraping.

    Args:
        url: The URL of the content.
        context: Optional context for the content.
        copy: Optional copy for the content.
        utm_campaign: Optional UTM campaign for the content.
        submitted_by_id: The ID of the user submitting the content.

    Returns:
        A tuple containing the created Content object and the Celery AsyncResult task object.

    Raises:
        DuplicateContentError: If the URL already exists.
        Exception: For other database or unexpected errors during content creation.
    """
    logger.info(
        f"Attempting to create content for URL: {url} by user_id: {submitted_by_id}"
    )

    existing_content = Content.query.filter_by(url=url).first()
    if existing_content:
        logger.warning(f"Attempt to create duplicate content for URL: {url}")
        raise DuplicateContentError("This URL has already been added as content.")

    try:
        content = Content(
            url=url,
            title="Processing...",  # Initial title
            context=context,
            copy=copy,
            utm_campaign=utm_campaign,
            submitted_by_id=submitted_by_id,
        )
        db.session.add(content)
        db.session.commit()
        logger.info(f"Content object created with ID: {content.id} for URL: {url}")

        task = scrape_content_task.delay(content.id, url)
        logger.info(f"Scraping task {task.id} initiated for content ID: {content.id}")

        return content, task
    except Exception as e:
        logger.exception(f"Error during content item creation for URL {url}: {e}")
        db.session.rollback()
        raise  # Re-raise the exception to be handled by the caller
