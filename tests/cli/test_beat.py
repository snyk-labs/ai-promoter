"""
Tests for the CLI beat commands.

This module tests the beat CLI commands which are responsible for:
1. Running the Celery beat scheduler (beat command)
2. Manually triggering the initiate_posts task (trigger-posts command)
3. Manually triggering the fetch_content_task (trigger-fetch-content command)

Test Organization:
- TestBeatCommand: Tests for the main 'beat' command
- TestTriggerPostsCommand: Tests for the 'trigger-posts' command
- TestTriggerFetchContentCommand: Tests for the 'trigger-fetch-content' command
- TestBeatCommandsIntegration: Integration tests across all commands

Test Markers:
- unit: Unit tests that test individual functions in isolation
- integration: Integration tests that test multiple components together
- cli: Tests specifically for CLI command functionality

Example usage:
    # Run all beat tests
    pytest tests/cli/test_beat.py -v

    # Run with coverage
    pytest tests/cli/test_beat.py --cov=cli.beat --cov-report=term-missing

    # Run specific test
    pytest tests/cli/test_beat.py::TestBeatCommand::test_beat_command_exists -v

    # Run only unit tests
    pytest tests/cli/test_beat.py -m unit -v

    # Run only integration tests
    pytest tests/cli/test_beat.py -m integration -v
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner

from cli.beat import beat_command, trigger_posts_command, trigger_fetch_content_command


# Constants for repeated strings to improve maintainability
class TestMessages:
    """Constants for expected test messages."""

    TASK_TRIGGERED = "Task triggered! Task ID:"
    TASK_STATUS_CHECK = "You can check the task status in the Celery worker logs."
    BEAT_HELP_TEXT = "Run the Celery beat scheduler"
    TRIGGER_POSTS_HELP_TEXT = "Manually trigger the initiate_posts task for testing"
    TRIGGER_FETCH_CONTENT_HELP_TEXT = (
        "Manually trigger the fetch_content_task for testing"
    )


class BeatTestHelpers:
    """Helper methods for beat command testing."""

    @staticmethod
    def create_mock_celery_instance():
        """Create a properly configured mock Celery instance."""
        mock_celery = Mock()
        mock_beat = Mock()
        mock_celery.Beat.return_value = mock_beat
        return mock_celery, mock_beat

    @staticmethod
    def create_mock_task_result(task_id: str):
        """Create a mock task result with the specified ID."""
        mock_result = Mock()
        mock_result.id = task_id
        return mock_result

    @staticmethod
    def setup_celery_extension_mock(mock_current_app, celery_instance=None):
        """Setup the current_app.extensions mock with Celery instance."""
        if celery_instance is None:
            celery_instance, _ = BeatTestHelpers.create_mock_celery_instance()
        mock_current_app.extensions = {"celery": celery_instance}
        return celery_instance

    @staticmethod
    def assert_command_success(result, expected_output_fragments=None):
        """Assert that a CLI command executed successfully."""
        assert result.exit_code == 0
        if expected_output_fragments:
            for fragment in expected_output_fragments:
                assert fragment in result.output

    @staticmethod
    def assert_command_failure(result):
        """Assert that a CLI command failed as expected."""
        assert result.exit_code != 0
        assert result.exception is not None


# Pytest fixtures for common test setup
@pytest.fixture
def cli_runner():
    """Provide a Click CLI runner for testing."""
    return CliRunner()


@pytest.fixture
def mock_celery_setup():
    """Provide a mock Celery setup with beat instance."""
    return BeatTestHelpers.create_mock_celery_instance()


@pytest.fixture
def mock_task_result():
    """Provide a factory function for creating mock task results."""
    return BeatTestHelpers.create_mock_task_result


@pytest.mark.cli
@pytest.mark.unit
class TestBeatCommand:
    """Test suite for the beat CLI command."""

    def test_beat_command_exists(self, app, cli_runner):
        """Test that the beat command is properly registered."""
        with app.app_context():
            result = cli_runner.invoke(beat_command, ["--help"])
            BeatTestHelpers.assert_command_success(
                result, [TestMessages.BEAT_HELP_TEXT]
            )

    def test_beat_command_help_text(self, app, cli_runner):
        """Test that the beat command help text is correct."""
        with app.app_context():
            result = cli_runner.invoke(beat_command, ["--help"])
            BeatTestHelpers.assert_command_success(
                result,
                [
                    "Run the Celery beat scheduler",
                    "--loglevel",
                    "Logging level",
                ],
            )

    @patch("cli.beat.current_app")
    def test_beat_command_default_loglevel(
        self, mock_current_app, app, cli_runner, mock_celery_setup
    ):
        """Test beat command with default log level."""
        with app.app_context():
            # Setup mock celery instance
            mock_celery, mock_beat = mock_celery_setup
            BeatTestHelpers.setup_celery_extension_mock(mock_current_app, mock_celery)

            result = cli_runner.invoke(beat_command)

            # Verify command succeeded
            BeatTestHelpers.assert_command_success(result)

            # Verify celery Beat was called with default loglevel
            mock_celery.Beat.assert_called_once_with(loglevel="info")
            mock_beat.run.assert_called_once()

    @patch("cli.beat.current_app")
    def test_beat_command_custom_loglevel(
        self, mock_current_app, app, cli_runner, mock_celery_setup
    ):
        """Test beat command with custom log level."""
        with app.app_context():
            # Setup mock celery instance
            mock_celery, mock_beat = mock_celery_setup
            BeatTestHelpers.setup_celery_extension_mock(mock_current_app, mock_celery)

            result = cli_runner.invoke(beat_command, ["--loglevel", "debug"])

            # Verify command succeeded
            BeatTestHelpers.assert_command_success(result)

            # Verify celery Beat was called with custom loglevel
            mock_celery.Beat.assert_called_once_with(loglevel="debug")
            mock_beat.run.assert_called_once()

    @pytest.mark.parametrize(
        "loglevel", ["debug", "info", "warning", "error", "critical"]
    )
    @patch("cli.beat.current_app")
    def test_beat_command_various_loglevels(
        self, mock_current_app, app, cli_runner, mock_celery_setup, loglevel
    ):
        """Test beat command with various log levels."""
        with app.app_context():
            # Setup mock celery instance
            mock_celery, mock_beat = mock_celery_setup
            BeatTestHelpers.setup_celery_extension_mock(mock_current_app, mock_celery)

            result = cli_runner.invoke(beat_command, ["--loglevel", loglevel])

            # Verify command succeeded
            BeatTestHelpers.assert_command_success(result)

            # Verify celery Beat was called with the specified loglevel
            mock_celery.Beat.assert_called_once_with(loglevel=loglevel)
            mock_beat.run.assert_called_once()

    @patch("cli.beat.current_app")
    def test_beat_command_missing_celery_extension(
        self, mock_current_app, app, cli_runner
    ):
        """Test beat command when celery extension is missing."""
        with app.app_context():
            # Setup mock without celery extension
            mock_current_app.extensions = {}

            result = cli_runner.invoke(beat_command)

            # Verify command failed
            BeatTestHelpers.assert_command_failure(result)

    @patch("cli.beat.current_app")
    def test_beat_command_celery_beat_exception(
        self, mock_current_app, app, cli_runner
    ):
        """Test beat command when celery Beat raises an exception."""
        with app.app_context():
            # Setup mock celery instance that raises an exception
            mock_celery = Mock()
            mock_celery.Beat.side_effect = Exception("Beat initialization failed")
            BeatTestHelpers.setup_celery_extension_mock(mock_current_app, mock_celery)

            result = cli_runner.invoke(beat_command)

            # Verify command failed
            BeatTestHelpers.assert_command_failure(result)

    @patch("cli.beat.current_app")
    def test_beat_command_celery_run_exception(self, mock_current_app, app, cli_runner):
        """Test beat command when celery Beat.run() raises an exception."""
        with app.app_context():
            # Setup mock celery instance where run() raises an exception
            mock_celery = Mock()
            mock_beat = Mock()
            mock_beat.run.side_effect = Exception("Beat run failed")
            mock_celery.Beat.return_value = mock_beat
            BeatTestHelpers.setup_celery_extension_mock(mock_current_app, mock_celery)

            result = cli_runner.invoke(beat_command)

            # Verify command failed
            BeatTestHelpers.assert_command_failure(result)


@pytest.mark.cli
@pytest.mark.unit
class TestTriggerPostsCommand:
    """Test suite for the trigger-posts CLI command."""

    def test_trigger_posts_command_exists(self, app, cli_runner):
        """Test that the trigger-posts command is properly registered."""
        with app.app_context():
            result = cli_runner.invoke(trigger_posts_command, ["--help"])
            BeatTestHelpers.assert_command_success(
                result, [TestMessages.TRIGGER_POSTS_HELP_TEXT]
            )

    def test_trigger_posts_command_help_text(self, app, cli_runner):
        """Test that the trigger-posts command help text is correct."""
        with app.app_context():
            result = cli_runner.invoke(trigger_posts_command, ["--help"])
            BeatTestHelpers.assert_command_success(
                result, ["Manually trigger the initiate_posts task for testing"]
            )

    @patch("cli.beat.initiate_posts")
    def test_trigger_posts_command_success(
        self, mock_initiate_posts, app, cli_runner, mock_task_result
    ):
        """Test successful execution of trigger-posts command."""
        with app.app_context():
            # Setup mock task result
            task_id = "test-task-id-12345"
            mock_result = mock_task_result(task_id)
            mock_initiate_posts.delay.return_value = mock_result

            result = cli_runner.invoke(trigger_posts_command)

            # Verify command succeeded
            BeatTestHelpers.assert_command_success(
                result,
                [
                    TestMessages.TASK_TRIGGERED,
                    task_id,
                    TestMessages.TASK_STATUS_CHECK,
                ],
            )

            # Verify the task was triggered
            mock_initiate_posts.delay.assert_called_once()

    @patch("cli.beat.initiate_posts")
    def test_trigger_posts_command_task_exception(
        self, mock_initiate_posts, app, cli_runner
    ):
        """Test trigger-posts command when task.delay() raises an exception."""
        with app.app_context():
            # Setup mock to raise an exception
            mock_initiate_posts.delay.side_effect = Exception("Task dispatch failed")

            result = cli_runner.invoke(trigger_posts_command)

            # Verify command failed
            BeatTestHelpers.assert_command_failure(result)

    @patch("cli.beat.initiate_posts")
    @patch("cli.beat.click.echo")
    def test_trigger_posts_command_output_format(
        self, mock_echo, mock_initiate_posts, app, cli_runner, mock_task_result
    ):
        """Test that trigger-posts command outputs are properly formatted."""
        with app.app_context():
            # Setup mock task result
            task_id = "formatted-task-id"
            mock_result = mock_task_result(task_id)
            mock_initiate_posts.delay.return_value = mock_result

            result = cli_runner.invoke(trigger_posts_command)

            # Verify command succeeded
            BeatTestHelpers.assert_command_success(result)

            # Verify click.echo was called with correct messages
            assert mock_echo.call_count == 2
            mock_echo.assert_any_call(f"Task triggered! Task ID: {task_id}")
            mock_echo.assert_any_call(TestMessages.TASK_STATUS_CHECK)

    @patch("cli.beat.initiate_posts")
    def test_trigger_posts_command_preserves_app_context(
        self, mock_initiate_posts, app, cli_runner, mock_task_result
    ):
        """Test that trigger-posts command preserves Flask app context."""
        with app.app_context():
            # Setup mock task result
            mock_result = mock_task_result("context-test-id")
            mock_initiate_posts.delay.return_value = mock_result

            result = cli_runner.invoke(trigger_posts_command)

            # Verify command succeeded and context is preserved
            BeatTestHelpers.assert_command_success(result)
            # The @with_appcontext decorator should ensure the app context is available
            mock_initiate_posts.delay.assert_called_once()


@pytest.mark.cli
@pytest.mark.unit
class TestTriggerFetchContentCommand:
    """Test suite for the trigger-fetch-content CLI command."""

    def test_trigger_fetch_content_command_exists(self, app, cli_runner):
        """Test that the trigger-fetch-content command is properly registered."""
        with app.app_context():
            result = cli_runner.invoke(trigger_fetch_content_command, ["--help"])
            BeatTestHelpers.assert_command_success(
                result, [TestMessages.TRIGGER_FETCH_CONTENT_HELP_TEXT]
            )

    def test_trigger_fetch_content_command_help_text(self, app, cli_runner):
        """Test that the trigger-fetch-content command help text is correct."""
        with app.app_context():
            result = cli_runner.invoke(trigger_fetch_content_command, ["--help"])
            BeatTestHelpers.assert_command_success(
                result, ["Manually trigger the fetch_content_task for testing"]
            )

    @patch("cli.beat.fetch_content_task")
    def test_trigger_fetch_content_command_success(
        self, mock_fetch_content_task, app, cli_runner, mock_task_result
    ):
        """Test successful execution of trigger-fetch-content command."""
        with app.app_context():
            # Setup mock task result
            task_id = "fetch-task-id-67890"
            mock_result = mock_task_result(task_id)
            mock_fetch_content_task.delay.return_value = mock_result

            result = cli_runner.invoke(trigger_fetch_content_command)

            # Verify command succeeded
            BeatTestHelpers.assert_command_success(
                result,
                [
                    TestMessages.TASK_TRIGGERED,
                    task_id,
                    TestMessages.TASK_STATUS_CHECK,
                ],
            )

            # Verify the task was triggered
            mock_fetch_content_task.delay.assert_called_once()

    @patch("cli.beat.fetch_content_task")
    def test_trigger_fetch_content_command_task_exception(
        self, mock_fetch_content_task, app, cli_runner
    ):
        """Test trigger-fetch-content command when task.delay() raises an exception."""
        with app.app_context():
            # Setup mock to raise an exception
            mock_fetch_content_task.delay.side_effect = Exception(
                "Fetch task dispatch failed"
            )

            result = cli_runner.invoke(trigger_fetch_content_command)

            # Verify command failed
            BeatTestHelpers.assert_command_failure(result)

    @patch("cli.beat.fetch_content_task")
    @patch("cli.beat.click.echo")
    def test_trigger_fetch_content_command_output_format(
        self, mock_echo, mock_fetch_content_task, app, cli_runner, mock_task_result
    ):
        """Test that trigger-fetch-content command outputs are properly formatted."""
        with app.app_context():
            # Setup mock task result
            task_id = "formatted-fetch-id"
            mock_result = mock_task_result(task_id)
            mock_fetch_content_task.delay.return_value = mock_result

            result = cli_runner.invoke(trigger_fetch_content_command)

            # Verify command succeeded
            BeatTestHelpers.assert_command_success(result)

            # Verify click.echo was called with correct messages
            assert mock_echo.call_count == 2
            mock_echo.assert_any_call(f"Task triggered! Task ID: {task_id}")
            mock_echo.assert_any_call(TestMessages.TASK_STATUS_CHECK)

    @patch("cli.beat.fetch_content_task")
    def test_trigger_fetch_content_command_preserves_app_context(
        self, mock_fetch_content_task, app, cli_runner, mock_task_result
    ):
        """Test that trigger-fetch-content command preserves Flask app context."""
        with app.app_context():
            # Setup mock task result
            mock_result = mock_task_result("context-fetch-id")
            mock_fetch_content_task.delay.return_value = mock_result

            result = cli_runner.invoke(trigger_fetch_content_command)

            # Verify command succeeded and context is preserved
            BeatTestHelpers.assert_command_success(result)
            # The @with_appcontext decorator should ensure the app context is available
            mock_fetch_content_task.delay.assert_called_once()


@pytest.mark.cli
@pytest.mark.integration
class TestBeatCommandsIntegration:
    """Integration tests for beat CLI commands."""

    def test_all_beat_commands_registered(self, app, cli_runner):
        """Test that all beat commands are properly registered and accessible."""
        with app.app_context():
            commands_to_test = [
                beat_command,
                trigger_posts_command,
                trigger_fetch_content_command,
            ]

            for command in commands_to_test:
                result = cli_runner.invoke(command, ["--help"])
                BeatTestHelpers.assert_command_success(result)

    @patch("cli.beat.initiate_posts")
    @patch("cli.beat.fetch_content_task")
    def test_trigger_commands_independent_execution(
        self, mock_fetch_task, mock_posts_task, app, cli_runner, mock_task_result
    ):
        """Test that trigger commands can be executed independently."""
        with app.app_context():
            # Setup mock results
            posts_task_id = "posts-task-id"
            fetch_task_id = "fetch-task-id"

            mock_posts_result = mock_task_result(posts_task_id)
            mock_posts_task.delay.return_value = mock_posts_result

            mock_fetch_result = mock_task_result(fetch_task_id)
            mock_fetch_task.delay.return_value = mock_fetch_result

            # Execute trigger-posts command
            result1 = cli_runner.invoke(trigger_posts_command)
            BeatTestHelpers.assert_command_success(result1, [posts_task_id])

            # Execute trigger-fetch-content command
            result2 = cli_runner.invoke(trigger_fetch_content_command)
            BeatTestHelpers.assert_command_success(result2, [fetch_task_id])

            # Verify both tasks were triggered independently
            mock_posts_task.delay.assert_called_once()
            mock_fetch_task.delay.assert_called_once()

    @pytest.mark.parametrize(
        "command_func,task_mock_path",
        [
            (trigger_posts_command, "cli.beat.initiate_posts"),
            (trigger_fetch_content_command, "cli.beat.fetch_content_task"),
        ],
    )
    def test_trigger_commands_error_handling(
        self, command_func, task_mock_path, app, cli_runner
    ):
        """Test error handling for trigger commands using parametrized tests."""
        with app.app_context():
            with patch(task_mock_path) as mock_task:
                # Setup mock to raise an exception
                mock_task.delay.side_effect = Exception("Task failed")

                result = cli_runner.invoke(command_func)

                # Verify command failed gracefully
                BeatTestHelpers.assert_command_failure(result)
                mock_task.delay.assert_called_once()

    def test_beat_command_imports(self, app):
        """Test that all necessary imports are available for beat commands."""
        with app.app_context():
            # Test that the imported modules are accessible
            from cli.beat import click, current_app, initiate_posts, fetch_content_task

            # Verify imports are not None
            required_imports = [click, current_app, initiate_posts, fetch_content_task]
            for import_obj in required_imports:
                assert import_obj is not None

    @patch("cli.beat.current_app")
    def test_beat_command_celery_configuration_access(
        self, mock_current_app, app, cli_runner
    ):
        """Test that beat command properly accesses Celery configuration."""
        with app.app_context():
            # Setup mock celery instance with configuration
            mock_celery = Mock()
            mock_celery.conf = {"timezone": "US/Eastern", "beat_schedule": {}}
            mock_beat = Mock()
            mock_celery.Beat.return_value = mock_beat
            BeatTestHelpers.setup_celery_extension_mock(mock_current_app, mock_celery)

            result = cli_runner.invoke(beat_command)

            # Verify command succeeded and accessed celery from extensions
            BeatTestHelpers.assert_command_success(result)
            mock_celery.Beat.assert_called_once_with(loglevel="info")
            mock_beat.run.assert_called_once()
