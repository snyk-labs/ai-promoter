import pytest

from app import create_app, db as _db

# from models import User # Import models as needed for fixtures

# It's a good practice to use a new, separate database for testing.
# You might need to configure this based on your setup (e.g., environment variables).
TEST_DATABASE_URI = (
    "sqlite:///:memory:"  # Example: Use an in-memory SQLite DB for tests
)


@pytest.fixture(scope="session")
def app():  # pytest-flask will discover and use this fixture
    """
    Session-wide test Flask application.
    Creates a Flask app instance configured for testing.
    pytest-flask will automatically use this fixture if it's named 'app'.
    """
    flask_app = create_app()
    flask_app.config.update(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": TEST_DATABASE_URI,
            "WTF_CSRF_ENABLED": False,  # Often disabled for testing forms
            "LOGIN_DISABLED": True,  # Useful if you want to bypass login for some tests
            # or handle auth specifically in tests.
            # Add other test-specific configurations here
            "SERVER_NAME": "localhost.localdomain",  # Often needed for url_for to work in tests
            "APPLICATION_ROOT": "/",
            "PREFERRED_URL_SCHEME": "http",
        }
    )

    # Any other app setup needed for tests, e.g., creating an initial user,
    # or setting up specific routes/blueprints if they are conditional.

    yield flask_app

    # Teardown can go here if needed, but usually managed by other fixtures (e.g., db)


# The 'client' fixture is now provided by pytest-flask.
# It will use the 'app' fixture defined above.
# You can use it in your tests like: def test_example(client):

# The 'cli_runner' fixture (note the name change from 'runner') is also provided by pytest-flask.
# It will use the 'app' fixture defined above.
# You can use it in your tests like: def test_cli_command(cli_runner):


@pytest.fixture(scope="session")
def db(app):
    """
    Session-wide test database.
    Sets up and tears down the database for the entire test session.
    """
    with app.app_context():
        _db.create_all()  # Create all tables

    yield _db  # Provide the database instance to tests

    # Teardown: drop all tables after the test session
    with app.app_context():
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def session(db, app):
    """
    Rolls back the database session after each test.
    Ensures that each test starts with a clean database state relative to
    changes made within the test itself (session-scoped fixtures like 'db' handle
    the broader setup/teardown).
    """
    with app.app_context():
        connection = db.engine.connect()
        transaction = connection.begin()

        # Configure the session to use this connection and transaction
        db.session.configure(bind=connection)

        yield db.session  # This is the session that tests will use

        # Teardown: rollback transaction and close connection
        db.session.remove()
        transaction.rollback()
        connection.close()


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
