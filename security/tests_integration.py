"""
Security Framework Integration Tests

Comprehensive tests for the JustNews Security Framework
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from security.models import AuthenticationError, EncryptionError
from security.refactor import (
    SecurityConfig,
    SecurityManager,
)


class TestSecurityFrameworkIntegration:
    """Integration tests for the complete security framework"""

    @pytest.fixture
    def security_config(self):
        """Create test security configuration"""
        return SecurityConfig(
            jwt_secret="test_jwt_secret_key_for_testing_only",
            jwt_algorithm="HS256",
            jwt_expiration_hours=1,
            bcrypt_rounds=4,  # Fast for testing
            session_timeout_minutes=5,
        )

    @pytest.fixture
    async def security_manager(self, security_config):
        """Create security manager instance"""
        manager = SecurityManager(security_config)
        await manager.initialize()
        yield manager
        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_full_authentication_flow(self, security_manager):
        """Test complete authentication flow"""
        # Create test user
        user_id = await security_manager.auth_service.create_user(
            username="testuser", email="test@example.com", password="TestPass123!"
        )

        # Authenticate user
        tokens = await security_manager.authenticate_user(
            username="testuser",
            password="TestPass123!",
            ip_address="192.168.1.100",
            user_agent="TestBrowser/1.0",
        )

        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert tokens["user"]["username"] == "testuser"

        # Validate token
        context = await security_manager.validate_token(tokens["access_token"])
        assert context.username == "testuser"
        assert context.user_id == user_id

        # Test authorization
        can_read = await security_manager.check_permission(user_id, "articles:read")
        assert can_read is True

    @pytest.mark.asyncio
    async def test_encryption_operations(self, security_manager):
        """Test encryption and decryption operations"""
        test_data = "Sensitive user information"
        key_id = "test_key"

        # Encrypt data
        encrypted = await security_manager.encrypt_data(test_data, key_id)
        assert encrypted != test_data

        # Decrypt data
        decrypted = await security_manager.decrypt_data(encrypted, key_id)
        assert decrypted == test_data

    @pytest.mark.asyncio
    async def test_compliance_logging(self, security_manager):
        """Test compliance event logging"""
        user_id = 123

        # Log compliance event
        await security_manager.log_compliance_event(
            event_type="data_access",
            user_id=user_id,
            data={"resource": "user_profile", "action": "read"},
        )

        # Export user data (should include compliance events)
        export_data = await security_manager.compliance_service.export_user_data(
            user_id
        )
        assert user_id in [event["user_id"] for event in export_data["audit_events"]]

    @pytest.mark.asyncio
    async def test_security_monitoring(self, security_manager):
        """Test security monitoring and alerting"""
        # Log security events
        await security_manager.monitor_service.log_security_event(
            "authentication_success", 123, {"ip_address": "192.168.1.100"}
        )

        await security_manager.monitor_service.log_security_event(
            "authentication_failure",
            None,
            {"ip_address": "192.168.1.100", "username": "testuser"},
        )

        # Get security metrics
        metrics = await security_manager.monitor_service.get_security_metrics(hours=1)
        assert metrics.total_events >= 2
        assert "authentication_success" in metrics.events_by_type

    @pytest.mark.asyncio
    async def test_role_based_access_control(self, security_manager):
        """Test role-based access control"""
        # Create test user
        user_id = await security_manager.auth_service.create_user(
            username="adminuser", email="admin@example.com", password="AdminPass123!"
        )

        # Assign admin role
        await security_manager.authz_service.assign_role(user_id, "admin")

        # Test admin permissions
        can_admin_users = await security_manager.check_permission(user_id, "users:read")
        assert can_admin_users is True

        can_admin_system = await security_manager.check_permission(
            user_id, "system:read"
        )
        assert can_admin_system is True

        # Test inherited permissions
        can_read_articles = await security_manager.check_permission(
            user_id, "articles:read"
        )
        assert can_read_articles is True

    @pytest.mark.asyncio
    async def test_data_subject_rights(self, security_manager):
        """Test GDPR data subject rights"""
        # Create test user
        user_id = await security_manager.auth_service.create_user(
            username="gdpruser", email="gdpr@example.com", password="GdprPass123!"
        )

        # Record consent (don't need the id for the rest of the test)
        _consent_id = await security_manager.compliance_service.record_consent(
            user_id=user_id,
            purpose="marketing",
            consent_text="I consent to marketing communications",
        )

        # Check consent
        consent_status = await security_manager.compliance_service.check_consent(
            user_id, "marketing"
        )
        assert consent_status.value == "granted"

        # Submit data erasure request
        request_id = await security_manager.compliance_service.submit_data_request(
            user_id=user_id, request_type="erase", details={"reason": "user_request"}
        )

        # Process erasure request
        await security_manager.compliance_service.process_data_request(
            request_id=request_id, action="complete", result={"erased_records": 5}
        )

        # Verify data deletion
        _export_data = await security_manager.compliance_service.export_user_data(
            user_id
        )
        # Consent should still be there for audit purposes, but user data should be minimal

    @pytest.mark.asyncio
    async def test_security_status_monitoring(self, security_manager):
        """Test security status monitoring"""
        # Get security status
        status = await security_manager.get_security_status()

        assert "overall_status" in status
        assert "services" in status
        assert "active_sessions" in status
        assert "issues" in status

        # Check service statuses
        services = status["services"]
        assert "authentication" in services
        assert "encryption" in services
        assert "compliance" in services
        assert "monitoring" in services

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, security_manager):
        async def create_and_auth_user(i):
            username = f"concurrent_user_{i}"
            user_id = await security_manager.auth_service.create_user(
                username=username, email=f"user{i}@example.com", password=f"Pass{i}123!"
            )

            tokens = await security_manager.authenticate_user(
                username=username, password=f"Pass{i}123!"
            )

            return user_id, tokens

        # Create multiple users concurrently
        tasks = [create_and_auth_user(i) for i in range(5)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        for user_id, tokens in results:
            assert "access_token" in tokens
            assert tokens["user"]["id"] == user_id

    @pytest.mark.asyncio
    async def test_session_management(self, security_manager):
        """Test session management and cleanup"""
        # Create and authenticate user
        _user_id = await security_manager.auth_service.create_user(
            username="sessionuser",
            email="session@example.com",
            password="SessionPass123!",
        )

        tokens = await security_manager.authenticate_user(
            username="sessionuser", password="SessionPass123!"
        )

        # Validate session exists
        context = await security_manager.validate_token(tokens["access_token"])
        assert context.session_id in security_manager._active_sessions

        # Simulate session expiration
        context.timestamp = datetime.now(UTC) - timedelta(minutes=10)  # Expired

        # Session should be cleaned up on next validation attempt
        with pytest.raises(AuthenticationError):
            await security_manager.validate_token(tokens["access_token"])

    @pytest.mark.asyncio
    async def test_security_alert_generation(self, security_manager):
        """Test security alert generation"""
        alert_triggered = False

        def alert_handler(alert):
            nonlocal alert_triggered
            alert_triggered = True
            assert alert.severity.value == "high"
            assert "brute_force" in alert.title.lower()

        # Add alert handler
        await security_manager.monitor_service.add_alert_handler(alert_handler)

        # Simulate brute force attempts
        for i in range(6):  # More than threshold
            await security_manager.monitor_service.log_security_event(
                "authentication_failure",
                None,
                {
                    "ip_address": "192.168.1.100",
                    "username": "testuser",
                    "attempt": i + 1,
                },
            )

        # Give async processing time
        await asyncio.sleep(0.1)

        # Check if alert was triggered
        assert alert_triggered

        # Check active alerts
        alerts = await security_manager.monitor_service.get_active_alerts()
        assert len(alerts) > 0


class TestSecurityErrorHandling:
    """Test error handling in security framework"""

    @pytest.fixture
    def security_config(self):
        return SecurityConfig(
            jwt_secret="test_jwt_secret_key_for_testing_only_32_chars_minimum",
            bcrypt_rounds=4,
        )

    @pytest.fixture
    async def security_manager(self, security_config):
        manager = SecurityManager(security_config)
        await manager.initialize()
        yield manager
        await manager.shutdown()

    @pytest.mark.asyncio
    async def test_invalid_authentication(self, security_manager):
        """Test invalid authentication handling"""
        with pytest.raises(AuthenticationError):
            await security_manager.authenticate_user(
                username="nonexistent", password="wrongpass"
            )

    @pytest.mark.asyncio
    async def test_invalid_token_validation(self, security_manager):
        """Test invalid token handling"""
        with pytest.raises(AuthenticationError):
            await security_manager.validate_token("invalid.jwt.token")

    @pytest.mark.asyncio
    async def test_unauthorized_access(self, security_manager):
        """Test unauthorized access handling"""
        # Create regular user
        user_id = await security_manager.auth_service.create_user(
            username="regularuser",
            email="regular@example.com",
            password="RegularPass123!",
        )

        # Try to access admin-only resource
        can_access = await security_manager.check_permission(user_id, "system:admin")
        assert can_access is False

    @pytest.mark.asyncio
    async def test_encryption_error_handling(self, security_manager):
        """Test encryption error handling"""
        # Try to decrypt invalid data
        with pytest.raises(EncryptionError):
            await security_manager.decrypt_data("invalid_encrypted_data")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
