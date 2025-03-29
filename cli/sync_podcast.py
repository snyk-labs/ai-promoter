import click
import feedparser
from datetime import datetime
from flask.cli import with_appcontext
from sqlalchemy.exc import IntegrityError
from bs4 import BeautifulSoup

from extensions import db
from models import Episode
from cli.utils import handle_autonomous_posting


@click.command("sync-podcast")
@click.argument("rss_url")
@with_appcontext
def sync_podcast(rss_url):
    """Sync podcast episodes from the RSS feed."""
    click.echo("Fetching podcast episodes from RSS feed...")

    feed = feedparser.parse(rss_url)

    if feed.bozo:  # Check if there was an error parsing the feed
        click.echo(f"Error parsing RSS feed: {feed.bozo_exception}")
        return

    new_episodes = 0
    total_episodes = len(feed.entries)
    newly_added_episodes = []

    # Get podcast image from feed if available (used as a fallback)
    podcast_image_url = None
    if (
        hasattr(feed, "feed")
        and hasattr(feed.feed, "image")
        and hasattr(feed.feed.image, "href")
    ):
        podcast_image_url = feed.feed.image.href

    for index, entry in enumerate(feed.entries):
        # Use the episode number from the feed if available, otherwise use reverse index
        episode_number = total_episodes - index

        # Get the title
        title = entry.title

        # Get the description - clean up HTML if present
        description = entry.get("summary", "")
        if description:
            # Remove HTML tags if present
            soup = BeautifulSoup(description, "html.parser")
            description = soup.get_text()

        # Convert published date to datetime
        try:
            publish_date = datetime(*entry.published_parsed[:6])
        except (AttributeError, TypeError):
            publish_date = datetime.utcnow()

        # Get the episode URL
        player_url = entry.get("link", "")

        # Get episode image URL - try multiple possible locations in RSS feed
        image_url = None

        # Check for itunes:image
        if "image" in entry and hasattr(entry.image, "href"):
            image_url = entry.image.href
        elif hasattr(entry, "itunes_image") and hasattr(entry.itunes_image, "href"):
            image_url = entry.itunes_image.href
        # Check for media:thumbnail
        elif "media_thumbnail" in entry and len(entry.media_thumbnail) > 0:
            image_url = entry.media_thumbnail[0].get("url", "")
        # Check for media:content
        elif "media_content" in entry and len(entry.media_content) > 0:
            for content in entry.media_content:
                if content.get("type", "").startswith("image/"):
                    image_url = content.get("url", "")
                    break
        # Use podcast-level image as fallback
        elif podcast_image_url:
            image_url = podcast_image_url

        # Create episode object
        episode = Episode(
            episode_number=episode_number,
            title=title,
            description=description,
            player_url=player_url,
            image_url=image_url,
            publish_date=publish_date,
        )

        # Check if episode already exists
        existing_episode = Episode.query.filter_by(
            title=title,  # Check by title instead of episode number
            publish_date=publish_date,  # And publish date for uniqueness
        ).first()

        if existing_episode:
            continue

        try:
            db.session.add(episode)
            db.session.commit()
            new_episodes += 1
            newly_added_episodes.append(episode)
            click.echo(f"Added episode: {title}")
        except IntegrityError:
            db.session.rollback()
            click.echo(f'Error saving episode "{title}", skipping...')

    click.echo(f"Successfully added {new_episodes} new episodes to the database.")

    # Handle autonomous posting for each new episode
    if newly_added_episodes:
        click.echo("\nProcessing autonomous posting for new episodes...")
        for episode in newly_added_episodes:
            click.echo(f"Processing autonomous posting for episode: {episode.title}")
            handle_autonomous_posting(episode)
