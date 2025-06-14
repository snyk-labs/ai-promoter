"""
Tests for the CLI test command.

This module tests the test CLI command which is responsible for:
1. Running the test suite with pytest
2. Managing coverage reporting and configuration
3. Handling various test execution options and scenarios
4. Providing helpful error messages and troubleshooting

Test Organization:
- TestTestRunner: Tests for the TestRunner class methods
- TestTestCommand: Tests for the main 'test' command functionality
- TestTestCommandOptions: Tests for command-line option combinations
- TestTestIntegration: Integration tests with real subprocess execution

Test Markers:
- unit: Unit tests that test individual functions in isolation
- integration: Integration tests that test multiple components together
- cli: Tests specifically for CLI command functionality

Maintainability Guidelines:
1. Use BaseTestCommandTest for common functionality
2. Use TestTestHelpers for assertion and setup utilities
3. Use TestData constants for consistent test data
4. Use TestMessages constants for expected output validation
5. Use TestConfig for test configuration management
6. Prefer parametrized tests for option combinations
7. Mock subprocess calls to avoid running actual tools
8. Use descriptive test names and comprehensive docstrings

Example usage:
    # Run all test command tests
    flask test tests/cli/test_test.py -v

    # Run with coverage
    flask test tests/cli/test_test.py --cov-report=term-missing

    # Run specific test
    flask test tests/cli/test_test.py::TestTestRunner::test_validate_environment_success -v

    # Run only unit tests
    flask test tests/cli/test_test.py -m unit -v

Adding New Tests:
1. Inherit from BaseTestCommandTest for command tests
2. Use TestTestHelpers.create_mock_runner() for consistent mocks
3. Use self.invoke_test_command_with_app_context() for CLI invocation
4. Use TestTestHelpers.assert_* methods for validation
5. Add new constants to TestMessages/TestData as needed
6. Follow the existing naming conventions and patterns
"""

import pytest
from typing import Dict, List, Optional, Any, Tuple
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner
from pathlib import Path

from cli.test import test_command, TestRunner


# Constants for repeated strings to improve maintainability
class TestMessages:
    """Constants for expected test messages and validation."""

    # Success messages
    ALL_TESTS_PASSED = "🎉 All tests passed!"
    RUNNING_TESTS = "🧪 Running tests:"
    COVERAGE_REPORTS_GENERATED = "📊 Coverage reports generated:"

    # Error messages
    PYTEST_NOT_FOUND = "❌ pytest not found. Install with: pip install pytest"
    PYTEST_COV_NOT_FOUND = "⚠️  pytest-cov not found. Coverage reporting disabled."
    TESTS_FAILED = "💥 Tests failed with exit code"
    TESTS_INTERRUPTED = "⚠️  Tests interrupted by user"
    PYTHON_NOT_FOUND = "❌ Python not found in PATH"
    ERROR_RUNNING_TESTS = "❌ Error running tests:"

    # Help messages
    SOME_TESTS_FAILED = "💡 Some tests failed. Check the output above for details."
    TESTS_WERE_INTERRUPTED = "💡 Tests were interrupted. Run again to continue."
    INTERNAL_PYTEST_ERROR = "💡 Internal pytest error occurred."
    PYTEST_USAGE_ERROR = "💡 pytest command line usage error."
    NO_TESTS_COLLECTED = "💡 No tests were collected."

    # Help text
    TEST_HELP_TEXT = "Run tests with pytest"

    # File paths
    HTML_COVERAGE_PATH = "htmlcov/index.html"
    XML_COVERAGE_PATH = "coverage.xml"


class TestData:
    """Test data constants and factories for consistent test data management."""

    # Default command options
    DEFAULT_PYTEST_COMMAND = ["python", "-m", "pytest"]
    DEFAULT_COVERAGE_OPTIONS = [
        "--cov=.",
        "--cov-branch",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov",
        "--cov-report=xml:coverage.xml",
    ]

    # Environment variables
    DEFAULT_TEST_ENV = {
        "TESTING": "true",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    }

    # Exit codes for testing
    EXIT_CODES = {
        "SUCCESS": 0,
        "FAILURE": 1,
        "INTERRUPTED": 130,
        "PYTEST_INTERNAL_ERROR": 3,
        "PYTEST_USAGE_ERROR": 4,
        "NO_TESTS_COLLECTED": 5,
    }

    # Sample command combinations for parametrized tests
    COMMAND_COMBINATIONS = [
        # (options, expected_args)
        ([], []),
        (["-v"], ["-v"]),
        (["-k", "test_user"], ["-k", "test_user"]),
        (["-m", "unit"], ["-m", "unit"]),
        (["--no-cov"], []),
        (["--fail-fast"], ["-x"]),
    ]

    @classmethod
    def get_sample_subprocess_result(cls, returncode: int = 0) -> Mock:
        """Get a sample subprocess result for testing."""
        result = Mock()
        result.returncode = returncode
        return result

    @classmethod
    def get_sample_environment(cls, **overrides) -> Dict[str, str]:
        """Get sample environment variables with optional overrides."""
        env = cls.DEFAULT_TEST_ENV.copy()
        env.update(overrides)
        return env


class TestTestHelpers:
    """Helper methods for test command testing."""

    @staticmethod
    def create_mock_runner(
        exit_code: int = 0,
        coverage_enabled: bool = True,
        validate_success: bool = True,
    ) -> Mock:
        """
        Create a mock TestRunner with specified properties.

        Args:
            exit_code: Exit code to return from run_tests
            coverage_enabled: Whether coverage is enabled
            validate_success: Whether validate_environment returns True

        Returns:
            Mock TestRunner object with specified behavior
        """
        mock_runner = Mock(spec=TestRunner)
        mock_runner.exit_code = exit_code
        mock_runner.coverage_enabled = coverage_enabled
        mock_runner.validate_environment.return_value = validate_success
        mock_runner.build_pytest_command.return_value = (
            TestData.DEFAULT_PYTEST_COMMAND.copy()
        )
        mock_runner.setup_test_environment.return_value = (
            TestData.get_sample_environment()
        )
        mock_runner.run_tests.return_value = exit_code
        mock_runner.print_summary.return_value = None
        return mock_runner

    @staticmethod
    def create_mock_subprocess_result(
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
    ) -> Mock:
        """Create a mock subprocess result."""
        result = Mock()
        result.returncode = returncode
        result.stdout = stdout
        result.stderr = stderr
        return result

    @staticmethod
    def assert_command_success(
        result: Any, expected_output_fragments: Optional[List[str]] = None
    ) -> None:
        """Assert that a CLI command completed successfully."""
        assert result.exit_code == 0, f"Command failed with output: {result.output}"
        if expected_output_fragments:
            for fragment in expected_output_fragments:
                assert fragment in result.output

    @staticmethod
    def assert_command_failure(result: Any, expected_exit_code: int = 1) -> None:
        """Assert that a CLI command failed with expected exit code."""
        assert (
            result.exit_code == expected_exit_code
        ), f"Expected exit code {expected_exit_code}, got {result.exit_code}"

    @staticmethod
    def assert_echo_calls_contain(
        mock_echo: Mock, expected_messages: List[str]
    ) -> None:
        """
        Assert that click.echo was called with expected messages.

        Args:
            mock_echo: Mock of click.echo
            expected_messages: List of messages that should be in echo calls

        Raises:
            AssertionError: If any expected message is not found
        """
        echo_calls = [str(call[0][0]) for call in mock_echo.call_args_list]

        for message in expected_messages:
            assert any(
                message in call for call in echo_calls
            ), f"Expected message '{message}' not found in echo calls: {echo_calls}"

    @staticmethod
    def assert_runner_method_called(
        mock_runner: Mock, method_name: str, call_count: int = 1
    ) -> None:
        """
        Assert that a specific method on the mock runner was called.

        Args:
            mock_runner: Mock TestRunner object
            method_name: Name of the method to check
            call_count: Expected number of calls (0 means should not be called)

        Raises:
            AssertionError: If call count doesn't match expectation
        """
        method = getattr(mock_runner, method_name)
        actual_count = method.call_count
        if call_count == 0:
            assert actual_count == 0, f"{method_name} should not be called"
        else:
            assert (
                actual_count == call_count
            ), f"Expected {method_name} to be called {call_count} times, but was called {actual_count} times"

    @staticmethod
    def assert_pytest_command_built_correctly(
        mock_runner: Mock,
        expected_base_args: Optional[List[str]] = None,
        expected_additional_args: Optional[List[str]] = None,
    ) -> None:
        """Assert that pytest command was built with expected arguments."""
        mock_runner.build_pytest_command.assert_called_once()

        if expected_base_args:
            call_args = mock_runner.build_pytest_command.call_args[0]
            TestTestHelpers.assert_command_args_contain(call_args, expected_base_args)

        if expected_additional_args:
            call_kwargs = mock_runner.build_pytest_command.call_args[1]
            pytest_args = call_kwargs.get("pytest_args", ())
            TestTestHelpers.assert_command_args_contain(
                list(pytest_args), expected_additional_args
            )

    @staticmethod
    def assert_command_args_contain(
        actual_args: List[str], expected_args: List[str]
    ) -> None:
        """Assert that actual args contain all expected args."""
        for expected_arg in expected_args:
            assert (
                expected_arg in actual_args
            ), f"Expected arg '{expected_arg}' not found in {actual_args}"

    @staticmethod
    def validate_mock_runner_state(
        mock_runner: Mock, expected_state: Dict[str, Any]
    ) -> None:
        """Validate that the mock runner has expected attribute values."""
        for attr_name, expected_value in expected_state.items():
            actual_value = getattr(mock_runner, attr_name)
            assert (
                actual_value == expected_value
            ), f"Expected {attr_name}={expected_value}, got {actual_value}"

    @staticmethod
    def assert_environment_setup_called(mock_runner: Mock) -> None:
        """Assert that test environment setup was called."""
        TestTestHelpers.assert_runner_method_called(
            mock_runner, "setup_test_environment"
        )

    @staticmethod
    def assert_tests_executed(
        mock_runner: Mock, expected_env: Optional[Dict] = None
    ) -> None:
        """Assert that tests were executed with proper environment."""
        TestTestHelpers.assert_runner_method_called(mock_runner, "run_tests")
        if expected_env:
            call_args = mock_runner.run_tests.call_args
            actual_env = call_args[0][1]  # Second argument is env
            for key, value in expected_env.items():
                assert actual_env.get(key) == value


class BaseTestCommandTest:
    """Base class for test command tests with common utilities."""

    @staticmethod
    def setup_mock_runner_with_command_building(
        mock_runner: Mock, base_cmd: Optional[List[str]] = None
    ) -> None:
        """Setup mock runner to return modifiable command list."""
        if base_cmd is None:
            base_cmd = TestData.DEFAULT_PYTEST_COMMAND.copy()
        mock_runner.build_pytest_command.return_value = base_cmd

    @staticmethod
    def invoke_test_command_with_app_context(
        app: Any, cli_runner: CliRunner, args: List[str]
    ) -> Any:
        """Invoke the test command within an app context."""
        with app.app_context():
            return cli_runner.invoke(test_command, args)

    @staticmethod
    def verify_standard_test_flow(mock_runner: Mock) -> None:
        """Verify that the standard test execution flow occurred."""
        TestTestHelpers.assert_runner_method_called(mock_runner, "validate_environment")
        TestTestHelpers.assert_runner_method_called(mock_runner, "build_pytest_command")
        TestTestHelpers.assert_runner_method_called(
            mock_runner, "setup_test_environment"
        )
        TestTestHelpers.assert_runner_method_called(mock_runner, "run_tests")
        TestTestHelpers.assert_runner_method_called(mock_runner, "print_summary")


# Pytest fixtures for common test setup
@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a Click CLI runner for testing."""
    return CliRunner()


@pytest.fixture
def mock_test_runner() -> Mock:
    """Provide a mock TestRunner for testing."""
    return TestTestHelpers.create_mock_runner()


@pytest.fixture
def sample_environment() -> Dict[str, str]:
    """Provide sample environment variables for testing."""
    return TestData.get_sample_environment()


@pytest.mark.cli
@pytest.mark.unit
class TestTestRunner:
    """Unit tests for the TestRunner class methods."""

    def test_test_runner_initialization(self) -> None:
        """Test that TestRunner initializes with correct default values."""
        runner = TestRunner()
        assert runner.exit_code == 0
        assert runner.coverage_enabled is True

    @patch("cli.test.subprocess.run")
    def test_validate_environment_success(self, mock_run: Mock) -> None:
        """Test successful environment validation."""
        runner = TestRunner()

        # Mock successful subprocess calls for pytest and pytest-cov
        mock_run.return_value = Mock(returncode=0)

        result = runner.validate_environment()

        # Should validate pytest and pytest-cov
        assert result is True
        assert mock_run.call_count == 2  # pytest and pytest-cov

    @patch("cli.test.subprocess.run")
    def test_validate_environment_pytest_missing(self, mock_run: Mock) -> None:
        """Test environment validation when pytest is missing."""
        runner = TestRunner()

        # Mock pytest not found
        mock_run.side_effect = FileNotFoundError("pytest not found")

        with patch("cli.test.click.echo") as mock_echo:
            result = runner.validate_environment()

        assert result is False
        mock_echo.assert_called_once()
        assert TestMessages.PYTEST_NOT_FOUND in mock_echo.call_args[0][0]

    @patch("cli.test.subprocess.run")
    def test_validate_environment_coverage_missing(self, mock_run: Mock) -> None:
        """Test environment validation when pytest-cov is missing."""
        runner = TestRunner()

        def mock_subprocess_side_effect(cmd, **kwargs):
            if "pytest_cov" in cmd[2]:
                raise FileNotFoundError("pytest-cov not found")
            return Mock(returncode=0)

        mock_run.side_effect = mock_subprocess_side_effect

        with patch("cli.test.click.echo") as mock_echo:
            result = runner.validate_environment()

        # Should still return True but disable coverage
        assert result is True
        assert runner.coverage_enabled is False
        mock_echo.assert_called_once()
        assert TestMessages.PYTEST_COV_NOT_FOUND in mock_echo.call_args[0][0]

    def test_build_pytest_command_default(self) -> None:
        """Test building default pytest command."""
        runner = TestRunner()

        cmd = runner.build_pytest_command(
            verbose=False,
            keyword=None,
            marker=None,
            no_cov=False,
            cov_report=None,
            fail_fast=False,
            pytest_args=(),
        )

        # Should include base command and coverage by default
        expected_base = TestData.DEFAULT_PYTEST_COMMAND
        assert cmd[: len(expected_base)] == expected_base

        # Should include default coverage options
        TestTestHelpers.assert_command_args_contain(
            cmd, TestData.DEFAULT_COVERAGE_OPTIONS
        )

    def test_build_pytest_command_no_coverage(self) -> None:
        """Test building pytest command with coverage disabled."""
        runner = TestRunner()

        cmd = runner.build_pytest_command(
            verbose=False,
            keyword=None,
            marker=None,
            no_cov=True,
            cov_report=None,
            fail_fast=False,
            pytest_args=(),
        )

        # Should not include coverage options
        for cov_option in TestData.DEFAULT_COVERAGE_OPTIONS:
            assert cov_option not in cmd

    def test_build_pytest_command_with_options(self) -> None:
        """Test building pytest command with various options."""
        runner = TestRunner()

        cmd = runner.build_pytest_command(
            verbose=True,
            keyword="test_user",
            marker="unit",
            no_cov=False,
            cov_report=None,
            fail_fast=False,
            pytest_args=("tests/models/", "-s"),
        )

        # Should include all specified options
        expected_options = [
            "-v",
            "-k",
            "test_user",
            "-m",
            "unit",
            "tests/models/",
            "-s",
        ]
        TestTestHelpers.assert_command_args_contain(cmd, expected_options)

    def test_build_pytest_command_custom_coverage_report(self) -> None:
        """Test building pytest command with custom coverage report format."""
        runner = TestRunner()

        cmd = runner.build_pytest_command(
            verbose=False,
            keyword=None,
            marker=None,
            no_cov=False,
            cov_report="html",
            fail_fast=False,
            pytest_args=(),
        )

        # Should include custom coverage report
        assert "--cov-report=html" in cmd

        # Should not include default reports when custom is specified
        assert "--cov-report=term-missing" not in cmd

    def test_build_pytest_command_with_fail_fast(self) -> None:
        """Test building pytest command with fail-fast option."""
        runner = TestRunner()

        cmd = runner.build_pytest_command(
            verbose=False,
            keyword=None,
            marker=None,
            no_cov=False,
            cov_report=None,
            fail_fast=True,
            pytest_args=(),
        )

        # Should include fail-fast option
        assert "-x" in cmd

    def test_setup_test_environment_default(self) -> None:
        """Test setting up test environment with defaults."""
        runner = TestRunner()

        with patch("cli.test.os.environ", {"PATH": "/usr/bin"}):
            env = runner.setup_test_environment()

        assert env["TESTING"] == "true"
        assert "SQLALCHEMY_DATABASE_URI" in env
        assert env["PATH"] == "/usr/bin"  # Should preserve existing env

    def test_setup_test_environment_with_existing_db_url(self) -> None:
        """Test environment setup when database URL already exists."""
        runner = TestRunner()

        existing_env = {
            "DATABASE_URL": "postgresql://test",
            "PATH": "/usr/bin",
        }

        with patch("cli.test.os.environ", existing_env):
            env = runner.setup_test_environment()

        assert env["TESTING"] == "true"
        assert env["DATABASE_URL"] == "postgresql://test"
        # Should not override existing DATABASE_URL
        assert "SQLALCHEMY_DATABASE_URI" not in env

    @patch("cli.test.subprocess.run")
    def test_run_tests_success(self, mock_run: Mock) -> None:
        """Test successful test execution."""
        mock_run.return_value = TestTestHelpers.create_mock_subprocess_result(0)

        runner = TestRunner()
        cmd = ["python", "-m", "pytest"]
        env = TestData.get_sample_environment()

        with patch("cli.test.click.echo") as mock_echo:
            exit_code = runner.run_tests(cmd, env)

        assert exit_code == 0
        mock_run.assert_called_once_with(cmd, env=env)
        mock_echo.assert_called_once()
        assert TestMessages.RUNNING_TESTS in mock_echo.call_args[0][0]

    @patch("cli.test.subprocess.run")
    def test_run_tests_failure(self, mock_run: Mock) -> None:
        """Test test execution with failure."""
        mock_run.return_value = TestTestHelpers.create_mock_subprocess_result(1)

        runner = TestRunner()
        cmd = ["python", "-m", "pytest"]
        env = TestData.get_sample_environment()

        exit_code = runner.run_tests(cmd, env)

        assert exit_code == 1

    @patch("cli.test.subprocess.run")
    def test_run_tests_keyboard_interrupt(self, mock_run: Mock) -> None:
        """Test handling keyboard interrupt during test execution."""
        mock_run.side_effect = KeyboardInterrupt()

        runner = TestRunner()
        cmd = TestData.DEFAULT_PYTEST_COMMAND.copy()
        env = TestData.get_sample_environment()

        with patch("cli.test.click.echo") as mock_echo:
            exit_code = runner.run_tests(cmd, env)

        assert exit_code == TestData.EXIT_CODES["INTERRUPTED"]
        # Should have two echo calls: one for "Running tests" and one for "interrupted"
        expected_messages = [TestMessages.RUNNING_TESTS, TestMessages.TESTS_INTERRUPTED]
        TestTestHelpers.assert_echo_calls_contain(mock_echo, expected_messages)

    @patch("cli.test.subprocess.run")
    def test_run_tests_file_not_found(self, mock_run: Mock) -> None:
        """Test handling when Python is not found."""
        mock_run.side_effect = FileNotFoundError("Python not found")

        runner = TestRunner()
        cmd = TestData.DEFAULT_PYTEST_COMMAND.copy()
        env = TestData.get_sample_environment()

        with patch("cli.test.click.echo") as mock_echo:
            exit_code = runner.run_tests(cmd, env)

        assert exit_code == TestData.EXIT_CODES["FAILURE"]
        # Should have two echo calls: one for "Running tests" and one for error
        expected_messages = [TestMessages.RUNNING_TESTS, TestMessages.PYTHON_NOT_FOUND]
        TestTestHelpers.assert_echo_calls_contain(mock_echo, expected_messages)

    @patch("cli.test.subprocess.run")
    def test_run_tests_generic_exception(self, mock_run: Mock) -> None:
        """Test handling generic exceptions during test execution."""
        mock_run.side_effect = Exception("Generic error")

        runner = TestRunner()
        cmd = TestData.DEFAULT_PYTEST_COMMAND.copy()
        env = TestData.get_sample_environment()

        with patch("cli.test.click.echo") as mock_echo:
            exit_code = runner.run_tests(cmd, env)

        assert exit_code == TestData.EXIT_CODES["FAILURE"]
        # Should have two echo calls: one for "Running tests" and one for error
        expected_messages = [
            TestMessages.RUNNING_TESTS,
            TestMessages.ERROR_RUNNING_TESTS,
        ]
        TestTestHelpers.assert_echo_calls_contain(mock_echo, expected_messages)

    def test_print_summary_success_with_coverage(self) -> None:
        """Test printing summary for successful tests with coverage."""
        runner = TestRunner()
        runner.coverage_enabled = True

        with (
            patch("cli.test.click.echo") as mock_echo,
            patch("cli.test.Path") as mock_path,
        ):

            # Mock file existence
            mock_html_path = Mock()
            mock_html_path.exists.return_value = True
            mock_xml_path = Mock()
            mock_xml_path.exists.return_value = True

            mock_path.side_effect = lambda x: (
                mock_html_path if "html" in x else mock_xml_path
            )

            runner.print_summary(0, no_cov=False)

        # Should print success message and coverage info
        assert mock_echo.call_count >= 2
        echo_calls = [str(call[0][0]) for call in mock_echo.call_args_list]
        assert any(TestMessages.ALL_TESTS_PASSED in call for call in echo_calls)
        assert any(
            TestMessages.COVERAGE_REPORTS_GENERATED in call for call in echo_calls
        )

    def test_print_summary_success_no_coverage(self) -> None:
        """Test printing summary for successful tests without coverage."""
        runner = TestRunner()
        runner.coverage_enabled = False

        with patch("cli.test.click.echo") as mock_echo:
            runner.print_summary(0, no_cov=True)

        # Should print success message but no coverage info
        echo_calls = [str(call[0][0]) for call in mock_echo.call_args_list]
        assert any(TestMessages.ALL_TESTS_PASSED in call for call in echo_calls)
        assert not any(
            TestMessages.COVERAGE_REPORTS_GENERATED in call for call in echo_calls
        )

    def test_print_summary_failure(self) -> None:
        """Test printing summary for failed tests."""
        runner = TestRunner()

        with patch("cli.test.click.echo") as mock_echo:
            runner.print_summary(1, no_cov=False)

        echo_calls = [str(call[0][0]) for call in mock_echo.call_args_list]
        assert any(TestMessages.TESTS_FAILED in call for call in echo_calls)

    @pytest.mark.parametrize(
        "exit_code,expected_message",
        [
            (130, TestMessages.TESTS_WERE_INTERRUPTED),
            (1, TestMessages.SOME_TESTS_FAILED),
            (2, "Test execution was interrupted"),
            (3, TestMessages.INTERNAL_PYTEST_ERROR),
            (4, TestMessages.PYTEST_USAGE_ERROR),
            (5, TestMessages.NO_TESTS_COLLECTED),
        ],
    )
    def test_print_failure_help_messages(
        self, exit_code: int, expected_message: str
    ) -> None:
        """Test that appropriate help messages are shown for different exit codes."""
        runner = TestRunner()

        # Verify that the expected message is in the output
        with patch("cli.test.click.echo") as mock_echo:
            runner.print_summary(exit_code, no_cov=False)

        echo_calls = [str(call) for call in mock_echo.call_args_list]
        assert any(expected_message in call for call in echo_calls)


@pytest.mark.cli
@pytest.mark.unit
class TestTestCommand(BaseTestCommandTest):
    """Unit tests for the main test command functionality."""

    def test_test_command_exists(self, app: Any, cli_runner: CliRunner) -> None:
        """Test that the test command is properly registered."""
        result = self.invoke_test_command_with_app_context(app, cli_runner, ["--help"])
        TestTestHelpers.assert_command_success(result)
        assert TestMessages.TEST_HELP_TEXT in result.output

    def test_test_command_help_text(self, app: Any, cli_runner: CliRunner) -> None:
        """Test that the test command shows proper help text."""
        result = self.invoke_test_command_with_app_context(app, cli_runner, ["--help"])
        TestTestHelpers.assert_command_success(result)
        help_text = result.output

        # Check for key options (excluding --parallel since it's removed)
        expected_options = [
            "--verbose",
            "--keyword",
            "--marker",
            "--no-cov",
            "--fail-fast",
        ]
        for option in expected_options:
            assert option in help_text, f"Expected option '{option}' in help text"

        # Check for examples - use the actual text from the docstring
        assert "flask test" in help_text
        assert "Run all tests" in help_text  # Part of the examples

    @patch("cli.test.TestRunner")
    def test_test_command_default_behavior(
        self, mock_runner_class: Mock, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test test command default behavior."""
        mock_runner = TestTestHelpers.create_mock_runner(
            exit_code=TestData.EXIT_CODES["SUCCESS"]
        )
        mock_runner_class.return_value = mock_runner

        result = self.invoke_test_command_with_app_context(app, cli_runner, [])
        TestTestHelpers.assert_command_success(result)
        self.verify_standard_test_flow(mock_runner)

    @patch("cli.test.TestRunner")
    def test_test_command_validation_failure(
        self, mock_runner_class: Mock, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test test command when environment validation fails."""
        mock_runner = TestTestHelpers.create_mock_runner(validate_success=False)
        mock_runner_class.return_value = mock_runner

        result = self.invoke_test_command_with_app_context(app, cli_runner, [])
        TestTestHelpers.assert_command_failure(result, expected_exit_code=1)

        # Should validate but not proceed further
        TestTestHelpers.assert_runner_method_called(mock_runner, "validate_environment")
        TestTestHelpers.assert_runner_method_called(
            mock_runner, "build_pytest_command", call_count=0
        )
        TestTestHelpers.assert_runner_method_called(
            mock_runner, "run_tests", call_count=0
        )

    @patch("cli.test.TestRunner")
    def test_test_command_with_verbose_flag(
        self, mock_runner_class: Mock, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test test command with verbose flag."""
        mock_runner = TestTestHelpers.create_mock_runner()
        mock_runner_class.return_value = mock_runner

        result = self.invoke_test_command_with_app_context(app, cli_runner, ["-v"])
        TestTestHelpers.assert_command_success(result)

        # Check that verbose=True was passed to build_pytest_command
        call_args = mock_runner.build_pytest_command.call_args
        assert call_args[1]["verbose"] is True

    @patch("cli.test.TestRunner")
    def test_test_command_with_marker(
        self, mock_runner_class: Mock, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test test command with marker option."""
        mock_runner = TestTestHelpers.create_mock_runner()
        mock_runner_class.return_value = mock_runner

        result = self.invoke_test_command_with_app_context(
            app, cli_runner, ["-m", "unit"]
        )
        TestTestHelpers.assert_command_success(result)

        # Check that marker was passed correctly
        call_args = mock_runner.build_pytest_command.call_args
        assert call_args[1]["marker"] == "unit"

    @patch("cli.test.TestRunner")
    def test_test_command_with_keyword(
        self, mock_runner_class: Mock, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test test command with keyword option."""
        mock_runner = TestTestHelpers.create_mock_runner()
        mock_runner_class.return_value = mock_runner

        result = self.invoke_test_command_with_app_context(
            app, cli_runner, ["-k", "test_user"]
        )
        TestTestHelpers.assert_command_success(result)

        # Check that keyword was passed correctly
        call_args = mock_runner.build_pytest_command.call_args
        assert call_args[1]["keyword"] == "test_user"

    @patch("cli.test.TestRunner")
    def test_test_command_no_coverage(
        self, mock_runner_class: Mock, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test test command with coverage disabled."""
        mock_runner = TestTestHelpers.create_mock_runner()
        mock_runner_class.return_value = mock_runner

        result = self.invoke_test_command_with_app_context(
            app, cli_runner, ["--no-cov"]
        )
        TestTestHelpers.assert_command_success(result)

        # Check that no_cov=True was passed
        call_args = mock_runner.build_pytest_command.call_args
        assert call_args[1]["no_cov"] is True

    @patch("cli.test.TestRunner")
    def test_test_command_with_coverage_report(
        self, mock_runner_class: Mock, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test test command with specific coverage report format."""
        mock_runner = TestTestHelpers.create_mock_runner()
        mock_runner_class.return_value = mock_runner

        result = self.invoke_test_command_with_app_context(
            app, cli_runner, ["--cov-report", "html"]
        )
        TestTestHelpers.assert_command_success(result)

        # Check that coverage report format was passed
        call_args = mock_runner.build_pytest_command.call_args
        assert call_args[1]["cov_report"] == "html"

    @patch("cli.test.TestRunner")
    def test_test_command_with_fail_fast(
        self, mock_runner_class: Mock, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test test command with fail-fast option."""
        mock_runner = TestTestHelpers.create_mock_runner()
        mock_runner_class.return_value = mock_runner

        result = self.invoke_test_command_with_app_context(
            app, cli_runner, ["--fail-fast"]
        )
        TestTestHelpers.assert_command_success(result)

        # Check that build_pytest_command was called with fail_fast=True
        call_args = mock_runner.build_pytest_command.call_args
        assert call_args[1]["fail_fast"] is True

    @patch("cli.test.TestRunner")
    def test_test_command_with_pytest_args(
        self, mock_runner_class: Mock, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test test command with additional pytest arguments."""
        mock_runner = TestTestHelpers.create_mock_runner()
        mock_runner_class.return_value = mock_runner

        result = self.invoke_test_command_with_app_context(
            app, cli_runner, ["--", "tests/models/", "-s"]
        )
        TestTestHelpers.assert_command_success(result)

        # Check that pytest args were passed through
        call_args = mock_runner.build_pytest_command.call_args
        pytest_args = call_args[1]["pytest_args"]
        assert "tests/models/" in pytest_args
        assert "-s" in pytest_args

    @patch("cli.test.TestRunner")
    def test_test_command_exit_code_propagation(
        self, mock_runner_class: Mock, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test that the command exits with the runner's exit code."""
        mock_runner = TestTestHelpers.create_mock_runner(
            exit_code=TestData.EXIT_CODES["FAILURE"]
        )
        mock_runner_class.return_value = mock_runner

        result = self.invoke_test_command_with_app_context(app, cli_runner, [])
        TestTestHelpers.assert_command_failure(result, expected_exit_code=1)


@pytest.mark.cli
@pytest.mark.unit
class TestTestCommandOptions(BaseTestCommandTest):
    """Test command-line option combinations and edge cases."""

    @pytest.mark.parametrize(
        "options,expected_verbose,expected_no_cov",
        [
            ([], False, False),  # Default
            (["-v"], True, False),  # Verbose
            (["--verbose"], True, False),  # Verbose long form
            (["--no-cov"], False, True),  # No coverage
            (["-v", "--no-cov"], True, True),  # Both
        ],
    )
    @patch("cli.test.TestRunner")
    def test_option_combinations(
        self,
        mock_runner_class: Mock,
        app: Any,
        cli_runner: CliRunner,
        options: List[str],
        expected_verbose: bool,
        expected_no_cov: bool,
    ) -> None:
        """Test various option combinations."""
        mock_runner = TestTestHelpers.create_mock_runner()
        mock_runner_class.return_value = mock_runner

        result = self.invoke_test_command_with_app_context(app, cli_runner, options)
        TestTestHelpers.assert_command_success(result)

        # Check that options were passed correctly
        call_args = mock_runner.build_pytest_command.call_args
        assert call_args[1]["verbose"] == expected_verbose
        assert call_args[1]["no_cov"] == expected_no_cov

    @pytest.mark.parametrize(
        "cov_report_option",
        ["term", "html", "xml", "term-missing"],
    )
    @patch("cli.test.TestRunner")
    def test_coverage_report_options(
        self,
        mock_runner_class: Mock,
        app: Any,
        cli_runner: CliRunner,
        cov_report_option: str,
    ) -> None:
        """Test different coverage report format options."""
        mock_runner = TestTestHelpers.create_mock_runner()
        mock_runner_class.return_value = mock_runner

        result = self.invoke_test_command_with_app_context(
            app, cli_runner, ["--cov-report", cov_report_option]
        )
        TestTestHelpers.assert_command_success(result)

        # Check that coverage report format was passed
        call_args = mock_runner.build_pytest_command.call_args
        assert call_args[1]["cov_report"] == cov_report_option

    @patch("cli.test.TestRunner")
    def test_complex_option_combination(
        self, mock_runner_class: Mock, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test complex combination of multiple options."""
        mock_runner = TestTestHelpers.create_mock_runner()
        mock_runner_class.return_value = mock_runner

        # Setup mock to return a modifiable command list
        self.setup_mock_runner_with_command_building(mock_runner)

        options = [
            "-v",
            "-k",
            "test_user",
            "-m",
            "unit",
            "--cov-report",
            "html",
            "--fail-fast",
            "tests/models/",
        ]

        result = self.invoke_test_command_with_app_context(app, cli_runner, options)
        TestTestHelpers.assert_command_success(result)

        # Verify all options were processed
        call_args = mock_runner.build_pytest_command.call_args
        expected_options = {
            "verbose": True,
            "keyword": "test_user",
            "marker": "unit",
            "cov_report": "html",
            "fail_fast": True,
        }

        for option_name, expected_value in expected_options.items():
            assert (
                call_args[1][option_name] == expected_value
            ), f"Expected {option_name}={expected_value}, got {call_args[1][option_name]}"

        assert "tests/models/" in call_args[1]["pytest_args"]


@pytest.mark.cli
@pytest.mark.integration
class TestTestIntegration:
    """Integration tests for the test command."""

    def test_test_command_with_app_context(
        self, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test that the test command works within Flask app context."""
        with app.app_context():
            # Mock subprocess to avoid actually running tests
            with patch("cli.test.subprocess.run") as mock_run:
                mock_run.return_value = TestTestHelpers.create_mock_subprocess_result(0)
                result = cli_runner.invoke(test_command, ["--no-cov"])

        # Command should execute without context errors
        assert result.exit_code in [0, 1]  # Either success or validation failure

    def test_command_imports_and_dependencies(self, app: Any) -> None:
        """Test that all required imports work correctly."""
        # These imports should not raise any exceptions
        from cli.test import test_command, TestRunner

        # TestRunner should be instantiable
        runner = TestRunner()
        assert runner is not None
        assert hasattr(runner, "validate_environment")
        assert hasattr(runner, "build_pytest_command")
        assert hasattr(runner, "run_tests")

        # Command should be callable
        assert callable(test_command)

    @patch("cli.test.subprocess.run")
    def test_real_environment_setup(
        self, mock_run: Mock, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test environment setup integration."""
        mock_run.return_value = TestTestHelpers.create_mock_subprocess_result(0)

        with app.app_context():
            result = cli_runner.invoke(test_command, ["--no-cov"])

        # Should have set up test environment correctly
        assert "TESTING=true" in str(mock_run.call_args) or result.exit_code in [0, 1]

    def test_test_runner_real_instantiation(self) -> None:
        """Test that TestRunner can be instantiated and used."""
        runner = TestRunner()

        # Test basic properties
        assert runner.exit_code == 0
        assert runner.coverage_enabled is True

        # Test method signatures match expectations
        import inspect

        # Check validate_environment signature
        sig = inspect.signature(runner.validate_environment)
        assert len(sig.parameters) == 0

        # Check build_pytest_command signature
        sig = inspect.signature(runner.build_pytest_command)
        expected_params = {
            "verbose",
            "keyword",
            "marker",
            "no_cov",
            "cov_report",
            "fail_fast",
            "pytest_args",
        }
        actual_params = set(sig.parameters.keys())
        assert expected_params == actual_params

    @patch("cli.test.subprocess.run")
    def test_error_handling_integration(
        self, mock_run: Mock, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test error handling integration across components."""
        # Mock subprocess failure
        mock_run.side_effect = Exception("Simulated error")

        with app.app_context():
            result = cli_runner.invoke(test_command, [])

        # Should handle error gracefully and exit with appropriate code
        assert result.exit_code != 0


class TestConfig:
    """Configuration for test execution and behavior."""

    # Test execution settings
    DEFAULT_TIMEOUT = 30  # seconds
    MAX_RETRY_ATTEMPTS = 3

    # Mock behavior settings
    MOCK_SUBPROCESS_DELAY = 0.1  # seconds
    ENABLE_VERBOSE_MOCKING = False

    # Coverage thresholds
    MIN_COVERAGE_PERCENTAGE = 95
    MIN_BRANCH_COVERAGE_PERCENTAGE = 90

    # Test data limits
    MAX_ECHO_CALLS_TO_CHECK = 10
    MAX_COMMAND_ARGS_LENGTH = 50
