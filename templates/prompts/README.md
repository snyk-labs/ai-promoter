# AI Prompt Templates

This directory contains Jinja2 templates used for AI prompt generation. The templates make it easier to maintain, update, and extend the prompts used for generating social media posts with OpenAI.

## Structure

```
prompts/
├── base_system.html         # Base template for system prompts
├── base_user.html           # Base template for user prompts
├── podcast_system.html      # Podcast-specific system prompt
├── podcast_user.html        # Podcast-specific user prompt
├── video_system.html        # Video-specific system prompt
├── video_user.html          # Video-specific user prompt
├── blog_system.html         # Blog-specific system prompt
├── blog_user.html           # Blog-specific user prompt
└── README.md                # This file
```

## Template Inheritance

The templates use Jinja2's template inheritance to create a flexible and DRY system:

- Base templates (`base_system.html`, `base_user.html`) define the common structure and variables
- Content-specific templates extend the base templates and override specific blocks

## Variables

### System Prompt Variables

- `content_type_name`: Type of content being promoted (e.g., "podcast episode")
- `platform_name`: Name of the social platform (e.g., "Twitter")
- `char_limit`: Character limit for the platform
- `url_char_approx`: Approximate characters used by the URL
- `content_limit`: Content limit excluding URL
- `platform_style`: Style guidelines for the platform
- `retry_attempt`: Current retry number
- `last_length`: Length of the previous generation attempt (for retries)
- `blog_author`: Author of the blog post (if applicable)

### User Prompt Variables

- `platform_name`: Name of the social platform
- `content_type_name`: Type of content being promoted
- `char_limit`: Character limit for the platform
- `content_limit`: Content limit excluding URL
- `title`: Title of the content
- `description`: Description or excerpt of the content
- `url`: URL of the content
- `timing`: Human-readable timing information
- `user_name`: Name of the user generating the post
- `user_bio`: Bio of the user
- `platform`: Platform identifier (e.g., "twitter", "linkedin")
- `blog_author`: Author of the blog post (if applicable)

## How to Use

The templates are used by the `helpers/prompt_templates.py` module, which provides functions for rendering the templates:

```python
from helpers.prompt_templates import render_system_prompt, render_user_prompt

# Render a system prompt for a podcast
system_prompt = render_system_prompt(
    podcast_episode,
    current_user,
    platform=SocialPlatform.TWITTER
)

# Render a user prompt for a podcast
user_prompt = render_user_prompt(
    podcast_episode,
    current_user,
    platform=SocialPlatform.TWITTER
)
```

## How to Update

To modify the prompts:

1. Edit the appropriate template file
2. For major changes, update the corresponding variables in `helpers/prompt_templates.py`

## Adding New Content Types

To add a new content type:

1. Add a new enum value to `ContentType` in `helpers/prompt_templates.py`
2. Create new templates: `new_type_system.html` and `new_type_user.html`
3. Update the `get_content_type_info` and template selection logic in `helpers/prompt_templates.py` 