"""
Tests for the CLI lint command.

This module tests the lint CLI command which is responsible for:
1. Running Black formatter (check or fix mode)
2. Running Flake8 linter
3. Handling tool availability and errors
4. Providing user-friendly output and exit codes
5. Supporting various command-line options

Test Organization:
- TestLintResult: Tests for the LintResult dataclass
- TestLintRunner: Tests for the LintRunner class methods
- TestLintCommand: Tests for the main 'lint' command functionality
- TestLintCommandOptions: Tests for command-line option handling
- TestLintIntegration: Integration tests with actual tool execution

Test Markers:
- unit: Unit tests that test individual functions in isolation
- integration: Integration tests that test multiple components together
- cli: Tests specifically for CLI command functionality

Example usage:
    # Run all lint tests
    pytest tests/cli/test_lint.py -v

    # Run with coverage
    pytest tests/cli/test_lint.py --cov=cli.lint --cov-report=term-missing

    # Run specific test
    pytest tests/cli/test_lint.py::TestLintCommand::test_lint_command_exists -v

    # Run only unit tests
    pytest tests/cli/test_lint.py -m unit -v
"""

import pytest
import subprocess
from typing import List, Dict, Any, Optional, Callable
from unittest.mock import Mock, patch, MagicMock, call
from click.testing import CliRunner, Result

from cli.lint import lint_command, LintResult, LintRunner


class TestConstants:
    """Constants for test configuration and expected values."""

    # Success messages
    BLACK_SUCCESS_CHECK = "✅ Code formatting is correct!"
    BLACK_SUCCESS_FIX = "✅ Code formatted successfully!"
    FLAKE8_SUCCESS = "✅ No linting issues found!"
    ALL_CHECKS_PASSED = "🎉 All linting checks passed!"

    # Warning/Error messages
    BLACK_REFORMATTED = "⚠️  Code was reformatted"
    BLACK_ISSUES_FOUND = "❌ Code formatting issues found"
    FLAKE8_ISSUES_FOUND = "❌ Linting issues found:"
    CHECKS_FAILED = "💥 Linting checks failed!"
    TOOL_NOT_FOUND = "not found. Install with: pip install"
    FIX_TIP = "💡 Tip: Run 'flask lint --fix' to automatically fix formatting issues"

    # Option validation
    MUTUALLY_EXCLUSIVE_ERROR = "❌ Cannot use --flake8-only and --black-only together"

    # Help text
    LINT_HELP_TEXT = "Run code linting and formatting checks"

    # Sample tool outputs
    BLACK_CHECK_OUTPUT = "would reformat 3 files"
    BLACK_FIX_OUTPUT = "reformatted 3 files"
    FLAKE8_OUTPUT = "./app.py:10:1: E302 expected 2 blank lines, found 1"

    # Command variations
    BLACK_CHECK_COMMAND = ["black", "--check", "."]
    BLACK_FIX_COMMAND = ["black", "."]
    FLAKE8_COMMAND = ["flake8", "."]


class LintTestHelpers:
    """Helper methods for lint command testing."""

    @staticmethod
    def create_mock_subprocess_result(
        returncode: int = 0, stdout: str = "", stderr: str = ""
    ) -> Mock:
        """Create a mock subprocess result with specified properties."""
        mock_result = Mock()
        mock_result.returncode = returncode
        mock_result.stdout = stdout
        mock_result.stderr = stderr
        return mock_result

    @staticmethod
    def assert_command_success(
        result: Result, expected_fragments: Optional[List[str]] = None
    ) -> None:
        """Assert that a CLI command executed successfully."""
        assert result.exit_code == 0, (
            f"Command failed with exit code {result.exit_code}. "
            f"Output: {result.output}"
        )
        if expected_fragments:
            for fragment in expected_fragments:
                assert fragment in result.output, (
                    f"Expected '{fragment}' in command output. "
                    f"Full output: {result.output}"
                )

    @staticmethod
    def assert_command_failure(result: Result, expected_exit_code: int = 1) -> None:
        """Assert that a CLI command failed with the expected exit code."""
        assert result.exit_code == expected_exit_code, (
            f"Expected exit code {expected_exit_code}, got {result.exit_code}. "
            f"Output: {result.output}"
        )

    @staticmethod
    def assert_output_contains(result: Result, expected_fragments: List[str]) -> None:
        """Assert that command output contains all expected fragments."""
        for fragment in expected_fragments:
            assert fragment in result.output, (
                f"Expected '{fragment}' in command output. "
                f"Full output: {result.output}"
            )

    @staticmethod
    def assert_output_not_contains(
        result: Result, unexpected_fragments: List[str]
    ) -> None:
        """Assert that command output does not contain unexpected fragments."""
        for fragment in unexpected_fragments:
            assert fragment not in result.output, (
                f"Unexpected '{fragment}' found in command output. "
                f"Full output: {result.output}"
            )

    @staticmethod
    def create_mock_runner_with_exit_code(exit_code: int = 0) -> Mock:
        """Create a mock LintRunner with specified exit code."""
        mock_runner = Mock(spec=LintRunner)
        mock_runner.exit_code = exit_code
        mock_runner.run_black = Mock()
        mock_runner.run_flake8 = Mock()
        mock_runner.print_summary = Mock()
        return mock_runner

    @staticmethod
    def assert_tool_execution_order(
        mock_runner: Mock, expected_black: bool, expected_flake8: bool
    ) -> None:
        """Assert that tools were executed in the expected order."""
        if expected_black and expected_flake8:
            # Both tools should be called, Black first
            assert mock_runner.run_black.called
            assert mock_runner.run_flake8.called
        elif expected_black:
            assert mock_runner.run_black.called
            assert not mock_runner.run_flake8.called
        elif expected_flake8:
            assert not mock_runner.run_black.called
            assert mock_runner.run_flake8.called
        else:
            assert not mock_runner.run_black.called
            assert not mock_runner.run_flake8.called


# Fixtures
@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a Click CLI runner for testing."""
    return CliRunner()


@pytest.fixture
def lint_runner() -> LintRunner:
    """Provide a LintRunner instance for testing."""
    return LintRunner()


@pytest.fixture
def mock_subprocess_success():
    """Mock subprocess.run for successful tool execution."""
    with patch("cli.lint.subprocess.run") as mock_run:
        mock_run.return_value = LintTestHelpers.create_mock_subprocess_result(
            returncode=0, stdout="All good!"
        )
        yield mock_run


@pytest.fixture
def mock_subprocess_failure():
    """Mock subprocess.run for failed tool execution."""
    with patch("cli.lint.subprocess.run") as mock_run:
        mock_run.return_value = LintTestHelpers.create_mock_subprocess_result(
            returncode=1, stdout="Issues found"
        )
        yield mock_run


# Test Classes
@pytest.mark.cli
@pytest.mark.unit
class TestLintResult:
    """Test the LintResult dataclass."""

    def test_lint_result_creation_success(self) -> None:
        """Test creating a successful LintResult instance."""
        result = LintResult(success=True, output="test output", tool_name="test_tool")

        assert result.success is True
        assert result.output == "test output"
        assert result.tool_name == "test_tool"

    def test_lint_result_creation_failure(self) -> None:
        """Test creating a failed LintResult instance."""
        result = LintResult(
            success=False, output="error output", tool_name="failing_tool"
        )

        assert result.success is False
        assert result.output == "error output"
        assert result.tool_name == "failing_tool"

    def test_lint_result_empty_output(self) -> None:
        """Test LintResult with empty output."""
        result = LintResult(success=True, output="", tool_name="silent_tool")

        assert result.success is True
        assert result.output == ""
        assert result.tool_name == "silent_tool"


@pytest.mark.cli
@pytest.mark.unit
class TestLintRunner:
    """Test the LintRunner class methods."""

    def test_lint_runner_initialization(self, lint_runner: LintRunner) -> None:
        """Test LintRunner initializes with correct default state."""
        assert lint_runner.exit_code == 0

    @patch("cli.lint.subprocess.run")
    def test_run_tool_success(self, mock_run: Mock, lint_runner: LintRunner) -> None:
        """Test successful tool execution."""
        mock_run.return_value = LintTestHelpers.create_mock_subprocess_result(
            returncode=0, stdout="Success output"
        )

        result = lint_runner.run_tool(
            command=["test_tool", "--check"],
            tool_name="TestTool",
            action_description="Testing tool",
        )

        assert result.success is True
        assert result.output == "Success output"
        assert result.tool_name == "TestTool"
        mock_run.assert_called_once_with(
            ["test_tool", "--check"], capture_output=True, text=True, check=False
        )

    @patch("cli.lint.subprocess.run")
    def test_run_tool_failure(self, mock_run: Mock, lint_runner: LintRunner) -> None:
        """Test failed tool execution."""
        mock_run.return_value = LintTestHelpers.create_mock_subprocess_result(
            returncode=1, stdout="Error output"
        )

        result = lint_runner.run_tool(
            command=["test_tool", "--check"],
            tool_name="TestTool",
            action_description="Testing tool",
        )

        assert result.success is False
        assert result.output == "Error output"
        assert result.tool_name == "TestTool"

    @patch("cli.lint.subprocess.run")
    def test_run_tool_not_found(self, mock_run: Mock, lint_runner: LintRunner) -> None:
        """Test handling when tool is not found."""
        mock_run.side_effect = FileNotFoundError("Tool not found")

        result = lint_runner.run_tool(
            command=["nonexistent_tool"],
            tool_name="NonexistentTool",
            action_description="Testing missing tool",
        )

        assert result.success is False
        assert result.output == ""
        assert result.tool_name == "NonexistentTool"
        assert lint_runner.exit_code == 1

    @patch("cli.lint.subprocess.run")
    def test_run_tool_with_stderr(
        self, mock_run: Mock, lint_runner: LintRunner
    ) -> None:
        """Test tool execution that produces stderr output."""
        mock_run.return_value = LintTestHelpers.create_mock_subprocess_result(
            returncode=1, stdout="stdout content", stderr="stderr content"
        )

        result = lint_runner.run_tool(
            command=["test_tool"],
            tool_name="TestTool",
            action_description="Testing tool with stderr",
        )

        assert result.success is False
        assert result.output == "stdout content"  # Only stdout is captured
        assert result.tool_name == "TestTool"

    def test_handle_black_result_success_check_mode(
        self, lint_runner: LintRunner
    ) -> None:
        """Test handling successful Black result in check mode."""
        result = LintResult(success=True, output="", tool_name="Black")

        with patch("cli.lint.click.echo") as mock_echo:
            lint_runner.handle_black_result(result, is_fix_mode=False)

        mock_echo.assert_called()
        args = mock_echo.call_args[0]
        assert TestConstants.BLACK_SUCCESS_CHECK in str(args)

    def test_handle_black_result_success_fix_mode(
        self, lint_runner: LintRunner
    ) -> None:
        """Test handling successful Black result in fix mode."""
        result = LintResult(success=True, output="", tool_name="Black")

        with patch("cli.lint.click.echo") as mock_echo:
            lint_runner.handle_black_result(result, is_fix_mode=True)

        mock_echo.assert_called()
        args = mock_echo.call_args[0]
        assert TestConstants.BLACK_SUCCESS_FIX in str(args)

    def test_handle_black_result_failure_check_mode(
        self, lint_runner: LintRunner
    ) -> None:
        """Test handling failed Black result in check mode."""
        result = LintResult(
            success=False, output="formatting issues", tool_name="Black"
        )

        with patch("cli.lint.click.echo"):
            lint_runner.handle_black_result(result, is_fix_mode=False)

        # Should set exit code to 1 in check mode
        assert lint_runner.exit_code == 1

    def test_handle_black_result_failure_fix_mode(
        self, lint_runner: LintRunner
    ) -> None:
        """Test handling failed Black result in fix mode."""
        result = LintResult(
            success=False, output="reformatted files", tool_name="Black"
        )

        with patch("cli.lint.click.echo"):
            lint_runner.handle_black_result(result, is_fix_mode=True)

        # Should NOT set exit code to 1 in fix mode (reformatting is expected)
        assert lint_runner.exit_code == 0

    def test_handle_black_result_tool_not_found(self, lint_runner: LintRunner) -> None:
        """Test handling Black result when tool was not found."""
        result = LintResult(success=False, output="", tool_name="Black")

        with patch("cli.lint.click.echo") as mock_echo:
            lint_runner.handle_black_result(result, is_fix_mode=False)

        # Should not call echo when tool wasn't found (empty output and not success)
        mock_echo.assert_not_called()

    def test_handle_flake8_result_success(self, lint_runner: LintRunner) -> None:
        """Test handling successful Flake8 result."""
        result = LintResult(success=True, output="", tool_name="Flake8")

        with patch("cli.lint.click.echo") as mock_echo:
            lint_runner.handle_flake8_result(result)

        mock_echo.assert_called()
        args = mock_echo.call_args[0]
        assert TestConstants.FLAKE8_SUCCESS in str(args)

    def test_handle_flake8_result_failure(self, lint_runner: LintRunner) -> None:
        """Test handling failed Flake8 result."""
        result = LintResult(success=False, output="linting issues", tool_name="Flake8")

        with patch("cli.lint.click.echo"):
            lint_runner.handle_flake8_result(result)

        # Should set exit code to 1
        assert lint_runner.exit_code == 1

    def test_handle_flake8_result_tool_not_found(self, lint_runner: LintRunner) -> None:
        """Test handling Flake8 result when tool was not found."""
        result = LintResult(success=False, output="", tool_name="Flake8")

        with patch("cli.lint.click.echo") as mock_echo:
            lint_runner.handle_flake8_result(result)

        # Should not call echo when tool wasn't found
        mock_echo.assert_not_called()

    @patch("cli.lint.subprocess.run")
    def test_run_black_check_mode(
        self, mock_run: Mock, lint_runner: LintRunner
    ) -> None:
        """Test running Black in check mode."""
        mock_run.return_value = LintTestHelpers.create_mock_subprocess_result()

        with patch.object(lint_runner, "handle_black_result") as mock_handle:
            lint_runner.run_black(fix_mode=False)

        mock_run.assert_called_once_with(
            TestConstants.BLACK_CHECK_COMMAND,
            capture_output=True,
            text=True,
            check=False,
        )
        mock_handle.assert_called_once()

    @patch("cli.lint.subprocess.run")
    def test_run_black_fix_mode(self, mock_run: Mock, lint_runner: LintRunner) -> None:
        """Test running Black in fix mode."""
        mock_run.return_value = LintTestHelpers.create_mock_subprocess_result()

        with patch.object(lint_runner, "handle_black_result") as mock_handle:
            lint_runner.run_black(fix_mode=True)

        mock_run.assert_called_once_with(
            TestConstants.BLACK_FIX_COMMAND, capture_output=True, text=True, check=False
        )
        mock_handle.assert_called_once()

    @patch("cli.lint.subprocess.run")
    def test_run_flake8(self, mock_run: Mock, lint_runner: LintRunner) -> None:
        """Test running Flake8."""
        mock_run.return_value = LintTestHelpers.create_mock_subprocess_result()

        with patch.object(lint_runner, "handle_flake8_result") as mock_handle:
            lint_runner.run_flake8()

        mock_run.assert_called_once_with(
            TestConstants.FLAKE8_COMMAND, capture_output=True, text=True, check=False
        )
        mock_handle.assert_called_once()

    def test_print_summary_success(self, lint_runner: LintRunner) -> None:
        """Test printing summary for successful run."""
        lint_runner.exit_code = 0

        with patch("cli.lint.click.echo") as mock_echo:
            lint_runner.print_summary(fix_mode=False, ran_black=True)

        mock_echo.assert_called()
        args = str(mock_echo.call_args_list)
        assert TestConstants.ALL_CHECKS_PASSED in args

    def test_print_summary_failure_with_tip(self, lint_runner: LintRunner) -> None:
        """Test printing summary for failed run with fix tip."""
        lint_runner.exit_code = 1

        with patch("cli.lint.click.echo") as mock_echo:
            lint_runner.print_summary(fix_mode=False, ran_black=True)

        args = str(mock_echo.call_args_list)
        assert TestConstants.CHECKS_FAILED in args
        assert TestConstants.FIX_TIP in args

    def test_print_summary_failure_no_tip(self, lint_runner: LintRunner) -> None:
        """Test printing summary for failed run without fix tip."""
        lint_runner.exit_code = 1

        with patch("cli.lint.click.echo") as mock_echo:
            lint_runner.print_summary(fix_mode=True, ran_black=True)

        args = str(mock_echo.call_args_list)
        assert TestConstants.CHECKS_FAILED in args
        assert TestConstants.FIX_TIP not in args

    def test_print_summary_flake8_only_no_tip(self, lint_runner: LintRunner) -> None:
        """Test printing summary for failed run with flake8-only (no fix tip)."""
        lint_runner.exit_code = 1

        with patch("cli.lint.click.echo") as mock_echo:
            lint_runner.print_summary(fix_mode=False, ran_black=False)

        args = str(mock_echo.call_args_list)
        assert TestConstants.CHECKS_FAILED in args
        assert TestConstants.FIX_TIP not in args


@pytest.mark.cli
@pytest.mark.unit
class TestLintCommand:
    """Test the main lint command functionality."""

    def test_lint_command_exists(self, app: Any, cli_runner: CliRunner) -> None:
        """Test that the lint command is properly registered."""
        with app.app_context():
            result = cli_runner.invoke(lint_command, ["--help"])

        assert result.exit_code == 0
        assert TestConstants.LINT_HELP_TEXT in result.output

    def test_lint_command_help_text(self, app: Any, cli_runner: CliRunner) -> None:
        """Test that the lint command shows proper help text."""
        with app.app_context():
            result = cli_runner.invoke(lint_command, ["--help"])

        LintTestHelpers.assert_command_success(result)
        assert "--fix" in result.output
        assert "--flake8-only" in result.output
        assert "--black-only" in result.output

    @patch("cli.lint.LintRunner")
    def test_lint_command_default_behavior(
        self, mock_runner_class: Mock, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test lint command default behavior (both tools, check mode)."""
        mock_runner = LintTestHelpers.create_mock_runner_with_exit_code(0)
        mock_runner_class.return_value = mock_runner

        with app.app_context():
            result = cli_runner.invoke(lint_command, [])

        # Should run both tools in check mode
        LintTestHelpers.assert_command_success(result)
        mock_runner.run_black.assert_called_once_with(fix_mode=False)
        mock_runner.run_flake8.assert_called_once()
        mock_runner.print_summary.assert_called_once_with(
            fix_mode=False, ran_black=True
        )

    @patch("cli.lint.LintRunner")
    def test_lint_command_fix_mode(
        self, mock_runner_class: Mock, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test lint command with --fix flag."""
        mock_runner = LintTestHelpers.create_mock_runner_with_exit_code(0)
        mock_runner_class.return_value = mock_runner

        with app.app_context():
            result = cli_runner.invoke(lint_command, ["--fix"])

        # Should run both tools with fix mode enabled for Black
        LintTestHelpers.assert_command_success(result)
        mock_runner.run_black.assert_called_once_with(fix_mode=True)
        mock_runner.run_flake8.assert_called_once()
        mock_runner.print_summary.assert_called_once_with(fix_mode=True, ran_black=True)

    @patch("cli.lint.LintRunner")
    def test_lint_command_black_only(
        self, mock_runner_class: Mock, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test lint command with --black-only flag."""
        mock_runner = LintTestHelpers.create_mock_runner_with_exit_code(0)
        mock_runner_class.return_value = mock_runner

        with app.app_context():
            result = cli_runner.invoke(lint_command, ["--black-only"])

        # Should run only Black
        LintTestHelpers.assert_command_success(result)
        mock_runner.run_black.assert_called_once_with(fix_mode=False)
        mock_runner.run_flake8.assert_not_called()
        mock_runner.print_summary.assert_called_once_with(
            fix_mode=False, ran_black=True
        )

    @patch("cli.lint.LintRunner")
    def test_lint_command_flake8_only(
        self, mock_runner_class: Mock, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test lint command with --flake8-only flag."""
        mock_runner = LintTestHelpers.create_mock_runner_with_exit_code(0)
        mock_runner_class.return_value = mock_runner

        with app.app_context():
            result = cli_runner.invoke(lint_command, ["--flake8-only"])

        # Should run only Flake8
        LintTestHelpers.assert_command_success(result)
        mock_runner.run_black.assert_not_called()
        mock_runner.run_flake8.assert_called_once()
        mock_runner.print_summary.assert_called_once_with(
            fix_mode=False, ran_black=False
        )

    def test_lint_command_mutually_exclusive_options(
        self, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test that --flake8-only and --black-only are mutually exclusive."""
        with app.app_context():
            result = cli_runner.invoke(lint_command, ["--flake8-only", "--black-only"])

        LintTestHelpers.assert_command_failure(result, expected_exit_code=1)
        assert TestConstants.MUTUALLY_EXCLUSIVE_ERROR in result.output

    @patch("cli.lint.LintRunner")
    def test_lint_command_exit_code_propagation(
        self, mock_runner_class: Mock, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test that the command exits with the runner's exit code."""
        mock_runner = LintTestHelpers.create_mock_runner_with_exit_code(1)
        mock_runner_class.return_value = mock_runner

        with app.app_context():
            result = cli_runner.invoke(lint_command, [])

        LintTestHelpers.assert_command_failure(result, expected_exit_code=1)


@pytest.mark.cli
@pytest.mark.unit
class TestLintCommandOptions:
    """Test command-line option combinations and edge cases."""

    @pytest.mark.parametrize(
        "fix_flag,expected_fix_mode",
        [
            ([], False),
            (["--fix"], True),
        ],
    )
    @patch("cli.lint.LintRunner")
    def test_fix_flag_combinations(
        self,
        mock_runner_class: Mock,
        app: Any,
        cli_runner: CliRunner,
        fix_flag: List[str],
        expected_fix_mode: bool,
    ) -> None:
        """Test various fix flag combinations."""
        mock_runner = LintTestHelpers.create_mock_runner_with_exit_code(0)
        mock_runner_class.return_value = mock_runner

        with app.app_context():
            result = cli_runner.invoke(lint_command, fix_flag)

        LintTestHelpers.assert_command_success(result)
        mock_runner.run_black.assert_called_once_with(fix_mode=expected_fix_mode)
        mock_runner.print_summary.assert_called_once_with(
            fix_mode=expected_fix_mode, ran_black=True
        )

    @pytest.mark.parametrize(
        "options,expected_black,expected_flake8",
        [
            ([], True, True),  # Default: run both
            (["--black-only"], True, False),  # Black only
            (["--flake8-only"], False, True),  # Flake8 only
            (["--fix"], True, True),  # Fix mode: run both
            (["--fix", "--black-only"], True, False),  # Fix + Black only
            (["--fix", "--flake8-only"], False, True),  # Fix + Flake8 only
        ],
    )
    @patch("cli.lint.LintRunner")
    def test_tool_selection_combinations(
        self,
        mock_runner_class: Mock,
        app: Any,
        cli_runner: CliRunner,
        options: List[str],
        expected_black: bool,
        expected_flake8: bool,
    ) -> None:
        """Test various tool selection combinations."""
        mock_runner = LintTestHelpers.create_mock_runner_with_exit_code(0)
        mock_runner_class.return_value = mock_runner

        with app.app_context():
            result = cli_runner.invoke(lint_command, options)

        LintTestHelpers.assert_command_success(result)
        LintTestHelpers.assert_tool_execution_order(
            mock_runner, expected_black, expected_flake8
        )


@pytest.mark.cli
@pytest.mark.integration
class TestLintIntegration:
    """Integration tests for the lint command."""

    def test_lint_command_with_app_context(
        self, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test that the lint command works within Flask app context."""
        with app.app_context():
            # Mock the tools to avoid actually running them
            with patch("cli.lint.subprocess.run") as mock_run:
                mock_run.return_value = LintTestHelpers.create_mock_subprocess_result()
                result = cli_runner.invoke(lint_command, [])

        # Command should execute without context errors
        assert result.exit_code in [0, 1]  # Either success or linting issues

    @patch("cli.lint.subprocess.run")
    def test_lint_command_tool_not_found_handling(
        self, mock_run: Mock, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test handling when linting tools are not installed."""
        mock_run.side_effect = FileNotFoundError("Tool not found")

        with app.app_context():
            result = cli_runner.invoke(lint_command, [])

        LintTestHelpers.assert_command_failure(result, expected_exit_code=1)
        LintTestHelpers.assert_output_contains(result, [TestConstants.TOOL_NOT_FOUND])

    def test_command_imports_and_dependencies(self, app: Any) -> None:
        """Test that all required imports and dependencies are available."""
        with app.app_context():
            # Test that we can import the command
            from cli.lint import lint_command, LintResult, LintRunner

            # Test that the command is callable
            assert callable(lint_command)

            # Test that classes can be instantiated
            runner = LintRunner()
            assert runner.exit_code == 0

            result = LintResult(success=True, output="test", tool_name="test")
            assert result.success is True

    @patch("cli.lint.subprocess.run")
    def test_realistic_tool_execution_flow(
        self, mock_run: Mock, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test a realistic flow of tool execution with mixed results."""

        # Simulate Black finding issues, Flake8 passing
        def side_effect(command, **kwargs):
            if "black" in command:
                return LintTestHelpers.create_mock_subprocess_result(
                    returncode=1, stdout=TestConstants.BLACK_CHECK_OUTPUT
                )
            elif "flake8" in command:
                return LintTestHelpers.create_mock_subprocess_result(
                    returncode=0, stdout=""
                )
            return LintTestHelpers.create_mock_subprocess_result()

        mock_run.side_effect = side_effect

        with app.app_context():
            result = cli_runner.invoke(lint_command, [])

        # Should fail due to Black issues
        LintTestHelpers.assert_command_failure(result, expected_exit_code=1)

        # Should contain both tool outputs
        LintTestHelpers.assert_output_contains(
            result,
            [
                "🔍 Running Black formatter",
                "🔍 Running Flake8 linter",
                TestConstants.CHECKS_FAILED,
                TestConstants.FIX_TIP,
            ],
        )

    @patch("cli.lint.subprocess.run")
    def test_both_tools_fail_scenario(
        self, mock_run: Mock, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test scenario where both Black and Flake8 fail."""

        def side_effect(command, **kwargs):
            if "black" in command:
                return LintTestHelpers.create_mock_subprocess_result(
                    returncode=1, stdout=TestConstants.BLACK_CHECK_OUTPUT
                )
            elif "flake8" in command:
                return LintTestHelpers.create_mock_subprocess_result(
                    returncode=1, stdout=TestConstants.FLAKE8_OUTPUT
                )
            return LintTestHelpers.create_mock_subprocess_result()

        mock_run.side_effect = side_effect

        with app.app_context():
            result = cli_runner.invoke(lint_command, [])

        # Should fail due to both tools having issues
        LintTestHelpers.assert_command_failure(result, expected_exit_code=1)

        # Should contain outputs from both tools
        LintTestHelpers.assert_output_contains(
            result,
            [
                "🔍 Running Black formatter",
                "🔍 Running Flake8 linter",
                TestConstants.CHECKS_FAILED,
            ],
        )

    @patch("cli.lint.subprocess.run")
    def test_both_tools_succeed_scenario(
        self, mock_run: Mock, app: Any, cli_runner: CliRunner
    ) -> None:
        """Test scenario where both Black and Flake8 succeed."""
        mock_run.return_value = LintTestHelpers.create_mock_subprocess_result(
            returncode=0, stdout=""
        )

        with app.app_context():
            result = cli_runner.invoke(lint_command, [])

        # Should succeed
        LintTestHelpers.assert_command_success(result)

        # Should contain success messages
        LintTestHelpers.assert_output_contains(
            result,
            [
                "🔍 Running Black formatter",
                "🔍 Running Flake8 linter",
                TestConstants.ALL_CHECKS_PASSED,
            ],
        )
