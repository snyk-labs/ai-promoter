import click
from datetime import datetime
from models import Content
from helpers.openai import generate_platform_specific_posts
from helpers.arcade import post_to_linkedin, post_to_x


def handle_autonomous_posting(content_item):
    """Automatically post about new content for users with autonomous mode enabled."""
    # Import here to avoid circular imports
    from models import User

    # Find all users with autonomous mode enabled who have at least one social account connected
    users = User.query.filter(
        User.autonomous_mode == True,
        (User.linkedin_authorized == True) | (User.x_authorized == True),
    ).all()

    if not users:
        click.echo(
            "No users with autonomous mode enabled and social accounts connected."
        )
        return

    # Get content type for log messages
    content_type = content_item.content_type
    content_title = content_item.title

    click.echo(f"Processing autonomous posting for {len(users)} users...")

    # Process each user
    for user in users:
        try:
            # Generate platform-specific posts
            posts = generate_platform_specific_posts(content_item, user)

            # Post to Twitter if available and authorized
            if user.x_authorized and posts.get("twitter"):
                click.echo(f"Posting to Twitter for user {user.name}...")
                post_to_x(user, posts["twitter"])

            # Post to LinkedIn if available and authorized
            if user.linkedin_authorized and posts.get("linkedin"):
                click.echo(f"Posting to LinkedIn for user {user.name}...")
                post_to_linkedin(user, posts["linkedin"])

        except Exception as e:
            click.echo(f"Error processing user {user.name}: {str(e)}")
            continue
