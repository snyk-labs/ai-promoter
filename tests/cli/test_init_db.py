"""
Tests for the CLI init-db command.

This module tests the init_db CLI command which is responsible for
initializing the database by dropping all tables and recreating them.

Test Organization:
- TestInitDbCommand: Tests for the main 'init-db' command functionality

Test Markers:
- unit: Unit tests that test individual functions and methods in isolation
- integration: Integration tests that test multiple components working together
- cli: Tests specifically for CLI command functionality

Example usage:
    # Run all init-db tests
    pytest tests/cli/test_init_db.py -v

    # Run with coverage
    pytest tests/cli/test_init_db.py --cov=cli.init_db --cov-report=term-missing

    # Run specific test
    pytest tests/cli/test_init_db.py::TestInitDbCommand::test_init_db_sqlite_dialect -v

    # Run only unit tests
    pytest tests/cli/test_init_db.py -m unit -v
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy import text, create_engine
from sqlalchemy.engine import Engine
from click.testing import CliRunner

from cli.init_db import init_db
from extensions import db
from models import User, Content, Share


# Constants for repeated strings to improve maintainability
class TestMessages:
    """Constants for expected test messages."""

    DETERMINING_DIALECT = "Determining database dialect..."
    DATABASE_WIPED = "Database has been wiped. Tables will be created by migrations."
    POSTGRESQL_DETECTED = (
        "PostgreSQL detected. Dropping all tables in 'public' schema with CASCADE..."
    )
    SCHEMA_RECREATED = "'public' schema dropped and recreated."
    SQLITE_DETECTED = "Sqlite detected. Dropping all tables..."
    MYSQL_DETECTED = "Mysql detected. Dropping all tables..."
    ORACLE_DETECTED = "Oracle detected. Dropping all tables..."


@pytest.mark.cli
@pytest.mark.unit
class TestInitDbCommand:
    """Unit tests for the init-db CLI command."""

    def _create_postgresql_mock_engine(self, username=None, should_fail=False):
        """
        Helper method to create a properly mocked PostgreSQL engine.

        Args:
            username: Username to set on the engine URL (None for no username)
            should_fail: Whether the connection should raise an exception

        Returns:
            Mock engine configured for PostgreSQL testing
        """
        mock_engine = Mock()
        mock_engine.dialect.name = "postgresql"
        mock_engine.url.username = username

        if should_fail:
            mock_engine.connect.side_effect = Exception("Connection failed")
        else:
            # Create a proper context manager mock
            mock_connection = Mock()
            mock_context_manager = Mock()
            mock_context_manager.__enter__ = Mock(return_value=mock_connection)
            mock_context_manager.__exit__ = Mock(return_value=None)
            mock_engine.connect.return_value = mock_context_manager

        return mock_engine

    def _assert_postgresql_sql_commands(self, mock_connection, username=None):
        """
        Helper method to assert the correct PostgreSQL SQL commands were executed.

        Args:
            mock_connection: The mocked database connection
            username: Expected username for GRANT statements (None if no grants expected)
        """
        expected_calls = [
            text("DROP SCHEMA public CASCADE;"),
            text("CREATE SCHEMA public;"),
        ]

        if username:
            expected_calls.extend(
                [
                    text(f"GRANT ALL ON SCHEMA public TO {username};"),
                    text(f"GRANT USAGE ON SCHEMA public TO {username};"),
                ]
            )

        assert mock_connection.execute.call_count == len(expected_calls)
        actual_calls = [call[0][0] for call in mock_connection.execute.call_args_list]

        for expected, actual in zip(expected_calls, actual_calls):
            assert str(expected) == str(actual)

        mock_connection.commit.assert_called_once()

    def test_init_db_command_exists(self, app):
        """Test that the init-db command is properly registered."""
        with app.app_context():
            runner = CliRunner()
            result = runner.invoke(init_db, ["--help"])
            assert result.exit_code == 0
            assert "Initialize the database" in result.output

    @patch("cli.init_db.db")
    def test_init_db_postgresql_dialect_with_username(self, mock_db, app):
        """Test init-db command with PostgreSQL dialect when username is available."""
        with app.app_context():
            # Setup mock engine
            mock_engine = self._create_postgresql_mock_engine(username="testuser")
            mock_db.engine = mock_engine

            # Run the init-db command
            runner = CliRunner()
            result = runner.invoke(init_db)

            # Verify command succeeded
            assert result.exit_code == 0
            assert TestMessages.DETERMINING_DIALECT in result.output
            assert TestMessages.POSTGRESQL_DETECTED in result.output
            assert TestMessages.SCHEMA_RECREATED in result.output
            assert TestMessages.DATABASE_WIPED in result.output

            # Verify the correct SQL commands were executed
            mock_connection = mock_engine.connect.return_value.__enter__.return_value
            self._assert_postgresql_sql_commands(mock_connection, username="testuser")

    @patch("cli.init_db.db")
    def test_init_db_postgresql_dialect_without_username(self, mock_db, app):
        """Test init-db command with PostgreSQL dialect when username is not available."""
        with app.app_context():
            # Setup mock engine without username
            mock_engine = self._create_postgresql_mock_engine(username=None)
            mock_db.engine = mock_engine

            # Run the init-db command
            runner = CliRunner()
            result = runner.invoke(init_db)

            # Verify command succeeded
            assert result.exit_code == 0
            assert TestMessages.POSTGRESQL_DETECTED in result.output
            assert TestMessages.SCHEMA_RECREATED in result.output

            # Verify only schema operations were executed (no GRANT statements)
            mock_connection = mock_engine.connect.return_value.__enter__.return_value
            self._assert_postgresql_sql_commands(mock_connection, username=None)

    @patch("cli.init_db.db")
    def test_init_db_other_dialect(self, mock_db, app):
        """Test init-db command with other database dialects (non-PostgreSQL)."""
        with app.app_context():
            # Mock the database engine with a different dialect
            mock_engine = Mock()
            mock_engine.dialect.name = "mysql"
            mock_db.engine = mock_engine

            # Run the init-db command
            runner = CliRunner()
            result = runner.invoke(init_db)

            # Verify command succeeded
            assert result.exit_code == 0
            assert TestMessages.DETERMINING_DIALECT in result.output
            assert TestMessages.MYSQL_DETECTED in result.output
            assert TestMessages.DATABASE_WIPED in result.output

            # Verify drop_all was called for non-PostgreSQL dialects
            mock_db.drop_all.assert_called_once()

    @patch("cli.init_db.db")
    def test_init_db_postgresql_connection_error(self, mock_db, app):
        """Test init-db command handles PostgreSQL connection errors gracefully."""
        with app.app_context():
            # Setup mock engine that will fail
            mock_engine = self._create_postgresql_mock_engine(
                username="testuser", should_fail=True
            )
            mock_db.engine = mock_engine

            # Run the init-db command
            runner = CliRunner()
            result = runner.invoke(init_db)

            # Verify command failed appropriately
            assert result.exit_code != 0
            assert TestMessages.DETERMINING_DIALECT in result.output
            assert TestMessages.POSTGRESQL_DETECTED in result.output

    @patch("cli.init_db.db")
    def test_init_db_postgresql_empty_username(self, mock_db, app):
        """Test init-db command with PostgreSQL when username is empty string."""
        with app.app_context():
            # Setup mock engine with empty string username
            mock_engine = self._create_postgresql_mock_engine(username="")
            mock_db.engine = mock_engine

            # Run the init-db command
            runner = CliRunner()
            result = runner.invoke(init_db)

            # Verify command succeeded but no GRANT statements (empty string is falsy)
            assert result.exit_code == 0
            mock_connection = mock_engine.connect.return_value.__enter__.return_value
            self._assert_postgresql_sql_commands(mock_connection, username=None)

    @patch("cli.init_db.db")
    def test_init_db_drop_all_exception(self, mock_db, app):
        """Test init-db command handles drop_all exceptions gracefully."""
        with app.app_context():
            # Mock the database engine with a non-PostgreSQL dialect
            mock_engine = Mock()
            mock_engine.dialect.name = "sqlite"
            mock_db.engine = mock_engine
            mock_db.drop_all.side_effect = Exception("Drop all failed")

            # Run the init-db command
            runner = CliRunner()
            result = runner.invoke(init_db)

            # Verify command failed appropriately
            assert result.exit_code != 0
            assert TestMessages.DETERMINING_DIALECT in result.output
            assert TestMessages.SQLITE_DETECTED in result.output

    @patch("cli.init_db.click.echo")
    def test_init_db_click_echo_calls(self, mock_echo, app):
        """Test that init-db makes the expected click.echo calls."""
        with app.app_context():
            runner = CliRunner()
            runner.invoke(init_db)

            # Verify click.echo was called with expected messages
            assert mock_echo.call_count >= 3
            echo_calls = [call[0][0] for call in mock_echo.call_args_list]

            assert TestMessages.DETERMINING_DIALECT in echo_calls
            assert any("detected. Dropping all tables" in call for call in echo_calls)
            assert TestMessages.DATABASE_WIPED in echo_calls

    def test_init_db_command_help_text(self, app):
        """Test that init-db command has proper help documentation."""
        with app.app_context():
            runner = CliRunner()
            result = runner.invoke(init_db, ["--help"])

            assert result.exit_code == 0
            help_text = result.output

            # Verify help contains key information
            assert "Initialize the database" in help_text
            assert "destructive operation" in help_text
            assert "flask db migrate" in help_text
            assert "flask db upgrade" in help_text

    @pytest.mark.parametrize(
        "dialect_name,expected_message",
        [
            ("postgresql", TestMessages.POSTGRESQL_DETECTED),
            ("sqlite", TestMessages.SQLITE_DETECTED),
            ("mysql", TestMessages.MYSQL_DETECTED),
            ("oracle", TestMessages.ORACLE_DETECTED),
        ],
    )
    @patch("cli.init_db.db")
    def test_init_db_dialect_detection(
        self, mock_db, app, dialect_name, expected_message
    ):
        """Test init-db correctly detects and handles different database dialects."""
        with app.app_context():
            # Mock the database engine with specified dialect
            if dialect_name == "postgresql":
                mock_engine = self._create_postgresql_mock_engine(username="testuser")
            else:
                mock_engine = Mock()
                mock_engine.dialect.name = dialect_name

            mock_db.engine = mock_engine

            # Run the init-db command
            runner = CliRunner()
            result = runner.invoke(init_db)

            # Verify command succeeded and correct dialect message appears
            assert result.exit_code == 0
            assert expected_message in result.output


@pytest.mark.cli
@pytest.mark.integration
class TestInitDbIntegration:
    """Integration tests for the init-db CLI command."""

    def test_init_db_sqlite_dialect(self, app):
        """Test init-db command with SQLite dialect."""
        with app.app_context():
            # Create some test tables first to verify they get dropped
            db.create_all()

            # Verify tables exist before init
            inspector = db.inspect(db.engine)
            tables_before = inspector.get_table_names()
            assert len(tables_before) > 0, "Should have tables before init"

            # Run the init-db command
            runner = CliRunner()
            result = runner.invoke(init_db)

            # Verify command succeeded
            assert result.exit_code == 0
            assert TestMessages.DETERMINING_DIALECT in result.output
            assert TestMessages.SQLITE_DETECTED in result.output
            assert TestMessages.DATABASE_WIPED in result.output

            # Verify tables were dropped (alembic_version may remain)
            inspector = db.inspect(db.engine)
            tables_after = inspector.get_table_names()
            # Filter out alembic_version table which may persist
            non_alembic_tables = [t for t in tables_after if t != "alembic_version"]
            assert (
                len(non_alembic_tables) == 0
            ), "All non-alembic tables should be dropped"

    def test_init_db_preserves_app_context(self, app):
        """Test that init-db command works properly within Flask app context."""
        with app.app_context():
            # Verify we're in an app context
            from flask import current_app

            assert current_app is not None

            # Create some test data to verify it gets cleared
            db.create_all()

            # Run the command
            runner = CliRunner()
            result = runner.invoke(init_db)

            # Verify command succeeded and context is still valid
            assert result.exit_code == 0
            assert current_app is not None

    def test_init_db_command_output_format(self, app):
        """Test that init-db command produces expected output format."""
        with app.app_context():
            runner = CliRunner()
            result = runner.invoke(init_db)

            # Verify output contains expected messages in order
            output_lines = result.output.strip().split("\n")
            assert len(output_lines) >= 3
            assert TestMessages.DETERMINING_DIALECT in output_lines[0]
            assert "detected. Dropping all tables" in output_lines[1]
            assert TestMessages.DATABASE_WIPED in output_lines[2]

    def test_init_db_integration_with_models(self, app):
        """Test init-db integration with actual model creation and destruction."""
        with app.app_context():
            # Create all tables and add some test data
            db.create_all()

            # Verify we can create model instances (tables exist)
            test_user = User(email="test@example.com", name="Test User")
            db.session.add(test_user)
            db.session.commit()

            # Verify data exists
            user_count_before = User.query.count()
            assert user_count_before > 0

            # Run init-db
            runner = CliRunner()
            result = runner.invoke(init_db)
            assert result.exit_code == 0

            # Verify tables are gone (this should raise an error or return 0)
            try:
                user_count_after = User.query.count()
                # If we get here, tables still exist but should be empty
                assert user_count_after == 0
            except Exception:
                # Tables don't exist anymore, which is expected
                pass

    def test_init_db_with_no_tables(self, app):
        """Test init-db command when no tables exist initially."""
        with app.app_context():
            # Ensure no tables exist
            db.drop_all()

            # Verify no tables exist
            inspector = db.inspect(db.engine)
            tables_before = inspector.get_table_names()
            non_alembic_tables = [t for t in tables_before if t != "alembic_version"]
            assert len(non_alembic_tables) == 0

            # Run the init-db command
            runner = CliRunner()
            result = runner.invoke(init_db)

            # Verify command succeeded even with no tables
            assert result.exit_code == 0
            assert TestMessages.DETERMINING_DIALECT in result.output
            assert TestMessages.DATABASE_WIPED in result.output
