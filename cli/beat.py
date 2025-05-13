import click
from flask.cli import with_appcontext
from celery.schedules import crontab
from flask import current_app
from tasks.notifications import initiate_posts

@click.command('beat')
@click.option('--loglevel', default='info', help='Logging level')
@with_appcontext
def beat_command(loglevel):
    """Run the Celery beat scheduler."""
    # Get celery instance from Flask app context
    celery = current_app.extensions["celery"]
    
    # Set timezone for the celery app
    celery.conf.timezone = 'US/Eastern'
    
    # Ensure the beat schedule is configured
    celery.conf.beat_schedule = {
        'initiate-posts-9am': {
            'task': 'tasks.notifications.initiate_posts',
            'schedule': crontab(hour=9, minute=0),
        },
        'initiate-posts-12pm': {
            'task': 'tasks.notifications.initiate_posts',
            'schedule': crontab(hour=12, minute=0),
        },
        'initiate-posts-3pm': {
            'task': 'tasks.notifications.initiate_posts',
            'schedule': crontab(hour=15, minute=0),
        },
    }
    
    # Start the beat scheduler
    celery.Beat(loglevel=loglevel).run()

@click.command('trigger-posts')
@with_appcontext
def trigger_posts_command():
    """Manually trigger the initiate_posts task for testing."""
    result = initiate_posts.delay()
    click.echo(f"Task triggered! Task ID: {result.id}")
    click.echo("You can check the task status in the Celery worker logs.") 