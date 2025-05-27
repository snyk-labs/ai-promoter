import click
from flask import current_app
from flask.cli import with_appcontext


@click.command("routes")
@with_appcontext
def list_routes():
    """List all registered routes in the application."""
    output = []
    routes = []

    # Get all registered routes
    for rule in current_app.url_map.iter_rules():
        methods = ",".join(
            sorted(
                method for method in rule.methods if method not in ("HEAD", "OPTIONS")
            )
        )
        routes.append((rule.endpoint, methods, str(rule)))

    # Sort routes by endpoint
    routes.sort(key=lambda x: x[0])

    # Format the output
    for endpoint, methods, url in routes:
        row = f"{endpoint:40s} {methods:20s} {url}"
        output.append(row)

    # Print all routes
    click.echo("\n".join(output))

    # Display the count of routes
    click.echo(f"\nTotal routes: {len(routes)}")
