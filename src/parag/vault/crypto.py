"""Encrypted vault: AES-256-GCM per file, key derived from a passphrase with scrypt.

The passphrase is never stored. A random salt lives next to the vault; without the passphrase the
encrypted files are unreadable.
"""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

_MAGIC = b"PARAG1"
_NONCE_LEN = 12


class VaultLockedError(RuntimeError):
    """Raised when the vault is used without a passphrase."""


class WrongPassphraseError(RuntimeError):
    """Raised when decryption fails (wrong passphrase or tampered file)."""


class Vault:
    def __init__(self, vault_dir: Path, passphrase: str | None):
        self.dir = Path(vault_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._key = self._derive_key(passphrase) if passphrase else None

    @property
    def unlocked(self) -> bool:
        return self._key is not None

    def _salt(self) -> bytes:
        salt_file = self.dir / "salt"
        if not salt_file.exists():
            salt_file.write_bytes(os.urandom(16))
        return salt_file.read_bytes()

    def _derive_key(self, passphrase: str) -> bytes:
        kdf = Scrypt(salt=self._salt(), length=32, n=2**15, r=8, p=1)
        return kdf.derive(passphrase.encode("utf-8"))

    def _require_key(self) -> bytes:
        if self._key is None:
            raise VaultLockedError("Vault is locked. Set PARAG_PASSPHRASE to store or open sensitive files.")
        return self._key

    def encrypt_bytes(self, data: bytes) -> bytes:
        nonce = os.urandom(_NONCE_LEN)
        return _MAGIC + nonce + AESGCM(self._require_key()).encrypt(nonce, data, _MAGIC)

    def decrypt_bytes(self, blob: bytes) -> bytes:
        if not blob.startswith(_MAGIC):
            raise WrongPassphraseError("Not a vault file.")
        nonce = blob[len(_MAGIC):len(_MAGIC) + _NONCE_LEN]
        try:
            return AESGCM(self._require_key()).decrypt(nonce, blob[len(_MAGIC) + _NONCE_LEN:], _MAGIC)
        except InvalidTag as exc:
            raise WrongPassphraseError("Wrong passphrase or the file was modified.") from exc

    def put(self, name: str, data: bytes) -> str:
        """Encrypt and store; returns the vault file name."""
        vault_name = f"{name}.enc"
        (self.dir / vault_name).write_bytes(self.encrypt_bytes(data))
        return vault_name

    def get(self, vault_name: str) -> bytes:
        return self.decrypt_bytes((self.dir / vault_name).read_bytes())
