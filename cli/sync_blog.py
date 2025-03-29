import click
import feedparser
from datetime import datetime
from flask.cli import with_appcontext
from sqlalchemy.exc import IntegrityError
from bs4 import BeautifulSoup
import re

from extensions import db
from models import Post
from cli.utils import handle_autonomous_posting
from helpers.utils import clean_html, parse_date, normalize_url, truncate_text


@click.command("sync-blog")
@click.argument("rss_url")
@with_appcontext
def sync_blog(rss_url):
    """Sync blog posts from the RSS feed."""
    click.echo("Fetching blog posts from RSS feed...")

    feed = feedparser.parse(rss_url)

    if feed.bozo:  # Check if there was an error parsing the feed
        click.echo(f"Error parsing RSS feed: {feed.bozo_exception}")
        return

    new_posts = 0
    total_posts = len(feed.entries)
    newly_added_posts = []

    # Get blog image from feed if available (used as a fallback)
    blog_image_url = None
    if (
        hasattr(feed, "feed")
        and hasattr(feed.feed, "image")
        and hasattr(feed.feed.image, "href")
    ):
        blog_image_url = feed.feed.image.href

    for entry in feed.entries:
        # Get the title
        title = entry.title

        # Get the link/URL
        url = entry.get("link", "")

        # Get the content - clean up HTML if present
        content = ""
        content_html = ""
        if "content" in entry:
            if isinstance(entry.content, list) and len(entry.content) > 0:
                content_html = entry.content[0].value
                content = entry.content[0].value
            else:
                content_html = entry.content
                content = entry.content
        elif "summary" in entry:
            content_html = entry.summary
            content = entry.summary
        elif "description" in entry:
            content_html = entry.description
            content = entry.description

        # Clean HTML and extract text
        content = clean_html(content)

        # Create an excerpt (shorter version for display)
        excerpt = truncate_text(content, 200)

        # Get author
        author = entry.get("author", "")

        # Try to get full author name if it exists as a complex object
        if not author and "author_detail" in entry and "name" in entry.author_detail:
            author = entry.author_detail.name

        # Get publish date
        publish_date = datetime.utcnow()  # Default to now if no date found

        # Try multiple date fields that might be present in different RSS formats
        date_fields = ["published", "pubDate", "updated", "created", "date"]

        for field in date_fields:
            if field in entry:
                try:
                    # Try to use feedparser's parsed date
                    parsed_field = f"{field}_parsed"
                    if parsed_field in entry and entry[parsed_field]:
                        publish_date = datetime(*entry[parsed_field][:6])
                        break

                    # Fall back to string parsing
                    date_str = entry[field]
                    parsed_date = parse_date(date_str)
                    if parsed_date:
                        publish_date = parsed_date
                        break
                except:
                    continue

        # Get image URL from various possible locations
        image_url = None

        # Check for featured image
        if "media_content" in entry:
            for media in entry.media_content:
                if media.get("medium") == "image" or media.get("type", "").startswith(
                    "image/"
                ):
                    image_url = media.get("url")
                    break

        # Check for media:thumbnail
        if (
            not image_url
            and "media_thumbnail" in entry
            and len(entry.media_thumbnail) > 0
        ):
            image_url = entry.media_thumbnail[0].get("url", "")

        # Check for itunes:image
        if (
            not image_url
            and hasattr(entry, "itunes_image")
            and hasattr(entry.itunes_image, "href")
        ):
            image_url = entry.itunes_image.href

        # Check for standard image tag inside content
        if not image_url and content_html:
            soup = BeautifulSoup(content_html, "html.parser")
            img_tag = soup.find("img")
            if img_tag and img_tag.get("src"):
                image_url = img_tag.get("src")

        # Normalize image URL if found
        if image_url:
            image_url = normalize_url(image_url, url)
        elif blog_image_url:
            # Fallback to feed image
            image_url = blog_image_url

        # Determine source from feed title or URL
        source = None
        if hasattr(feed, "feed") and hasattr(feed.feed, "title"):
            source = feed.feed.title
        else:
            # Extract domain from URL as a fallback source name
            match = re.search(r"https?://(?:www\.)?([^/]+)", rss_url)
            if match:
                source = match.group(1)

        # Create post object
        post = Post(
            title=title,
            content=content,
            excerpt=excerpt,
            url=url,
            image_url=image_url,
            author=author,
            publish_date=publish_date,
            source=source,
        )

        # Check if post already exists
        existing_post = Post.query.filter_by(url=url).first()

        if existing_post:
            continue

        try:
            db.session.add(post)
            db.session.commit()
            new_posts += 1
            newly_added_posts.append(post)
            click.echo(f"Added post: {title}")
        except IntegrityError:
            db.session.rollback()
            click.echo(f'Error saving post "{title}", skipping...')

    click.echo(f"Successfully added {new_posts} new posts to the database.")

    # Handle autonomous posting for each new post
    if newly_added_posts:
        click.echo("\nProcessing autonomous posting for new blog posts...")
        for post in newly_added_posts:
            click.echo(f"Processing autonomous posting for blog post: {post.title}")
            handle_autonomous_posting(post)
