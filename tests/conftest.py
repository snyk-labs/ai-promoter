import os

# Set TESTING environment variable before any imports to prevent config issues
os.environ["TESTING"] = "true"

import pytest
from unittest.mock import patch

from app import create_app, db as _db


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """
    Session-scoped fixture that automatically sets up the test environment.
    This runs before any tests and ensures TESTING environment variable is set.
    """
    yield
    # Cleanup after all tests
    if "TESTING" in os.environ:
        del os.environ["TESTING"]


@pytest.fixture(scope="session")
def app():
    """
    Session-scoped test Flask application.
    Creates a Flask app instance configured for testing.
    """
    flask_app = create_app()

    # Force test configuration
    flask_app.config.update(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,
            "LOGIN_DISABLED": True,
            "SERVER_NAME": "localhost.localdomain",
            "APPLICATION_ROOT": "/",
            "PREFERRED_URL_SCHEME": "http",
            # Disable background tasks during testing
            "CELERY_TASK_ALWAYS_EAGER": True,
            "CELERY_TASK_EAGER_PROPAGATES": True,
        }
    )

    yield flask_app


@pytest.fixture()
def client(app):
    """
    Function-scoped test client for making HTTP requests.
    """
    return app.test_client()


@pytest.fixture()
def db(app):
    """
    Function-scoped test database with complete isolation.
    Each test gets its own fresh database state.
    """
    with app.app_context():
        # Create all tables fresh for each test
        _db.create_all()

        yield _db

        # Clean up: drop all tables after each test
        _db.drop_all()


@pytest.fixture()
def session(db, app):
    """
    Provides a database session for each test.
    Uses the function-scoped database for complete isolation.
    """
    with app.app_context():
        yield _db.session


@pytest.fixture
def cli_runner(app):
    """
    Custom CLI runner for testing CLI commands.
    """
    return app.test_cli_runner()


@pytest.fixture
def cli_test_env(app, db):
    """
    Sets up environment for CLI integration tests.
    Patches the create_app function to return the test app.
    """
    test_db_uri = app.config["SQLALCHEMY_DATABASE_URI"]

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
        with test_app.app_context():
            _db.create_all()
        return test_app

    with patch("app.create_app", side_effect=mock_create_app):
        with app.app_context():
            _db.create_all()
        yield


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
