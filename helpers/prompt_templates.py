from flask import render_template
from datetime import datetime
from enum import Enum

# Import constants from openai module
from helpers.openai import (
    SocialPlatform,
    URL_CHAR_APPROX,
    TWITTER_CHAR_LIMIT,
    LINKEDIN_CHAR_LIMIT,
)


class ContentType(Enum):
    PODCAST = "podcast"
    VIDEO = "video"
    BLOG = "blog"


def get_platform_config(platform):
    """
    Get platform-specific configuration for social media posts.

    Args:
        platform: SocialPlatform enum value

    Returns:
        Dictionary with platform config values
    """
    if platform == SocialPlatform.TWITTER:
        return {
            "name": "Twitter",
            "char_limit": TWITTER_CHAR_LIMIT,
            "content_limit": TWITTER_CHAR_LIMIT - URL_CHAR_APPROX,
            "style": "Short, punchy, and attention-grabbing.",
        }
    elif platform == SocialPlatform.LINKEDIN:
        return {
            "name": "LinkedIn",
            "char_limit": LINKEDIN_CHAR_LIMIT,
            "content_limit": LINKEDIN_CHAR_LIMIT - URL_CHAR_APPROX,
            "style": "Professional, insightful, and value-focused.",
        }
    else:
        # Default/Generic platform settings
        return {
            "name": "social media",
            "char_limit": TWITTER_CHAR_LIMIT,  # Use Twitter as the default constraint
            "content_limit": TWITTER_CHAR_LIMIT - URL_CHAR_APPROX,
            "style": "Engaging, informative, and concise.",
        }


def format_time_context(publish_date):
    """
    Format a human-readable time description based on the publish date.

    Args:
        publish_date: Datetime object representing the publication date

    Returns:
        String with human-readable time context
    """
    now = datetime.utcnow()
    time_diff = now - publish_date
    days_ago = time_diff.days

    if days_ago == 0:
        return "just released today"
    elif days_ago == 1:
        return "released yesterday"
    elif days_ago < 7:
        return f"released {days_ago} days ago"
    elif days_ago < 14:
        return "released last week"
    elif days_ago < 30:
        return "released a few weeks ago"
    elif days_ago < 60:
        return "released last month"
    else:
        return f"from {publish_date.strftime('%B %Y')}"


def get_content_type_info(content_item):
    """
    Get content type information based on the item type.

    Args:
        content_item: The content object (Episode, Video, or Post)

    Returns:
        Tuple with (ContentType, content_type_name, url_field, content_description)
    """
    from models import Episode, Video, Post

    if isinstance(content_item, Episode):
        content_type = ContentType.PODCAST
        content_type_name = "podcast episode"
        url_field = content_item.player_url
        content_description = (
            f"Episode {content_item.episode_number}: {content_item.title}"
        )
    elif isinstance(content_item, Video):
        content_type = ContentType.VIDEO
        content_type_name = "YouTube video"
        url_field = content_item.url
        content_description = content_item.title
    elif isinstance(content_item, Post):
        content_type = ContentType.BLOG
        content_type_name = "blog post"
        url_field = content_item.url
        content_description = content_item.title
    else:
        # Default to podcast if unknown type
        content_type = ContentType.PODCAST
        content_type_name = "podcast episode"
        url_field = getattr(content_item, "url", "https://example.com")
        content_description = getattr(content_item, "title", "Unknown content")

    return content_type, content_type_name, url_field, content_description


def render_system_prompt(
    content_item, user, platform=SocialPlatform.GENERIC, retry_attempt=1, last_length=0
):
    """
    Render the system prompt for OpenAI using the appropriate template.

    Args:
        content_item: The content object (Episode, Video, or Post)
        user: The user object with profile info
        platform: The social platform to generate content for
        retry_attempt: The current attempt number (for retries)
        last_length: The length of the last generation attempt (for retries)

    Returns:
        Rendered system prompt string
    """
    platform_config = get_platform_config(platform)
    content_type, content_type_name, url_field, content_description = (
        get_content_type_info(content_item)
    )

    # Determine which template to use based on content type
    if content_type == ContentType.PODCAST:
        template = "prompts/podcast_system.html"
    elif content_type == ContentType.VIDEO:
        template = "prompts/video_system.html"
    elif content_type == ContentType.BLOG:
        template = "prompts/blog_system.html"
    else:
        template = "prompts/base_system.html"

    # Get blog author if available
    blog_author = (
        getattr(content_item, "author", "") if hasattr(content_item, "author") else ""
    )

    # Render the template with all required variables
    return render_template(
        template,
        content_type_name=content_type_name,
        platform_name=platform_config["name"],
        char_limit=platform_config["char_limit"],
        url_char_approx=URL_CHAR_APPROX,
        content_limit=platform_config["content_limit"],
        platform_style=platform_config["style"],
        retry_attempt=retry_attempt,
        last_length=last_length,
        blog_author=blog_author,
    )


def render_user_prompt(content_item, user, platform=SocialPlatform.GENERIC):
    """
    Render the user prompt for OpenAI using the appropriate template.

    Args:
        content_item: The content object (Episode, Video, or Post)
        user: The user object with profile info
        platform: The social platform to generate content for

    Returns:
        Rendered user prompt string
    """
    platform_config = get_platform_config(platform)
    content_type, content_type_name, url_field, content_description = (
        get_content_type_info(content_item)
    )

    # Format the time context
    time_context = format_time_context(content_item.publish_date)

    # Get description, using excerpt if available
    description = getattr(content_item, "description", "")
    if (
        content_type in [ContentType.VIDEO, ContentType.BLOG]
        and hasattr(content_item, "excerpt")
        and content_item.excerpt
    ):
        description = content_item.excerpt

    # Truncate description if too long
    if len(description) > 400:
        description = description[:397] + "..."

    # Get user information
    user_name = getattr(user, "name", "AI Promoter User")
    user_bio = getattr(user, "bio", "")
    if not user_bio or (isinstance(user_bio, str) and not user_bio.strip()):
        user_bio = "Security professional"

    # Get blog author if available
    blog_author = (
        getattr(content_item, "author", "") if hasattr(content_item, "author") else ""
    )

    # Choose the appropriate template based on content type
    if content_type == ContentType.PODCAST:
        template = "prompts/podcast_user.html"
    elif content_type == ContentType.VIDEO:
        template = "prompts/video_user.html"
    elif content_type == ContentType.BLOG:
        template = "prompts/blog_user.html"
    else:
        template = "prompts/base_user.html"

    # Convert platform enum to string for template
    platform_str = (
        platform.name.lower() if isinstance(platform, SocialPlatform) else "generic"
    )

    # Render the template with all required variables
    return render_template(
        template,
        platform_name=platform_config["name"],
        content_type_name=content_type_name,
        char_limit=platform_config["char_limit"],
        content_limit=platform_config["content_limit"],
        title=content_item.title,
        description=description,
        url=url_field,
        timing=time_context,
        user_name=user_name,
        user_bio=user_bio,
        platform=platform_str,
        blog_author=blog_author,
    )
