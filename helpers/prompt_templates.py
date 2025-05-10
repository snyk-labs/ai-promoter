from flask import render_template
from datetime import datetime

# Define character limits for different platforms
TWITTER_CHAR_LIMIT = 280
LINKEDIN_CHAR_LIMIT = 3000
URL_CHAR_APPROX = 30


def get_platform_config(platform):
    """
    Get platform-specific configuration for social media posts.

    Args:
        platform: String platform name ('twitter', 'linkedin', or 'generic')

    Returns:
        Dictionary with platform config values
    """
    configs = {
        'twitter': {
            "name": "Twitter",
            "max_length": TWITTER_CHAR_LIMIT,
            "max_tokens": 100
        },
        'linkedin': {
            "name": "LinkedIn",
            "max_length": LINKEDIN_CHAR_LIMIT,
            "max_tokens": 500
        },
        'generic': {
            "name": "Generic",
            "max_length": TWITTER_CHAR_LIMIT,
            "max_tokens": 300
        }
    }
    return configs.get(platform, configs['generic'])


def format_time_context(publish_date):
    """
    Format a human-readable time description based on the publish date.

    Args:
        publish_date: Datetime object representing the publication date

    Returns:
        String with human-readable time context
    """
    if not publish_date:
        return ""
    
    now = datetime.utcnow()
    diff = now - publish_date
    
    if diff.days == 0:
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
    Get content type information based on the item type.

    Args:
        content_item: The content object

    Returns:
        Tuple with (content_type, content_type_name, url_field, content_description)
    """
    content_type = content_item.content_type.lower()
    
    if content_type == 'podcast':
        content_type_name = "podcast episode"
        url_field = content_item.url
        content_description = content_item.title
    elif content_type == 'video':
        content_type_name = "YouTube video"
        url_field = content_item.url
        content_description = content_item.title
    elif content_type == 'article':
        content_type_name = "blog post"
        url_field = content_item.url
        content_description = content_item.title
    else:
        # Default to blog if unknown type
        content_type_name = "blog post"
        url_field = content_item.url
        content_description = content_item.title

    return content_type, content_type_name, url_field, content_description


def render_system_prompt(platform):
    """Render the system prompt for OpenAI."""
    platform_config = get_platform_config(platform)
    
    return f"""You are a social media content creator specializing in security and technology content.
Your task is to create engaging social media posts for {platform_config['name']}.
The post should be informative, engaging, and encourage clicks while staying within {platform_config['max_length']} characters.
Focus on the key value proposition and make it compelling for the target audience."""


def render_user_prompt(content_item, user, platform='generic'):
    """
    Render the user prompt for OpenAI using the appropriate template.

    Args:
        content_item: The content object
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
    description = content_item.excerpt if content_item.excerpt else ""

    # Truncate description if too long
    if len(description) > 400:
        description = description[:397] + "..."

    # Get user information
    user_name = getattr(user, "name", "AI Promoter User")
    user_bio = getattr(user, "bio", "")
    if not user_bio or (isinstance(user_bio, str) and not user_bio.strip()):
        user_bio = "Security professional"

    # Get blog author if available
    blog_author = content_item.author if content_item.author else ""

    # Choose the appropriate template based on content type
    if content_type == 'podcast':
        template = "prompts/podcast_user.html"
    elif content_type == 'video':
        template = "prompts/video_user.html"
    elif content_type == 'article':
        template = "prompts/blog_user.html"
    else:
        template = "prompts/base_user.html"

    return {
        "content_type": content_type_name,
        "content_description": content_description,
        "url": url_field,
        "description": description,
        "time_context": time_context,
        "user_name": user_name,
        "user_bio": user_bio,
        "blog_author": blog_author,
        "platform": platform
    }
