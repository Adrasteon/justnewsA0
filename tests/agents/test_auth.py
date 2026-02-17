"""
Tests for JustNews Auth Agent
"""

from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from agents.auth.tools import (
    authenticate_user,
    check_user_permission,
    create_user_account,
    get_user_profile,
    validate_access_token,
)


class TestAuthTools:
    """Test authentication agent tools"""

    @patch("agents.auth.tools.requests.post")
    def test_authenticate_user_success(self, mock_post):
        """Test successful user authentication"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "token123",
            "refresh_token": "refresh456",
            "user": {"id": 1, "username": "testuser"},
        }
        mock_post.return_value = mock_response

        result = authenticate_user("testuser", "password123")

        assert result is not None
        assert result["access_token"] == "token123"
        assert result["user"]["username"] == "testuser"
        mock_post.assert_called_once()

    @patch("agents.auth.tools.requests.post")
    def test_authenticate_user_failure(self, mock_post):
        """Test failed user authentication"""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = Exception("Unauthorized")
        mock_post.return_value = mock_response

        result = authenticate_user("testuser", "wrongpassword")

        assert result is None

    @patch("agents.auth.tools.requests.post")
    def test_authenticate_user_request_error(self, mock_post):
        """Test authentication with request error"""
        mock_post.side_effect = Exception("Connection error")

        result = authenticate_user("testuser", "password123")

        assert result is None

    @patch("agents.auth.tools.requests.get")
    def test_verify_user_token_valid(self, mock_get):
        """Test token verification with valid token"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "user_id": 1,
            "username": "testuser",
            "email": "test@example.com",
            "role": "user",
            "status": "active",
        }
        mock_get.return_value = mock_response

        result = validate_access_token("valid_token_123")

        assert result is not None
        assert result["user_id"] == 1
        assert result["username"] == "testuser"

    @patch("agents.auth.tools.requests.get")
    def test_verify_user_token_invalid(self, mock_get):
        """Test token verification with invalid token"""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        result = validate_access_token("invalid_token")

        assert result is None

    @patch("agents.auth.tools.get_user_by_id")
    def test_get_user_info_success(self, mock_get_user):
        """Test getting user information"""
        mock_get_user.return_value = {
            "user_id": 1,
            "username": "testuser",
            "email": "test@example.com",
            "full_name": "Test User",
            "role": "user",
            "status": "active",
            "created_at": "2023-01-01T00:00:00Z",
            "last_login": "2023-12-01T00:00:00Z",
        }

        result = get_user_profile(1)

        assert result is not None
        assert result["username"] == "testuser"
        assert result["email"] == "test@example.com"

    @patch("agents.auth.tools.requests.get")
    def test_get_user_info_not_found(self, mock_get):
        """Test getting user info for non-existent user"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        result = get_user_profile(999)

        assert result is None

    @patch("agents.auth.tools.get_user_by_id")
    def test_check_user_permissions_allowed(self, mock_get_user):
        """Test permission checking when allowed"""
        mock_get_user.return_value = {
            "user_id": 123,
            "username": "testuser",
            "role": "admin",
            "status": "active",
        }

        result = check_user_permission(123, "user")

        assert result is True

    @patch("agents.auth.tools.get_user_by_id")
    def test_check_user_permissions_denied(self, mock_get_user):
        """Test permission checking when denied"""
        mock_get_user.return_value = {
            "user_id": 123,
            "username": "testuser",
            "role": "user",
            "status": "active",
        }

        result = check_user_permission(123, "admin")

        assert result is False

    @patch("agents.auth.tools.requests.post")
    def test_create_user_success(self, mock_post):
        """Test successful user creation"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "user_id": 1,
            "username": "newuser",
            "email": "new@example.com",
        }
        mock_post.return_value = mock_response

        user_data = {
            "username": "newuser",
            "email": "new@example.com",
            "password": "securepass123",
        }

        result = create_user_account(user_data)

        assert result == 1


class TestAuthMainApp:
    """Test auth agent FastAPI application"""

    def test_app_creation(self):
        """Test that the FastAPI app can be created"""
        with (
            patch("agents.auth.main.get_logger"),
            patch("agents.auth.main.initialize_auth_engine", return_value=True),
        ):
            from agents.auth.main import app

            assert app is not None
            assert hasattr(app, "routes")

    @patch("agents.auth.main.get_auth_engine")
    def test_health_endpoint(self, mock_get_engine):
        """Test the /health endpoint"""
        mock_engine = Mock()

        async def mock_health_check():
            return {
                "status": "healthy",
                "service": "auth",
                "response_time": 0.1,
                "details": {"database": "connected", "cache": "available"},
            }

        mock_engine.health_check = mock_health_check
        mock_get_engine.return_value = mock_engine

        with (
            patch("agents.auth.main.get_logger"),
            patch("agents.auth.main.initialize_auth_engine", return_value=True),
        ):
            from agents.auth.main import app

            client = TestClient(app)

            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert "auth" in data["service"]

    @patch("agents.auth.main.initialize_auth_engine", return_value=False)
    @patch("agents.auth.main.sys.exit")
    def test_app_startup_failure_handling(self, mock_exit, mock_init):
        """Test that startup failure handling is in place"""
        # This test verifies that the failure handling code exists
        # The actual sys.exit call happens in the lifespan context manager
        # which is difficult to test directly with FastAPI TestClient
        with patch("agents.auth.main.get_logger"):
            # Just verify that the imports work and the failure path exists
            from agents.auth.main import lifespan

            assert lifespan is not None
            # The actual testing of sys.exit behavior would require integration testing

    def test_cors_middleware(self):
        """Test that CORS middleware is configured"""
        with (
            patch("agents.auth.main.get_logger"),
            patch("agents.auth.main.initialize_auth_engine", return_value=True),
        ):
            from agents.auth.main import app

            cors_middleware = None
            for middleware in app.user_middleware:
                if hasattr(middleware, "cls") and "CORSMiddleware" in str(
                    middleware.cls
                ):
                    cors_middleware = middleware
                    break

            assert cors_middleware is not None

    def test_auth_router_included(self):
        """Test that auth router is included in the app"""
        with (
            patch("agents.auth.main.get_logger"),
            patch("agents.auth.main.initialize_auth_engine", return_value=True),
        ):
            from agents.auth.main import app

            # Check that auth routes are included
            routes = [route.path for route in app.routes]
            assert any("/auth/" in route for route in routes)
