"""
BYOK (Bring Your Own Key) API Key Vault

Provides encrypted storage and secure pass-through for user-supplied LLM API keys.
Issue: #1227 - Security: BYOK API key vault

Features:
- Fernet symmetric encryption for API keys at rest
- Key validation via provider APIs before storage
- Secure pass-through to LLM clients
- PII scrubbing in logs
"""

import base64
import logging
from enum import Enum
from typing import Optional

import httpx

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import BYTEA
from sqlalchemy.orm import Mapped, mapped_column

from core.secrets import get_secret

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """Supported LLM providers for BYOK"""

    OPENROUTER = "openrouter"
    OPENAI = "openai"


class BYOKEncryptionError(Exception):
    """Raised when encryption/decryption fails"""

    pass


class BYOKValidationError(Exception):
    """Raised when API key validation fails"""

    pass


def get_encryption_key() -> bytes:
    """
    Get the encryption key from secrets manager.
    Falls back to a derived key from SECRET_KEY if BYOK_MASTER_KEY not set.

    Returns:
        32-byte encryption key for Fernet
    """
    master_key = get_secret("BYOK_MASTER_KEY")

    if master_key:
        key_bytes = master_key.encode() if isinstance(master_key, str) else master_key
        if len(key_bytes) < 32:
            key_bytes = key_bytes.ljust(32, b"\0")
        return base64.urlsafe_b64encode(key_bytes[:32])

    secret_key = get_secret("SECRET_KEY")
    if not secret_key:
        raise ValueError("BYOK_MASTER_KEY or SECRET_KEY must be set for BYOK encryption")

    key_bytes = secret_key.encode() if isinstance(secret_key, str) else secret_key
    if len(key_bytes) < 32:
        key_bytes = key_bytes.ljust(32, b"\0")
    return base64.urlsafe_b64encode(key_bytes[:32])


class BYOKKeyVault:
    """
    Handles encryption/decryption of user-supplied LLM API keys.

    Uses Fernet symmetric encryption with a master key stored in Fly.io secrets.
    """

    def __init__(self):
        self._fernet: Optional[Fernet] = None

    def _get_fernet(self) -> Fernet:
        """Get or create Fernet instance"""
        if self._fernet is None:
            key = get_encryption_key()
            self._fernet = Fernet(key)
        return self._fernet

    def encrypt(self, api_key: str) -> bytes:
        """
        Encrypt an API key for storage.

        Args:
            api_key: Plain text API key

        Returns:
            Encrypted bytes suitable for database storage
        """
        if not api_key:
            raise BYOKEncryptionError("Cannot encrypt empty API key")

        try:
            fernet = self._get_fernet()
            encrypted = fernet.encrypt(api_key.encode("utf-8"))
            return encrypted
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise BYOKEncryptionError(f"Failed to encrypt API key: {e}")

    def decrypt(self, encrypted_key: bytes) -> str:
        """
        Decrypt an API key from storage.

        Args:
            encrypted_key: Encrypted bytes from database

        Returns:
            Plain text API key
        """
        if not encrypted_key:
            raise BYOKEncryptionError("Cannot decrypt empty value")

        try:
            fernet = self._get_fernet()
            decrypted = fernet.decrypt(encrypted_key)
            return decrypted.decode("utf-8")
        except InvalidToken:
            raise BYOKEncryptionError("Invalid encryption key or corrupted data")
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise BYOKEncryptionError(f"Failed to decrypt API key: {e}")

    def mask_key(self, api_key: str) -> str:
        """
        Return a masked version of the API key (last 4 chars only).

        Args:
            api_key: Plain text API key

        Returns:
            Masked key like "***********abc1"
        """
        if not api_key or len(api_key) <= 4:
            return "****"
        return "*" * (len(api_key) - 4) + api_key[-4:]


byok_vault = BYOKKeyVault()


async def validate_api_key(api_key: str, provider: LLMProvider) -> bool:
    """
    Validate an API key by making a test call to the provider.

    Args:
        api_key: The API key to validate
        provider: The LLM provider enum

    Returns:
        True if valid, False otherwise

    Raises:
        BYOKValidationError: If validation fails with a clear error message
    """
    if provider == LLMProvider.OPENROUTER:
        return await _validate_openrouter_key(api_key)
    elif provider == LLMProvider.OPENAI:
        return await _validate_openai_key(api_key)
    else:
        raise BYOKValidationError(f"Unsupported provider: {provider}")


async def _validate_openrouter_key(api_key: str) -> bool:
    """Validate OpenRouter API key by checking model list"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if response.status_code == 200:
                return True
            elif response.status_code == 401:
                raise BYOKValidationError(
                    "Your OpenRouter API key is invalid. Please check your API key settings."
                )
            elif response.status_code == 429:
                raise BYOKValidationError(
                    "Your OpenRouter API key is rate-limited. Please try again later."
                )
            else:
                logger.warning(f"OpenRouter validation returned {response.status_code}")
                return False
    except httpx.TimeoutException:
        raise BYOKValidationError(
            "OpenRouter validation timed out. Please check your internet connection."
        )
    except Exception as e:
        logger.error(f"OpenRouter validation error: {e}")
        raise BYOKValidationError(f"Failed to validate OpenRouter API key: {e}")


async def _validate_openai_key(api_key: str) -> bool:
    """Validate OpenAI API key by checking model list"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {api_key}"}
            )
            if response.status_code == 200:
                return True
            elif response.status_code == 401:
                raise BYOKValidationError(
                    "Your OpenAI API key is invalid. Please check your API key settings."
                )
            elif response.status_code == 429:
                raise BYOKValidationError(
                    "Your OpenAI API key is rate-limited. Please try again later."
                )
            else:
                logger.warning(f"OpenAI validation returned {response.status_code}")
                return False
    except httpx.TimeoutException:
        raise BYOKValidationError(
            "OpenAI validation timed out. Please check your internet connection."
        )
    except Exception as e:
        logger.error(f"OpenAI validation error: {e}")
        raise BYOKValidationError(f"Failed to validate OpenAI API key: {e}")


class BYOKUserFields:
    """
    Mixin fields for BYOK support on User model.
    Issue: #1227
    """

    llm_api_key_encrypted: Mapped[Optional[bytes]] = mapped_column(BYTEA, nullable=True)
    llm_api_key_provider: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)


def add_byok_fields_to_user():
    """
    Return SQL migration string to add BYOK fields to users table.
    """
    return """
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS llm_api_key_encrypted BYTEA,
    ADD COLUMN IF NOT EXISTS llm_api_key_provider VARCHAR(20);
    """


class PIIScrubbingFilter(logging.Filter):
    """
    Logging filter that scrubs API keys and other PII from log messages.
    Issue: #1227 - Never log API keys
    """

    API_KEY_PATTERNS = [
        r"(sk-[a-zA-Z0-9_-]{20,})",
        r"(mpk_[a-zA-Z0-9_-]{20,})",
        r"(Bearer\s+[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+)",
        r"(openrouter\|[a-zA-Z0-9_-]{20,})",
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if record.msg and isinstance(record.msg, str):
            record.msg = self._scrub_message(record.msg)
        if record.args:
            record.args = tuple(
                self._scrub_message(str(arg)) if isinstance(arg, str) else arg
                for arg in record.args
            )
        return True

    def _scrub_message(self, message: str) -> str:
        import re

        for pattern in self.API_KEY_PATTERNS:
            message = re.sub(pattern, "***REDACTED_API_KEY***", message)
        return message


def setup_byok_logging():
    """
    Configure logging with PII scrubbing for BYOK.
    Should be called during app initialization.
    """
    pii_filter = PIIScrubbingFilter()

    for handler in logging.root.handlers:
        handler.addFilter(pii_filter)

    logger.info("BYOK PII logging filter installed")
