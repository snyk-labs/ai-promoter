from flask import Blueprint, render_template
from flask_login import current_user
from models import Episode, Post, Video, ManualContent

# Create a blueprint for main routes
bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    """Main index page that shows all content sorted by publish date."""
    # Get all episodes, posts, and videos ordered by publish date (most recent first)
    # Limit to 100 items total for the initial load
    episodes = Episode.query.order_by(Episode.publish_date.desc()).all()
    posts = Post.query.order_by(Post.publish_date.desc()).all()
    videos = Video.query.order_by(Video.publish_date.desc()).all()
    manual_content = ManualContent.query.filter_by(is_active=True).order_by(ManualContent.created_at.desc()).all()

    # Combine all content into a single list
    content_items = []

    # Add episodes with a content_type indicator
    for episode in episodes:
        content_items.append({"item": episode, "content_type": "podcast"})

    # Add posts with a content_type indicator
    for post in posts:
        content_items.append({"item": post, "content_type": "blog"})

    # Add videos with a content_type indicator
    for video in videos:
        content_items.append({"item": video, "content_type": "video"})

    # Add manual content with a content_type indicator
    for content in manual_content:
        content_items.append({"item": content, "content_type": content.content_type})

    # Sort all content by publish date (most recent first)
    content_items.sort(key=lambda x: x["item"].publish_date if hasattr(x["item"], "publish_date") else x["item"].created_at, reverse=True)

    # Get total count of items to determine if there are more than 100
    total_count = len(content_items)

    return render_template(
        "index.html", content_items=content_items, total_count=total_count
    )
