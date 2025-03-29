from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from models import Episode, Post, Video
from helpers.openai import (
    generate_social_post,
    validate_post_length,
    TWITTER_CHAR_LIMIT,
    LINKEDIN_CHAR_LIMIT,
    SocialPlatform,
)

# Create a blueprint for API routes
bp = Blueprint("api", __name__, url_prefix="/api")


@bp.route("/promote/podcast/<int:episode_id>", methods=["POST"])
@login_required
def promote_podcast(episode_id):
    """API endpoint for podcast promotion."""
    episode = Episode.query.get_or_404(episode_id)

    try:
        # Generate post with retry logic for character limit validation
        social_post = generate_social_post(episode, current_user, max_retries=3)

        # Validate length for different platforms
        is_valid_for_twitter, is_valid_for_linkedin, total_length = (
            validate_post_length(social_post)
        )

        # Prepare warnings if needed
        warnings = []
        # Improved bio check: Only warn if bio is None, empty string, or just whitespace
        if not current_user.bio or (
            isinstance(current_user.bio, str) and not current_user.bio.strip()
        ):
            warnings.append(
                "Adding information about yourself in your profile will help generate better posts!"
            )

        if not is_valid_for_twitter:
            warnings.append(
                f"Post exceeds Twitter character limit ({total_length}/{TWITTER_CHAR_LIMIT} characters)"
            )

        if not is_valid_for_linkedin:
            warnings.append(
                f"Post exceeds LinkedIn character limit ({total_length}/{LINKEDIN_CHAR_LIMIT} characters)"
            )

        return jsonify(
            {
                "success": True,
                "post": social_post,
                "character_count": total_length,
                "twitter_limit": TWITTER_CHAR_LIMIT,
                "linkedin_limit": LINKEDIN_CHAR_LIMIT,
                "warnings": warnings if warnings else None,
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/promote/video/<int:video_id>", methods=["POST"])
@login_required
def promote_video(video_id):
    """API endpoint for video promotion."""
    video = Video.query.get_or_404(video_id)

    try:
        # Generate post with retry logic for character limit validation
        social_post = generate_social_post(video, current_user, max_retries=3)

        # Validate length for different platforms
        is_valid_for_twitter, is_valid_for_linkedin, total_length = (
            validate_post_length(social_post)
        )

        # Prepare warnings if needed
        warnings = []
        # Improved bio check: Only warn if bio is None, empty string, or just whitespace
        if not current_user.bio or (
            isinstance(current_user.bio, str) and not current_user.bio.strip()
        ):
            warnings.append(
                "Adding information about yourself in your profile will help generate better posts!"
            )

        if not is_valid_for_twitter:
            warnings.append(
                f"Post exceeds Twitter character limit ({total_length}/{TWITTER_CHAR_LIMIT} characters)"
            )

        if not is_valid_for_linkedin:
            warnings.append(
                f"Post exceeds LinkedIn character limit ({total_length}/{LINKEDIN_CHAR_LIMIT} characters)"
            )

        return jsonify(
            {
                "success": True,
                "post": social_post,
                "character_count": total_length,
                "twitter_limit": TWITTER_CHAR_LIMIT,
                "linkedin_limit": LINKEDIN_CHAR_LIMIT,
                "warnings": warnings if warnings else None,
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/promote/blog/<int:post_id>", methods=["POST"])
@login_required
def promote_blog_post(post_id):
    """API endpoint for blog post promotion."""
    blog_post = Post.query.get_or_404(post_id)

    try:
        # Generate post with retry logic for character limit validation
        social_post = generate_social_post(blog_post, current_user, max_retries=3)

        # Validate length for different platforms
        is_valid_for_twitter, is_valid_for_linkedin, total_length = (
            validate_post_length(social_post)
        )

        # Prepare warnings if needed
        warnings = []
        # Improved bio check: Only warn if bio is None, empty string, or just whitespace
        if not current_user.bio or (
            isinstance(current_user.bio, str) and not current_user.bio.strip()
        ):
            warnings.append(
                "Adding information about yourself in your profile will help generate better posts!"
            )

        if not is_valid_for_twitter:
            warnings.append(
                f"Post exceeds Twitter character limit ({total_length}/{TWITTER_CHAR_LIMIT} characters)"
            )

        if not is_valid_for_linkedin:
            warnings.append(
                f"Post exceeds LinkedIn character limit ({total_length}/{LINKEDIN_CHAR_LIMIT} characters)"
            )

        return jsonify(
            {
                "success": True,
                "post": social_post,
                "character_count": total_length,
                "twitter_limit": TWITTER_CHAR_LIMIT,
                "linkedin_limit": LINKEDIN_CHAR_LIMIT,
                "warnings": warnings if warnings else None,
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/content", methods=["GET"])
def get_paginated_content():
    """API endpoint for fetching paginated content."""
    # Get pagination parameters
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 100, type=int)

    # Limit per_page to reasonable values
    per_page = min(max(per_page, 10), 100)

    # Calculate offset
    offset = (page - 1) * per_page

    # Get episodes, posts, and videos with pagination
    episodes = (
        Episode.query.order_by(Episode.publish_date.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )
    posts = (
        Post.query.order_by(Post.publish_date.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )
    videos = (
        Video.query.order_by(Video.publish_date.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )

    # Get total count to determine if there are more items
    total_episodes = Episode.query.count()
    total_posts = Post.query.count()
    total_videos = Video.query.count()
    total_count = total_episodes + total_posts + total_videos

    # Combine all content into a single list
    content_items = []

    # Add episodes with a content_type indicator
    for episode in episodes:
        content_items.append(
            {
                "id": episode.id,
                "content_type": "podcast",
                "title": f"Episode {episode.episode_number}: {episode.title}",
                "description": episode.description,
                "image_url": episode.image_url,
                "publish_date": episode.publish_date.strftime("%b %d, %Y"),
                "url": episode.player_url,
                "episode_number": episode.episode_number,
            }
        )

    # Add posts with a content_type indicator
    for post in posts:
        content_items.append(
            {
                "id": post.id,
                "content_type": "blog",
                "title": post.title,
                "description": post.excerpt,
                "image_url": post.image_url,
                "publish_date": post.publish_date.strftime("%b %d, %Y"),
                "url": post.url,
                "author": post.author,
            }
        )

    # Add videos with a content_type indicator
    for video in videos:
        content_items.append(
            {
                "id": video.id,
                "content_type": "video",
                "title": video.title,
                "description": video.excerpt if video.excerpt else video.description,
                "image_url": video.thumbnail_url,
                "publish_date": video.publish_date.strftime("%b %d, %Y"),
                "url": video.url,
            }
        )

    # Sort all content by publish date (most recent first)
    # We use a custom key function that parses the date string
    from datetime import datetime

    content_items.sort(
        key=lambda x: datetime.strptime(x["publish_date"], "%b %d, %Y"), reverse=True
    )

    # Calculate if there are more items to load
    has_more = total_count > offset + per_page

    return jsonify(
        {
            "items": content_items,
            "page": page,
            "per_page": per_page,
            "has_more": has_more,
            "total_count": total_count,
        }
    )
