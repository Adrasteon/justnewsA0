# JustNews Security Framework

A comprehensive, production-ready security framework for JustNews providing authentication, authorization, encryption,
compliance monitoring, and security event tracking.

## Features

- **🔐 Authentication**: JWT-based authentication with MFA support

- **🛡️ Authorization**: Role-based access control (RBAC) with hierarchical permissions

- **🔒 Encryption**: AES-256 encryption for data protection

- **⚖️ Compliance**: GDPR/CCPA compliance with audit trails and data subject rights

- **👁️ Monitoring**: Real-time security monitoring and threat detection

- **🚨 Alerting**: Automated security alerts and incident response

## Quick Start

### Installation

```bash
cd security/refactor
pip install -r requirements.txt

```bash

### Basic Usage

```python
from security.refactor import SecurityManager, SecurityConfig

## Configure security

config = SecurityConfig(
    jwt_secret="your-secret-key",
    jwt_expiration_hours=24,
    bcrypt_rounds=12
)

## Initialize security framework

security = SecurityManager(config)
await security.initialize()

## Create user

user_id = await security.auth_service.create_user(
    username="john_doe",
    email="john@example.com",
    password="SecurePass123!"
)

## Authenticate user

tokens = await security.authenticate_user("john_doe", "SecurePass123!")

## Check permissions

can_read = await security.check_permission(user_id, "articles:read")

## Encrypt sensitive data

encrypted = await security.encrypt_data("sensitive information")

## Cleanup

await security.shutdown()

```

## Architecture

### Core Components

#### SecurityManager

Central orchestrator coordinating all security operations.

#### AuthenticationService

- User registration and login

- JWT token generation and validation

- Session management

- Multi-factor authentication (MFA) support

#### AuthorizationService

- Role-based access control (RBAC)

- Permission validation

- User role management

- Resource-level permissions

#### EncryptionService

- Symmetric encryption (AES-256-GCM)

- Asymmetric encryption (RSA)

- Key management and rotation

- Digital signatures

#### ComplianceService

- GDPR/CCPA compliance

- Consent management

- Data subject rights (access, rectify, erase)

- Audit trail generation

#### SecurityMonitor

- Real-time security event logging

- Threat detection rules

- Automated alerting

- Security metrics and reporting

## Configuration

```python
from security.refactor import SecurityConfig

config = SecurityConfig(
    # JWT settings
    jwt_secret="your-256-bit-secret",
    jwt_algorithm="HS256",
    jwt_expiration_hours=24,

    # Password security
    bcrypt_rounds=12,

    # Session management
    session_timeout_minutes=30,
    max_login_attempts=5,

    # Encryption
    encryption_key=None,  # Auto-generated if not provided

    # Compliance
    audit_retention_days=2555,  # 7 years for GDPR
    consent_retention_days=2555,

    # Monitoring
    enable_mfa=True
)

```bash

## API Reference

### Authentication

```python

## Create user

user_id = await auth_service.create_user(username, email, password, roles)

## Authenticate

tokens = await auth_service.authenticate(username, password)

## Validate token

payload = await auth_service.validate_token(access_token)

## Refresh token

new_tokens = await auth_service.refresh_access_token(refresh_token)

```

### Authorization

```python

## Check permission

allowed = await authz_service.check_permission(user_id, "articles:read")

## Get user roles

roles = await authz_service.get_user_roles(user_id)

## Assign role

await authz_service.assign_role(user_id, "moderator")

## Create custom role

await authz_service.create_role(Role(
    name="editor",
    description="Content editor",
    permissions=["articles:write", "comments:moderate"]
))

```bash

### Encryption

```python

## Encrypt data

encrypted = await encrypt_service.encrypt_data(data, key_id)

## Decrypt data

decrypted = await encrypt_service.decrypt_data(encrypted_data, key_id)

## Generate key pair

key_pair = await encrypt_service.generate_key_pair()

## Sign data

signature = await encrypt_service.sign_data(data, private_key_id)

## Verify signature

valid = await encrypt_service.verify_signature(data, signature, public_key_id)

```

### Compliance

```python

## Record consent

consent_id = await compliance_service.record_consent(
    user_id, "marketing", "consent text"
)

## Check consent

status = await compliance_service.check_consent(user_id, "marketing")

## Export user data (GDPR Article 15)

data = await compliance_service.export_user_data(user_id)

## Delete user data (GDPR Article 17)

await compliance_service.delete_user_data(user_id)

## Generate compliance report

report = await compliance_service.get_compliance_report("gdpr")

```bash

### Monitoring

```python

## Log security event

await monitor.log_security_event(
    "authentication_failure",
    user_id,
    {"ip_address": "192.168.1.100"}
)

## Get security metrics

metrics = await monitor.get_security_metrics(hours=24)

## Get active alerts

alerts = await monitor.get_active_alerts()

## Resolve alert

await monitor.resolve_alert(alert_id, "Issue resolved")

```

## Security Policies

### Authentication Policies

- **Password Requirements**: Minimum 12 characters, complexity rules

- **Account Lockout**: 5 failed attempts trigger 30-minute lockout

- **Session Timeout**: Automatic logout after 30 minutes of inactivity

- **MFA Support**: Optional TOTP-based multi-factor authentication

### Authorization Policies

- **Role Hierarchy**: user < moderator < admin

- **Principle of Least Privilege**: Users get minimum required permissions

- **Permission Inheritance**: Roles inherit permissions from parent roles

- **Resource-Level Access**: Granular permissions per resource

### Data Protection Policies

- **Encryption at Rest**: AES-256-GCM encryption for sensitive data

- **Encryption in Transit**: TLS 1.3 required for all communications

- **Key Rotation**: Automatic key rotation every 90 days

- **Secure Deletion**: Cryptographic erasure of deleted data

### Compliance Policies

- **GDPR Compliance**: Full support for data subject rights

- **CCPA Compliance**: California Consumer Privacy Act support

- **Audit Trails**: Complete logging of all security-relevant operations

- **Consent Management**: Granular consent tracking with legal basis

## Integration Examples

### FastAPI Integration

```python
from fastapi import Depends, HTTPException
from security.refactor import SecurityManager

security = SecurityManager(config)

@app.post("/api/articles")
async def create_article(
    article: ArticleCreate,
    current_user = Depends(security.get_current_user)
):
    # User automatically authenticated and authorized
    if not await security.check_permission(current_user.id, "articles:create"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    return await create_article_logic(article, current_user)

```bash

### Database Integration

```python
class SecureDatabase:
    def __init__(self, security: SecurityManager):
        self.security = security

    async def save_user_profile(self, user_id: int, profile_data: dict):
        # Encrypt sensitive fields
        secure_data = profile_data.copy()
        if "ssn" in profile_data:
            secure_data["ssn"] = await self.security.encrypt_data(profile_data["ssn"])

        # Save with audit trail
        await self.db.save("user_profiles", secure_data)
        await self.security.log_compliance_event(
            "data_storage",
            user_id,
            {"data_types": list(profile_data.keys())}
        )

```

## Testing

Run the integration tests:

```bash
pytest security/refactor/tests_integration.py -v

```bash

Run the demo:

```bash
python security/refactor/demo.py

```

## Security Best Practices

### Development

- **Input Validation**: Always validate inputs using Pydantic models

- **SQL Injection Prevention**: Use parameterized queries only

- **XSS Protection**: Sanitize all user-generated content

- **CSRF Protection**: Implement anti-CSRF tokens

### Operations

- **Regular Updates**: Keep all dependencies updated

- **Security Scanning**: Regular vulnerability scans

- **Access Reviews**: Quarterly access permission reviews

- **Incident Response**: Documented incident response procedures

### Compliance

- **Data Classification**: Classify data by sensitivity level

- **Privacy by Design**: Build privacy into system architecture

- **Regular Audits**: Conduct regular security and compliance audits

- **Training**: Security awareness training for all team members

## Monitoring & Alerting

### Built-in Rules

- **Brute Force Detection**: Multiple failed login attempts

- **Unusual Traffic**: Abnormal request patterns

- **Account Lockouts**: Security-relevant account changes

- **Compliance Violations**: GDPR/CCPA violations

### Custom Rules

```python
await monitor.add_monitoring_rule(MonitoringRule(
    id="custom_rule",
    name="Custom Security Rule",
    description="Detect custom security patterns",
    event_pattern={"event_type": "custom_event"},
    condition="event.get('severity', 0) > 8",
    severity=AlertSeverity.HIGH
))

```bash

## Performance Considerations

- **Key Caching**: Encryption keys cached in memory for performance

- **Async Operations**: All operations are async for scalability

- **Connection Pooling**: Database connections pooled for efficiency

- **Background Cleanup**: Automatic cleanup of expired sessions and data

## Troubleshooting

### Common Issues

**Authentication fails**

- Check JWT secret configuration

- Verify user credentials

- Check account lockout status

**Permission denied**

- Verify user roles and permissions

- Check role hierarchy

- Review resource-level permissions

**Encryption errors**

- Verify encryption key configuration

- Check key rotation status

- Validate data format

### Debug Mode

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

```

## Contributing

1. Follow PEP 8 style guidelines

1. Add comprehensive tests for new features

1. Update documentation for API changes

1. Ensure compliance with security policies

## License

This security framework is part of JustNews and follows the same licensing terms.

---

**Version**: 1.0.0 **Last Updated**: October 22, 2025 **Contact**: security@justnews.com
