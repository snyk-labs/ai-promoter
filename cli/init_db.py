import click
from flask.cli import with_appcontext
from extensions import db


@click.command("init-db")
@with_appcontext
def init_db():
    """Initialize the database by dropping all tables and recreating them.

    This is a destructive operation and should only be used during initial setup
    or when you want to completely reset the database.

    For normal database migrations, use 'flask db migrate' and 'flask db upgrade'
    commands provided by Flask-Migrate.
    """
    click.echo("Dropping all tables...")
    db.drop_all()
    click.echo("Creating database tables...")
    db.create_all()
    click.echo("Database tables created successfully.")
