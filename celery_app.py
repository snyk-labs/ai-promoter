# Placeholder for Celery CLI. Actual app created in app.py.

# celery_app.py
# This module is primarily used as a target for the `celery -A` command.
# It ensures that task modules are imported so Celery can find the tasks
# when the worker starts. The actual Celery application instance is created
# and configured within the Flask app factory (`create_app` in `app.py`).

# Import task modules here so the worker can find them.
import tasks.content
import tasks.promote
import tasks.notifications
import tasks.fetch_content
import tasks.linkedin_tasks
import tasks.social_media

from celery import Celery
from config import Config  # Import Config to access REDIS_URL and other CELERY settings

# Directly configure the Celery instance with Redis broker and backend
# This aligns with the Celery "First Steps" guide and makes the instance
# self-sufficient for broker/backend configuration.
celery = Celery(
    __name__,  # Will be updated by celery_init_app to app.name
    broker=Config.REDIS_URL,  # Directly set the broker
    backend=Config.REDIS_URL,  # Directly set the backend
    include=[
        "tasks.content",
        "tasks.promote",
        "tasks.notifications",
        "tasks.fetch_content",
        "tasks.linkedin_tasks",
        "tasks.social_media",
    ],  # Ensure tasks from all modules are discovered
)

# Apply all other settings from the CELERY dictionary in Config
# This ensures the worker has the same settings as the Flask app when it starts.
if hasattr(Config, "CELERY") and isinstance(Config.CELERY, dict):
    celery.conf.update(Config.CELERY)

# Additional configurations can still be loaded via Flask app context if needed,
# but broker/backend are now set.
# For example, in app.py's celery_init_app:
# celery.conf.update(app.config.get("CELERY", {})) # To load other settings

# Example of updating other configurations if not done through Flask app:
# celery.conf.update(
#     task_serializer='json',
#     accept_content=['json'],
#     result_serializer='json',
#     timezone='UTC',
#     enable_utc=True,
#     # etc.
# )
