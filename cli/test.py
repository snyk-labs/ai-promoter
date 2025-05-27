import click
import pytest
import sys
import os


@click.command("test")
@click.option("--pdb", is_flag=True, help="Drop into debugger on test failure.")
@click.option("-k", default=None, help="Run tests that match the given expression.")
@click.option("-m", default=None, help="Run tests with the given marker.")
@click.option("-v", is_flag=True, help="Enable verbose output.")
@click.option(
    "--collect-only", is_flag=True, help="Only collect tests, don't run them."
)
def test_command(pdb, k, m, v, collect_only):
    """Run the test suite."""
    args = []
    if pdb:
        args.append("--pdb")
    if k:
        args.extend(["-k", k])
    if m:
        args.extend(["-m", m])
    if v:
        args.append("-v")
    if collect_only:
        args.append("--collect-only")

    # Add the tests directory to the arguments
    args.append("tests")

    # Add current directory to sys.path to ensure pytest can find the app
    # and its modules, especially when tests are in a subdirectory.
    # This is often necessary if your project isn't installed as a package.
    if os.getcwd() not in sys.path:
        sys.path.insert(0, os.getcwd())

    # Ensure that the app context is available for tests that might need it,
    # for example, when using app.test_client() or accessing app.config.
    # However, pytest-flask handles app context creation for tests,
    # so explicitly pushing an app context here before calling pytest.main
    # is usually not needed and can sometimes interfere.
    # Pytest's fixtures (like `client` from pytest-flask) will manage this.

    exit_code = pytest.main(args)
    sys.exit(exit_code)
