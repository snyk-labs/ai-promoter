import click
from datetime import datetime
from models import Content, User
from helpers.openai import generate_social_post
from helpers.arcade import post_to_linkedin


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
            posts = generate_social_post(content_item, user)

            # Post to LinkedIn if available and authorized
            if user.linkedin_authorized and posts.get("linkedin"):
                click.echo(f"Posting to LinkedIn for user {user.name}...")
                post_to_linkedin(user, posts["linkedin"])

        except Exception as e:
            click.echo(f"Error processing user {user.name}: {str(e)}")
            continue


def get_authorized_users():
    """Get all users who have authorized social media accounts."""
    return User.query.filter(User.linkedin_authorized == True).all()


def post_to_social_media(user, content, posts):
    """
    Post content to social media for a user.

    Args:
        user: The user to post as
        content: The content item to post about
        posts: Dictionary of generated posts
    """
    # Post to LinkedIn if available and authorized
    if user.linkedin_authorized and posts.get("linkedin"):
        click.echo(f"Posting to LinkedIn for user {user.name}...")
        post_to_linkedin(user, posts["linkedin"])
