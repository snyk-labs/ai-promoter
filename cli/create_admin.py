import click
from flask.cli import with_appcontext
from extensions import db
from models import User


@click.command("create-admin")
@click.option("--email", prompt=True, help="Email address of the admin user")
@click.option(
    "--name",
    default=None,
    help="Full name of the admin user (required if creating new)",
)
@click.option(
    "--password",
    default=None,
    hide_input=True,
    confirmation_prompt=True,
    help="Password for the new admin user (required if creating new)",
)
@with_appcontext
def create_admin(email, name, password):
    """Create a new admin user or promote an existing user to admin."""
    user = User.query.filter_by(email=email).first()
    if user:
        if user.is_admin:
            click.echo(f"User {email} is already an admin.")
            return
        user.is_admin = True
        db.session.commit()
        click.echo(f"User {email} has been promoted to admin.")
    else:
        if not name or not password:
            click.echo("Name and password are required to create a new admin user.")
            return
        user = User(email=email, name=name, auth_type="password", is_admin=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"New admin user {email} created successfully.")
