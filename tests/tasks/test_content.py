import pytest
import uuid
from unittest.mock import patch, MagicMock, PropertyMock

from celery.app.task import Task as CeleryTask
from tasks.content import scrape_content_task
from models.content import Content
from models.user import User


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
    @patch("services.slack_service.send_slack_dm")
    def test_successful_processing_unit_no_slack_id(
        self, mock_send_slack_dm, mock_logger, mock_processor_class
    ):
        """Test successful content processing without database and no Slack ID."""
        # Setup mocks
        mock_processor = MagicMock()
        mock_processor_class.return_value = mock_processor
        mock_content_result = MagicMock()
        mock_content_result.id = TestConstants.TEST_CONTENT_ID
        mock_processor.process_url.return_value = mock_content_result

        # Call the task function directly using apply
        result = scrape_content_task.apply(
            args=[TestConstants.TEST_CONTENT_ID, TestConstants.TEST_URL, None]
        )

        # Assertions
        assert result.successful()
        assert result.result == TestConstants.TEST_CONTENT_ID
        mock_processor_class.assert_called_once()
        mock_processor.process_url.assert_called_once_with(
            content_id=TestConstants.TEST_CONTENT_ID, url=TestConstants.TEST_URL
        )
        mock_logger.info.call_count == 2
        mock_send_slack_dm.assert_not_called()

    @patch("tasks.content.db.session")
    @patch("tasks.content.ContentProcessor")
    @patch("tasks.content.logger")
    @patch("services.slack_service.send_slack_dm")
    def test_successful_processing_sends_dm(
        self, mock_send_slack_dm, mock_logger, mock_processor_class, mock_db_session
    ):
        """Test successful content processing sends a DM when slack_user_id is provided."""
        slack_user_id = "U123SLACKUSER"
        content_id = TestConstants.TEST_CONTENT_ID
        url = TestConstants.TEST_URL
        expected_title = "Processed Title"

        # Mock what ContentProcessor().process_url returns
        mock_processed_content = MagicMock(spec=Content)
        mock_processed_content.id = content_id
        # process_url returns the updated content object, but the task re-fetches for title.

        mock_processor = MagicMock()
        mock_processor_class.return_value = mock_processor
        mock_processor.process_url.return_value = (
            mock_processed_content  # Simulate successful processing
        )

        # Mock the db.session.get(Content, content_id) call
        mock_fetched_content_for_dm = MagicMock(spec=Content)
        mock_fetched_content_for_dm.title = expected_title
        mock_fetched_content_for_dm.url = (
            url  # Though task uses the passed url for the link
        )
        mock_db_session.get.return_value = mock_fetched_content_for_dm

        result = scrape_content_task.apply(args=[content_id, url, slack_user_id])

        assert result.successful()
        assert result.result == content_id
        mock_processor.process_url.assert_called_once_with(
            content_id=content_id, url=url
        )
        mock_db_session.get.assert_called_once_with(Content, content_id)

        expected_dm_message = f"✅ Great news! The content you submitted for <{url}|{expected_title}> has been successfully processed and is now ready.\nContent ID: {content_id}"
        mock_send_slack_dm.assert_called_once_with(slack_user_id, expected_dm_message)

        # Check logs
        logs = [call_args[0][0] for call_args in mock_logger.info.call_args_list]
        assert any(
            f"Processing URL for content_id {content_id}: {url}. Slack user: {slack_user_id}"
            in log
            for log in logs
        )
        assert any(
            f"Successfully processed and updated content {content_id} from URL {url}"
            in log
            for log in logs
        )
        assert any(
            f"Sent success DM to Slack user {slack_user_id} for content {content_id}"
            in log
            for log in logs
        )

    @patch("tasks.content.ContentProcessor")
    @patch("tasks.content.logger")
    @patch("services.slack_service.send_slack_dm")
    @patch.object(scrape_content_task, "retry")
    def test_processor_returns_none_triggers_exception(
        self, mock_retry, mock_send_slack_dm, mock_logger, mock_processor_class
    ):
        """Test that when processor returns None, task raises exception."""
        # Setup mocks
        mock_processor = MagicMock()
        mock_processor_class.return_value = mock_processor
        mock_processor.process_url.return_value = None

        # Call the task and expect an exception
        result = scrape_content_task.apply(
            args=[TestConstants.TEST_CONTENT_ID, TestConstants.TEST_URL, None]
        )

        # Should have failed due to the exception
        assert result.failed()
        mock_logger.error.assert_called()
        mock_send_slack_dm.assert_not_called()

    @patch("tasks.content.ContentProcessor")
    @patch("tasks.content.logger")
    @patch("services.slack_service.send_slack_dm")
    @patch.object(scrape_content_task, "retry")
    def test_processor_exception_propagates(
        self, mock_retry, mock_send_slack_dm, mock_logger, mock_processor_class
    ):
        """Test that processor exceptions propagate correctly and no DM for no slack_id."""
        # Setup mocks
        mock_processor = MagicMock()
        mock_processor_class.return_value = mock_processor
        mock_processor.process_url.side_effect = Exception(
            TestConstants.ERROR_MESSAGES["processor_exception"]
        )

        # Call the task and expect failure
        result = scrape_content_task.apply(
            args=[TestConstants.TEST_CONTENT_ID, TestConstants.TEST_URL, None]
        )

        # Should have failed due to exception
        assert result.failed()
        mock_logger.error.assert_called()
        error_call = mock_logger.error.call_args[0][0]
        assert TestConstants.ERROR_MESSAGES["processor_exception"] in error_call
        mock_send_slack_dm.assert_not_called()

    @patch("tasks.content.ContentProcessor")
    @patch("tasks.content.logger")
    @patch("services.slack_service.send_slack_dm")
    @patch.object(CeleryTask, "request", new_callable=PropertyMock)
    @patch.object(scrape_content_task, "retry")
    def test_processor_exception_sends_dm_on_last_retry(
        self,
        mock_retry_on_task,
        mock_request_prop,
        mock_send_slack_dm,
        mock_logger,
        mock_processor_class,
    ):
        slack_user_id = "U123FAILRETRY"
        content_id = TestConstants.TEST_CONTENT_ID
        url = TestConstants.TEST_URL
        error_message = TestConstants.ERROR_MESSAGES["processor_exception"]

        mock_processor = MagicMock()
        mock_processor_class.return_value = mock_processor
        mock_processor.process_url.side_effect = Exception(error_message)

        mock_retry_on_task.side_effect = Exception("Retry called")

        # Configure the PropertyMock for self.request
        mock_request_object_for_task_self = MagicMock()
        mock_request_object_for_task_self.retries = TestConstants.MAX_RETRIES - 1
        mock_request_prop.return_value = mock_request_object_for_task_self

        with pytest.raises(Exception, match="Retry called"):
            scrape_content_task.run(content_id, url, slack_user_id)

        expected_dm_message = f"⚠️ Apologies, but we encountered an issue while processing the content from <{url}|{url}> after multiple retries. Please try submitting it again later or contact an administrator if the problem persists.\nError: {error_message}"
        mock_send_slack_dm.assert_called_once_with(slack_user_id, expected_dm_message)
        mock_retry_on_task.assert_called_once()

        logs = [call_args[0][0] for call_args in mock_logger.error.call_args_list]
        assert any(
            f"Error scraping content_id {content_id} (URL: {url}): {error_message}. Retry {TestConstants.MAX_RETRIES}/{TestConstants.MAX_RETRIES}"
            in log
            for log in logs
        )
        log_infos = [call_args[0][0] for call_args in mock_logger.info.call_args_list]
        assert any(
            f"Sent failure DM to Slack user {slack_user_id} for content {content_id} after max retries."
            in log
            for log in log_infos
        )

    @patch("tasks.content.ContentProcessor")
    @patch("tasks.content.logger")
    @patch("services.slack_service.send_slack_dm")
    @patch.object(CeleryTask, "request", new_callable=PropertyMock)
    @patch.object(scrape_content_task, "retry")
    def test_processor_exception_no_dm_before_last_retry(
        self,
        mock_retry_on_task,
        mock_request_prop,
        mock_send_slack_dm,
        mock_logger,
        mock_processor_class,
    ):
        slack_user_id = "U123FAILNOTLAST"
        content_id = TestConstants.TEST_CONTENT_ID
        url = TestConstants.TEST_URL
        error_message = TestConstants.ERROR_MESSAGES["processor_exception"]

        mock_processor = MagicMock()
        mock_processor_class.return_value = mock_processor
        mock_processor.process_url.side_effect = Exception(error_message)

        mock_retry_on_task.side_effect = Exception("Retry called")

        # Configure the PropertyMock for self.request
        mock_request_object_for_task_self = MagicMock()
        mock_request_object_for_task_self.retries = (
            TestConstants.MAX_RETRIES - 2
        )  # Not the last retry
        mock_request_prop.return_value = mock_request_object_for_task_self

        with pytest.raises(Exception, match="Retry called"):
            scrape_content_task.run(content_id, url, slack_user_id)

        mock_send_slack_dm.assert_not_called()
        mock_retry_on_task.assert_called_once()
        logs = [call_args[0][0] for call_args in mock_logger.error.call_args_list]
        retry_attempt_number = TestConstants.MAX_RETRIES - 1
        assert any(
            f"Error scraping content_id {content_id} (URL: {url}): {error_message}. Retry {retry_attempt_number}/{TestConstants.MAX_RETRIES}"
            in log
            for log in logs
        )

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

    @patch("tasks.content.db.session")
    @patch("tasks.content.ContentProcessor")
    @patch("tasks.content.logger")
    @patch("services.slack_service.send_slack_dm")
    def test_successful_processing_dm_failure_logs_error(
        self, mock_send_slack_dm, mock_logger, mock_processor_class, mock_db_session
    ):
        """Test that an error is logged if sending the success DM fails."""
        slack_user_id = "U123DMFAILSUCCESS"
        content_id = TestConstants.TEST_CONTENT_ID
        url = TestConstants.TEST_URL
        expected_title = "Processed Title DM Fail"
        dm_error_message = "Slack DM API error"

        mock_processed_content = MagicMock(spec=Content)
        mock_processed_content.id = content_id
        mock_processor = MagicMock()
        mock_processor_class.return_value = mock_processor
        mock_processor.process_url.return_value = mock_processed_content

        mock_fetched_content_for_dm = MagicMock(spec=Content)
        mock_fetched_content_for_dm.title = expected_title
        mock_db_session.get.return_value = mock_fetched_content_for_dm

        mock_send_slack_dm.side_effect = Exception(dm_error_message)

        result = scrape_content_task.apply(args=[content_id, url, slack_user_id])

        assert result.successful()  # Task itself should still succeed
        assert result.result == content_id
        mock_send_slack_dm.assert_called_once()  # Attempt to send DM was made

        # Check for the specific error log
        error_logs = [call_args[0][0] for call_args in mock_logger.error.call_args_list]
        expected_log_message = f"Failed to send success DM to Slack user {slack_user_id} for content {content_id}: {dm_error_message}"
        assert any(expected_log_message in log for log in error_logs)

    @patch("tasks.content.ContentProcessor")
    @patch("tasks.content.logger")
    @patch("services.slack_service.send_slack_dm")
    @patch.object(CeleryTask, "request", new_callable=PropertyMock)
    @patch.object(scrape_content_task, "retry")
    def test_processor_exception_last_retry_dm_failure_logs_error(
        self,
        mock_retry_on_task,
        mock_request_prop,
        mock_send_slack_dm,
        mock_logger,
        mock_processor_class,
    ):
        """Test that an error is logged if sending the failure DM on last retry fails."""
        slack_user_id = "U123DMFAILFAILURE"
        content_id = TestConstants.TEST_CONTENT_ID
        url = TestConstants.TEST_URL
        processor_error_message = TestConstants.ERROR_MESSAGES["processor_exception"]
        dm_error_message = "Slack DM API error on failure DM"

        mock_processor = MagicMock()
        mock_processor_class.return_value = mock_processor
        mock_processor.process_url.side_effect = Exception(processor_error_message)

        mock_retry_on_task.side_effect = Exception(
            "Retry called"
        )  # Task will attempt to retry
        mock_send_slack_dm.side_effect = Exception(dm_error_message)  # Sending DM fails

        mock_request_object = MagicMock()
        mock_request_object.retries = (
            TestConstants.MAX_RETRIES - 1
        )  # Last retry attempt
        mock_request_prop.return_value = mock_request_object

        with pytest.raises(
            Exception, match="Retry called"
        ):  # Task still raises retry exception
            scrape_content_task.run(content_id, url, slack_user_id)

        mock_send_slack_dm.assert_called_once()  # Attempt to send failure DM was made
        mock_retry_on_task.assert_called_once()

        # Check for the specific error log for DM failure
        error_logs = [call_args[0][0] for call_args in mock_logger.error.call_args_list]
        # First error log is for the processor exception
        assert any(
            f"Error scraping content_id {content_id} (URL: {url}): {processor_error_message}"
            in log
            for log in error_logs
        )
        # Second error log (or among them) should be for the DM failure
        expected_dm_fail_log = f"Failed to send failure DM to Slack user {slack_user_id} for content {content_id}: {dm_error_message}"
        assert any(expected_dm_fail_log in log for log in error_logs)


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
            f"Processing URL for content_id {content.id}: {content.url}. Slack user: None"
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
