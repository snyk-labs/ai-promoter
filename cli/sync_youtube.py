import click
import feedparser
from datetime import datetime
from flask.cli import with_appcontext
from sqlalchemy.exc import IntegrityError
from bs4 import BeautifulSoup
import re
import urllib.parse

from extensions import db
from models import Video
from cli.utils import handle_autonomous_posting
from helpers.utils import extract_youtube_id


@click.command("sync-youtube")
@click.argument("rss_url")
@with_appcontext
def sync_youtube(rss_url):
    """Sync videos from a YouTube channel's RSS feed."""
    click.echo("Fetching videos from YouTube RSS feed...")

    feed = feedparser.parse(rss_url)

    if feed.bozo:  # Check if there was an error parsing the feed
        click.echo(f"Error parsing RSS feed: {feed.bozo_exception}")
        return

    new_videos = 0
    total_videos = len(feed.entries)
    newly_added_videos = []
    shorts_filtered = 0

    # Get channel info from feed if available
    channel_name = feed.feed.get("title", "").replace(" - YouTube", "")
    channel_id = ""

    for entry in feed.entries:
        # Get video ID from link or entry ID
        video_id = ""
        if "link" in entry:
            # Extract video ID from URL
            parsed_url = urllib.parse.urlparse(entry.link)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            video_id = query_params.get("v", [""])[0]

            # Check if this is a YouTube Short (shorts format URL)
            is_short = "/shorts/" in entry.link

        if not video_id and "yt_videoid" in entry:
            video_id = entry.yt_videoid

        if not video_id:
            # If still no video ID, try to extract from entry ID
            if "id" in entry:
                match = re.search(r"video:([a-zA-Z0-9_-]+)", entry.id)
                if match:
                    video_id = match.group(1)

        if not video_id:
            click.echo(
                f'Could not extract video ID for entry: {entry.get("title", "Unknown")}'
            )
            continue

        # Get the title
        title = entry.title

        # Get the description
        description = ""
        if "summary" in entry:
            description = entry.summary
        elif "media_description" in entry:
            description = entry.media_description

        if description:
            # Strip HTML tags if present
            soup = BeautifulSoup(description, "html.parser")
            full_description = soup.get_text().strip()

            # Create a shorter version for display
            excerpt = full_description
            if len(excerpt) > 250:
                excerpt = excerpt[:250].strip() + "..."
        else:
            full_description = ""
            excerpt = ""

        # Get video URL
        url = entry.get("link", f"https://www.youtube.com/watch?v={video_id}")

        # Get thumbnail URL
        thumbnail_url = ""
        if "media_thumbnail" in entry and len(entry.media_thumbnail) > 0:
            thumbnail_url = entry.media_thumbnail[0].get("url", "")

        # Get channel ID if not found earlier
        if (
            not channel_id
            and "author_detail" in entry
            and "href" in entry.author_detail
        ):
            channel_url = entry.author_detail.href
            channel_id_match = re.search(r"channel/([a-zA-Z0-9_-]+)", channel_url)
            if channel_id_match:
                channel_id = channel_id_match.group(1)

        # If still no channel name, try to get from author
        if not channel_name and "author" in entry:
            channel_name = entry.author

        # Convert published date to datetime
        try:
            publish_date = datetime(*entry.published_parsed[:6])
        except (AttributeError, TypeError):
            publish_date = datetime.utcnow()

        # Get duration if available
        duration = ""
        if "media_content" in entry and len(entry.media_content) > 0:
            duration = entry.media_content[0].get("duration", "")

        # Check for YouTube Shorts based on available criteria
        is_short = False

        # Primary method: Check if the URL explicitly contains "/shorts/"
        if "/shorts/" in url:
            is_short = True
            shorts_filtered += 1
            click.echo(f"Skipping YouTube Short (URL pattern detected): {title}")
            continue

        # Secondary method: Look for #shorts hashtag in title or description
        if "#shorts" in title.lower() or (
            full_description and "#shorts" in full_description.lower()
        ):
            is_short = True
            shorts_filtered += 1
            click.echo(f"Skipping YouTube Short (hashtag detected): {title}")
            continue

        # Tertiary method: Check duration (if available) and title patterns
        # This is less reliable, so we add additional checks
        if duration and duration.isdigit() and int(duration) <= 60:
            # Common Short title patterns
            short_title_patterns = [
                "short",
                "#short",
                "#ytshort",
                "#ytshorts",
                "vertical",
                "tiktok",
                "reel",
                "trending",
            ]

            if any(pattern in title.lower() for pattern in short_title_patterns):
                is_short = True
                shorts_filtered += 1
                click.echo(
                    f"Skipping YouTube Short (duration + title pattern detected): {title}"
                )
                continue

        # Create video object
        video = Video(
            video_id=video_id,
            title=title,
            description=full_description,  # Store full description
            excerpt=excerpt,  # Store shorter version for display
            thumbnail_url=thumbnail_url,
            url=url,
            channel_name=channel_name,
            channel_id=channel_id,
            publish_date=publish_date,
            duration=duration,
        )

        # Check if video already exists
        existing_video = Video.query.filter_by(video_id=video_id).first()

        if existing_video:
            continue

        try:
            db.session.add(video)
            db.session.commit()
            new_videos += 1
            newly_added_videos.append(video)
            click.echo(f"Added video: {title}")
        except IntegrityError:
            db.session.rollback()
            click.echo(f'Error saving video "{title}", skipping...')

    click.echo(f"Successfully added {new_videos} new videos to the database.")
    if shorts_filtered > 0:
        click.echo(f"Filtered out {shorts_filtered} YouTube Shorts.")

    # Handle autonomous posting for each new video
    if newly_added_videos:
        click.echo("\nProcessing autonomous posting for new videos...")
        for video in newly_added_videos:
            click.echo(f"Processing autonomous posting for video: {video.title}")
            handle_autonomous_posting(video)
