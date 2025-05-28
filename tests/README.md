# Test Suite Documentation

This directory contains comprehensive tests for the entire AI Promoter application, covering all major components and functionality.

## Test Structure

### Test Organization
The test suite is organized by application layers and uses pytest markers for flexible test execution:

- **Unit Tests** (`@pytest.mark.unit`): Test individual functions and methods in isolation
- **Integration Tests** (`@pytest.mark.integration`): Test multiple components working together  
- **CLI Tests** (`@pytest.mark.cli`): Tests specifically for CLI command functionality
- **Slow Tests** (`@pytest.mark.slow`): Tests that take significant time to run

### Test Directories

#### 📁 `cli/` - Command Line Interface Tests
- `test_lint.py`: Tests for the `flask lint` command (45 tests, 100% coverage)
- `test_create_admin.py`: Tests for the `flask create-admin` command (57 tests)
- `test_init_db.py`: Tests for the `flask init-db` command (17 tests)
- `test_beat.py`: Tests for Celery beat scheduler commands (30 tests)

#### 📁 `views/` - Web Route and View Tests
- `test_auth.py`: Authentication and login/logout functionality
- `test_api.py`: API endpoint tests
- `test_admin.py`: Admin interface and functionality
- `test_okta_auth.py`: Okta authentication integration
- `test_main.py`: Main application routes and views

#### 📁 `models/` - Database Model Tests
- `test_user.py`: User model functionality and relationships
- `test_content.py`: Content model and data validation
- `test_share.py`: Share model and social media integration

#### 📁 `services/` - Business Logic Service Tests
- `test_slack_service.py`: Slack integration and messaging
- `test_content_processor.py`: Content processing and transformation

#### 📁 `tasks/` - Background Task Tests
- `test_linkedin_tasks.py`: LinkedIn posting and automation
- `test_fetch_content.py`: Content fetching and aggregation
- `test_promote.py`: Content promotion workflows
- `test_slack_tasks.py`: Slack notification tasks
- `test_content.py`: Content processing tasks
- `test_notifications.py`: Notification system tasks

#### 📁 `helpers/` - Utility and Helper Tests
- `test_okta.py`: Okta authentication helpers
- `test_arcade.py`: Arcade API integration helpers
- `test_gemini.py`: Google Gemini AI integration
- `test_prompts.py`: AI prompt generation and management
- `test_template_helpers.py`: Template rendering utilities
- `test_linkedin_native.py`: LinkedIn native API helpers

## Running Tests

### Run All Tests
```bash
# Run entire test suite with coverage
flask test

# Run without coverage (faster)
flask test --no-cov

# Run with verbose output
flask test -v
```

### Run Tests by Directory
```bash
# CLI tests only
flask test tests/cli/

# View tests only  
flask test tests/views/

# Model tests only
flask test tests/models/

# Service tests only
flask test tests/services/

# Task tests only
flask test tests/tasks/

# Helper tests only
flask test tests/helpers/
```

### Run Tests by Marker
```bash
# Run only unit tests (fast, no external dependencies)
flask test -m unit

# Run only integration tests (slower, uses real components)
flask test -m integration

# Run only CLI-specific tests
flask test -m cli

# Skip slow tests
flask test -m "not slow"

# Run only slow tests
flask test -m slow
```

### Run Specific Test Files or Functions
```bash
# Specific test file
flask test tests/cli/test_lint.py

# Specific test class (pass through to pytest)
flask test tests/models/test_user.py::TestUserModel

# Specific test function (pass through to pytest)
flask test tests/cli/test_lint.py::TestLintCommand::test_lint_command_exists
```

### Run with Coverage Options
```bash
# Default coverage (terminal + HTML + XML reports)
flask test

# Specific coverage report format
flask test --cov-report=html
flask test --cov-report=xml
flask test --cov-report=term-missing

# No coverage reporting
flask test --no-cov
```

### Performance and Optimization
```bash
# Run tests in parallel (requires pytest-xdist)
flask test --parallel

# Stop on first failure
flask test --fail-fast

# Run tests matching keyword
flask test -k "user"

# Combine options for fast development
flask test -m unit --no-cov --fail-fast
```

## Test Configuration

### Global Fixtures (`conftest.py`)
- **`app`**: Session-wide Flask application configured for testing
- **`client`**: HTTP test client for making requests (provided by pytest-flask)
- **`cli_runner`**: CLI test runner for testing Flask commands (provided by pytest-flask)
- **`db`**: Session-wide test database setup
- **`session`**: Database session with automatic rollback after each test

### Test Database
- Uses SQLite in-memory database for fast, isolated testing
- Automatically creates and tears down tables for each test session
- Each test gets a clean database state via transaction rollback

## Test Patterns and Best Practices

### Helper Classes and Constants
Most test files include standardized helper classes:
- **`TestMessages`**: Expected messages, error strings, and validation text
- **`TestData`**: Sample data, factories, and test fixtures
- **`*TestHelpers`**: Reusable assertion methods and mock creation utilities

### Mock Patterns
```python
# External API calls
@patch("services.slack_service.requests.post")
def test_slack_integration(mock_post):
    mock_post.return_value.status_code = 200
    # Test implementation

# Database operations
@patch("models.User.query")
def test_user_lookup(mock_query):
    mock_query.filter_by.return_value.first.return_value = mock_user
    # Test implementation

# File system operations
@patch("builtins.open", mock_open(read_data="test content"))
def test_file_processing(mock_file):
    # Test implementation
```

### Assertion Patterns
```python
# Descriptive assertions with context
assert result.status_code == 200, f"Expected 200, got {result.status_code}: {result.data}"

# Multiple related assertions
def assert_user_created_correctly(user, expected_data):
    assert user.email == expected_data["email"]
    assert user.name == expected_data["name"]
    assert user.is_active is True
```

## Writing New Tests

### 1. Choose the Right Directory
- **CLI tests**: `tests/cli/` for Flask commands
- **View tests**: `tests/views/` for web routes and templates
- **Model tests**: `tests/models/` for database models and relationships
- **Service tests**: `tests/services/` for business logic and external integrations
- **Task tests**: `tests/tasks/` for background jobs and Celery tasks
- **Helper tests**: `tests/helpers/` for utility functions and shared code

### 2. Use Appropriate Markers
```python
@pytest.mark.unit  # Fast tests with mocks
@pytest.mark.integration  # Tests with real components
@pytest.mark.cli  # CLI command tests
@pytest.mark.slow  # Long-running tests
```

### 3. Follow Naming Conventions
- Test files: `test_*.py`
- Test classes: `TestComponentName`
- Test methods: `test_specific_behavior`

### 4. Structure Test Classes
```python
@pytest.mark.unit
class TestUserModel:
    """Test the User model functionality."""
    
    def test_user_creation(self, session):
        """Test creating a new user."""
        # Test implementation
        
    def test_user_validation(self, session):
        """Test user data validation."""
        # Test implementation

@pytest.mark.integration  
class TestUserIntegration:
    """Integration tests for User model with database."""
    
    def test_user_creation_with_database(self, session):
        """Test user creation with real database."""
        # Test implementation
        pass
```

## Debugging Tests

### Common Issues and Solutions

#### Import Errors
```bash
# Check Python path and module imports
flask test tests/models/test_user.py -v
```

#### Mock Not Working
```python
# Ensure patch target matches actual import path
# Wrong: @patch("models.User")
# Right: @patch("tests.test_file.User") if imported as "from models import User"
```

#### Database Issues
```bash
# Run with database debugging
flask test tests/models/ -v --no-cov
```

### Debugging Commands
```bash
# Maximum verbosity
flask test tests/cli/test_lint.py::TestLintCommand::test_lint_command_exists -v

# Drop into debugger on failure (pass through to pytest)
flask test tests/models/test_user.py --pdb

# Show print statements and logging (pass through to pytest)
flask test tests/services/test_slack_service.py -s

# Run specific test with coverage
flask test tests/models/test_user.py::TestUserModel::test_user_creation --cov-report=term-missing
```

## Development Workflows

### Fast Development Cycle
```bash
# Quick unit tests during development
flask test -m unit --no-cov --fail-fast

# Test specific component you're working on
flask test tests/models/ --no-cov -v

# Test with keyword matching
flask test -k "user" --no-cov
```

### Pre-Commit Testing
```bash
# Run all tests with coverage
flask test

# Run linting and tests together
flask lint && flask test
```

### CI/CD Pipeline Testing
```bash
# Fast tests for pull requests
flask test -m "not slow" --parallel

# Full test suite for main branch
flask test --parallel
```

## Continuous Integration

### GitHub Actions Integration
The test suite is designed to work with CI/CD pipelines:

```yaml
# Example GitHub Actions step
- name: Run Tests
  run: |
    flask test -m "not slow"
    
- name: Run Integration Tests  
  run: |
    flask test -m integration
    
- name: Run All Tests with Coverage
  run: |
    flask test --parallel
```

### Coverage Requirements
- **CLI tests**: Maintain 100% coverage for all CLI commands
- **Models**: Aim for >95% coverage of model methods
- **Services**: Focus on business logic coverage >90%
- **Views**: Test all routes and error conditions >85%

## Example Test Implementation

```python
"""
Example test file structure following best practices.
"""
import pytest
from unittest.mock import Mock, patch
from flask import url_for

from models import User
from services.user_service import UserService


class TestConstants:
    """Test constants and expected values."""
    VALID_EMAIL = "test@example.com"
    VALID_NAME = "Test User"
    EXPECTED_SUCCESS_MESSAGE = "User created successfully"


class UserTestHelpers:
    """Helper methods for user testing."""
    
    @staticmethod
    def create_mock_user(email=TestConstants.VALID_EMAIL, **kwargs):
        """Create a mock user with default values."""
        mock_user = Mock(spec=User)
        mock_user.email = email
        mock_user.name = kwargs.get('name', TestConstants.VALID_NAME)
        return mock_user


@pytest.mark.unit
class TestUserService:
    """Unit tests for UserService."""
    
    @patch("services.user_service.db.session")
    def test_create_user_success(self, mock_session):
        """Test successful user creation."""
        # Test implementation
        pass


@pytest.mark.integration
class TestUserIntegration:
    """Integration tests for User functionality."""
    
    def test_user_creation_with_database(self, session):
        """Test user creation with real database."""
        # Test implementation
        pass
```

## Flask Test Command Features

The `flask test` command provides several advantages over raw pytest:

### Built-in Features
- **Automatic Flask app context setup**
- **Test database configuration**
- **Coverage reporting with multiple formats**
- **Environment variable management**
- **Parallel execution support**
- **Helpful error messages and troubleshooting**

### Command Options
- `-v, --verbose`: Verbose output
- `-k, --keyword`: Run tests matching keyword
- `-m, --marker`: Run tests with specific marker
- `--no-cov`: Disable coverage reporting
- `--cov-report`: Choose coverage report format
- `--parallel`: Run tests in parallel
- `--fail-fast`: Stop on first failure

This comprehensive test suite ensures reliable, maintainable code with confidence for production deployments. 