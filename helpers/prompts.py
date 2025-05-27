from flask import render_template, current_app
from datetime import datetime
from markupsafe import Markup

# Define character limits for different platforms
LINKEDIN_CHAR_LIMIT = 3000
URL_CHAR_APPROX = 30


def get_platform_config(platform):
    """
    Get platform-specific configuration for social media posts.

    Args:
        platform: String platform name ('linkedin' or 'generic')

    Returns:
        Dictionary with platform config values
    """
    configs = {
        "linkedin": {
            "name": "LinkedIn",
            "max_length": LINKEDIN_CHAR_LIMIT,
            "max_tokens": 700,
            "url_char_approx": URL_CHAR_APPROX,
            "style": "Professional and informative, focusing on value and insights",
        },
        "generic": {
            "name": "Generic Platform",
            "max_length": LINKEDIN_CHAR_LIMIT,
            "max_tokens": 700,
            "url_char_approx": URL_CHAR_APPROX,
            "style": "Engaging and informative, focusing on key value propositions",
        },
    }
    return configs.get(platform, configs["generic"])


def format_time_context(publish_date):
    """
    Format a human-readable time description based on the publish date.
    Handles cases where publish_date might be None.
    """
    if not publish_date:
        return "recently"

    now = datetime.utcnow()

    diff = now - publish_date

    if diff.days < 0:
        return "upcoming"
    elif diff.days == 0:
        return "today"
    elif diff.days == 1:
        return "yesterday"
    elif diff.days < 7:
        return f"{diff.days} days ago"
    elif diff.days < 30:
        weeks = diff.days // 7
        return f"{weeks} {'week' if weeks == 1 else 'weeks'} ago"
    elif diff.days < 365:
        months = diff.days // 30
        return f"{months} {'month' if months == 1 else 'months'} ago"
    else:
        years = diff.days // 365
        return f"{years} {'year' if years == 1 else 'years'} ago"


def get_content_type_info(content_item):
    """
    Get generic content type information for the unified Content model.
    The original distinction by 'podcast', 'video', 'article' is no longer
    derived from a 'content_type' field on the model.

    Args:
        content_item: The Content object.

    Returns:
        Tuple with (content_type_string, content_type_name, url_field, content_description)
    """
    content_type_string = "content"
    content_type_name = "Content Item"

    url_field = content_item.url
    content_description = content_item.title

    return content_type_string, content_type_name, url_field, content_description


def render_system_prompt(platform, retry_attempt=0, last_length=0):
    """Render the system prompt for OpenAI."""
    platform_config = get_platform_config(platform)

    return render_template(
        "prompts/base_system.html",
        platform=platform,
        platform_config=platform_config,
        retry_attempt=retry_attempt,
        last_length=last_length,
    )


def render_user_prompt(content_item, user, platform="linkedin"):
    """
    Render the user prompt for OpenAI using the appropriate template.

    Args:
        content_item: The Content object.
        user: The User object with profile info.
        platform: The social platform to generate content for.

    Returns:
        Rendered user prompt string.
    """
    platform_config = get_platform_config(platform)

    _, _, _, content_title_for_template = get_content_type_info(content_item)
    content_type_for_template, _, _, _ = get_content_type_info(content_item)

    time_context = format_time_context(content_item.publish_date)
    description = content_item.excerpt if content_item.excerpt else ""
    if len(description) > 400:
        description = description[:397] + "..."

    # Get scraped content, limiting its length if necessary
    scraped_content = (
        content_item.scraped_content if content_item.scraped_content else ""
    )
    if (
        len(scraped_content) > 2000
    ):  # Limit to 2000 chars to avoid overwhelming the context
        scraped_content = scraped_content[:1997] + "..."

    user_name = getattr(user, "name", "AI Promoter User")
    user_bio = getattr(user, "bio", "")
    if not user_bio or (isinstance(user_bio, str) and not user_bio.strip()):
        user_bio = "Security professional"

    # Get user's example social posts
    user_example_posts = getattr(user, "example_social_posts", "")

    # Get the URL with all UTMs applied directly from the content_item
    url_with_utms = content_item.get_url_with_all_utms()

    # Create a Markup object to prevent HTML escaping for the URL
    url_with_utms_safe = Markup(url_with_utms)

    return render_template(
        "prompts/base_user.html",
        content_description=content_title_for_template,
        url=url_with_utms_safe,  # URL is now marked as safe via Markup
        description=description,
        time_context=time_context,
        user_name=user_name,
        user_bio=user_bio,
        user_example_posts=user_example_posts,
        platform=platform,
        platform_config=platform_config,
        content_type=content_type_for_template,
        scraped_content=scraped_content,
    )
