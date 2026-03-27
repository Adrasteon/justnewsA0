"""
JustNews Encryption Service

Provides data encryption, key management, and secure communication capabilities.
"""

import base64
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import aiofiles
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from pydantic import BaseModel

from ..models import EncryptionError, SecurityConfig

logger = logging.getLogger(__name__)


class EncryptionKey(BaseModel):
    """Encryption key information"""

    id: str
    algorithm: str
    created_at: datetime
    expires_at: datetime | None = None
    is_active: bool = True
    key_type: str  # symmetric, asymmetric
    usage: str  # encrypt, sign, both


class EncryptedData(BaseModel):
    """Encrypted data container"""

    data: str  # Base64 encoded encrypted data
    key_id: str
    algorithm: str
    iv: str | None = None  # Initialization vector for AES-GCM
    signature: str | None = None  # For signed data


class KeyPair(BaseModel):
    """Asymmetric key pair"""

    public_key: str  # PEM encoded
    private_key: str  # Encrypted PEM encoded
    key_id: str
    algorithm: str = "RSA-2048"


@dataclass
class EncryptionConfig:
    """Encryption service configuration"""

    default_algorithm: str = "AES-256-GCM"
    key_rotation_days: int = 90
    master_key_provider: str = "local"  # local, aws-kms, azure-keyvault
    enable_key_caching: bool = True
    max_cached_keys: int = 100


class EncryptionService:
    """
    Encryption service for data protection and secure communication

    Provides symmetric and asymmetric encryption, key management,
    digital signatures, and secure key storage.
    """

    def __init__(self, config: SecurityConfig):
        self.config = config
        self.encryption_config = EncryptionConfig()
        self._keys: dict[str, dict[str, Any]] = {}  # key_id -> key data
        self._key_cache: dict[str, Fernet] = {}  # key_id -> Fernet instance
        self._master_key: bytes | None = None

        # Initialize with master key
        self._master_key = self._get_master_key()

    def _get_master_key(self) -> bytes:
        """Get or generate master encryption key"""
        if self.config.encryption_key:
            # Use provided key
            key = self.config.encryption_key.encode()
        else:
            # Generate a key (not recommended for production)
            key = Fernet.generate_key()

        # Ensure it's a valid Fernet key (32 bytes base64 encoded)
        try:
            Fernet(key)
            return key
        except Exception:
            # Generate a new valid key
            return Fernet.generate_key()

    async def initialize(self) -> None:
        """Initialize encryption service"""
        await self._load_keys()
        await self._initialize_key_rotation()
        logger.info("EncryptionService initialized")

    async def shutdown(self) -> None:
        """Shutdown encryption service"""
        await self._save_keys()
        # Clear sensitive data from memory
        self._keys.clear()
        self._key_cache.clear()
        if self._master_key:
            self._master_key = None
        logger.info("EncryptionService shutdown")

    async def encrypt_data(
        self, data: str | bytes, key_id: str | None = None, algorithm: str | None = None
    ) -> str:
        """
        Encrypt data using symmetric encryption

        Args:
            data: Data to encrypt
            key_id: Optional key ID (uses default if not provided)
            algorithm: Optional algorithm override

        Returns:
            Base64 encoded encrypted data

        Raises:
            EncryptionError: If encryption fails
        """
        try:
            # Get encryption key
            if key_id is None:
                key_id = await self._get_or_create_default_key()

            fernet = await self._get_fernet_key(key_id)

            # Convert data to bytes
            if isinstance(data, str):
                data_bytes = data.encode("utf-8")
            else:
                data_bytes = data

            # Encrypt data
            encrypted = fernet.encrypt(data_bytes)

            # Return base64 encoded
            return base64.b64encode(encrypted).decode("utf-8")

        except Exception as e:
            logger.error(f"Data encryption failed: {e}")
            raise EncryptionError(f"Encryption failed: {str(e)}") from e

    async def decrypt_data(
        self, encrypted_data: str, key_id: str | None = None
    ) -> str | bytes:
        """
        Decrypt data using symmetric encryption

        Args:
            encrypted_data: Base64 encoded encrypted data
            key_id: Optional key ID

        Returns:
            Decrypted data

        Raises:
            EncryptionError: If decryption fails
        """
        try:
            # Decode from base64
            encrypted_bytes = base64.b64decode(encrypted_data)

            # Get decryption key
            if key_id is None:
                # Try to find the key by attempting decryption with known keys
                key_id = await self._find_decryption_key(encrypted_bytes)

            if not key_id:
                raise EncryptionError("Unable to determine decryption key")

            fernet = await self._get_fernet_key(key_id)

            # Decrypt data
            decrypted = fernet.decrypt(encrypted_bytes)

            # Try to decode as string, return bytes if it fails
            try:
                return decrypted.decode("utf-8")
            except UnicodeDecodeError:
                return decrypted

        except InvalidToken as exc:
            raise EncryptionError("Invalid encrypted data or key") from exc
        except Exception as e:
            logger.error(f"Data decryption failed: {e}")
            raise EncryptionError(f"Decryption failed: {str(e)}") from e

    async def generate_key(
        self,
        algorithm: str = "AES-256",
        key_type: str = "symmetric",
        usage: str = "encrypt",
    ) -> str:
        """
        Generate new encryption key

        Args:
            algorithm: Key algorithm
            key_type: Key type (symmetric, asymmetric)
            usage: Key usage (encrypt, sign, both)

        Returns:
            Key ID of generated key
        """
        try:
            key_id = f"key_{secrets.token_urlsafe(8)}"
            created_at = datetime.now(UTC)
            expires_at = created_at + timedelta(
                days=self.encryption_config.key_rotation_days
            )

            if key_type == "symmetric":
                # Generate Fernet key
                key_material = Fernet.generate_key()

                # Encrypt the key with master key
                master_fernet = Fernet(self._master_key)
                encrypted_key = master_fernet.encrypt(key_material)

                key_data = {
                    "id": key_id,
                    "algorithm": algorithm,
                    "key_type": key_type,
                    "usage": usage,
                    "created_at": created_at.isoformat(),
                    "expires_at": expires_at.isoformat(),
                    "is_active": True,
                    "key_material": base64.b64encode(encrypted_key).decode("utf-8"),
                }

            elif key_type == "asymmetric":
                # Generate RSA key pair
                private_key = rsa.generate_private_key(
                    public_exponent=65537, key_size=2048
                )

                # Serialize private key
                private_pem = private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )

                # Encrypt private key with master key
                master_fernet = Fernet(self._master_key)
                encrypted_private = master_fernet.encrypt(private_pem)

                # Serialize public key
                public_key = private_key.public_key()
                public_pem = public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                )

                key_data = {
                    "id": key_id,
                    "algorithm": "RSA-2048",
                    "key_type": key_type,
                    "usage": usage,
                    "created_at": created_at.isoformat(),
                    "expires_at": expires_at.isoformat(),
                    "is_active": True,
                    "public_key": base64.b64encode(public_pem).decode("utf-8"),
                    "private_key": base64.b64encode(encrypted_private).decode("utf-8"),
                }

            else:
                raise EncryptionError(f"Unsupported key type: {key_type}")

            self._keys[key_id] = key_data
            await self._save_keys()

            logger.info(f"Generated {key_type} key {key_id} with algorithm {algorithm}")
            return key_id

        except Exception as e:
            logger.error(f"Key generation failed: {e}")
            raise EncryptionError(f"Key generation failed: {str(e)}") from e

    async def rotate_key(self, old_key_id: str) -> str:
        """
        Rotate encryption key

        Args:
            old_key_id: Key ID to rotate

        Returns:
            New key ID

        Raises:
            EncryptionError: If rotation fails
        """
        try:
            if old_key_id not in self._keys:
                raise EncryptionError(f"Key {old_key_id} not found")

            old_key = self._keys[old_key_id]

            # Generate new key with same parameters
            new_key_id = await self.generate_key(
                algorithm=old_key["algorithm"],
                key_type=old_key["key_type"],
                usage=old_key["usage"],
            )

            # Mark old key as inactive
            old_key["is_active"] = False
            old_key["rotated_at"] = datetime.now(UTC).isoformat()
            old_key["rotated_to"] = new_key_id

            await self._save_keys()

            # Clear old key from cache
            if old_key_id in self._key_cache:
                del self._key_cache[old_key_id]

            logger.info(f"Rotated key {old_key_id} to {new_key_id}")
            return new_key_id

        except Exception as e:
            logger.error(f"Key rotation failed: {e}")
            raise EncryptionError(f"Key rotation failed: {str(e)}") from e

    async def generate_key_pair(self, algorithm: str = "RSA-2048") -> KeyPair:
        """
        Generate asymmetric key pair

        Args:
            algorithm: Key algorithm

        Returns:
            KeyPair object
        """
        try:
            key_id = await self.generate_key(algorithm=algorithm, key_type="asymmetric")
            key_data = self._keys[key_id]

            return KeyPair(
                public_key=key_data["public_key"],
                private_key=key_data["private_key"],
                key_id=key_id,
                algorithm=algorithm,
            )

        except Exception as e:
            logger.error(f"Key pair generation failed: {e}")
            raise EncryptionError(f"Key pair generation failed: {str(e)}") from e

    async def sign_data(self, data: str | bytes, key_id: str) -> str:
        """
        Sign data with private key

        Args:
            data: Data to sign
            key_id: Private key ID

        Returns:
            Base64 encoded signature

        Raises:
            EncryptionError: If signing fails
        """
        try:
            if key_id not in self._keys:
                raise EncryptionError(f"Key {key_id} not found")

            key_data = self._keys[key_id]
            if key_data["key_type"] != "asymmetric":
                raise EncryptionError("Key is not asymmetric")

            # Decrypt private key
            master_fernet = Fernet(self._master_key)
            encrypted_private = base64.b64decode(key_data["private_key"])
            private_pem = master_fernet.decrypt(encrypted_private)

            # Load private key
            private_key = serialization.load_pem_private_key(private_pem, password=None)

            # Convert data to bytes
            if isinstance(data, str):
                data_bytes = data.encode("utf-8")
            else:
                data_bytes = data

            # Sign data
            signature = private_key.sign(
                data_bytes,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )

            return base64.b64encode(signature).decode("utf-8")

        except Exception as e:
            logger.error(f"Data signing failed: {e}")
            raise EncryptionError(f"Signing failed: {str(e)}") from e

    async def verify_signature(
        self, data: str | bytes, signature: str, key_id: str
    ) -> bool:
        """
        Verify data signature

        Args:
            data: Original data
            signature: Base64 encoded signature
            key_id: Public key ID

        Returns:
            True if signature is valid

        Raises:
            EncryptionError: If verification fails
        """
        try:
            if key_id not in self._keys:
                raise EncryptionError(f"Key {key_id} not found")

            key_data = self._keys[key_id]

            # Load public key
            public_pem = base64.b64decode(key_data["public_key"])
            public_key = serialization.load_pem_public_key(public_pem)

            # Convert data to bytes
            if isinstance(data, str):
                data_bytes = data.encode("utf-8")
            else:
                data_bytes = data

            # Decode signature
            signature_bytes = base64.b64decode(signature)

            # Verify signature
            public_key.verify(
                signature_bytes,
                data_bytes,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )

            return True

        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return False

    async def get_active_keys(self) -> list[dict[str, Any]]:
        """
        Get list of active encryption keys

        Returns:
            List of active key information
        """
        active_keys = []
        now = datetime.now(UTC)

        for key_data in self._keys.values():
            if key_data.get("is_active", True):
                expires_at = key_data.get("expires_at")
                if expires_at:
                    expires_at = datetime.fromisoformat(expires_at)
                    if expires_at < now:
                        continue  # Key expired

                active_keys.append(
                    {
                        "id": key_data["id"],
                        "algorithm": key_data["algorithm"],
                        "key_type": key_data["key_type"],
                        "usage": key_data["usage"],
                        "created_at": key_data["created_at"],
                        "expires_at": key_data.get("expires_at"),
                    }
                )

        return active_keys

    async def get_status(self) -> dict[str, Any]:
        """
        Get encryption service status

        Returns:
            Status information
        """
        active_keys = await self.get_active_keys()
        expired_keys = sum(
            1
            for k in self._keys.values()
            if not k.get("is_active", True)
            or (
                k.get("expires_at")
                and datetime.fromisoformat(k["expires_at"]) < datetime.now(UTC)
            )
        )

        return {
            "status": "healthy",
            "total_keys": len(self._keys),
            "active_keys": len(active_keys),
            "expired_keys": expired_keys,
            "cached_keys": len(self._key_cache),
            "default_algorithm": self.encryption_config.default_algorithm,
        }

    async def _get_or_create_default_key(self) -> str:
        """Get or create default encryption key"""
        # Look for active symmetric key
        for key_data in self._keys.values():
            if (
                key_data.get("is_active", True)
                and key_data["key_type"] == "symmetric"
                and key_data["usage"] in ["encrypt", "both"]
            ):
                expires_at = key_data.get("expires_at")
                if expires_at and datetime.fromisoformat(expires_at) > datetime.now(
                    UTC
                ):
                    return key_data["id"]

        # Create new default key
        return await self.generate_key()

    async def _get_fernet_key(self, key_id: str) -> Fernet:
        """Get Fernet instance for key ID"""
        # Check cache first
        if key_id in self._key_cache:
            return self._key_cache[key_id]

        if key_id not in self._keys:
            raise EncryptionError(f"Key {key_id} not found")

        key_data = self._keys[key_id]
        if key_data["key_type"] != "symmetric":
            raise EncryptionError(f"Key {key_id} is not symmetric")

        # Decrypt key material
        master_fernet = Fernet(self._master_key)
        encrypted_key = base64.b64decode(key_data["key_material"])
        key_material = master_fernet.decrypt(encrypted_key)

        # Create Fernet instance
        fernet = Fernet(key_material)

        # Cache if enabled
        if self.encryption_config.enable_key_caching:
            if len(self._key_cache) >= self.encryption_config.max_cached_keys:
                # Remove oldest cached key
                oldest_key = min(
                    self._key_cache.keys(), key=lambda k: self._keys[k]["created_at"]
                )
                del self._key_cache[oldest_key]

            self._key_cache[key_id] = fernet

        return fernet

    async def _find_decryption_key(self, encrypted_data: bytes) -> str | None:
        """Try to find the correct decryption key by attempting decryption"""
        for key_id in self._keys:
            try:
                fernet = await self._get_fernet_key(key_id)
                fernet.decrypt(encrypted_data)
                return key_id
            except (InvalidToken, EncryptionError):
                continue
        return None

    async def _initialize_key_rotation(self) -> None:
        """Initialize automatic key rotation"""
        # Check for expired keys and rotate them
        now = datetime.now(UTC)

        for key_id, key_data in list(self._keys.items()):
            if not key_data.get("is_active", True):
                continue

            expires_at = key_data.get("expires_at")
            if expires_at:
                expires_at = datetime.fromisoformat(expires_at)
                if expires_at < now:
                    logger.info(f"Key {key_id} has expired, rotating...")
                    try:
                        await self.rotate_key(key_id)
                    except Exception as e:
                        logger.error(f"Failed to rotate expired key {key_id}: {e}")

    async def _load_keys(self) -> None:
        """Load encryption keys from storage"""
        try:
            async with aiofiles.open("data/encryption_keys.json") as f:
                data = json.loads(await f.read())
                self._keys = data.get("keys", {})
                logger.info(f"Loaded {len(self._keys)} encryption keys")
        except FileNotFoundError:
            logger.info("No encryption keys file found, starting fresh")
        except Exception as e:
            logger.error(f"Failed to load encryption keys: {e}")

    async def _save_keys(self) -> None:
        """Save encryption keys to storage"""
        try:
            data = {"keys": self._keys}
            async with aiofiles.open("data/encryption_keys.json", "w") as f:
                await f.write(json.dumps(data, indent=2))
        except Exception as e:
            logger.error(f"Failed to save encryption keys: {e}")
