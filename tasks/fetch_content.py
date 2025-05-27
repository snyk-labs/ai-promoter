import requests
import feedparser
import logging
from celery import shared_task, chain
from flask import current_app
from models import Content, User  # Assuming User might be needed for submitted_by_id
from extensions import db
from tasks.content import scrape_content_task  # Import the existing scrape task

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="tasks.fetch_content.fetch_content_task")
def fetch_content_task(self):
    """
    Fetches content from RSS feeds defined in CONTENT_FEEDS,
    parses them, and initiates scraping for new content items.
    """
    content_feeds = current_app.config.get("CONTENT_FEEDS")
    if not content_feeds:
        logger.info("No content feeds configured. Skipping fetch content task.")
        return "No content feeds configured."

    processed_feed_urls = set()
    new_content_count = 0

    for feed_url in content_feeds:
        if not feed_url or feed_url in processed_feed_urls:
            continue
        processed_feed_urls.add(feed_url)

        logger.info(f"Fetching content from feed: {feed_url}")
        try:
            response = requests.get(feed_url, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch RSS feed {feed_url}: {e}")
            continue

        feed = feedparser.parse(response.content)

        if feed.bozo:
            logger.warning(
                f"Feed {feed_url} may be malformed. Bozo bit set: {feed.bozo_exception}"
            )
            # Continue processing despite potential malformation

        for entry in feed.entries:
            entry_url = entry.get("link")
            if not entry_url:
                logger.warning(
                    f"No URL found for an entry in {feed_url}. Entry title: {entry.get('title')}"
                )
                continue

            # Check if content with this URL already exists
            existing_content = Content.query.filter_by(url=entry_url).first()
            if existing_content:
                logger.debug(f"Content with URL {entry_url} already exists. Skipping.")
                continue

            # If URL doesn't exist, create a preliminary Content item
            # and then chain the scrape_content_task.
            # The admin UI flow creates a content item first, then scrapes.
            # We mimic that here.

            # Determine a sensible title, fallback to URL if not found
            entry_title = entry.get("title", entry_url)
            if (
                len(entry_title) > 250
            ):  # Assuming a max length for title, adjust if necessary
                entry_title = entry_title[:247] + "..."

            logger.info(
                f"New content found: '{entry_title}' from {entry_url}. Initiating scrape."
            )
            try:
                # Create a new content item with a placeholder title
                # The scrape_content_task will update title, excerpt, etc.
                new_content = Content(
                    url=entry_url,
                    title="Processing: " + entry_title,  # Placeholder title
                    # submitted_by_id could be set to a system user ID if you have one, or None
                    # For now, let's leave it as None or find a generic system user.
                    # submitted_by_id = get_system_user_id(), # Placeholder
                )
                db.session.add(new_content)
                db.session.commit()  # Commit to get an ID for the new_content item

                # Initiate the scrape_content_task.
                # The .get() will make this task wait for scrape_content_task to complete.
                scrape_task_result = scrape_content_task.delay(
                    content_id=new_content.id, url=entry_url
                )

                # Wait for the task to complete.
                # This mimics the "wait for it to finish" requirement.
                # Adding a timeout to prevent indefinite blocking.
                # try:
                #     scrape_task_result.get(timeout=3500) # Slightly less than Celery task_time_limit
                #     logger.info(f"Scraping finished for {entry_url} (Content ID: {new_content.id}).")
                #     new_content_count += 1
                # except Exception as e:
                #     logger.error(f"Waiting for scrape_content_task for {entry_url} (Content ID: {new_content.id}) failed or timed out: {e}")
                #     # Optionally, you might want to clean up the placeholder content item or mark it as failed.
                #     # For now, we log the error. The content item will remain with "Processing..." title.

                # Log that the task has been dispatched. The actual scraping will happen asynchronously.
                logger.info(
                    f"Dispatched scrape_content_task for {entry_url} (Content ID: {new_content.id})."
                )
                new_content_count += 1

            except Exception as e:
                db.session.rollback()
                logger.error(
                    f"Error creating initial content item for {entry_url} or dispatching scrape task: {e}"
                )
                continue

    return f"Fetched and processed {len(feed.entries) if 'feed' in locals() and feed.entries else 0} entries from {feed_url}. Initiated scraping for {new_content_count} new items."


# Optional: Helper to get a system user ID if you have one.
# def get_system_user_id():
#     # Implement logic to find or create a system user
#     # For example:
#     # system_user = User.query.filter_by(email="system@example.com").first()
#     # if system_user:
#     #     return system_user.id
#     return None
