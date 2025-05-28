# make_celery.py
# This script creates the Flask application and exposes the configured Celery
# application instance for use by Celery worker and beat commands.
# This is the recommended pattern when using the Flask application factory.

from app import create_app  # Import your Flask app factory

flask_app = create_app()  # Create the Flask app instance

# The celery_init_app function (called within create_app) stores the
# configured Celery instance in app.extensions["celery"].
# We expose that instance here as `celery` so the CLI command
# `celery -A make_celery.celery worker ...` can find it.
celery = flask_app.extensions["celery"]

# If you want to ensure task modules are loaded when `make_celery.py` is processed by the worker,
# you could add imports here, e.g.:
# import tasks.content
# However, the `include` argument in the Celery app instantiation within `celery_init_app`
# (in app.py) should handle task discovery for the `celery` instance we are exposing here.
