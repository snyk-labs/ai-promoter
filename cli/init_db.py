import click
from flask.cli import with_appcontext
from extensions import db
from sqlalchemy import text  # Import text for raw SQL


@click.command("init-db")
@with_appcontext
def init_db():
    """Initialize the database by dropping all tables and recreating them.

    This is a destructive operation and should only be used during initial setup
    or when you want to completely reset the database.

    For normal database migrations, use 'flask db migrate' and 'flask db upgrade'
    commands provided by Flask-Migrate.
    """
    click.echo("Determining database dialect...")
    dialect_name = db.engine.dialect.name

    if dialect_name == "postgresql":
        click.echo(
            "PostgreSQL detected. Dropping all tables in 'public' schema with CASCADE..."
        )
        with db.engine.connect() as connection:
            # Temporarily disable foreign key checks is not a standard SQL command
            # and varies by database. For PostgreSQL, dropping with CASCADE is preferred
            # or dropping tables in reverse order of dependency.
            # The most straightforward for a full reset is to drop and recreate the schema.
            connection.execute(text("DROP SCHEMA public CASCADE;"))
            connection.execute(text("CREATE SCHEMA public;"))
            # Restore default permissions for the public schema for the current user
            # Heroku's default user should be able to do this.
            if db.engine.url.username:  # Ensure username is available
                connection.execute(
                    text(f"GRANT ALL ON SCHEMA public TO {db.engine.url.username};")
                )
                connection.execute(
                    text(f"GRANT USAGE ON SCHEMA public TO {db.engine.url.username};")
                )  # For pg_catalog access
            connection.commit()
        click.echo("'public' schema dropped and recreated.")
    else:
        click.echo(f"{dialect_name.capitalize()} detected. Dropping all tables...")
        db.drop_all()

    click.echo("Database has been wiped. Tables will be created by migrations.")
