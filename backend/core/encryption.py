"""Fernet symmetric encryption utilities for credentials at rest.

Uses DJANGO_ENCRYPTION_KEY env var (Fernet-compatible base64url 32-byte key).
"""

import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger("security")


def _get_fernet() -> Fernet:
    key = getattr(settings, "ENCRYPTION_KEY", None)
    if not key:
        raise ValueError(
            "ENCRYPTION_KEY is not configured. "
            "Set DJANGO_ENCRYPTION_KEY env var (generate with: python -c "
            '"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")',
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string, returning a Fernet token as a string."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a Fernet token string, returning the original plaintext."""
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        logger.error("Failed to decrypt value — invalid token or wrong key")
        raise
