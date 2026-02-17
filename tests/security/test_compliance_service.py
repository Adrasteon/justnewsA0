import asyncio
import importlib
import importlib.util
import sys
import types
from pathlib import Path

# Create a minimal 'security.models' module in sys.modules to satisfy the relative import
models_mod = types.ModuleType("security.models")


class _ComplianceError(Exception):
    pass


class _SecurityConfig:
    def __init__(self):
        self.jwt_secret = "X" * 32


models_mod.ComplianceError = _ComplianceError
models_mod.SecurityConfig = _SecurityConfig

sys.modules["security"] = types.ModuleType("security")
sys.modules["security.models"] = models_mod

# Import module directly from file to avoid package __init__ side-effects
spec = importlib.util.spec_from_file_location(
    "security.compliance.service",
    str(Path(__file__).resolve().parents[2] / "security" / "compliance" / "service.py"),
)
svc_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(svc_mod)  # type: ignore

ComplianceService = svc_mod.ComplianceService
ConsentStatus = svc_mod.ConsentStatus


def make_config():
    # Use a lightweight config object to avoid importing package-level side-effects
    class _C:
        def __init__(self):
            self.jwt_secret = "X" * 32

    return _C()


def test_record_and_check_consent_and_export():
    cfg = make_config()
    svc = ComplianceService(cfg)

    # Patch save to avoid file I/O
    async def _noop():
        return None

    svc._save_compliance_data = _noop

    # Record consent
    consent_id = asyncio.run(
        svc.record_consent(1, "analytics", "text", status=ConsentStatus.GRANTED)
    )
    assert consent_id.startswith("consent_")

    # Check consent reflects granted state
    status = asyncio.run(svc.check_consent(1, "analytics"))
    assert status == ConsentStatus.GRANTED

    # Export data for user (should include consent and audit event)
    exported = asyncio.run(svc.export_user_data(1))
    assert exported["user_id"] == 1
    assert isinstance(exported["consent_records"], list)


def test_submit_and_process_data_request_and_delete_user():
    cfg = make_config()
    svc = ComplianceService(cfg)

    # Patch save to avoid file I/O
    async def _noop():
        return None

    svc._save_compliance_data = _noop

    # Submit a data request
    req_id = asyncio.run(svc.submit_data_request(2, "access", details={"info": "x"}))
    assert req_id.startswith("dsr_")

    # Process request - complete
    asyncio.run(svc.process_data_request(req_id, "complete", result={"ok": True}))

    # Verify status changed
    request = [r for r in svc._data_requests if r.id == req_id][0]
    assert request.status == "completed"

    # Record consent and then delete user data
    asyncio.run(svc.record_consent(2, "analytics", "t", status=ConsentStatus.GRANTED))
    assert 2 in svc._consent_records

    asyncio.run(svc.delete_user_data(2))
    assert 2 not in svc._consent_records
    # Data requests for user should be removed
    assert all(r.user_id != 2 for r in svc._data_requests)
