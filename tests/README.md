# AI Promoter Test Suite Documentation

This document provides guidance on the AI Promoter test suite architecture, patterns, and best practices.

## 🏗️ Test Architecture

### Test Organization

```
tests/
├── README.md                    # This documentation
├── test_utils.py               # Shared utilities and fixtures
├── conftest.py                 # Global pytest configuration
├── views/
│   └── test_api.py            # API endpoint tests
├── cli/                       # CLI command tests
├── models/                    # Database model tests
├── services/                  # Business logic tests
└── tasks/                     # Celery task tests
```

### Test Categories & Markers

Use pytest markers to categorize and filter tests:

```bash
# Run only fast unit tests
pytest -m "unit"

# Run integration tests (slower, require database)
pytest -m "integration"

# Run API-specific tests
pytest -m "api"

# Run tests related to Celery tasks
pytest -m "tasks"

# Skip slow tests for quick feedback
pytest -m "not slow"

# Run authentication-related tests
pytest -m "auth"

# Combine markers
pytest -m "api and not slow"
```

Available markers:
- `unit`: Fast, isolated tests
- `integration`: Database-dependent tests
- `slow`: Long-running tests (>2 seconds)
- `api`: API endpoint tests
- `cli`: CLI command tests
- `models`: Database model tests
- `services`: Service layer tests
- `tasks`: Celery task tests
- `auth`: Authentication/authorization tests
- `smoke`: Basic functionality tests
- `regression`: Bug fix verification tests

## 🔧 Test Utilities

### TestDataFactory

Creates test data with consistent patterns:

```python
from tests.test_utils import TestDataFactory

factory = TestDataFactory()

# Create users
admin = factory.create_user(is_admin=True)
user = factory.create_user(is_admin=False, linkedin_authorized=True)

# Create content
content = factory.create_content(user=admin)
multiple_content = factory.create_multiple_content(10, admin)
```

### Test Mixins

Reusable testing patterns:

```python
# For API response validation
class MyTest(ResponseValidationMixin):
    def test_api_response(self):
        response = client.get("/api/content")
        json_data = assert_json_response(response, 200)
        self.assert_pagination_response_structure(json_data)

# For task status testing
class MyTaskTest(TaskStatusTestMixin):
    def test_task_status(self):
        mock_result = self.create_mock_task_result("SUCCESS", "task123")
        # Use in test...

# For performance testing
class MyPerfTest(PerformanceTestMixin):
    def test_fast_operation(self):
        with self.assert_max_execution_time(1.0):
            # Operation that should complete in <1 second
            pass
```

### Authentication Helpers

```python
from tests.test_utils import AuthenticationTestMixin

# In test
AuthenticationTestMixin.login_user(client, user)
AuthenticationTestMixin.assert_requires_authentication(response)
```

## 🎯 Test Patterns

### 1. Constants Usage

Use centralized constants for maintainability:

```python
from tests.views.test_api import TestConstants

# Instead of magic strings
assert json_data["message"] == TestConstants.CONTENT_GENERATION_STARTED
assert response.status_code == TestConstants.NONEXISTENT_CONTENT_ID
```

### 2. Parametrized Tests

Test multiple scenarios efficiently:

```python
@pytest.mark.parametrize("invalid_platform", [
    "invalid_platform",
    "instagram", 
    "tiktok"
])
def test_invalid_platforms(self, invalid_platform, app, client):
    # Test logic here
    pass
```

### 3. Fixture Usage

Use fixtures for common test setup:

```python
def test_with_admin_user(self, admin_user, app, client):
    # admin_user fixture provides a pre-created admin
    with app.app_context():
        db.session.add(admin_user)
        # ... rest of test
```

### 4. Database Setup Pattern

Standard pattern for database tests:

```python
def test_database_operation(self, app, client):
    unique_id = create_unique_id()
    admin_user = create_admin_user(unique_id)
    
    with app.app_context():
        db.create_all()
        db.session.add(admin_user)
        db.session.commit()
        
        # Create test data
        content = create_test_content(unique_id, submitted_by_user=admin_user)
        db.session.add(content)
        db.session.commit()
        
        # Perform authentication
        login_user(client, admin_user)
        
        # Test the actual functionality
        response = client.get(f"/api/content/{content.id}")
        json_data = assert_json_response(response, 200)
```

##  Running Tests

### The `flask test` Command

The AI Promoter project includes a custom `flask test` command that provides several advantages over running pytest directly:

**Benefits:**
- ✅ **Automatic Environment Setup**: Sets `TESTING=true` and configures test database
- ✅ **Built-in Coverage**: Enables coverage reporting by default with multiple formats
- ✅ **Consistent Configuration**: Ensures all developers use the same test settings
- ✅ **Enhanced Reporting**: Provides colorized output and helpful error messages
- ✅ **Simplified Workflow**: Single command for most testing needs

**Important Note:**
The `TESTING=true` environment variable must be set before running `flask test` to allow the Flask app to initialize properly:

```bash
# Required: Set TESTING environment variable
export TESTING=true

# Then run tests normally
flask test
```

**Available Options:**
```bash
flask test --help           # Show all available options
flask test                  # Run all tests with coverage
flask test -v               # Verbose output
flask test -k keyword       # Run tests matching keyword
flask test -m marker        # Run tests with specific marker
flask test --no-cov         # Disable coverage reporting
flask test --fail-fast      # Stop on first failure
flask test --cov-report=xml # Specify coverage report format
```

**When to use `pytest` directly:**
- For advanced debugging flags like `--pdb`, `--lf`, `-s`
- For pytest-specific options not exposed by `flask test`
- For IDE integration that expects direct pytest commands

### Development Workflow

**One-time setup for your terminal session:**
```bash
# Set this once per terminal session
export TESTING=true
```

**Then run tests as needed:**
```bash
# Quick feedback loop - unit tests only
flask test -m "unit"

# API tests during API development
flask test -m "api" -v

# Full test suite before committing
flask test

# Performance tests
flask test -m "slow" -v

# Skip slow tests for quick feedback
flask test -m "not slow"

# Run tests related to Celery tasks
flask test -m "tasks"

# Run authentication-related tests
flask test -m "auth"

# Combine markers
flask test -m "api and not slow"

# Specific test file
flask test tests/views/test_api.py

# Specific test class
flask test -k "TestContentGenerationIntegration"

# Specific test method
flask test -k "test_generate_content_success_default_platform"

# Run tests matching keyword
flask test -k "content"

# Stop on first failure
flask test --fail-fast

# Disable coverage reporting for faster execution
flask test --no-cov
```

**Alternative: Inline environment variable (for single commands):**
```bash
# Use inline environment variable for one-off commands
TESTING=true flask test -m "api" -v
```

### CI/CD Integration

```yaml
# Example GitHub Actions workflow
- name: Run Unit Tests
  env:
    TESTING: true
  run: flask test -m "unit"

- name: Run Integration Tests
  env:
    TESTING: true
  run: flask test -m "integration"

- name: Run API Tests
  env:
    TESTING: true
  run: flask test -m "api" -v

- name: Run Smoke Tests
  env:
    TESTING: true
  run: flask test -m "smoke"

- name: Full Test Suite with Coverage
  env:
    TESTING: true
  run: flask test --cov-report=xml

- name: Performance Tests
  env:
    TESTING: true
  run: flask test -m "slow" -v
```

**Alternative: Set environment variable once for the entire job:**
```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    env:
      TESTING: true
    steps:
      - name: Run Unit Tests
        run: flask test -m "unit"
      
      - name: Run Integration Tests
        run: flask test -m "integration"
      
      # ... other test steps
```

## 📊 Performance Considerations

### Test Performance Guidelines

- **Unit tests**: Should complete in <0.1 seconds each
- **Integration tests**: Should complete in <2 seconds each
- **Slow tests**: Mark with `@pytest.mark.slow` if >2 seconds
- **Database tests**: Use transactions and rollback when possible

### Performance Testing

```python
from tests.test_utils import PerformanceTestMixin

class TestPerformance(PerformanceTestMixin):
    def test_api_performance(self):
        with self.assert_max_execution_time(1.0):
            response = client.get("/api/content?page=1&per_page=100")
            assert response.status_code == 200

    @performance_test(0.5)  # Must complete in <0.5 seconds
    def test_fast_operation(self):
        # Test implementation
        pass
```

## 🔍 Debugging Tests

### Common Issues

1. **Database state conflicts**: Use unique IDs and clear database state
2. **Session management**: Ensure proper Flask app context usage
3. **Mock conflicts**: Reset mocks between tests
4. **Authentication state**: Clear sessions between tests

### Debug Commands

```bash
# Note: Set TESTING=true first: export TESTING=true

# Run with verbose output
flask test -v

# Run with specific coverage reporting
flask test --cov-report=html

# Stop on first failure for quick debugging
flask test --fail-fast

# Run specific test with verbose output
flask test -k "test_name" -v

# Disable coverage for faster debugging iterations
flask test --no-cov -v

# Inline environment variable for one-off debugging
TESTING=true flask test -k "failing_test" -v --fail-fast

# Use pytest directly for advanced debugging options (no TESTING env needed)
pytest -v --tb=long        # Verbose with long tracebacks
pytest --pdb              # Drop into debugger on failure
pytest --lf               # Run last failed tests only  
pytest -s                 # Show print statements
```

## 🏅 Best Practices

### DO ✅

- Use descriptive test names that explain what is being tested
- Use constants instead of magic strings
- Use parametrized tests for multiple similar scenarios
- Use appropriate test markers for categorization
- Use fixtures for common setup patterns
- Use helper methods for common assertions
- Keep tests focused and testing one thing
- Use proper database isolation patterns

### DON'T ❌

- Don't use hardcoded IDs that might conflict
- Don't leave database state between tests
- Don't test multiple unrelated things in one test
- Don't use overly complex test setup
- Don't skip proper error testing
- Don't forget to test edge cases and error conditions

### Example: Well-Structured Test

```python
@pytest.mark.integration
@pytest.mark.api
class TestContentCRUD(ResponseValidationMixin):
    """Integration tests for content CRUD operations."""

    def test_create_content_success(self, app, client):
        """Test successful content creation by admin user."""
        # Arrange
        unique_id = create_unique_id()
        admin_user = create_admin_user(unique_id)
        
        with app.app_context():
            db.create_all()
            db.session.add(admin_user)
            db.session.commit()
            
            login_user(client, admin_user)
            
            # Act
            content_data = {
                "title": f"Test Article {unique_id}",
                "url": f"https://example.com/{unique_id}",
                "excerpt": f"Test excerpt {unique_id}"
            }
            response = client.post("/api/content", json=content_data)
            
            # Assert
            json_data = assert_json_response(response, 201)
            self.assert_success_response(json_data, TestConstants.CONTENT_CREATED)
            assert json_data["content"]["title"] == content_data["title"]

    @pytest.mark.parametrize("missing_field", ["title", "url", "excerpt"])
    def test_create_content_missing_fields(self, missing_field, app, client):
        """Test content creation fails with missing required fields."""
        # Test implementation...
```

## 🔄 Migration Guide

If updating existing tests to use the new patterns:

1. **Add appropriate markers** to test classes
2. **Replace magic strings** with constants from `TestConstants`
3. **Use helper methods** from mixins for common assertions
4. **Convert similar tests** to parametrized tests
5. **Use fixtures** for common setup patterns
6. **Add performance markers** for slow tests

This improved test suite provides better maintainability, consistency, and development experience while ensuring comprehensive coverage of the AI Promoter application. 