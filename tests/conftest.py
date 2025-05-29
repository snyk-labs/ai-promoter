import pytest
import os
import tempfile
from unittest.mock import patch

from app import create_app, db as _db

# from models import User # Import models as needed for fixtures


# It's a good practice to use a new, separate database for testing.
# You might need to configure this based on your setup (e.g., environment variables).
def get_test_database_uri():
    """Get test database URI, with worker-specific naming for parallel execution."""
    # Check if we're running in parallel (pytest-xdist sets this)
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")

    if worker_id == "master":
        # Single process execution - use in-memory database
        return "sqlite:///:memory:"
    else:
        # Parallel execution - use worker-specific temporary file database
        # This ensures each worker has its own isolated database file
        temp_dir = tempfile.gettempdir()
        db_file = os.path.join(temp_dir, f"test_db_{worker_id}.sqlite")
        return f"sqlite:///{db_file}"


@pytest.fixture(scope="function")  # Changed from session to function scope
def app():  # pytest-flask will discover and use this fixture
    """
    Function-scoped test Flask application.
    Creates a Flask app instance configured for testing.
    pytest-flask will automatically use this fixture if it's named 'app'.
    """
    flask_app = create_app()
    flask_app.config.update(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": get_test_database_uri(),
            "WTF_CSRF_ENABLED": False,  # Often disabled for testing forms
            "LOGIN_DISABLED": True,  # Useful if you want to bypass login for some tests
            # or handle auth specifically in tests.
            # Add other test-specific configurations here
            "SERVER_NAME": "localhost.localdomain",  # Often needed for url_for to work in tests
            "APPLICATION_ROOT": "/",
            "PREFERRED_URL_SCHEME": "http",
            # Disable background tasks during testing
            "CELERY_TASK_ALWAYS_EAGER": True,
            "CELERY_TASK_EAGER_PROPAGATES": True,
        }
    )

    # Any other app setup needed for tests, e.g., creating an initial user,
    # or setting up specific routes/blueprints if they are conditional.

    yield flask_app

    # Cleanup: remove temporary database files for parallel execution
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
    if worker_id != "master":
        temp_dir = tempfile.gettempdir()
        db_file = os.path.join(temp_dir, f"test_db_{worker_id}.sqlite")
        try:
            if os.path.exists(db_file):
                os.remove(db_file)
        except OSError:
            pass  # Ignore cleanup errors


# The 'client' fixture is now provided by pytest-flask.
# It will use the 'app' fixture defined above.
# You can use it in your tests like: def test_example(client):

# The 'cli_runner' fixture (note the name change from 'runner') is also provided by pytest-flask.
# It will use the 'app' fixture defined above.
# You can use it in your tests like: def test_cli_command(cli_runner):


@pytest.fixture(scope="function")  # Changed from session to function scope
def db(app):
    """
    Function-scoped test database.
    Sets up and tears down the database for each test function.
    This ensures proper isolation in parallel execution.
    """
    with app.app_context():
        # Ensure we're working with a clean database
        _db.drop_all()  # Drop any existing tables first
        _db.create_all()  # Create all tables

    yield _db  # Provide the database instance to tests

    # Teardown: drop all tables after each test
    with app.app_context():
        try:
            _db.session.remove()
            _db.drop_all()
        except Exception:
            # If cleanup fails, just continue
            pass


@pytest.fixture()
def session(db, app):
    """
    Provides a database session for each test.
    Now works with function-scoped db fixture for better parallel execution support.
    """
    with app.app_context():
        # For test databases, we can use the session directly
        # since each test gets its own database instance
        yield db.session

        # Cleanup: rollback any uncommitted changes
        try:
            db.session.rollback()
        except Exception:
            # If rollback fails, just remove the session
            pass
        finally:
            try:
                db.session.remove()
            except Exception:
                # If session removal fails, just continue
                pass


# Override the default cli_runner fixture to ensure it uses the test app context
@pytest.fixture
def cli_runner(app):
    """
    Custom CLI runner that ensures commands run within the test app context.
    This is crucial for CLI commands that interact with the database.
    """
    return app.test_cli_runner()


# Special fixture for CLI integration tests that need database isolation
@pytest.fixture
def cli_test_env(app, db):
    """
    Sets up environment for CLI integration tests.
    This fixture patches the create_app function to return the test app
    so that CLI commands use the test database configuration.
    """
    test_db_uri = app.config["SQLALCHEMY_DATABASE_URI"]

    # Patch the create_app function to return a test-configured app
    def mock_create_app():
        test_app = create_app()
        test_app.config.update(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": test_db_uri,
                "WTF_CSRF_ENABLED": False,
                "LOGIN_DISABLED": True,
                "CELERY_TASK_ALWAYS_EAGER": True,
                "CELERY_TASK_EAGER_PROPAGATES": True,
            }
        )
        # Ensure the database is properly set up for the test app
        with test_app.app_context():
            try:
                _db.create_all()
            except Exception:
                # Tables might already exist, which is fine
                pass
        return test_app

    with patch("app.create_app", side_effect=mock_create_app):
        # Ensure tables are created in the test database
        with app.app_context():
            try:
                _db.create_all()
            except Exception:
                # Tables might already exist, which is fine
                pass
        yield
        # Cleanup is handled by the db fixture


# --- Example Fixtures (Uncomment and adapt as needed) ---

# @pytest.fixture
# def new_user(session):
#     """
#     Fixture to create a new user and add it to the test database.
#     This user will be rolled back after the test by the 'session' fixture.
#     """
#     # from models import User # Ensure User model is imported here
#     user = User(username='testuser', email='test@example.com', password='password123')
#     session.add(user)
#     session.commit()
#     return user

# @pytest.fixture
# def logged_in_client(client, new_user):
#     """
#     Fixture to get a test client that is already logged in as a specific user.
#     This might involve calling your login route with test credentials.
#     Adapt this based on your application's authentication mechanism.
#     """
#     # Example: If you have a /auth/login route that sets a session cookie
#     # client.post('/auth/login', data=dict(
#     #     email='test@example.com',
#     #     password='password123'
#     # ), follow_redirects=True)
#     #
#     # If you directly manipulate the session (ensure LOGIN_DISABLED is False in app config for this to be effective for Flask-Login):
#     # with client.session_transaction() as sess:
#     #     sess['_user_id'] = str(new_user.id)
#     #     sess['_fresh'] = True # if your app uses this
#     return client


# --- Hooks (Uncomment and adapt as needed) ---

# def pytest_addoption(parser):
# """
# Allows adding custom command-line options to pytest.
# Example: pytest --custom-option=value
# """
# parser.addoption(
# "--runslow", action="store_true", default=False, help="run slow tests"
# )

# def pytest_collection_modifyitems(config, items):
# """
# Called after test collection has been performed.
# Useful for deselecting tests based on options or markers.
# """
# if not config.getoption("--runslow"):
# # --runslow not given in cli: skip slow tests
# skip_slow = pytest.mark.skip(reason="need --runslow option to run")
# for item in items:
# if "slow" in item.keywords:
# item.add_marker(skip_slow)

# def pytest_configure(config):
# """
# Allows performing initial configuration.
# Example: Registering custom markers.
# """
# config.addinivalue_line(
# "markers", "slow: mark test as slow to run"
# )
# config.addinivalue_line(
# "markers", "smoke: mark test as a smoke test"
# )
