import click
from datetime import datetime
from models import Episode, Post, Video
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

    # Detect content type for log messages
    if isinstance(content_item, Episode):
        content_type = "podcast episode"
        content_title = f"Episode {content_item.episode_number}: {content_item.title}"
    elif isinstance(content_item, Video):
        content_type = "video"
        content_title = content_item.title
    elif isinstance(content_item, Post):
        content_type = "blog post"
        content_title = content_item.title
    else:
        content_type = "content"
        content_title = getattr(content_item, "title", "Unknown")

    click.echo(f"Processing autonomous posting for {len(users)} users...")

    for user in users:
        click.echo(f"\nProcessing for user: {user.email}")

        try:
            # Generate platform-specific posts
            platform_posts = generate_platform_specific_posts(
                content_item, user, max_retries=3
            )

            success = False

            # Post to LinkedIn if authorized and content was successfully generated
            if (
                user.linkedin_authorized
                and "linkedin" in platform_posts
                and platform_posts["linkedin"]
            ):
                try:
                    linkedin_content = platform_posts["linkedin"]
                    click.echo(f"LinkedIn post ({len(linkedin_content)} characters):")
                    click.echo(f"> {linkedin_content}")

                    post_to_linkedin(user, linkedin_content)
                    click.echo(f"✓ Posted to LinkedIn for {user.email}")
                    success = True
                except Exception as e:
                    click.echo(
                        f"× Failed to post to LinkedIn for {user.email}: {str(e)}"
                    )
            elif user.linkedin_authorized:
                click.echo(f"× No LinkedIn content was generated for {user.email}")

            # Post to X if authorized and content was successfully generated
            if (
                user.x_authorized
                and "twitter" in platform_posts
                and platform_posts["twitter"]
            ):
                try:
                    twitter_content = platform_posts["twitter"]
                    click.echo(f"Twitter post ({len(twitter_content)} characters):")
                    click.echo(f"> {twitter_content}")

                    post_to_x(user, twitter_content)
                    click.echo(f"✓ Posted to X for {user.email}")
                    success = True
                except Exception as e:
                    click.echo(f"× Failed to post to X for {user.email}: {str(e)}")
            elif user.x_authorized:
                click.echo(f"× No Twitter content was generated for {user.email}")

            if success:
                click.echo(f"Successfully posted {content_type} for user {user.email}")
            else:
                click.echo(f"No successful posts for user {user.email}")

        except Exception as e:
            click.echo(
                f"Error processing autonomous posting for user {user.email}: {str(e)}"
            )
