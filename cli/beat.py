import click
from flask.cli import with_appcontext
from celery.schedules import crontab
from flask import current_app
from tasks.notifications import initiate_posts
from tasks.fetch_content import fetch_content_task


@click.command("beat")
@click.option("--loglevel", default="info", help="Logging level")
@with_appcontext
def beat_command(loglevel):
    """Run the Celery beat scheduler."""
    # Get celery instance from Flask app context
    celery = current_app.extensions["celery"]

    # The beat_schedule and timezone are already configured on the celery instance
    # when the Flask app is initialized and Celery is configured from Config.CELERY.
    # No need to redefine them here.

    # Start the beat scheduler
    celery.Beat(loglevel=loglevel).run()


@click.command("trigger-posts")
@with_appcontext
def trigger_posts_command():
    """Manually trigger the initiate_posts task for testing."""
    result = initiate_posts.delay()
    click.echo(f"Task triggered! Task ID: {result.id}")
    click.echo("You can check the task status in the Celery worker logs.")


@click.command("trigger-fetch-content")
@with_appcontext
def trigger_fetch_content_command():
    """Manually trigger the fetch_content_task for testing."""
    result = fetch_content_task.delay()
    click.echo(f"Task triggered! Task ID: {result.id}")
    click.echo("You can check the task status in the Celery worker logs.")
