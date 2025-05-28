"""Code linting and formatting CLI commands."""

import subprocess
import sys
from dataclasses import dataclass
from typing import List

import click


@dataclass
class LintResult:
    """Result of a linting operation."""

    success: bool
    output: str
    tool_name: str


class LintRunner:
    """Handles running linting tools and formatting output."""

    def __init__(self) -> None:
        self.exit_code = 0

    def run_tool(
        self, command: List[str], tool_name: str, action_description: str
    ) -> LintResult:
        """Run a linting tool and return the result."""
        click.echo(f"🔍 Running {tool_name}...")
        click.echo(f"  {action_description}...")

        try:
            result = subprocess.run(
                command, capture_output=True, text=True, check=False
            )

            return LintResult(
                success=result.returncode == 0,
                output=result.stdout.strip(),
                tool_name=tool_name,
            )

        except FileNotFoundError:
            error_msg = f"  ❌ {tool_name} not found. Install with: pip install {tool_name.lower()}"
            click.echo(click.style(error_msg, fg="red"))
            self.exit_code = 1
            return LintResult(success=False, output="", tool_name=tool_name)

    def handle_black_result(self, result: LintResult, is_fix_mode: bool) -> None:
        """Handle and display Black formatter results."""
        # Skip if tool wasn't found (empty output and not success)
        if not result.success and not result.output:
            return

        if result.success:
            if is_fix_mode:
                click.echo(click.style("  ✅ Code formatted successfully!", fg="green"))
            else:
                click.echo(click.style("  ✅ Code formatting is correct!", fg="green"))
        else:
            if is_fix_mode:
                click.echo(click.style("  ⚠️  Code was reformatted", fg="yellow"))
            else:
                click.echo(click.style("  ❌ Code formatting issues found", fg="red"))

            if result.output:
                click.echo(result.output)

            if not is_fix_mode:
                self.exit_code = 1

    def handle_flake8_result(self, result: LintResult) -> None:
        """Handle and display Flake8 linting results."""
        # Skip if tool wasn't found (empty output and not success)
        if not result.success and not result.output:
            return

        if result.success:
            click.echo(click.style("  ✅ No linting issues found!", fg="green"))
        else:
            click.echo(click.style("  ❌ Linting issues found:", fg="red"))
            if result.output:
                click.echo(result.output)
            self.exit_code = 1

    def run_black(self, fix_mode: bool = False) -> None:
        """Run Black formatter."""
        if fix_mode:
            command = ["black", "."]
            action = "Formatting code with black"
        else:
            command = ["black", "--check", "."]
            action = "Checking code formatting"

        result = self.run_tool(command, "Black formatter", action)
        self.handle_black_result(result, fix_mode)

    def run_flake8(self) -> None:
        """Run Flake8 linter."""
        result = self.run_tool(
            ["flake8", "."], "Flake8 linter", "Checking code quality"
        )
        self.handle_flake8_result(result)

    def print_summary(self, fix_mode: bool, ran_black: bool) -> None:
        """Print final summary and exit."""
        if self.exit_code == 0:
            click.echo(click.style("\n🎉 All linting checks passed!", fg="green"))
        else:
            click.echo(click.style("\n💥 Linting checks failed!", fg="red"))
            if not fix_mode and ran_black:
                click.echo(
                    "💡 Tip: Run 'flask lint --fix' to automatically fix formatting issues"
                )


@click.command("lint")
@click.option(
    "--fix", is_flag=True, help="Automatically fix formatting issues with black."
)
@click.option(
    "--flake8-only", is_flag=True, help="Run only flake8 linting (skip black)."
)
@click.option(
    "--black-only", is_flag=True, help="Run only black formatting (skip flake8)."
)
def lint_command(fix: bool, flake8_only: bool, black_only: bool) -> None:
    """Run code linting and formatting checks (check-only by default)."""

    # Validate mutually exclusive options
    if flake8_only and black_only:
        click.echo(
            click.style(
                "❌ Cannot use --flake8-only and --black-only together", fg="red"
            )
        )
        sys.exit(1)

    # Determine what to run
    run_black = not flake8_only
    run_flake8 = not black_only

    # Initialize runner
    runner = LintRunner()

    # Run tools
    if run_black:
        runner.run_black(fix_mode=fix)

        # Add spacing between tools if running both
        if run_flake8:
            click.echo()

    if run_flake8:
        runner.run_flake8()

    # Print summary and exit
    runner.print_summary(fix_mode=fix, ran_black=run_black)
    sys.exit(runner.exit_code)
