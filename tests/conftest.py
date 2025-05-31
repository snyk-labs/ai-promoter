import pytest
import os
import tempfile
import threading
from unittest.mock import patch

from app import create_app, db as _db

# from models import User # Import models as needed for fixtures

# Global lock for database operations to prevent race conditions
db_lock = threading.Lock()


@pytest.fixture(scope="session")
def app():  # pytest-flask will discover and use this fixture
    """
    Session-scoped test Flask application.
    Creates a Flask app instance configured for testing.
    pytest-flask will automatically use this fixture if it's named 'app'.
    """
    flask_app = create_app()

    # Force test configuration regardless of environment
    flask_app.config.update(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "LOGIN_DISABLED": True,
            "SERVER_NAME": "localhost.localdomain",
            "APPLICATION_ROOT": "/",
            "PREFERRED_URL_SCHEME": "http",
            # Disable background tasks during testing
            "CELERY_TASK_ALWAYS_EAGER": True,
            "CELERY_TASK_EAGER_PROPAGATES": True,
            # Ensure we never accidentally use production database
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )

    yield flask_app


@pytest.fixture()  # Function-scoped for complete isolation
def db(app):
    """
    Function-scoped test database with complete isolation.
    Each test gets its own fresh database state.
    """
    # Get worker ID for parallel execution
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")

    # Create worker-specific temporary database file for parallel execution
    if worker_id != "master":
        temp_dir = tempfile.gettempdir()
        db_file = os.path.join(temp_dir, f"test_db_{worker_id}_{id(app)}.sqlite")
        db_uri = f"sqlite:///{db_file}"

        # Update app config for this specific test
        app.config["SQLALCHEMY_DATABASE_URI"] = db_uri

    with app.app_context():
        # Initialize database with proper locking for parallel execution
        with db_lock:
            try:
                # Reinitialize the database with new URI if needed
                if worker_id != "master":
                    _db.init_app(app)

                # Create all tables
                _db.create_all()
            except Exception as e:
                # If creation fails, ensure we have a clean state
                try:
                    _db.drop_all()
                    _db.create_all()
                except Exception:
                    print(f"Critical database setup failed for worker {worker_id}: {e}")
                    raise

    yield _db  # Provide the database instance to tests

    # Teardown: completely remove database after each test
    with app.app_context():
        try:
            _db.drop_all()
        except Exception:
            pass

    # Clean up temporary files for parallel workers
    if worker_id != "master":
        try:
            temp_dir = tempfile.gettempdir()
            db_file = os.path.join(temp_dir, f"test_db_{worker_id}_{id(app)}.sqlite")
            if os.path.exists(db_file):
                os.remove(db_file)
        except OSError:
            pass


@pytest.fixture()
def session(db, app):
    """
    Provides a database session for each test.
    Uses the function-scoped database which handles its own cleanup.
    """
    with app.app_context():
        # Create a new session for this test
        session = _db.session

        yield session

        # Cleanup: close session and rollback any uncommitted changes
        try:
            session.rollback()
            session.close()
        except Exception:
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
