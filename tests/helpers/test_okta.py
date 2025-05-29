"""
Tests for the Okta authentication helper module.

This test suite provides comprehensive coverage for the Okta SSO integration,
including configuration validation, OAuth flow, token management, and user profile functionality.

Test Organization:
- Unit tests: Individual function testing with mocked dependencies
- Integration tests: Multi-component interaction testing
- Slow tests: Complex workflow simulation and end-to-end scenarios

Coverage includes:
- All public functions in helpers/okta.py
- Error handling and edge cases
- Security validation (CSRF tokens, nonce validation)
- OAuth flow simulation
- Token validation and JWKS handling
- User profile retrieval
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import os
import secrets
import base64
import hashlib
import json
from jose import jwt
from datetime import datetime, timedelta, timezone

from helpers.okta import (
    validate_okta_config,
    build_authorization_url,
    exchange_code_for_tokens,
    validate_tokens,
    validate_id_token,
    get_user_profile,
    generate_secure_state_and_nonce,
    OKTA_ENABLED,
    OKTA_CLIENT_ID,
    OKTA_CLIENT_SECRET,
    OKTA_ISSUER,
    OKTA_AUTH_SERVER_ID,
    OKTA_AUDIENCE,
    OKTA_SCOPES,
    OKTA_REDIRECT_URI,
)


class TestConstants:
    """Test constants for better maintainability."""

    # HTTP Status Codes
    HTTP_OK = 200
    HTTP_BAD_REQUEST = 400
    HTTP_UNAUTHORIZED = 401
    HTTP_INTERNAL_ERROR = 500

    # Test URLs
    TEST_ISSUER = "https://test.okta.com/oauth2/default"
    TEST_REDIRECT_URI = "http://localhost:5000/auth/okta/callback"
    TEST_JWKS_URI = "https://test.okta.com/oauth2/default/v1/keys"
    TEST_TOKEN_URL = "https://test.okta.com/oauth2/default/v1/token"
    TEST_USERINFO_URL = "https://test.okta.com/oauth2/default/v1/userinfo"

    # Fixed timestamps for JWT claims (prevents flaky tests)
    FIXED_IAT_TIMESTAMP = 1640995200  # Jan 1, 2022 00:00:00 UTC
    FIXED_EXP_TIMESTAMP = 1640998800  # Jan 1, 2022 01:00:00 UTC


class TestMessages:
    """Expected messages and error strings for testing."""

    OKTA_DISABLED_MESSAGE = "Okta SSO integration is disabled"
    OKTA_CONFIG_SUCCESS_MESSAGE = "Okta configuration validated successfully"
    MISSING_CLIENT_ID_ERROR = "Missing required Okta configuration: OKTA_CLIENT_ID"
    MISSING_CLIENT_SECRET_ERROR = (
        "Missing required Okta configuration: OKTA_CLIENT_SECRET"
    )
    MISSING_ISSUER_ERROR = "Missing required Okta configuration: OKTA_ISSUER"
    MISSING_MULTIPLE_ERROR = (
        "Missing required Okta configuration: OKTA_CLIENT_ID, OKTA_CLIENT_SECRET"
    )
    TOKEN_EXCHANGE_SUCCESS = "Successfully exchanged code for tokens"
    PROFILE_SUCCESS = "Successfully retrieved user profile"
    NO_KID_ERROR = "No 'kid' in token header"
    NO_MATCHING_KEY_ERROR = "No matching key found for kid: test_kid"
    INVALID_NONCE_ERROR = "Invalid nonce in ID token"


class TestData:
    """Test data and fixtures."""

    VALID_CLIENT_ID = "test_client_id"
    VALID_CLIENT_SECRET = "test_client_secret"
    VALID_ISSUER = "https://test.okta.com/oauth2/default"
    VALID_CODE = "test_auth_code"
    VALID_STATE = "test_state_value"
    VALID_NONCE = "test_nonce_value"
    VALID_ACCESS_TOKEN = "test_access_token"
    VALID_ID_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsImtpZCI6InRlc3Rfa2lkIn0."

    SAMPLE_TOKEN_RESPONSE = {
        "access_token": "sample_access_token",
        "id_token": "sample_id_token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": "openid profile email",
    }

    SAMPLE_USER_PROFILE = {
        "sub": "test_user_id",
        "name": "Test User",
        "email": "test@example.com",
        "preferred_username": "testuser",
        "given_name": "Test",
        "family_name": "User",
    }

    SAMPLE_JWKS = {
        "keys": [
            {
                "kid": "test_kid",
                "kty": "RSA",
                "alg": "RS256",
                "use": "sig",
                "n": "test_n_value",
                "e": "AQAB",
            }
        ]
    }

    SAMPLE_JWT_HEADER = {
        "typ": "JWT",
        "alg": "RS256",
        "kid": "test_kid",
    }

    SAMPLE_JWT_CLAIMS = {
        "sub": "test_user_id",
        "name": "Test User",
        "email": "test@example.com",
        "iss": "https://test.okta.com/oauth2/default",
        "aud": "test_client_id",
        "iat": TestConstants.FIXED_IAT_TIMESTAMP,
        "exp": TestConstants.FIXED_EXP_TIMESTAMP,
        "nonce": "test_nonce_value",
    }


class OktaTestHelpers:
    """Helper methods for Okta tests."""

    @staticmethod
    def create_mock_response(status_code=200, json_data=None, text=None):
        """Create a mock HTTP response."""
        response = Mock()
        response.status_code = status_code
        response.json.return_value = json_data or {}
        response.text = text or str(json_data) if json_data else ""
        response.raise_for_status = Mock()
        if status_code >= 400:
            response.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
        return response

    @staticmethod
    def create_jwt_claims(overrides=None):
        """Create JWT claims with optional overrides for testing."""
        claims = TestData.SAMPLE_JWT_CLAIMS.copy()
        if overrides:
            claims.update(overrides)
        return claims

    @staticmethod
    def create_test_jwt_token(claims=None, header=None):
        """Create a test JWT token with given claims and header."""
        test_claims = claims or TestData.SAMPLE_JWT_CLAIMS.copy()
        test_header = header or TestData.SAMPLE_JWT_HEADER.copy()

        # Simple base64 encoding for testing (not a real JWT)
        encoded_header = (
            base64.urlsafe_b64encode(json.dumps(test_header).encode())
            .decode()
            .rstrip("=")
        )
        encoded_payload = (
            base64.urlsafe_b64encode(json.dumps(test_claims).encode())
            .decode()
            .rstrip("=")
        )

        return f"{encoded_header}.{encoded_payload}.fake_signature"

    @staticmethod
    def calculate_at_hash(access_token, alg="RS256"):
        """Calculate the at_hash value for testing."""
        hash_alg = {
            "RS256": "sha256",
            "RS384": "sha384",
            "RS512": "sha512",
        }.get(alg, "sha256")

        hash_obj = getattr(hashlib, hash_alg)(access_token.encode("utf-8"))
        hash_digest = hash_obj.digest()
        half_length = len(hash_digest) // 2
        half_hash = hash_digest[:half_length]

        return base64.urlsafe_b64encode(half_hash).decode("utf-8").rstrip("=")

    @staticmethod
    def setup_token_validation_mocks(
        mock_get, mock_header, mock_decode, claims_overrides=None, header_overrides=None
    ):
        """Set up common mocks for token validation tests."""
        # Mock JWKS response
        mock_jwks_response = OktaTestHelpers.create_mock_response(
            json_data=TestData.SAMPLE_JWKS
        )
        mock_get.return_value = mock_jwks_response

        # Mock JWT header and claims
        header = TestData.SAMPLE_JWT_HEADER.copy()
        if header_overrides:
            header.update(header_overrides)
        mock_header.return_value = header

        claims = OktaTestHelpers.create_jwt_claims(claims_overrides)
        mock_decode.return_value = claims

        return claims

    @staticmethod
    def get_valid_okta_env():
        """Get a valid Okta environment configuration for testing."""
        return {
            "OKTA_ENABLED": "true",
            "OKTA_CLIENT_ID": TestData.VALID_CLIENT_ID,
            "OKTA_CLIENT_SECRET": TestData.VALID_CLIENT_SECRET,
            "OKTA_ISSUER": TestData.VALID_ISSUER,
        }


@pytest.mark.unit
class TestValidateOktaConfig:
    """Test validate_okta_config function."""

    @patch("helpers.okta.OKTA_ENABLED", False)
    def test_okta_disabled_returns_true(self, caplog):
        """Test that function returns True when Okta is disabled."""
        result = validate_okta_config()

        assert result is True
        assert TestMessages.OKTA_DISABLED_MESSAGE in caplog.text

    @patch("helpers.okta.OKTA_ENABLED", True)
    @patch("helpers.okta.OKTA_CLIENT_ID", TestData.VALID_CLIENT_ID)
    @patch("helpers.okta.OKTA_CLIENT_SECRET", TestData.VALID_CLIENT_SECRET)
    @patch("helpers.okta.OKTA_ISSUER", TestData.VALID_ISSUER)
    def test_valid_config_returns_true(self, caplog):
        """Test that function returns True with valid configuration."""
        result = validate_okta_config()

        assert result is True
        assert TestMessages.OKTA_CONFIG_SUCCESS_MESSAGE in caplog.text

    @pytest.mark.parametrize(
        "missing_field,expected_error",
        [
            ("OKTA_CLIENT_ID", TestMessages.MISSING_CLIENT_ID_ERROR),
            ("OKTA_CLIENT_SECRET", TestMessages.MISSING_CLIENT_SECRET_ERROR),
            ("OKTA_ISSUER", TestMessages.MISSING_ISSUER_ERROR),
        ],
    )
    @patch("helpers.okta.OKTA_ENABLED", True)
    def test_missing_single_field_raises_error(self, missing_field, expected_error):
        """Test that missing individual fields raise appropriate errors."""
        # Set all fields to valid values first
        with (
            patch("helpers.okta.OKTA_CLIENT_ID", TestData.VALID_CLIENT_ID),
            patch("helpers.okta.OKTA_CLIENT_SECRET", TestData.VALID_CLIENT_SECRET),
            patch("helpers.okta.OKTA_ISSUER", TestData.VALID_ISSUER),
        ):

            # Then patch the specific missing field to empty string
            with patch(f"helpers.okta.{missing_field}", ""):
                with pytest.raises(ValueError, match=expected_error):
                    validate_okta_config()

    @patch("helpers.okta.OKTA_ENABLED", True)
    @patch("helpers.okta.OKTA_CLIENT_ID", "")
    @patch("helpers.okta.OKTA_CLIENT_SECRET", "")
    @patch("helpers.okta.OKTA_ISSUER", TestData.VALID_ISSUER)
    def test_missing_multiple_fields_raises_error(self):
        """Test that missing multiple fields shows all missing ones."""
        with pytest.raises(ValueError, match=TestMessages.MISSING_MULTIPLE_ERROR):
            validate_okta_config()

    @patch("helpers.okta.OKTA_ENABLED", True)
    @patch("helpers.okta.OKTA_CLIENT_ID", "")
    @patch("helpers.okta.OKTA_CLIENT_SECRET", "")
    @patch("helpers.okta.OKTA_ISSUER", "")
    def test_empty_values_treated_as_missing(self):
        """Test that empty string values are treated as missing."""
        with pytest.raises(ValueError) as exc_info:
            validate_okta_config()

        error_message = str(exc_info.value)
        assert "OKTA_CLIENT_ID" in error_message
        assert "OKTA_CLIENT_SECRET" in error_message
        assert "OKTA_ISSUER" in error_message


@pytest.mark.unit
class TestBuildAuthorizationUrl:
    """Test build_authorization_url function."""

    @patch("helpers.okta.OKTA_CLIENT_ID", TestData.VALID_CLIENT_ID)
    @patch("helpers.okta.OKTA_ISSUER", TestData.VALID_ISSUER)
    @patch("helpers.okta.OKTA_REDIRECT_URI", TestConstants.TEST_REDIRECT_URI)
    @patch("helpers.okta.OKTA_SCOPES", ["openid", "profile", "email"])
    def test_build_authorization_url_with_all_parameters(self):
        """Test building authorization URL with all parameters."""
        state = TestData.VALID_STATE
        nonce = TestData.VALID_NONCE

        url = build_authorization_url(state, nonce)

        assert url.startswith(f"{TestData.VALID_ISSUER}/v1/authorize?")

        # Check individual parameters (accounting for URL encoding)
        assert f"client_id={TestData.VALID_CLIENT_ID}" in url
        assert "response_type=code" in url
        assert "scope=openid+profile+email" in url
        # The redirect_uri gets URL encoded, so check for the encoded version
        assert (
            "redirect_uri=http%3A%2F%2Flocalhost%3A5000%2Fauth%2Fokta%2Fcallback" in url
        )
        assert f"state={state}" in url
        assert f"nonce={nonce}" in url

    @patch("helpers.okta.OKTA_CLIENT_ID", TestData.VALID_CLIENT_ID)
    @patch("helpers.okta.OKTA_ISSUER", TestData.VALID_ISSUER)
    @patch("helpers.okta.OKTA_SCOPES", ["openid", "profile"])
    def test_build_authorization_url_with_custom_scopes(self):
        """Test building authorization URL with different scopes."""
        state = "custom_state"
        nonce = "custom_nonce"

        url = build_authorization_url(state, nonce)

        assert "scope=openid+profile" in url
        assert f"state={state}" in url
        assert f"nonce={nonce}" in url


@pytest.mark.unit
class TestExchangeCodeForTokens:
    """Test exchange_code_for_tokens function."""

    @patch("helpers.okta.OKTA_ISSUER", TestData.VALID_ISSUER)
    @patch("helpers.okta.OKTA_CLIENT_ID", TestData.VALID_CLIENT_ID)
    @patch("helpers.okta.OKTA_CLIENT_SECRET", TestData.VALID_CLIENT_SECRET)
    @patch("helpers.okta.OKTA_REDIRECT_URI", TestConstants.TEST_REDIRECT_URI)
    @patch("helpers.okta.requests.post")
    def test_successful_token_exchange(self, mock_post, caplog):
        """Test successful token exchange."""
        mock_response = OktaTestHelpers.create_mock_response(
            status_code=TestConstants.HTTP_OK, json_data=TestData.SAMPLE_TOKEN_RESPONSE
        )
        mock_post.return_value = mock_response

        result = exchange_code_for_tokens(TestData.VALID_CODE)

        assert result == TestData.SAMPLE_TOKEN_RESPONSE
        assert TestMessages.TOKEN_EXCHANGE_SUCCESS in caplog.text

        # Verify the POST request was made correctly
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == f"{TestData.VALID_ISSUER}/v1/token"

        payload = call_args[1]["data"]
        expected_payload = {
            "grant_type": "authorization_code",
            "code": TestData.VALID_CODE,
            "redirect_uri": TestConstants.TEST_REDIRECT_URI,
            "client_id": TestData.VALID_CLIENT_ID,
            "client_secret": TestData.VALID_CLIENT_SECRET,
        }
        for key, value in expected_payload.items():
            assert payload[key] == value

    @pytest.mark.parametrize(
        "status_code,exception_type",
        [
            (TestConstants.HTTP_BAD_REQUEST, Exception),
            (TestConstants.HTTP_UNAUTHORIZED, Exception),
            (TestConstants.HTTP_INTERNAL_ERROR, Exception),
        ],
    )
    @patch("helpers.okta.OKTA_ISSUER", TestData.VALID_ISSUER)
    @patch("helpers.okta.requests.post")
    def test_token_exchange_http_errors(self, mock_post, status_code, exception_type):
        """Test token exchange with various HTTP errors."""
        mock_response = OktaTestHelpers.create_mock_response(status_code=status_code)
        mock_post.return_value = mock_response

        with pytest.raises(exception_type, match="Failed to exchange code for tokens"):
            exchange_code_for_tokens(TestData.VALID_CODE)

    @patch("helpers.okta.OKTA_ISSUER", TestData.VALID_ISSUER)
    @patch("helpers.okta.requests.post")
    def test_token_exchange_network_exception(self, mock_post):
        """Test token exchange with network exception."""
        mock_post.side_effect = Exception("Network error")

        with pytest.raises(Exception, match="Failed to exchange code for tokens"):
            exchange_code_for_tokens(TestData.VALID_CODE)


@pytest.mark.unit
class TestValidateTokens:
    """Test validate_tokens function."""

    @patch("helpers.okta.OKTA_ISSUER", TestData.VALID_ISSUER)
    @patch("helpers.okta.OKTA_CLIENT_ID", TestData.VALID_CLIENT_ID)
    @patch("helpers.okta.requests.get")
    @patch("helpers.okta.jwt.get_unverified_header")
    @patch("helpers.okta.jwt.decode")
    def test_successful_token_validation(
        self, mock_decode, mock_header, mock_get, caplog
    ):
        """Test successful token validation with valid ID token."""
        claims = OktaTestHelpers.setup_token_validation_mocks(
            mock_get, mock_header, mock_decode
        )

        result = validate_tokens(
            TestData.VALID_ID_TOKEN, TestData.VALID_ACCESS_TOKEN, TestData.VALID_NONCE
        )

        assert result == claims
        assert "Access token is present" in caplog.text
        assert "ID token validated successfully" in caplog.text

    @patch("helpers.okta.OKTA_ISSUER", TestData.VALID_ISSUER)
    @patch("helpers.okta.requests.get")
    def test_jwks_request_failure(self, mock_get):
        """Test token validation when JWKS request fails."""
        mock_get.side_effect = Exception("JWKS request failed")

        with pytest.raises(Exception, match="Failed to validate tokens"):
            validate_tokens(
                TestData.VALID_ID_TOKEN,
                TestData.VALID_ACCESS_TOKEN,
                TestData.VALID_NONCE,
            )

    @patch("helpers.okta.OKTA_ISSUER", TestData.VALID_ISSUER)
    @patch("helpers.okta.requests.get")
    @patch("helpers.okta.jwt.get_unverified_header")
    def test_missing_kid_in_header(self, mock_header, mock_get):
        """Test token validation when kid is missing from header."""
        mock_jwks_response = OktaTestHelpers.create_mock_response(
            json_data=TestData.SAMPLE_JWKS
        )
        mock_get.return_value = mock_jwks_response
        mock_header.return_value = {"alg": "RS256"}  # Missing kid

        with pytest.raises(Exception, match=TestMessages.NO_KID_ERROR):
            validate_tokens(
                TestData.VALID_ID_TOKEN,
                TestData.VALID_ACCESS_TOKEN,
                TestData.VALID_NONCE,
            )

    @patch("helpers.okta.OKTA_ISSUER", TestData.VALID_ISSUER)
    @patch("helpers.okta.requests.get")
    @patch("helpers.okta.jwt.get_unverified_header")
    def test_no_matching_key_in_jwks(self, mock_header, mock_get):
        """Test token validation when no matching key found in JWKS."""
        mock_jwks_response = OktaTestHelpers.create_mock_response(
            json_data={"keys": []}  # Empty keys array
        )
        mock_get.return_value = mock_jwks_response
        mock_header.return_value = {"kid": "test_kid", "alg": "RS256"}

        with pytest.raises(Exception, match=TestMessages.NO_MATCHING_KEY_ERROR):
            validate_tokens(
                TestData.VALID_ID_TOKEN,
                TestData.VALID_ACCESS_TOKEN,
                TestData.VALID_NONCE,
            )

    @patch("helpers.okta.OKTA_ISSUER", TestData.VALID_ISSUER)
    @patch("helpers.okta.OKTA_CLIENT_ID", TestData.VALID_CLIENT_ID)
    @patch("helpers.okta.requests.get")
    @patch("helpers.okta.jwt.get_unverified_header")
    @patch("helpers.okta.jwt.decode")
    def test_invalid_nonce_raises_error(self, mock_decode, mock_header, mock_get):
        """Test token validation with invalid nonce."""
        OktaTestHelpers.setup_token_validation_mocks(
            mock_get,
            mock_header,
            mock_decode,
            claims_overrides={"nonce": "wrong_nonce"},
        )

        with pytest.raises(Exception, match=TestMessages.INVALID_NONCE_ERROR):
            validate_tokens(
                TestData.VALID_ID_TOKEN,
                TestData.VALID_ACCESS_TOKEN,
                TestData.VALID_NONCE,
            )

    @patch("helpers.okta.OKTA_ISSUER", TestData.VALID_ISSUER)
    @patch("helpers.okta.OKTA_CLIENT_ID", TestData.VALID_CLIENT_ID)
    @patch("helpers.okta.requests.get")
    @patch("helpers.okta.jwt.get_unverified_header")
    @patch("helpers.okta.jwt.decode")
    def test_at_hash_validation_success(
        self, mock_decode, mock_header, mock_get, caplog
    ):
        """Test successful at_hash validation."""
        access_token = TestData.VALID_ACCESS_TOKEN
        at_hash = OktaTestHelpers.calculate_at_hash(access_token)

        claims = OktaTestHelpers.setup_token_validation_mocks(
            mock_get, mock_header, mock_decode, claims_overrides={"at_hash": at_hash}
        )

        result = validate_tokens(
            TestData.VALID_ID_TOKEN, access_token, TestData.VALID_NONCE
        )

        assert result == claims
        assert "Manually validating at_hash claim" in caplog.text
        assert "at_hash validation successful" in caplog.text

    @patch("helpers.okta.OKTA_ISSUER", TestData.VALID_ISSUER)
    @patch("helpers.okta.requests.get")
    @patch("helpers.okta.jwt.get_unverified_header")
    @patch("helpers.okta.jwt.decode")
    def test_at_hash_validation_mismatch_warning(
        self, mock_decode, mock_header, mock_get, caplog
    ):
        """Test at_hash validation with mismatch (should warn but not fail)."""
        claims = OktaTestHelpers.setup_token_validation_mocks(
            mock_get,
            mock_header,
            mock_decode,
            claims_overrides={"at_hash": "wrong_hash_value"},
        )

        result = validate_tokens(
            TestData.VALID_ID_TOKEN, TestData.VALID_ACCESS_TOKEN, TestData.VALID_NONCE
        )

        assert result == claims
        assert "at_hash mismatch" in caplog.text
        assert "Proceeding with caution" in caplog.text

    @patch("helpers.okta.OKTA_ISSUER", TestData.VALID_ISSUER)
    @patch("helpers.okta.requests.get")
    @patch("helpers.okta.jwt.get_unverified_header")
    @patch("helpers.okta.jwt.decode")
    def test_validation_without_access_token(
        self, mock_decode, mock_header, mock_get, caplog
    ):
        """Test token validation without access token."""
        claims = OktaTestHelpers.setup_token_validation_mocks(
            mock_get, mock_header, mock_decode
        )

        result = validate_tokens(
            TestData.VALID_ID_TOKEN, None, TestData.VALID_NONCE  # No access token
        )

        assert result == claims
        assert "No access token provided" in caplog.text


@pytest.mark.unit
class TestValidateIdToken:
    """Test validate_id_token function."""

    @patch("helpers.okta.validate_tokens")
    def test_validate_id_token_calls_validate_tokens(self, mock_validate_tokens):
        """Test that validate_id_token correctly calls validate_tokens."""
        mock_validate_tokens.return_value = TestData.SAMPLE_JWT_CLAIMS

        result = validate_id_token(
            TestData.VALID_ID_TOKEN, TestData.VALID_NONCE, TestData.VALID_ACCESS_TOKEN
        )

        assert result == TestData.SAMPLE_JWT_CLAIMS
        mock_validate_tokens.assert_called_once_with(
            TestData.VALID_ID_TOKEN, TestData.VALID_ACCESS_TOKEN, TestData.VALID_NONCE
        )

    @patch("helpers.okta.validate_tokens")
    def test_validate_id_token_without_access_token(self, mock_validate_tokens):
        """Test validate_id_token without access token."""
        mock_validate_tokens.return_value = TestData.SAMPLE_JWT_CLAIMS

        result = validate_id_token(TestData.VALID_ID_TOKEN, TestData.VALID_NONCE)

        assert result == TestData.SAMPLE_JWT_CLAIMS
        mock_validate_tokens.assert_called_once_with(
            TestData.VALID_ID_TOKEN, None, TestData.VALID_NONCE
        )


@pytest.mark.unit
class TestGetUserProfile:
    """Test get_user_profile function."""

    @patch("helpers.okta.OKTA_ISSUER", TestData.VALID_ISSUER)
    @patch("helpers.okta.requests.get")
    def test_successful_profile_retrieval(self, mock_get, caplog):
        """Test successful user profile retrieval."""
        mock_response = OktaTestHelpers.create_mock_response(
            status_code=TestConstants.HTTP_OK, json_data=TestData.SAMPLE_USER_PROFILE
        )
        mock_get.return_value = mock_response

        result = get_user_profile(TestData.VALID_ACCESS_TOKEN)

        assert result == TestData.SAMPLE_USER_PROFILE
        assert TestMessages.PROFILE_SUCCESS in caplog.text

        # Verify the request was made correctly
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[0][0] == f"{TestData.VALID_ISSUER}/v1/userinfo"
        assert (
            call_args[1]["headers"]["Authorization"]
            == f"Bearer {TestData.VALID_ACCESS_TOKEN}"
        )

    @pytest.mark.parametrize(
        "status_code",
        [
            TestConstants.HTTP_UNAUTHORIZED,
            TestConstants.HTTP_BAD_REQUEST,
            TestConstants.HTTP_INTERNAL_ERROR,
        ],
    )
    @patch("helpers.okta.OKTA_ISSUER", TestData.VALID_ISSUER)
    @patch("helpers.okta.requests.get")
    def test_profile_retrieval_http_errors(self, mock_get, status_code):
        """Test user profile retrieval with various HTTP errors."""
        mock_response = OktaTestHelpers.create_mock_response(status_code=status_code)
        mock_get.return_value = mock_response

        with pytest.raises(Exception, match="Failed to retrieve user profile"):
            get_user_profile(TestData.VALID_ACCESS_TOKEN)

    @patch("helpers.okta.OKTA_ISSUER", TestData.VALID_ISSUER)
    @patch("helpers.okta.requests.get")
    def test_profile_retrieval_network_exception(self, mock_get):
        """Test user profile retrieval with network exception."""
        mock_get.side_effect = Exception("Network error")

        with pytest.raises(Exception, match="Failed to retrieve user profile"):
            get_user_profile(TestData.VALID_ACCESS_TOKEN)


@pytest.mark.unit
class TestGenerateSecureStateAndNonce:
    """Test generate_secure_state_and_nonce function."""

    @patch("helpers.okta.secrets.token_urlsafe")
    def test_generate_state_and_nonce_with_mocked_secrets(self, mock_token_urlsafe):
        """Test generation of secure state and nonce with mocked values."""
        mock_token_urlsafe.side_effect = ["test_state", "test_nonce"]

        state, nonce = generate_secure_state_and_nonce()

        assert state == "test_state"
        assert nonce == "test_nonce"
        assert mock_token_urlsafe.call_count == 2
        # Verify that 32 bytes are requested for both
        mock_token_urlsafe.assert_any_call(32)

    def test_generate_state_and_nonce_returns_different_values(self):
        """Test that state and nonce are different values."""
        state, nonce = generate_secure_state_and_nonce()

        assert state != nonce
        assert len(state) > 0
        assert len(nonce) > 0
        assert isinstance(state, str)
        assert isinstance(nonce, str)

    def test_generate_state_and_nonce_multiple_calls_produce_unique_values(self):
        """Test that multiple calls return different values."""
        state1, nonce1 = generate_secure_state_and_nonce()
        state2, nonce2 = generate_secure_state_and_nonce()

        assert state1 != state2
        assert nonce1 != nonce2


@pytest.mark.integration
class TestOktaConfiguration:
    """Test Okta configuration and constants."""

    def test_okta_configuration_constants_exist(self):
        """Test that all required Okta configuration constants exist."""
        # These should be importable without error
        assert OKTA_ENABLED is not None
        assert OKTA_CLIENT_ID is not None
        assert OKTA_CLIENT_SECRET is not None
        assert OKTA_ISSUER is not None
        assert OKTA_AUTH_SERVER_ID is not None
        assert OKTA_AUDIENCE is not None
        assert OKTA_SCOPES is not None
        assert OKTA_REDIRECT_URI is not None

    def test_okta_scopes_default_value(self):
        """Test that OKTA_SCOPES has correct default structure."""
        # Should be a list of strings
        assert isinstance(OKTA_SCOPES, list)
        assert all(isinstance(scope, str) for scope in OKTA_SCOPES)

    def test_okta_constants_have_expected_types(self):
        """Test that Okta constants have expected types."""
        assert isinstance(OKTA_ENABLED, bool) or isinstance(OKTA_ENABLED, str)
        assert isinstance(OKTA_CLIENT_ID, str)
        assert isinstance(OKTA_CLIENT_SECRET, str)
        assert isinstance(OKTA_ISSUER, str)
        assert isinstance(OKTA_AUTH_SERVER_ID, str)
        assert isinstance(OKTA_AUDIENCE, str)
        assert isinstance(OKTA_REDIRECT_URI, str)


@pytest.mark.slow
class TestOktaIntegrationFlow:
    """Test complete Okta integration workflows."""

    @patch("helpers.okta.OKTA_ENABLED", True)
    @patch("helpers.okta.OKTA_CLIENT_ID", TestData.VALID_CLIENT_ID)
    @patch("helpers.okta.OKTA_CLIENT_SECRET", TestData.VALID_CLIENT_SECRET)
    @patch("helpers.okta.OKTA_ISSUER", TestData.VALID_ISSUER)
    @patch("helpers.okta.requests.post")
    @patch("helpers.okta.requests.get")
    @patch("helpers.okta.jwt.get_unverified_header")
    @patch("helpers.okta.jwt.decode")
    def test_complete_authentication_flow_simulation(
        self, mock_decode, mock_header, mock_get, mock_post
    ):
        """Test complete Okta authentication flow simulation."""
        # Step 1: Validate configuration
        assert validate_okta_config() is True

        # Step 2: Generate state and nonce
        state, nonce = generate_secure_state_and_nonce()
        assert state is not None
        assert nonce is not None

        # Step 3: Build authorization URL
        auth_url = build_authorization_url(state, nonce)
        assert TestData.VALID_CLIENT_ID in auth_url
        assert state in auth_url
        assert nonce in auth_url

        # Step 4: Exchange code for tokens
        mock_token_response = OktaTestHelpers.create_mock_response(
            json_data=TestData.SAMPLE_TOKEN_RESPONSE
        )
        mock_post.return_value = mock_token_response

        tokens = exchange_code_for_tokens(TestData.VALID_CODE)
        assert "access_token" in tokens
        assert "id_token" in tokens

        # Step 5: Validate tokens - use the actual nonce generated above
        claims = OktaTestHelpers.setup_token_validation_mocks(
            mock_get,
            mock_header,
            mock_decode,
            claims_overrides={"nonce": nonce},  # Use the actual generated nonce
        )

        validated_claims = validate_tokens(
            tokens["id_token"], tokens["access_token"], nonce
        )
        assert validated_claims["sub"] == claims["sub"]

        # Step 6: Get user profile
        mock_profile_response = OktaTestHelpers.create_mock_response(
            json_data=TestData.SAMPLE_USER_PROFILE
        )
        mock_get.return_value = mock_profile_response

        profile = get_user_profile(tokens["access_token"])
        assert profile["email"] == TestData.SAMPLE_USER_PROFILE["email"]

    @patch("helpers.okta.OKTA_ENABLED", True)
    @patch("helpers.okta.OKTA_CLIENT_ID", "")
    def test_invalid_config_prevents_authentication_flow(self):
        """Test that invalid configuration prevents authentication flow."""
        with pytest.raises(ValueError):
            validate_okta_config()

    def test_network_error_handling_in_authentication_flow(self):
        """Test network error handling at various points in the flow."""
        # Test token exchange failure
        with patch(
            "helpers.okta.requests.post", side_effect=Exception("Network error")
        ):
            with pytest.raises(Exception, match="Failed to exchange code for tokens"):
                exchange_code_for_tokens(TestData.VALID_CODE)

        # Test user profile fetch failure
        with patch("helpers.okta.requests.get", side_effect=Exception("Network error")):
            with pytest.raises(Exception, match="Failed to retrieve user profile"):
                get_user_profile(TestData.VALID_ACCESS_TOKEN)

        # Test JWKS fetch failure during token validation
        with patch("helpers.okta.requests.get", side_effect=Exception("Network error")):
            with pytest.raises(Exception, match="Failed to validate tokens"):
                validate_tokens(
                    TestData.VALID_ID_TOKEN,
                    TestData.VALID_ACCESS_TOKEN,
                    TestData.VALID_NONCE,
                )

    @pytest.mark.parametrize("algorithm", ["RS256", "RS384", "RS512"])
    @patch("helpers.okta.OKTA_ISSUER", TestData.VALID_ISSUER)
    @patch("helpers.okta.OKTA_CLIENT_ID", TestData.VALID_CLIENT_ID)
    @patch("helpers.okta.requests.get")
    @patch("helpers.okta.jwt.get_unverified_header")
    @patch("helpers.okta.jwt.decode")
    def test_token_validation_with_different_jwt_algorithms(
        self, mock_decode, mock_header, mock_get, algorithm
    ):
        """Test token validation with different JWT signing algorithms."""
        access_token = TestData.VALID_ACCESS_TOKEN
        at_hash = OktaTestHelpers.calculate_at_hash(access_token, algorithm)

        claims = OktaTestHelpers.setup_token_validation_mocks(
            mock_get,
            mock_header,
            mock_decode,
            header_overrides={"alg": algorithm},
            claims_overrides={"at_hash": at_hash},
        )

        result = validate_tokens(
            TestData.VALID_ID_TOKEN, access_token, TestData.VALID_NONCE
        )

        assert result == claims

        # Verify the correct algorithm was used in jwt.decode
        mock_decode.assert_called_once()
        call_kwargs = mock_decode.call_args[1]
        assert call_kwargs["algorithms"] == [algorithm]
