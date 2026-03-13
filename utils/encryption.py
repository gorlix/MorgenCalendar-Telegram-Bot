import os
import logging
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


class EncryptionError(Exception):
    """Custom exception for encryption/decryption errors."""

    pass


def get_master_key() -> str:
    """Retrieve the master key from environment variables."""
    master_key = os.environ.get("ENCRYPTION_MASTER_KEY")
    if not master_key:
        logger.error("ENCRYPTION_MASTER_KEY not found in environment.")
        raise EncryptionError("Master key missing.")
    return master_key


def encrypt_key(plain_text: str) -> str:
    """
    Encrypts a plain-text string using AES-256 (Fernet).
    Returns the URL-safe base64-encoded ciphertext.
    """
    try:
        master_key = get_master_key()
        f = Fernet(master_key.encode())
        return f.encrypt(plain_text.encode()).decode()
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        raise EncryptionError(f"Encryption failed: {e}")


def decrypt_key(cipher_text: str) -> str:
    """
    Decrypts a Fernet ciphertext back to plain-text.
    Raises EncryptionError if decryption fails (e.g. wrong key, invalid format).
    """
    try:
        master_key = get_master_key()
        f = Fernet(master_key.encode())
        return f.decrypt(cipher_text.encode()).decode()
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        raise EncryptionError(f"Decryption failed: {e}")
