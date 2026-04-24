"""Passphrase-based encryption for sync bundles."""

from __future__ import annotations

import base64
import json
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class SyncDecryptError(ValueError):
    """Raised when an encrypted sync payload cannot be decrypted."""


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def encrypt_json(data: dict[str, Any], passphrase: str) -> bytes:
    salt = os.urandom(16)
    token = Fernet(_derive_key(passphrase, salt)).encrypt(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    envelope = {
        "version": 1,
        "kdf": "pbkdf2-sha256",
        "iterations": 390_000,
        "salt": base64.b64encode(salt).decode("ascii"),
        "token": token.decode("ascii"),
    }
    return json.dumps(envelope, sort_keys=True).encode("utf-8")


def decrypt_json(payload: bytes, passphrase: str) -> dict[str, Any]:
    try:
        envelope = json.loads(payload.decode("utf-8"))
        if envelope.get("version") != 1:
            raise SyncDecryptError("Unsupported encrypted sync payload version.")
        salt = base64.b64decode(envelope["salt"])
        token = envelope["token"].encode("ascii")
        clear = Fernet(_derive_key(passphrase, salt)).decrypt(token)
        return json.loads(clear.decode("utf-8"))
    except (InvalidToken, KeyError, ValueError, TypeError) as exc:
        raise SyncDecryptError("Could not decrypt sync payload.") from exc

