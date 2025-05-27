import click
from datetime import datetime
from flask import current_app
from models import Content, User
from helpers.gemini import SocialPostGenerator
from helpers.arcade import post_to_linkedin as post_to_linkedin_arcade
from helpers.linkedin_native import post_to_linkedin_native


def handle_autonomous_posting(content_item):
    """Automatically post about new content for users with autonomous mode enabled."""
    from models import User

    users = User.query.filter(
        User.autonomous_mode == True, (User.linkedin_authorized == True)
    ).all()

    if not users:
        click.echo(
            "No users with autonomous mode enabled and LinkedIn accounts connected."
        )
        return

    content_title = content_item.title
    click.echo(
        f'Processing autonomous LinkedIn posting for "{content_title}" for {len(users)} users...'
    )

    for user in users:
        click.echo(f"Processing user: {user.name} ({user.email})")
        try:
            post_generator = SocialPostGenerator()
            posts = post_generator.generate_all_platform_posts(content_item, user)
            linkedin_post_content = posts.get("linkedin")

            if user.linkedin_authorized and linkedin_post_content:
                click.echo(f"  Attempting to post to LinkedIn for {user.name}...")
                if current_app.config.get("NATIVE_LINKEDIN"):
                    click.echo(f"    Using NATIVE LinkedIn integration.")
                    if not user.linkedin_native_access_token:
                        click.echo(
                            f"    User {user.name} missing native LinkedIn access token. Skipping."
                        )
                        continue
                    post_to_linkedin_native(user, linkedin_post_content)
                    click.echo(
                        f"    Successfully posted to LinkedIn (Native) for {user.name}."
                    )
                else:
                    click.echo(f"    Using ARCADE LinkedIn integration.")
                    post_to_linkedin_arcade(user, linkedin_post_content)
                    click.echo(
                        f"    Successfully posted to LinkedIn (Arcade) for {user.name}."
                    )
            elif not user.linkedin_authorized:
                click.echo(
                    f"  User {user.name} is not authorized for LinkedIn. Skipping."
                )
            elif not linkedin_post_content:
                click.echo(
                    f"  No LinkedIn post content generated for {user.name}. Skipping."
                )

        except ValueError as ve:
            click.echo(
                f"  A ValueError occurred while processing user {user.name} for LinkedIn: {str(ve)}"
            )
        except Exception as e:
            click.echo(
                f"  An unexpected error occurred while processing user {user.name} for LinkedIn: {str(e)}"
            )
        # Continue to the next user even if one fails


def get_authorized_users():
    """Get all users who have authorized social media accounts."""
    return User.query.filter(User.linkedin_authorized == True).all()


def post_to_social_media(user, content, posts):
    """
    Post content to social media for a user.

    Args:
        user: The user to post as
        content: The content item to post about (used for logging here)
        posts: Dictionary of generated posts (e.g., {"linkedin": "text"})
    """
    linkedin_post_content = posts.get("linkedin")

    if user.linkedin_authorized and linkedin_post_content:
        click.echo(
            f'Attempting to post "{content.title}" to LinkedIn for user {user.name}...'
        )
        try:
            if current_app.config.get("NATIVE_LINKEDIN"):
                click.echo(f"  Using NATIVE LinkedIn integration.")
                if not user.linkedin_native_access_token:
                    click.echo(
                        f"  User {user.name} missing native LinkedIn access token. Skipping post."
                    )
                    return
                post_to_linkedin_native(user, linkedin_post_content)
                click.echo(
                    f"  Successfully posted to LinkedIn (Native) for {user.name}."
                )
            else:
                click.echo(f"  Using ARCADE LinkedIn integration.")
                post_to_linkedin_arcade(user, linkedin_post_content)
                click.echo(
                    f"  Successfully posted to LinkedIn (Arcade) for {user.name}."
                )
        except ValueError as ve:
            click.echo(
                f"  A ValueError occurred while posting to LinkedIn for user {user.name}: {str(ve)}"
            )
        except Exception as e:
            click.echo(
                f"  An unexpected error occurred while posting to LinkedIn for user {user.name}: {str(e)}"
            )
    elif not user.linkedin_authorized:
        click.echo(
            f'User {user.name} is not authorized for LinkedIn. Skipping post for "{content.title}".'
        )
    elif not linkedin_post_content:
        click.echo(
            f'No LinkedIn post content available for user {user.name} for "{content.title}". Skipping.'
        )
