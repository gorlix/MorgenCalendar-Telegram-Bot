"""
Tests for the AES-256 encryption/decryption utility and its integration
with the database layer.
"""

import os
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet

from utils.encryption import EncryptionError, decrypt_key, encrypt_key


class TestEncryptionUtility(unittest.TestCase):
    """Unit tests for utils/encryption.py"""

    def setUp(self):
        self.test_master_key = Fernet.generate_key().decode()
        self.patcher = patch.dict(
            os.environ, {"ENCRYPTION_MASTER_KEY": self.test_master_key}
        )
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_encrypt_produces_different_ciphertext(self):
        """Encrypting a key must produce a ciphertext different from plaintext."""
        original = "sk_test_morgen_api_key_123"
        encrypted = encrypt_key(original)
        self.assertNotEqual(original, encrypted)

    def test_decrypt_restores_original_plaintext(self):
        """Decrypting with the correct master key must restore the original."""
        original = "sk_test_morgen_api_key_123"
        encrypted = encrypt_key(original)
        decrypted = decrypt_key(encrypted)
        self.assertEqual(original, decrypted)

    def test_decrypt_with_wrong_key_raises_error(self):
        """Decrypting with a different master key must raise EncryptionError."""
        original = "sk_test_morgen_api_key_123"
        encrypted = encrypt_key(original)

        wrong_key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"ENCRYPTION_MASTER_KEY": wrong_key}):
            with self.assertRaises(EncryptionError):
                decrypt_key(encrypted)

    def test_decrypt_invalid_ciphertext_raises_error(self):
        """Decrypting garbage data must raise EncryptionError."""
        with self.assertRaises(EncryptionError):
            decrypt_key("this-is-not-a-fernet-token")

    def test_encrypt_without_master_key_raises_error(self):
        """Encrypting without ENCRYPTION_MASTER_KEY set must raise EncryptionError."""
        self.patcher.stop()  # Remove the env var
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(EncryptionError):
                encrypt_key("some_key")
        self.patcher.start()  # Restore for tearDown


class TestDatabaseEncryptionIntegration(unittest.IsolatedAsyncioTestCase):
    """Integration tests for encryption within database.py"""

    async def asyncSetUp(self):
        from database import init_db

        self.test_db = "test_audit_morgen_bot.db"
        self.path_patcher = patch("database.DB_PATH", self.test_db)
        self.path_patcher.start()

        self.test_master_key = Fernet.generate_key().decode()
        self.env_patcher = patch.dict(
            os.environ, {"ENCRYPTION_MASTER_KEY": self.test_master_key}
        )
        self.env_patcher.start()

        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        await init_db()

    async def asyncTearDown(self):
        self.path_patcher.stop()
        self.env_patcher.stop()
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    async def test_upsert_stores_encrypted_get_returns_decrypted(self):
        """API key must be encrypted in DB and transparently decrypted by get_user."""
        from database import get_user, upsert_user

        user_id = 99999
        api_key = "morgen_secret_api_key"

        await upsert_user(user_id, morgen_api_key=api_key)
        user = await get_user(user_id)

        self.assertIsNotNone(user)
        self.assertEqual(user["morgen_api_key"], api_key)

    async def test_raw_db_value_is_not_plaintext(self):
        """The value stored in SQLite must NOT be the plain-text API key."""
        import aiosqlite

        from database import upsert_user

        user_id = 88888
        api_key = "morgen_secret_api_key"

        await upsert_user(user_id, morgen_api_key=api_key)

        async with (
            aiosqlite.connect(self.test_db) as db,
            db.execute(
                "SELECT morgen_api_key FROM users WHERE telegram_user_id = ?",
                (user_id,),
            ) as cursor,
        ):
            row = await cursor.fetchone()
            raw_value = row[0]

        self.assertNotEqual(raw_value, api_key)
        self.assertIsNotNone(raw_value)

    async def test_graceful_failover_returns_none_for_bad_key(self):
        """If decryption fails (e.g. old plain-text key), get_user returns None for the key."""
        import aiosqlite

        from database import get_user

        user_id = 77777
        # Manually insert a plain-text key to simulate pre-encryption data
        async with aiosqlite.connect(self.test_db) as db:
            await db.execute(
                "INSERT INTO users (telegram_user_id, morgen_api_key) VALUES (?, ?)",
                (user_id, "plain_text_old_key"),
            )
            await db.commit()

        user = await get_user(user_id)
        self.assertIsNotNone(user)
        self.assertIsNone(user["morgen_api_key"])


if __name__ == "__main__":
    unittest.main()
