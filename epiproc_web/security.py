from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app, has_app_context


ENCRYPTED_PREFIX = "enc$"


def _resolve_secret_material() -> str:
    if has_app_context():
        explicit = (current_app.config.get("EPIPROC_CREDENTIALS_KEY") or "").strip()
        if explicit:
            return explicit
        return str(current_app.config.get("SECRET_KEY", "epiproc-local-dev-secret"))
    return "epiproc-local-dev-secret"


def _build_cipher(secret_material: str) -> Fernet:
    digest = hashlib.sha256(secret_material.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(digest)
    return Fernet(fernet_key)


def is_visible_password_encrypted(value: str | None) -> bool:
    return bool(value) and str(value).startswith(ENCRYPTED_PREFIX)


def encrypt_visible_password(plain_value: str | None) -> str | None:
    if plain_value is None:
        return None

    raw = str(plain_value)
    if not raw:
        return None

    cipher = _build_cipher(_resolve_secret_material())
    token = cipher.encrypt(raw.encode("utf-8")).decode("utf-8")
    return f"{ENCRYPTED_PREFIX}{token}"


def decrypt_visible_password(stored_value: str | None) -> str:
    if not stored_value:
        return ""

    raw = str(stored_value)
    if not raw.startswith(ENCRYPTED_PREFIX):
        return raw

    token = raw[len(ENCRYPTED_PREFIX) :]
    if not token:
        return ""

    cipher = _build_cipher(_resolve_secret_material())

    try:
        return cipher.decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return ""