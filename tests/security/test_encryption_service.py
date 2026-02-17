import asyncio
import importlib.util
import os

import pytest

# Import security.models without executing package-level initialization which can
# import other components that are not under test. Load the module directly from file.
root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
models_path = os.path.join(root, "security", "models.py")
spec = importlib.util.spec_from_file_location("security.models", models_path)
models_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(models_mod)

encryption_path = os.path.join(root, "security", "encryption", "service.py")
spec2 = importlib.util.spec_from_file_location(
    "security.encryption.service", encryption_path
)
enc_mod = importlib.util.module_from_spec(spec2)

# Avoid executing the package-level security/__init__.py by inserting a lightweight
# security package module into sys.modules which exposes the already-loaded models
# module. This allows the relative imports inside the encryption service module to
# resolve (e.g. `from ..models import ...`) without triggering side-effects.
import sys as _sys  # noqa: E402
import types as _types  # noqa: E402

security_pkg = _types.ModuleType("security")
security_pkg.models = models_mod
_sys.modules["security"] = security_pkg
_sys.modules["security.models"] = models_mod

spec2.loader.exec_module(enc_mod)

SecurityConfig = models_mod.SecurityConfig
EncryptionError = models_mod.EncryptionError
EncryptionService = enc_mod.EncryptionService


def build_config():
    # Provide a long jwt_secret (required by SecurityConfig) but allow encryption_key None
    return SecurityConfig(jwt_secret="x" * 32)


def test_generate_symmetric_key_and_encrypt_decrypt():
    cfg = build_config()
    svc = EncryptionService(cfg)

    # Avoid writing to disk during tests
    async def _noop(*a, **k):
        return None

    svc._save_keys = _noop

    # Generate a symmetric key and perform round-trip encrypt/decrypt
    key_id = asyncio.run(
        svc.generate_key(algorithm="AES-256", key_type="symmetric", usage="encrypt")
    )
    assert key_id in svc._keys

    # Use the service to encrypt and decrypt
    ciphertext = asyncio.run(svc.encrypt_data("hello world", key_id=key_id))
    assert isinstance(ciphertext, str)

    plaintext = asyncio.run(svc.decrypt_data(ciphertext, key_id=key_id))
    assert plaintext == "hello world"


def test_generate_asymmetric_key_sign_and_verify():
    cfg = build_config()
    svc = EncryptionService(cfg)

    # Avoid disk writes
    async def _noop(*a, **k):
        return None

    svc._save_keys = _noop

    # Generate asymmetric key pair
    kp = asyncio.run(svc.generate_key_pair())
    assert kp.key_id in svc._keys

    # Sign and verify
    message = b"some important message"
    sig = asyncio.run(svc.sign_data(message, kp.key_id))
    assert isinstance(sig, str)

    is_valid = asyncio.run(svc.verify_signature(message, sig, kp.key_id))
    assert is_valid is True


def test_decrypt_with_unknown_key_raises():
    cfg = build_config()
    svc = EncryptionService(cfg)

    # avoid disk writes
    async def _noop(*a, **k):
        return None

    svc._save_keys = _noop

    # create a symmetric key and encrypt
    key_id = asyncio.run(svc.generate_key(key_type="symmetric"))
    ciphertext = asyncio.run(svc.encrypt_data("data", key_id=key_id))

    # Try to decrypt with a wrong key id
    with pytest.raises(EncryptionError):
        asyncio.run(svc.decrypt_data(ciphertext, key_id="nonexistent"))


def test_get_active_keys_and_status():
    cfg = build_config()
    svc = EncryptionService(cfg)

    # Initially should have no keys
    active = asyncio.run(svc.get_active_keys())
    assert isinstance(active, list)

    # Avoid disk writes then add a key and check status
    async def _noop(*a, **k):
        return None

    svc._save_keys = _noop
    _ = asyncio.run(svc.generate_key())
    status = asyncio.run(svc.get_status())
    assert status["total_keys"] >= 1
    assert "status" in status
