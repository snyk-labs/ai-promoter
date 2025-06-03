"""
Tests for configuration management.

This module tests the Config class and its handling of environment variables,
database configuration, Redis settings, SSL configuration, and validation logic.
"""

import os
import ssl
import pytest
from unittest.mock import patch, MagicMock
from datetime import timedelta
from celery.schedules import crontab

from config import Config


# --- Test Constants ---
class ConfigTestConstants:
    """Centralized test constants for configuration testing."""

    DEFAULT_SECRET_KEY = "dev-key-please-change"
    DEFAULT_COMPANY_NAME = "Your Company"
    DEFAULT_BASE_URL = "http://localhost:5001"
    DEFAULT_REDIS_URL = "redis://localhost:6379/0"
    DEFAULT_MAIL_SERVER = "smtp.gmail.com"
    DEFAULT_MAIL_PORT = 587
    DEFAULT_MAIL_SENDER = "noreply@example.com"

    TEST_SECRET_KEY = "test-secret-key"
    TEST_COMPANY_NAME = "Test Company"
    TEST_BASE_URL = "https://test.example.com"

    OKTA_TEST_CONFIG = {
        "OKTA_ENABLED": "true",
        "OKTA_CLIENT_ID": "test_client_id",
        "OKTA_CLIENT_SECRET": "test_client_secret",
        "OKTA_ISSUER": "https://test.okta.com",
        "OKTA_REDIRECT_URI": "https://app.com/callback",
    }

    LINKEDIN_TEST_CONFIG = {
        "LINKEDIN_CLIENT_ID": "test_client_id",
        "LINKEDIN_CLIENT_SECRET": "test_client_secret",
    }


# --- Helper Functions ---
def reload_config_with_env(env_vars=None):
    """Helper to reload config with specific environment variables."""
    env_to_use = env_vars or {}
    # Always include TESTING=true to avoid LinkedIn validation errors
    if "TESTING" not in env_to_use:
        env_to_use["TESTING"] = "true"

    with patch.dict(os.environ, env_to_use, clear=True):
        from importlib import reload
        import config

        reload(config)
        return config


def assert_config_value(config_module, attr_name, expected_value):
    """Helper to assert a configuration attribute value."""
    actual_value = getattr(config_module.Config, attr_name)
    assert (
        actual_value == expected_value
    ), f"Expected {attr_name}={expected_value}, got {actual_value}"


class ConfigTestMixin:
    """Mixin providing common configuration testing patterns."""

    @staticmethod
    def assert_database_uri_contains(config_module, expected_substring):
        """Assert database URI contains expected substring."""
        uri = config_module.Config.SQLALCHEMY_DATABASE_URI
        assert (
            expected_substring in uri
        ), f"Expected '{expected_substring}' in URI: {uri}"

    @staticmethod
    def assert_redis_ssl_configuration(config_module, should_have_ssl=True):
        """Assert Redis SSL configuration is correct."""
        if should_have_ssl:
            assert "ssl_cert_reqs=none" in config_module.Config.REDIS_URL
            assert config_module.Config.CELERY_BROKER_SSL_CONFIG == {
                "ssl_cert_reqs": ssl.CERT_NONE
            }
            assert config_module.Config.CELERY_BACKEND_SSL_CONFIG == {
                "ssl_cert_reqs": ssl.CERT_NONE
            }
        else:
            assert config_module.Config.CELERY_BROKER_SSL_CONFIG is None


@pytest.mark.unit
class TestConfigDefaults:
    """Test default configuration values."""

    def test_default_values_without_environment(self):
        """Test that default values are set correctly when environment variables are not present."""
        config = reload_config_with_env({})

        # Test basic Flask configuration
        assert_config_value(
            config, "SECRET_KEY", ConfigTestConstants.DEFAULT_SECRET_KEY
        )
        assert_config_value(
            config, "COMPANY_NAME", ConfigTestConstants.DEFAULT_COMPANY_NAME
        )
        assert_config_value(config, "UTM_PARAMS", "")
        assert_config_value(config, "DASHBOARD_BANNER", "")
        assert_config_value(config, "BASE_URL", ConfigTestConstants.DEFAULT_BASE_URL)
        assert_config_value(config, "COMPANY_PRIVACY_NOTICE", "")

        # Test derived values
        assert_config_value(config, "CONTENT_FEEDS", [])
        assert_config_value(config, "SQLALCHEMY_TRACK_MODIFICATIONS", False)
        assert_config_value(config, "REDIS_URL", ConfigTestConstants.DEFAULT_REDIS_URL)

    def test_environment_variable_overrides(self):
        """Test that environment variables override default values."""
        env_vars = {
            "SECRET_KEY": ConfigTestConstants.TEST_SECRET_KEY,
            "COMPANY_NAME": ConfigTestConstants.TEST_COMPANY_NAME,
            "UTM_PARAMS": "utm_source=test&utm_medium=social",
            "DASHBOARD_BANNER": "Test Environment",
            "BASE_URL": ConfigTestConstants.TEST_BASE_URL,
            "COMPANY_PRIVACY_NOTICE": "Test privacy notice",
        }

        config = reload_config_with_env(env_vars)

        assert_config_value(config, "SECRET_KEY", ConfigTestConstants.TEST_SECRET_KEY)
        assert_config_value(
            config, "COMPANY_NAME", ConfigTestConstants.TEST_COMPANY_NAME
        )
        assert_config_value(config, "UTM_PARAMS", "utm_source=test&utm_medium=social")
        assert_config_value(config, "DASHBOARD_BANNER", "Test Environment")
        assert_config_value(config, "BASE_URL", ConfigTestConstants.TEST_BASE_URL)
        assert_config_value(config, "COMPANY_PRIVACY_NOTICE", "Test privacy notice")


@pytest.mark.unit
class TestContentFeedsConfiguration:
    """Test content feeds parsing and configuration."""

    def test_content_feeds_single_url(self):
        """Test content feeds parsing with single URL."""
        config = reload_config_with_env(
            {"CONTENT_FEEDS": "https://example.com/feed.xml"}
        )
        assert_config_value(config, "CONTENT_FEEDS", ["https://example.com/feed.xml"])

    def test_content_feeds_multiple_urls(self):
        """Test content feeds parsing with multiple URLs separated by pipe."""
        feeds = "https://example.com/feed1.xml|https://example.com/feed2.xml|https://example.com/feed3.xml"
        config = reload_config_with_env({"CONTENT_FEEDS": feeds})

        expected = [
            "https://example.com/feed1.xml",
            "https://example.com/feed2.xml",
            "https://example.com/feed3.xml",
        ]
        assert_config_value(config, "CONTENT_FEEDS", expected)

    def test_content_feeds_empty_values(self):
        """Test content feeds with empty environment variable."""
        config = reload_config_with_env({"CONTENT_FEEDS": ""})
        assert_config_value(config, "CONTENT_FEEDS", [])

    def test_content_feeds_whitespace_handling(self):
        """Test content feeds handles whitespace correctly."""
        feeds = " https://example.com/feed1.xml | https://example.com/feed2.xml "
        config = reload_config_with_env({"CONTENT_FEEDS": feeds})

        # Should split on pipe but preserve the whitespace in URLs
        expected = [
            " https://example.com/feed1.xml ",
            " https://example.com/feed2.xml ",
        ]
        assert_config_value(config, "CONTENT_FEEDS", expected)


@pytest.mark.unit
class TestDatabaseConfiguration(ConfigTestMixin):
    """Test database URL configuration and processing."""

    def test_default_sqlite_database_uri(self):
        """Test default SQLite database URI construction."""
        config = reload_config_with_env({})

        self.assert_database_uri_contains(config, "sqlite:///")
        self.assert_database_uri_contains(config, "promoter.db")

    def test_database_url_postgresql(self):
        """Test PostgreSQL database URL handling."""
        config = reload_config_with_env(
            {"DATABASE_URL": "postgresql://user:pass@host:5432/dbname"}
        )

        assert_config_value(
            config, "SQLALCHEMY_DATABASE_URI", "postgresql://user:pass@host:5432/dbname"
        )

    def test_database_url_heroku_postgres_conversion(self):
        """Test Heroku-style postgres:// URL gets converted to postgresql://."""
        config = reload_config_with_env(
            {"DATABASE_URL": "postgres://user:pass@host:5432/dbname"}
        )

        assert_config_value(
            config, "SQLALCHEMY_DATABASE_URI", "postgresql://user:pass@host:5432/dbname"
        )

    def test_database_url_custom_sqlite(self):
        """Test custom SQLite database URL."""
        config = reload_config_with_env(
            {"DATABASE_URL": "sqlite:///custom/path/test.db"}
        )

        assert_config_value(
            config, "SQLALCHEMY_DATABASE_URI", "sqlite:///custom/path/test.db"
        )

    def test_database_url_edge_cases(self):
        """Test database URL edge cases."""
        # Test MySQL URL (should pass through unchanged)
        config = reload_config_with_env(
            {"DATABASE_URL": "mysql://user:pass@host:3306/dbname"}
        )
        assert_config_value(
            config, "SQLALCHEMY_DATABASE_URI", "mysql://user:pass@host:3306/dbname"
        )

        # Test URL with parameters
        config = reload_config_with_env(
            {"DATABASE_URL": "postgresql://user:pass@host:5432/dbname?sslmode=require"}
        )
        assert_config_value(
            config,
            "SQLALCHEMY_DATABASE_URI",
            "postgresql://user:pass@host:5432/dbname?sslmode=require",
        )


@pytest.mark.unit
class TestRedisConfiguration(ConfigTestMixin):
    """Test Redis configuration and SSL handling."""

    def test_default_redis_url(self):
        """Test default Redis URL."""
        config = reload_config_with_env({})
        assert_config_value(config, "REDIS_URL", ConfigTestConstants.DEFAULT_REDIS_URL)

    def test_custom_redis_url(self):
        """Test custom Redis URL from environment."""
        config = reload_config_with_env({"REDIS_URL": "redis://custom-host:6380/1"})
        assert_config_value(config, "REDIS_URL", "redis://custom-host:6380/1")

    def test_redis_ssl_configuration(self):
        """Test Redis SSL configuration for rediss:// URLs."""
        config = reload_config_with_env({"REDIS_URL": "rediss://ssl-host:6380/0"})

        # URL should be modified to include SSL cert requirements
        assert "ssl_cert_reqs=none" in config.Config.REDIS_URL
        self.assert_redis_ssl_configuration(config, should_have_ssl=True)

    def test_redis_ssl_existing_query_params(self):
        """Test Redis SSL configuration with existing query parameters."""
        config = reload_config_with_env(
            {"REDIS_URL": "rediss://ssl-host:6380/0?timeout=30"}
        )

        # Should append SSL cert requirements to existing params
        assert "timeout=30" in config.Config.REDIS_URL
        assert "ssl_cert_reqs=none" in config.Config.REDIS_URL

    def test_redis_connection_kwargs(self):
        """Test Redis connection kwargs configuration."""
        config = reload_config_with_env({})
        assert_config_value(
            config, "REDIS_CONNECTION_KWARGS", {"decode_responses": True}
        )

    def test_redis_connection_kwargs_ssl(self):
        """Test Redis connection kwargs with SSL configuration."""
        config = reload_config_with_env({"REDIS_URL": "rediss://ssl-host:6380/0"})

        expected_kwargs = {"decode_responses": True, "ssl_cert_reqs": ssl.CERT_NONE}
        assert_config_value(config, "REDIS_CONNECTION_KWARGS", expected_kwargs)

    def test_redis_non_ssl_configuration(self):
        """Test Redis configuration without SSL maintains defaults."""
        config = reload_config_with_env({"REDIS_URL": "redis://normal-host:6379/0"})

        self.assert_redis_ssl_configuration(config, should_have_ssl=False)
        assert_config_value(
            config, "REDIS_CONNECTION_KWARGS", {"decode_responses": True}
        )


@pytest.mark.unit
class TestCeleryConfiguration:
    """Test Celery configuration settings."""

    def test_celery_basic_configuration(self):
        """Test basic Celery configuration values."""
        config = reload_config_with_env({})
        celery_config = config.Config.CELERY

        # Test core settings
        assert celery_config["broker_url"] == config.Config.REDIS_URL
        assert celery_config["result_backend"] == config.Config.REDIS_URL
        assert celery_config["task_ignore_result"] is True
        assert celery_config["task_serializer"] == "json"
        assert celery_config["accept_content"] == ["json"]
        assert celery_config["result_serializer"] == "json"
        assert celery_config["timezone"] == "US/Eastern"
        assert celery_config["enable_utc"] is True
        assert celery_config["task_track_started"] is True
        assert celery_config["task_time_limit"] == 3600
        assert celery_config["worker_max_tasks_per_child"] == 200
        assert celery_config["worker_prefetch_multiplier"] == 1
        assert celery_config["broker_connection_retry_on_startup"] is True

    def test_celery_beat_schedule_structure(self):
        """Test Celery beat schedule configuration."""
        config = reload_config_with_env({})
        beat_schedule = config.Config.CELERY["beat_schedule"]

        # Test all expected tasks are present
        expected_tasks = [
            "initiate-posts-friday",
            "fetch-content-hourly",
            "refresh-linkedin-tokens-daily",
        ]

        for task_name in expected_tasks:
            assert task_name in beat_schedule, f"Missing task: {task_name}"
            task = beat_schedule[task_name]
            assert "task" in task, f"Task {task_name} missing 'task' key"
            assert "schedule" in task, f"Task {task_name} missing 'schedule' key"
            assert isinstance(
                task["schedule"], crontab
            ), f"Task {task_name} schedule is not crontab"

    def test_celery_beat_schedule_tasks(self):
        """Test specific Celery beat schedule tasks."""
        config = reload_config_with_env({})
        beat_schedule = config.Config.CELERY["beat_schedule"]

        # Test initiate-posts-friday task
        friday_task = beat_schedule["initiate-posts-friday"]
        assert friday_task["task"] == "tasks.notifications.initiate_posts"

        # Test fetch-content-hourly task
        hourly_task = beat_schedule["fetch-content-hourly"]
        assert hourly_task["task"] == "tasks.fetch_content.fetch_content_task"

        # Test refresh-linkedin-tokens-daily task
        daily_task = beat_schedule["refresh-linkedin-tokens-daily"]
        assert daily_task["task"] == "tasks.linkedin.refresh_expiring_tokens"

    def test_celery_ssl_configuration(self):
        """Test Celery SSL configuration with rediss:// URLs."""
        config = reload_config_with_env({"REDIS_URL": "rediss://ssl-host:6380/0"})
        celery_config = config.Config.CELERY

        expected_ssl_config = {"ssl_cert_reqs": ssl.CERT_NONE}
        assert celery_config["broker_use_ssl"] == expected_ssl_config
        assert celery_config["redis_backend_settings"] == expected_ssl_config


@pytest.mark.unit
class TestOktaConfiguration:
    """Test Okta authentication configuration."""

    def test_okta_disabled_by_default(self):
        """Test that Okta is disabled by default."""
        config = reload_config_with_env({})
        assert_config_value(config, "OKTA_ENABLED", False)

    def test_okta_enabled_with_complete_configuration(self):
        """Test Okta can be enabled via environment variable."""
        config = reload_config_with_env(ConfigTestConstants.OKTA_TEST_CONFIG)

        assert_config_value(config, "OKTA_ENABLED", True)
        assert_config_value(config, "OKTA_CLIENT_ID", "test_client_id")
        assert_config_value(config, "OKTA_CLIENT_SECRET", "test_client_secret")
        assert_config_value(config, "OKTA_ISSUER", "https://test.okta.com")
        assert_config_value(config, "OKTA_REDIRECT_URI", "https://app.com/callback")

    @pytest.mark.parametrize("okta_enabled_value", ["false", "False", "FALSE", "0", ""])
    def test_okta_disabled_variations(self, okta_enabled_value):
        """Test various ways to disable Okta."""
        config = reload_config_with_env({"OKTA_ENABLED": okta_enabled_value})
        assert_config_value(config, "OKTA_ENABLED", False)

    @pytest.mark.parametrize("okta_enabled_value", ["true", "True", "TRUE"])
    def test_okta_enabled_variations(self, okta_enabled_value):
        """Test various ways to enable Okta."""
        config = reload_config_with_env({"OKTA_ENABLED": okta_enabled_value})
        assert_config_value(config, "OKTA_ENABLED", True)

    def test_okta_environment_variables_none_by_default(self):
        """Test that Okta environment variables are None by default."""
        config = reload_config_with_env({})
        assert_config_value(config, "OKTA_CLIENT_ID", None)
        assert_config_value(config, "OKTA_CLIENT_SECRET", None)
        assert_config_value(config, "OKTA_ISSUER", None)
        assert_config_value(config, "OKTA_REDIRECT_URI", None)


@pytest.mark.unit
class TestLinkedInConfiguration:
    """Test LinkedIn configuration and validation."""

    def test_linkedin_configuration_testing_mode(self):
        """Test LinkedIn configuration in testing mode (no validation)."""
        config = reload_config_with_env({})
        # Should not raise error in testing mode even without LinkedIn credentials
        assert_config_value(config, "TESTING", True)

    def test_linkedin_configuration_production_mode_missing_credentials(self):
        """Test LinkedIn configuration raises error in production without credentials."""
        with pytest.raises(ValueError, match="LINKEDIN_CLIENT_ID is required"):
            reload_config_with_env({"TESTING": "false"})

    def test_linkedin_configuration_production_mode_missing_secret(self):
        """Test LinkedIn configuration raises error without client secret."""
        with pytest.raises(ValueError, match="LINKEDIN_CLIENT_SECRET is required"):
            reload_config_with_env(
                {"LINKEDIN_CLIENT_ID": "test_id", "TESTING": "false"}
            )

    def test_linkedin_configuration_production_mode_complete(self):
        """Test LinkedIn configuration works with complete credentials in production."""
        env_vars = ConfigTestConstants.LINKEDIN_TEST_CONFIG.copy()
        env_vars["TESTING"] = "false"

        config = reload_config_with_env(env_vars)

        assert_config_value(config, "LINKEDIN_CLIENT_ID", "test_client_id")
        assert_config_value(config, "LINKEDIN_CLIENT_SECRET", "test_client_secret")
        assert_config_value(config, "TESTING", False)

    def test_linkedin_environment_variables_none_by_default(self):
        """Test that LinkedIn environment variables are None by default."""
        config = reload_config_with_env({})
        assert_config_value(config, "LINKEDIN_CLIENT_ID", None)
        assert_config_value(config, "LINKEDIN_CLIENT_SECRET", None)


@pytest.mark.unit
class TestMailConfiguration:
    """Test email/mail configuration."""

    def test_mail_default_configuration(self):
        """Test default mail configuration values."""
        config = reload_config_with_env({})

        assert_config_value(
            config, "MAIL_SERVER", ConfigTestConstants.DEFAULT_MAIL_SERVER
        )
        assert_config_value(config, "MAIL_PORT", ConfigTestConstants.DEFAULT_MAIL_PORT)
        assert_config_value(config, "MAIL_USE_TLS", True)
        assert_config_value(
            config, "MAIL_DEFAULT_SENDER", ConfigTestConstants.DEFAULT_MAIL_SENDER
        )
        assert_config_value(config, "EMAIL_ENABLED", False)

    def test_mail_custom_configuration(self):
        """Test custom mail configuration from environment."""
        mail_env = {
            "MAIL_SERVER": "smtp.custom.com",
            "MAIL_PORT": "465",
            "MAIL_USE_TLS": "false",
            "MAIL_USERNAME": "test@custom.com",
            "MAIL_PASSWORD": "test_password",
            "MAIL_DEFAULT_SENDER": "sender@custom.com",
            "EMAIL_ENABLED": "true",
        }

        config = reload_config_with_env(mail_env)

        assert_config_value(config, "MAIL_SERVER", "smtp.custom.com")
        assert_config_value(config, "MAIL_PORT", 465)
        assert_config_value(config, "MAIL_USE_TLS", False)
        assert_config_value(config, "MAIL_USERNAME", "test@custom.com")
        assert_config_value(config, "MAIL_PASSWORD", "test_password")
        assert_config_value(config, "MAIL_DEFAULT_SENDER", "sender@custom.com")
        assert_config_value(config, "EMAIL_ENABLED", True)

    @pytest.mark.parametrize(
        "tls_value,expected",
        [
            ("true", True),
            ("True", True),
            ("on", True),
            ("1", True),
            ("false", False),
            ("False", False),
            ("off", False),
            ("0", False),
            ("", False),
        ],
    )
    def test_mail_tls_boolean_parsing(self, tls_value, expected):
        """Test MAIL_USE_TLS boolean parsing with various values."""
        config = reload_config_with_env({"MAIL_USE_TLS": tls_value})
        assert_config_value(config, "MAIL_USE_TLS", expected)

    def test_mail_port_type_conversion(self):
        """Test that MAIL_PORT is properly converted to integer."""
        config = reload_config_with_env({"MAIL_PORT": "25"})
        assert_config_value(config, "MAIL_PORT", 25)
        assert isinstance(config.Config.MAIL_PORT, int)

    def test_mail_environment_variables_none_by_default(self):
        """Test that mail environment variables are None by default."""
        config = reload_config_with_env({})
        assert_config_value(config, "MAIL_USERNAME", None)
        assert_config_value(config, "MAIL_PASSWORD", None)


@pytest.mark.unit
class TestSlackConfiguration:
    """Test Slack configuration settings."""

    def test_slack_default_configuration(self):
        """Test default Slack configuration."""
        config = reload_config_with_env({})

        assert_config_value(config, "SLACK_BOT_TOKEN", None)
        assert_config_value(config, "SLACK_SIGNING_SECRET", None)
        assert_config_value(config, "SLACK_DEFAULT_CHANNEL_ID", None)
        assert_config_value(config, "SLACK_NOTIFICATIONS_ENABLED", False)

    def test_slack_custom_configuration(self):
        """Test custom Slack configuration from environment."""
        slack_env = {
            "SLACK_BOT_TOKEN": "xoxb-test-token",
            "SLACK_SIGNING_SECRET": "test_signing_secret",
            "SLACK_DEFAULT_CHANNEL_ID": "C1234567890",
            "SLACK_NOTIFICATIONS_ENABLED": "true",
        }

        config = reload_config_with_env(slack_env)

        assert_config_value(config, "SLACK_BOT_TOKEN", "xoxb-test-token")
        assert_config_value(config, "SLACK_SIGNING_SECRET", "test_signing_secret")
        assert_config_value(config, "SLACK_DEFAULT_CHANNEL_ID", "C1234567890")
        assert_config_value(config, "SLACK_NOTIFICATIONS_ENABLED", True)

    @pytest.mark.parametrize(
        "notifications_value,expected",
        [
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("false", False),
            ("False", False),
            ("FALSE", False),
            ("", False),
        ],
    )
    def test_slack_notifications_boolean_parsing(self, notifications_value, expected):
        """Test SLACK_NOTIFICATIONS_ENABLED boolean parsing."""
        config = reload_config_with_env(
            {"SLACK_NOTIFICATIONS_ENABLED": notifications_value}
        )
        assert_config_value(config, "SLACK_NOTIFICATIONS_ENABLED", expected)


@pytest.mark.unit
class TestApiKeysConfiguration:
    """Test API keys configuration."""

    def test_api_keys_default_none(self):
        """Test API keys are None by default."""
        config = reload_config_with_env({})

        assert_config_value(config, "GEMINI_API_KEY", None)
        assert_config_value(config, "FIRECRAWL_API_KEY", None)

    def test_api_keys_from_environment(self):
        """Test API keys can be set from environment variables."""
        api_env = {
            "GEMINI_API_KEY": "test_gemini_key",
            "FIRECRAWL_API_KEY": "test_firecrawl_key",
        }

        config = reload_config_with_env(api_env)

        assert_config_value(config, "GEMINI_API_KEY", "test_gemini_key")
        assert_config_value(config, "FIRECRAWL_API_KEY", "test_firecrawl_key")

    def test_api_keys_empty_strings(self):
        """Test API keys handle empty strings correctly."""
        api_env = {
            "GEMINI_API_KEY": "",
            "FIRECRAWL_API_KEY": "",
        }

        config = reload_config_with_env(api_env)

        assert_config_value(config, "GEMINI_API_KEY", "")
        assert_config_value(config, "FIRECRAWL_API_KEY", "")


@pytest.mark.unit
class TestMiscellaneousConfiguration:
    """Test miscellaneous configuration settings."""

    def test_session_configuration(self):
        """Test session configuration."""
        config = reload_config_with_env({})

        session_lifetime = config.Config.PERMANENT_SESSION_LIFETIME
        assert isinstance(session_lifetime, timedelta)
        assert session_lifetime.days == 7

    def test_judoscale_configuration(self):
        """Test Judoscale configuration."""
        config = reload_config_with_env({})
        assert_config_value(config, "JUDOSCALE", {"LOG_LEVEL": "DEBUG"})

    def test_testing_flag_behavior(self):
        """Test TESTING flag behavior."""
        # Test with explicit true
        config = reload_config_with_env({"TESTING": "true"})
        assert_config_value(config, "TESTING", True)

        # Test with explicit false (need LinkedIn credentials for production mode)
        env_vars = ConfigTestConstants.LINKEDIN_TEST_CONFIG.copy()
        env_vars["TESTING"] = "false"
        config = reload_config_with_env(env_vars)
        assert_config_value(config, "TESTING", False)


@pytest.mark.integration
@pytest.mark.slow
class TestConfigurationIntegration:
    """Integration tests for configuration combinations."""

    def test_complete_production_configuration(self):
        """Test a complete production-like configuration."""
        production_env = {
            "SECRET_KEY": "super-secret-production-key",
            "DATABASE_URL": "postgresql://user:pass@prod-host:5432/proddb",
            "REDIS_URL": "rediss://prod-redis:6380/0",
            "MAIL_SERVER": "smtp.sendgrid.net",
            "MAIL_PORT": "587",
            "MAIL_USE_TLS": "true",
            "EMAIL_ENABLED": "true",
            "SLACK_NOTIFICATIONS_ENABLED": "true",
            "OKTA_ENABLED": "true",
            **ConfigTestConstants.OKTA_TEST_CONFIG,
            **ConfigTestConstants.LINKEDIN_TEST_CONFIG,
            "TESTING": "false",
        }

        config = reload_config_with_env(production_env)

        # Verify key production settings
        assert_config_value(config, "SECRET_KEY", "super-secret-production-key")
        assert_config_value(config, "TESTING", False)
        assert_config_value(config, "EMAIL_ENABLED", True)
        assert_config_value(config, "SLACK_NOTIFICATIONS_ENABLED", True)
        assert_config_value(config, "OKTA_ENABLED", True)

        # Verify SSL is configured for Redis
        assert "ssl_cert_reqs=none" in config.Config.REDIS_URL
        assert config.Config.CELERY_BROKER_SSL_CONFIG is not None

    def test_minimal_development_configuration(self):
        """Test minimal development configuration."""
        dev_env = {"SECRET_KEY": "dev-secret", "TESTING": "true"}

        config = reload_config_with_env(dev_env)

        # Should use defaults for most settings
        assert_config_value(config, "SECRET_KEY", "dev-secret")
        assert_config_value(config, "REDIS_URL", ConfigTestConstants.DEFAULT_REDIS_URL)
        assert_config_value(config, "EMAIL_ENABLED", False)
        assert_config_value(config, "OKTA_ENABLED", False)


@pytest.mark.unit
class TestConfigurationEdgeCases:
    """Test edge cases and error conditions."""

    def test_invalid_mail_port_handling(self):
        """Test behavior with invalid MAIL_PORT values."""
        with pytest.raises(ValueError):
            reload_config_with_env({"MAIL_PORT": "not-a-number"})

    def test_content_feeds_single_pipe(self):
        """Test content feeds with single pipe character."""
        config = reload_config_with_env({"CONTENT_FEEDS": "|"})
        # Should result in two empty strings
        assert_config_value(config, "CONTENT_FEEDS", ["", ""])

    def test_redis_url_with_complex_parameters(self):
        """Test Redis URL with complex query parameters."""
        redis_url = "rediss://user:pass@host:6380/1?ssl_cert_reqs=required&retry_on_timeout=true"
        config = reload_config_with_env({"REDIS_URL": redis_url})

        # Should append ssl_cert_reqs=none to existing parameters
        final_url = config.Config.REDIS_URL
        assert "ssl_cert_reqs=required" in final_url
        assert "ssl_cert_reqs=none" in final_url
        assert "retry_on_timeout=true" in final_url

    def test_database_url_with_special_characters(self):
        """Test database URL with special characters in password."""
        db_url = "postgresql://user:p@ss%20w0rd@host:5432/db"
        config = reload_config_with_env({"DATABASE_URL": db_url})

        assert_config_value(config, "SQLALCHEMY_DATABASE_URI", db_url)
