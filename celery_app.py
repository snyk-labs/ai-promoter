# Placeholder for Celery CLI. Actual app created in app.py.

# celery_app.py
# This module is primarily used as a target for the `celery -A` command.
# It ensures that task modules are imported so Celery can find the tasks
# when the worker starts. The actual Celery application instance is created
# and configured within the Flask app factory (`create_app` in `app.py`).

# Import task modules here so the worker can find them.
import tasks.content
import tasks.promote
# If you have more task modules, import them as well, e.g.:
# import tasks.another_module

# You can still specify task modules to be imported by the worker here if desired,
# though Celery can also auto-discover tasks.
# Example of ensuring tasks are loaded (if not using autodiscovery effectively):
# from . import tasks # Assuming your tasks are in a tasks package/directory

# If you have a tasks.content module specifically:
# import tasks.content

# For Celery to find tasks, it needs to import the modules where tasks are defined.
# If your tasks are in `tasks/content.py`, and `tasks` is a package (has __init__.py),
# the worker needs to be able to import `tasks.content`.
# The `include` argument in Celery app creation usually handles this, but since
# the app is created in `app.py`, we ensure worker can find tasks by importing them or their package.

# One way to ensure tasks are seen by `celery -A celery_app worker` is to ensure
# the modules containing tasks are imported when celery_app is processed.
# This can be done by adding an import statement here, e.g.:
# import tasks.content # Assuming your scrape_content_task is in tasks/content.py

# If you have other task modules, import them here as well.

from celery import Celery
from config import Config # Import Config to access REDIS_URL and other CELERY settings

# Directly configure the Celery instance with Redis broker and backend
# This aligns with the Celery "First Steps" guide and makes the instance
# self-sufficient for broker/backend configuration.
celery = Celery(
    __name__, # Will be updated by celery_init_app to app.name
    broker=Config.REDIS_URL, # Directly set the broker
    backend=Config.REDIS_URL, # Directly set the backend
    include=['tasks.content', 'tasks.promote'] # Ensure tasks from both modules are discovered
)

# Apply all other settings from the CELERY dictionary in Config
# This ensures the worker has the same settings as the Flask app when it starts.
if hasattr(Config, 'CELERY') and isinstance(Config.CELERY, dict):
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