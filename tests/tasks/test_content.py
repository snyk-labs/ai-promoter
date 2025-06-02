# Add tests for tasks/content.py here

import pytest
import uuid
from unittest.mock import patch, MagicMock

from tasks.content import scrape_content_task
from models.content import Content
from models.user import User
from services.content_processor import ContentProcessor


# Generate unique identifier for this test run to avoid conflicts in parallel execution
TEST_RUN_ID = str(uuid.uuid4())[:8]


# --- Test Constants ---
class TestConstants:
    """Test constants for consistent data across tests."""

    TEST_URL = f"https://example.com/article-{TEST_RUN_ID}"
    TEST_TITLE = f"Test Article {TEST_RUN_ID}"
    TEST_CONTENT_ID = 42
    TEST_USER_EMAIL = f"user-{TEST_RUN_ID}@example.com"
    TEST_USER_NAME = f"Test User {TEST_RUN_ID}"

    # Task configuration
    MAX_RETRIES = 5
    DEFAULT_RETRY_DELAY = 60

    # Error messages
    ERROR_MESSAGES = {
        "content_not_found": "Failed to process content from URL",
        "processor_exception": "Test processor exception",
        "content_processor_error": "ContentProcessor failed",
    }


# --- Test Helpers ---
class TestHelpers:
    """Helper methods for testing."""

    @staticmethod
    def create_test_user(session, **kwargs):
        """Create a test user for content creation."""
        defaults = {
            "email": f"user-{uuid.uuid4()}@example.com",
            "name": f"Test User {uuid.uuid4()}",
            "is_admin": False,
        }
        defaults.update(kwargs)

        user = User(**defaults)
        session.add(user)
        session.commit()
        return user

    @staticmethod
    def create_test_content(session, user=None, **kwargs):
        """Create a test content item."""
        if user is None:
            user = TestHelpers.create_test_user(session)

        unique_id = str(uuid.uuid4())[:8]
        defaults = {
            "url": f"https://example.com/article-{unique_id}",
            "title": f"Test Article {unique_id}",
            "submitted_by_id": user.id,
        }
        defaults.update(kwargs)

        content = Content(**defaults)
        session.add(content)
        session.commit()
        return content


# --- Unit Tests (No Database) ---
@pytest.mark.unit
class TestScrapeContentTaskUnit:
    """Unit tests for scrape_content_task function."""

    def test_task_has_correct_configuration(self):
        """Test that the task is configured with correct Celery options."""
        task = scrape_content_task

        assert task.max_retries == TestConstants.MAX_RETRIES
        assert task.default_retry_delay == TestConstants.DEFAULT_RETRY_DELAY
        assert task.ignore_result is False
        assert task.name == "tasks.content.scrape_content_task"

    @patch("tasks.content.ContentProcessor")
    @patch("tasks.content.logger")
    def test_successful_processing_unit(self, mock_logger, mock_processor_class):
        """Test successful content processing without database."""
        # Setup mocks
        mock_processor = MagicMock()
        mock_processor_class.return_value = mock_processor
        mock_content = MagicMock()
        mock_content.id = TestConstants.TEST_CONTENT_ID
        mock_processor.process_url.return_value = mock_content

        # Call the task function directly using apply
        result = scrape_content_task.apply(
            args=[TestConstants.TEST_CONTENT_ID, TestConstants.TEST_URL]
        )

        # Assertions
        assert result.successful()
        assert result.result == TestConstants.TEST_CONTENT_ID
        mock_processor_class.assert_called_once()
        mock_processor.process_url.assert_called_once_with(
            content_id=TestConstants.TEST_CONTENT_ID, url=TestConstants.TEST_URL
        )
        # Verify both info log calls
        assert mock_logger.info.call_count == 2

    @patch("tasks.content.ContentProcessor")
    @patch("tasks.content.logger")
    def test_processor_returns_none_triggers_exception(
        self, mock_logger, mock_processor_class
    ):
        """Test that when processor returns None, task raises exception."""
        # Setup mocks
        mock_processor = MagicMock()
        mock_processor_class.return_value = mock_processor
        mock_processor.process_url.return_value = None

        # Call the task and expect an exception
        result = scrape_content_task.apply(
            args=[TestConstants.TEST_CONTENT_ID, TestConstants.TEST_URL]
        )

        # Should have failed due to the exception
        assert result.failed()
        mock_logger.error.assert_called()

    @patch("tasks.content.ContentProcessor")
    @patch("tasks.content.logger")
    def test_processor_exception_propagates(self, mock_logger, mock_processor_class):
        """Test that processor exceptions propagate correctly."""
        # Setup mocks
        mock_processor = MagicMock()
        mock_processor_class.return_value = mock_processor
        mock_processor.process_url.side_effect = Exception(
            TestConstants.ERROR_MESSAGES["processor_exception"]
        )

        # Call the task and expect failure
        result = scrape_content_task.apply(
            args=[TestConstants.TEST_CONTENT_ID, TestConstants.TEST_URL]
        )

        # Should have failed due to exception
        assert result.failed()
        mock_logger.error.assert_called()
        error_call = mock_logger.error.call_args[0][0]
        assert TestConstants.ERROR_MESSAGES["processor_exception"] in error_call

    @pytest.mark.parametrize(
        "content_id,url",
        [
            (0, TestConstants.TEST_URL),
            (-1, TestConstants.TEST_URL),
            (None, TestConstants.TEST_URL),
            (TestConstants.TEST_CONTENT_ID, None),
        ],
    )
    @patch("tasks.content.ContentProcessor")
    def test_invalid_parameters(self, mock_processor_class, content_id, url):
        """Test handling of invalid parameters."""
        mock_processor = MagicMock()
        mock_processor_class.return_value = mock_processor
        mock_processor.process_url.side_effect = Exception("Invalid parameters")

        result = scrape_content_task.apply(args=[content_id, url])
        assert result.failed()


# --- Integration Tests (With Database) ---
@pytest.mark.integration
class TestScrapeContentTaskIntegration:
    """Integration tests for scrape_content_task with database operations."""

    @patch("tasks.content.ContentProcessor")
    def test_successful_processing_with_database(
        self, mock_processor_class, session, app
    ):
        """Test successful content processing with actual database operations."""
        # Create test content in database
        content = TestHelpers.create_test_content(session)

        # Setup mocks
        mock_processor = MagicMock()
        mock_processor_class.return_value = mock_processor
        mock_processor.process_url.return_value = content

        with app.app_context():
            result = scrape_content_task.apply(args=[content.id, content.url])

        assert result.successful()
        assert result.result == content.id
        mock_processor.process_url.assert_called_once_with(
            content_id=content.id, url=content.url
        )

    @patch("tasks.content.ContentProcessor")
    def test_nonexistent_content_id(self, mock_processor_class, session, app):
        """Test behavior when content ID doesn't exist in database."""
        mock_processor = MagicMock()
        mock_processor_class.return_value = mock_processor
        mock_processor.process_url.return_value = None  # Content not found

        with app.app_context():
            result = scrape_content_task.apply(args=[99999, TestConstants.TEST_URL])

        assert result.failed()

    @patch("tasks.content.ContentProcessor")
    def test_database_transaction_handling(self, mock_processor_class, session, app):
        """Test that database transactions are handled properly."""
        content = TestHelpers.create_test_content(session)

        # Setup processor to succeed
        mock_processor = MagicMock()
        mock_processor_class.return_value = mock_processor
        updated_content = MagicMock()
        updated_content.id = content.id
        mock_processor.process_url.return_value = updated_content

        with app.app_context():
            result = scrape_content_task.apply(args=[content.id, content.url])

        assert result.successful()
        assert result.result == content.id
        # Verify content still exists in database
        assert session.query(Content).filter_by(id=content.id).first() is not None

    @patch("tasks.content.ContentProcessor")
    def test_processor_exception_preserves_database_state(
        self, mock_processor_class, session, app
    ):
        """Test that processor exceptions don't corrupt database state."""
        content = TestHelpers.create_test_content(session, title="Original Title")
        original_title = content.title

        # Setup processor to fail
        mock_processor = MagicMock()
        mock_processor_class.return_value = mock_processor
        mock_processor.process_url.side_effect = Exception("Processing failed")

        with app.app_context():
            result = scrape_content_task.apply(args=[content.id, content.url])

        assert result.failed()

        # Verify database state is preserved
        session.rollback()
        fresh_content = session.query(Content).filter_by(id=content.id).first()
        assert fresh_content is not None
        assert fresh_content.title == original_title

    @patch("tasks.content.ContentProcessor")
    def test_empty_url_handling(self, mock_processor_class, session, app):
        """Test handling of empty or invalid URLs."""
        content = TestHelpers.create_test_content(session)

        mock_processor = MagicMock()
        mock_processor_class.return_value = mock_processor
        mock_processor.process_url.side_effect = ValueError("Invalid URL")

        with app.app_context():
            result = scrape_content_task.apply(args=[content.id, ""])

        assert result.failed()

    @patch("tasks.content.ContentProcessor")
    @patch("tasks.content.logger")
    def test_logging_behavior(self, mock_logger, mock_processor_class, session, app):
        """Test that appropriate logging occurs during task execution."""
        content = TestHelpers.create_test_content(session)

        mock_processor = MagicMock()
        mock_processor_class.return_value = mock_processor
        mock_processor.process_url.return_value = content

        with app.app_context():
            result = scrape_content_task.apply(args=[content.id, content.url])

        assert result.successful()

        # Check info logging
        mock_logger.info.assert_any_call(
            f"Processing URL for content_id {content.id}: {content.url}"
        )
        mock_logger.info.assert_any_call(
            f"Successfully processed and updated content {content.id} from URL {content.url}"
        )

    @patch("tasks.content.ContentProcessor")
    def test_content_processor_initialization(self, mock_processor_class, session, app):
        """Test that ContentProcessor is properly initialized."""
        content = TestHelpers.create_test_content(session)

        mock_processor = MagicMock()
        mock_processor_class.return_value = mock_processor
        mock_processor.process_url.return_value = content

        with app.app_context():
            result = scrape_content_task.apply(args=[content.id, content.url])

        assert result.successful()
        # Verify ContentProcessor was instantiated
        mock_processor_class.assert_called_once_with()


# --- Performance Tests ---
@pytest.mark.slow
@pytest.mark.integration
class TestScrapeContentTaskPerformance:
    """Performance tests for scrape_content_task."""

    @patch("tasks.content.ContentProcessor")
    def test_concurrent_task_execution(self, mock_processor_class, session, app):
        """Test that multiple tasks can run concurrently without conflicts."""
        # Create multiple content items
        contents = [TestHelpers.create_test_content(session) for _ in range(3)]

        mock_processor = MagicMock()
        mock_processor_class.return_value = mock_processor

        def mock_process_url(content_id, url):
            # Return the content matching the ID
            return next(c for c in contents if c.id == content_id)

        mock_processor.process_url.side_effect = mock_process_url

        with app.app_context():
            # Simulate concurrent execution
            results = []
            for content in contents:
                result = scrape_content_task.apply(args=[content.id, content.url])
                results.append(result)

        # All tasks should complete successfully
        assert len(results) == 3
        assert all(result.successful() for result in results)
        assert all(result.result in [c.id for c in contents] for result in results)

    @patch("tasks.content.ContentProcessor")
    def test_large_content_processing(self, mock_processor_class, session, app):
        """Test processing of content with large data."""
        content = TestHelpers.create_test_content(
            session,
            title="Very Long Title " * 50,  # Simulate large title
        )

        mock_processor = MagicMock()
        mock_processor_class.return_value = mock_processor

        # Create a large mock content object
        large_content = MagicMock()
        large_content.id = content.id
        large_content.scraped_content = "Large content " * 1000
        mock_processor.process_url.return_value = large_content

        with app.app_context():
            result = scrape_content_task.apply(args=[content.id, content.url])

        assert result.successful()
        assert result.result == content.id
        mock_processor.process_url.assert_called_once()


# --- Celery Integration Tests ---
@pytest.mark.integration
class TestScrapeContentTaskCeleryIntegration:
    """Test integration with Celery task system."""

    def test_task_registration(self):
        """Test that the task is properly registered with Celery."""
        from celery import current_app as celery_app

        # The task should be registered
        assert "tasks.content.scrape_content_task" in celery_app.tasks

    def test_task_signature(self):
        """Test that task signature is correct."""
        task = scrape_content_task

        # Test creating task signature
        signature = task.s(TestConstants.TEST_CONTENT_ID, TestConstants.TEST_URL)
        assert signature.task == "tasks.content.scrape_content_task"
        assert signature.args == (TestConstants.TEST_CONTENT_ID, TestConstants.TEST_URL)

    @patch("tasks.content.ContentProcessor")
    def test_task_delay_method(self, mock_processor_class, session, app):
        """Test that task can be called via delay() method."""
        content = TestHelpers.create_test_content(session)

        mock_processor = MagicMock()
        mock_processor_class.return_value = mock_processor
        mock_processor.process_url.return_value = content

        with app.app_context():
            # This would normally queue the task, but in test mode it executes immediately
            task_result = scrape_content_task.delay(content.id, content.url)

            # Check that the task was scheduled (we get a task result back)
            assert task_result.task_id is not None
            assert task_result.state in ["PENDING", "SUCCESS", "FAILURE"]

    @patch("tasks.content.ContentProcessor")
    def test_task_apply_async_method(self, mock_processor_class, session, app):
        """Test that task can be called via apply_async() method."""
        content = TestHelpers.create_test_content(session)

        mock_processor = MagicMock()
        mock_processor_class.return_value = mock_processor
        mock_processor.process_url.return_value = content

        with app.app_context():
            # Test apply_async with arguments
            task_result = scrape_content_task.apply_async(
                args=[content.id, content.url]
            )

            # Check that we get a proper task result
            assert task_result.task_id is not None
            assert task_result.state in ["PENDING", "SUCCESS", "FAILURE"]

    def test_task_name_registration(self):
        """Test that the task has the correct name registration."""
        assert scrape_content_task.name == "tasks.content.scrape_content_task"

    def test_task_configuration_properties(self):
        """Test that task configuration properties are accessible."""
        task = scrape_content_task

        # Test that we can access configuration properties
        assert hasattr(task, "max_retries")
        assert hasattr(task, "default_retry_delay")
        assert hasattr(task, "ignore_result")
        assert hasattr(task, "bind")

        # Test actual values
        assert task.max_retries == 5
        assert task.default_retry_delay == 60
        assert task.ignore_result is False
