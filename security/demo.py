#!/usr/bin/env python3
"""
JustNews Security Framework Usage Example

This script demonstrates how to use the comprehensive security framework
for authentication, authorization, encryption, compliance, and monitoring.
"""

import asyncio
import logging

from . import SecurityConfig, SecurityManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Demonstrate security framework usage"""

    print("🚀 JustNews Security Framework Demo")
    print("=" * 50)

    # Initialize security configuration
    config = SecurityConfig(
        jwt_secret="demo_jwt_secret_key_change_in_production",
        jwt_expiration_hours=24,
        bcrypt_rounds=12,
        session_timeout_minutes=30,
        max_login_attempts=5,
        enable_mfa=False,  # Disabled for demo
    )

    # Initialize security manager
    security = SecurityManager(config)
    await security.initialize()

    try:
        # 1. User Management
        print("\n1. 👤 User Management")
        print("-" * 30)

        # Create users
        admin_id = await security.auth_service.create_user(
            username="admin",
            email="admin@justnews.com",
            password="AdminPass123!",
            roles=["admin"],
        )
        print(f"✓ Created admin user (ID: {admin_id})")

        user_id = await security.auth_service.create_user(
            username="journalist",
            email="journalist@justnews.com",
            password="JournalistPass123!",
            roles=["user"],
        )
        print(f"✓ Created journalist user (ID: {user_id})")

        # 2. Authentication
        print("\n2. 🔐 Authentication")
        print("-" * 30)

        # Admin login
        admin_tokens = await security.authenticate_user(
            username="admin",
            password="AdminPass123!",
            ip_address="192.168.1.100",
            user_agent="DemoBrowser/1.0",
        )
        print("✓ Admin authentication successful")
        print(f"  Access Token: {admin_tokens['access_token'][:50]}...")

        # User login
        _user_tokens = await security.authenticate_user(
            username="journalist",
            password="JournalistPass123!",
            ip_address="192.168.1.101",
            user_agent="DemoBrowser/1.0",
        )
        print("✓ Journalist authentication successful")

        # 3. Authorization
        print("\n3. 🛡️ Authorization")
        print("-" * 30)

        # Check permissions
        admin_can_manage_users = await security.check_permission(admin_id, "users:read")
        user_can_manage_users = await security.check_permission(user_id, "users:read")

        print(f"✓ Admin can manage users: {admin_can_manage_users}")
        print(f"✓ User can manage users: {user_can_manage_users}")

        admin_can_read_articles = await security.check_permission(
            admin_id, "articles:read"
        )
        user_can_read_articles = await security.check_permission(
            user_id, "articles:read"
        )

        print(f"✓ Admin can read articles: {admin_can_read_articles}")
        print(f"✓ User can read articles: {user_can_read_articles}")

        # 4. Encryption
        print("\n4. 🔒 Encryption")
        print("-" * 30)

        sensitive_data = "This is confidential user information"
        print(f"Original: {sensitive_data}")

        # Encrypt data
        encrypted = await security.encrypt_data(sensitive_data)
        print(f"Encrypted: {encrypted[:50]}...")

        # Decrypt data
        decrypted = await security.decrypt_data(encrypted)
        print(f"Decrypted: {decrypted}")
        print(f"✓ Encryption/decryption successful: {sensitive_data == decrypted}")

        # 5. Compliance
        print("\n5. ⚖️ Compliance (GDPR)")
        print("-" * 30)

        # Record consent
        consent_id = await security.compliance_service.record_consent(
            user_id=user_id,
            purpose="marketing",
            consent_text="I consent to receive marketing communications",
            ip_address="192.168.1.101",
        )
        print(f"✓ Recorded marketing consent (ID: {consent_id})")

        # Check consent
        consent_status = await security.compliance_service.check_consent(
            user_id, "marketing"
        )
        print(f"✓ Marketing consent status: {consent_status.value}")

        # Log compliance event
        await security.log_compliance_event(
            event_type="data_processing",
            user_id=user_id,
            data={"purpose": "news_analysis", "data_types": ["articles", "metadata"]},
        )
        print("✓ Logged data processing event")

        # 6. Security Monitoring
        print("\n6. 👁️ Security Monitoring")
        print("-" * 30)

        # Log security events
        await security.monitor_service.log_security_event(
            "authentication_success",
            admin_id,
            {"ip_address": "192.168.1.100", "method": "password"},
        )

        await security.monitor_service.log_security_event(
            "data_access",
            user_id,
            {"resource": "articles", "action": "read", "count": 5},
        )

        print("✓ Logged security events")

        # Get security metrics
        metrics = await security.monitor_service.get_security_metrics(hours=1)
        print(f"✓ Security metrics - Total events: {metrics.total_events}")
        print(f"  Events by type: {metrics.events_by_type}")

        # 7. Security Status
        print("\n7. 📊 Security Status")
        print("-" * 30)

        status = await security.get_security_status()
        print(f"✓ Overall security status: {status['overall_status']}")
        print(f"  Active sessions: {status['active_sessions']}")
        print(f"  Security issues: {len(status['issues'])}")

        # 8. Data Subject Rights (GDPR)
        print("\n8. 🗂️ Data Subject Rights")
        print("-" * 30)

        # Export user data
        export_data = await security.compliance_service.export_user_data(user_id)
        print(
            f"✓ Exported user data - {len(export_data.get('consent_records', []))} consent records"
        )

        # Submit data erasure request
        erasure_request_id = await security.compliance_service.submit_data_request(
            user_id=user_id,
            request_type="erase",
            details={"reason": "demo_data_cleanup"},
        )
        print(f"✓ Submitted data erasure request (ID: {erasure_request_id})")

        # 9. Security Alert Demo
        print("\n9. 🚨 Security Alert Demo")
        print("-" * 30)

        # Set up alert handler
        alerts_received = []

        async def alert_handler(alert):
            alerts_received.append(alert)
            print(f"🚨 ALERT: {alert.title} (Severity: {alert.severity.value})")

        await security.monitor_service.add_alert_handler(alert_handler)

        # Simulate suspicious activity
        for i in range(3):
            await security.monitor_service.log_security_event(
                "authentication_failure",
                None,
                {
                    "ip_address": "192.168.1.200",
                    "username": "unknown_user",
                    "attempt": i + 1,
                },
            )

        # Wait for async processing
        await asyncio.sleep(0.1)

        print(f"✓ Generated {len(alerts_received)} security alerts")

        # Get active alerts
        active_alerts = await security.monitor_service.get_active_alerts()
        print(f"✓ Active alerts: {len(active_alerts)}")

        print("\n" + "=" * 50)
        print("✅ Security Framework Demo Complete!")
        print("\nKey Features Demonstrated:")
        print("• Multi-user authentication with JWT tokens")
        print("• Role-based access control (RBAC)")
        print("• Data encryption/decryption")
        print("• GDPR compliance (consent, data export, erasure)")
        print("• Real-time security monitoring")
        print("• Automated threat detection and alerting")
        print("• Comprehensive audit trails")

    except Exception as e:
        logger.error(f"Demo failed: {e}")
        raise
    finally:
        # Cleanup
        await security.shutdown()
        print("\n🧹 Security framework shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
