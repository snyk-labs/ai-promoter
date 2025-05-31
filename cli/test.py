"""Test execution CLI commands."""

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import click


class TestRunner:
    """Handles test execution and reporting."""

    def __init__(self) -> None:
        self.exit_code = 0
        self.coverage_enabled = True

    def validate_environment(self) -> bool:
        """Validate that the testing environment is properly set up."""
        # Check if pytest is available
        try:
            subprocess.run(
                ["python", "-m", "pytest", "--version"], capture_output=True, check=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            click.echo(
                click.style(
                    "❌ pytest not found. Install with: pip install pytest", fg="red"
                )
            )
            return False

        # Check if coverage is available (if needed)
        if self.coverage_enabled:
            try:
                # Check if pytest-cov is available by importing it
                subprocess.run(
                    ["python", "-c", "import pytest_cov"],
                    capture_output=True,
                    check=True,
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                click.echo(
                    click.style(
                        "⚠️  pytest-cov not found. Coverage reporting disabled.",
                        fg="yellow",
                    )
                )
                self.coverage_enabled = False

        return True

    def build_pytest_command(
        self,
        verbose: bool,
        keyword: Optional[str],
        marker: Optional[str],
        no_cov: bool,
        cov_report: Optional[str],
        fail_fast: bool,
        pytest_args: Tuple[str, ...],
    ) -> List[str]:
        """Build the pytest command with all options."""
        cmd = ["python", "-m", "pytest"]

        # Add coverage options (default behavior unless disabled)
        if not no_cov and self.coverage_enabled:
            cmd.extend(["--cov=.", "--cov-branch"])

            # Add coverage report format
            if cov_report:
                cmd.append(f"--cov-report={cov_report}")
            else:
                # Default coverage reports
                cmd.extend(
                    [
                        "--cov-report=term-missing",
                        "--cov-report=html:htmlcov",
                        "--cov-report=xml:coverage.xml",
                    ]
                )

        # Add pytest options
        if verbose:
            cmd.append("-v")

        if keyword:
            cmd.extend(["-k", keyword])

        if marker:
            cmd.extend(["-m", marker])

        # Add fail-fast option
        if fail_fast:
            cmd.append("-x")

        # Add any additional pytest arguments
        if pytest_args:
            cmd.extend(pytest_args)

        return cmd

    def setup_test_environment(self) -> dict:
        """Set up environment variables for testing."""
        env = os.environ.copy()
        env["TESTING"] = "true"

        # Ensure we have a test database URL if not set
        if "DATABASE_URL" not in env and "SQLALCHEMY_DATABASE_URI" not in env:
            env["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

        return env

    def run_tests(self, cmd: List[str], env: dict) -> int:
        """Execute the test command and handle the result."""
        click.echo(f"🧪 Running tests: {' '.join(cmd)}")

        try:
            result = subprocess.run(cmd, env=env)
            return result.returncode
        except KeyboardInterrupt:
            click.echo("\n⚠️  Tests interrupted by user")
            return 130
        except FileNotFoundError:
            click.echo(click.style("❌ Python not found in PATH", fg="red"))
            return 1
        except Exception as e:
            click.echo(click.style(f"❌ Error running tests: {e}", fg="red"))
            return 1

    def print_summary(self, exit_code: int, no_cov: bool) -> None:
        """Print test execution summary."""
        if exit_code == 0:
            click.echo(click.style("\n🎉 All tests passed!", fg="green"))

            if not no_cov and self.coverage_enabled:
                self._print_coverage_info()
        else:
            click.echo(
                click.style(f"\n💥 Tests failed with exit code {exit_code}", fg="red")
            )
            self._print_failure_help(exit_code)

    def _print_coverage_info(self) -> None:
        """Print coverage report information."""
        click.echo("📊 Coverage reports generated:")
        click.echo("  - Terminal: shown above")

        html_path = Path("htmlcov/index.html")
        if html_path.exists():
            click.echo(f"  - HTML: {html_path}")

        xml_path = Path("coverage.xml")
        if xml_path.exists():
            click.echo(f"  - XML: {xml_path}")

    def _print_failure_help(self, exit_code: int) -> None:
        """Print helpful information for test failures."""
        if exit_code == 130:
            click.echo("💡 Tests were interrupted. Run again to continue.")
        elif exit_code == 1:
            click.echo("💡 Some tests failed. Check the output above for details.")
        elif exit_code == 2:
            click.echo("💡 Test execution was interrupted or there was an error.")
        elif exit_code == 3:
            click.echo("💡 Internal pytest error occurred.")
        elif exit_code == 4:
            click.echo("💡 pytest command line usage error.")
        elif exit_code == 5:
            click.echo("💡 No tests were collected.")


@click.command("test")
@click.option("-v", "--verbose", is_flag=True, help="Verbose output")
@click.option("-k", "--keyword", help="Run tests matching keyword")
@click.option("-m", "--marker", help="Run tests with specific marker")
@click.option("--no-cov", is_flag=True, help="Disable coverage reporting")
@click.option(
    "--cov-report",
    type=click.Choice(["term", "html", "xml", "term-missing"]),
    help="Coverage report format (can be used multiple times)",
)
@click.option("--fail-fast", is_flag=True, help="Stop on first failure")
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def test_command(
    verbose: bool,
    keyword: Optional[str],
    marker: Optional[str],
    no_cov: bool,
    cov_report: Optional[str],
    fail_fast: bool,
    pytest_args: Tuple[str, ...],
) -> None:
    """Run tests with pytest.

    Examples:
        flask test                    # Run all tests
        flask test -v                 # Verbose output
        flask test -k user            # Run tests matching 'user'
        flask test -m slow            # Run tests marked as 'slow'
        flask test --no-cov           # Disable coverage
        flask test --fail-fast        # Stop on first failure
        flask test tests/models/      # Run specific directory
        flask test tests/test_user.py # Run specific file
    """
    runner = TestRunner()

    # Validate environment
    if not runner.validate_environment():
        sys.exit(1)

    # Build pytest command
    cmd = runner.build_pytest_command(
        verbose=verbose,
        keyword=keyword,
        marker=marker,
        no_cov=no_cov,
        cov_report=cov_report,
        fail_fast=fail_fast,
        pytest_args=pytest_args,
    )

    # Set up test environment
    env = runner.setup_test_environment()

    # Run tests
    exit_code = runner.run_tests(cmd, env)

    # Print summary
    runner.print_summary(exit_code, no_cov)

    # Exit with the same code as pytest
    sys.exit(exit_code)
