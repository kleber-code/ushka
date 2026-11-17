"""Fernet encryption: `encrypt`, `decrypt`, `generate_key` and key rotation.

A token is authenticated (AES-128-CBC plus HMAC-SHA256, the Fernet recipe of
the `cryptography` package) and carries the time it was made, so a changed
token, a wrong key and an expired token all fail the same way: with
`DecryptionError`, whose message says nothing about the content or the reason.

Keys come from ``[crypto] keys`` (``USHKA_CRYPTO_KEYS``, comma separated). The
first key encrypts, every key decrypts: to rotate, put the new key first and
keep the old one until nothing encrypted with it is left. Without ``keys``, a
key is derived from ``[app] secret_key`` (HKDF-SHA256), so encryption works
with no extra setup; `derive_key` shows how.

Decrypted values are plain `str`, never `Untrusted`: a token that decrypts was
written by this application (nobody else holds the key). If what you encrypted
was request data and it reaches a sink again, wrap it: ``Untrusted(text, "db")``.
"""

from __future__ import annotations

import base64
import functools
from collections.abc import Sequence
from typing import Any

__all__ = [
    "DecryptionError",
    "decrypt",
    "decrypt_bytes",
    "derive_key",
    "encrypt",
    "encrypt_bytes",
    "generate_key",
    "is_available",
    "keys_from_config",
    "uses_derived_key",
    "validate_config",
]

#: Fixed on purpose: changing it would make every derived key, and everything
#: encrypted with one, unreadable.
HKDF_INFO = b"ushka-fernet-v1"

INSTALL_HINT = 'Encryption needs the optional "cryptography" package: pip install "ushka[crypto]"'


class DecryptionError(Exception):
    """The token could not be decrypted: changed, truncated, expired, or made
    with another key. The message is the same for all of them on purpose."""

    def __init__(self, message: str = "The value could not be decrypted.") -> None:
        super().__init__(message)


def _load():
    """The pieces of `cryptography` Ushka uses, imported on first use."""
    try:
        from cryptography.fernet import Fernet, InvalidToken, MultiFernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    except ImportError:
        raise ImportError(INSTALL_HINT) from None
    return Fernet, InvalidToken, MultiFernet, hashes, HKDF


def is_available() -> bool:
    """True when the ``crypto`` extra is installed."""
    try:
        _load()
    except ImportError:
        return False
    return True


def generate_key() -> str:
    """A new random key (urlsafe base64 of 32 bytes), ready for ``USHKA_CRYPTO_KEYS``."""
    Fernet = _load()[0]
    return Fernet.generate_key().decode("ascii")


def derive_key(secret_key: str) -> str:
    """The key Ushka derives from ``[app] secret_key`` when no ``keys`` are set:
    HKDF-SHA256 with the fixed info ``b"ushka-fernet-v1"``, no salt, 32 bytes.

    It is stable (same secret, same key) and different from the secret itself.
    Use it to move to a dedicated key: ``keys = [new, derive_key(secret_key)]``.
    """
    _, _, _, hashes, HKDF = _load()
    material = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=HKDF_INFO).derive(str(secret_key).encode("utf-8"))
    return base64.urlsafe_b64encode(material).decode("ascii")


# -- keys ----------------------------------------------------------------------------


def _as_list(key: Any) -> list:
    if isinstance(key, (str, bytes)):
        return [key]
    if isinstance(key, Sequence):
        return list(key)
    raise TypeError("key must be a key or a list of keys (the first encrypts, all decrypt)")


@functools.lru_cache(maxsize=32)
def _multi(keys: tuple):
    Fernet, _, MultiFernet, _, _ = _load()
    if not keys:
        raise ValueError("No encryption key given.")
    try:
        return MultiFernet([Fernet(k) for k in keys])
    except (ValueError, TypeError):
        # Never echo the key: it is a secret.
        raise ValueError('Not a valid encryption key: make one with "ushka crypto genkey".') from None


def keys_from_config(config: Any) -> list[str]:
    """The keys of an app: ``[crypto] keys``, or the one derived from ``[app] secret_key``.

    With ``[crypto] keep_derived`` the derived key is also kept, last, so data written before
    the move to a dedicated key can still be read.
    """
    configured = [str(k).strip() for k in (config.get("crypto_keys") or []) if str(k).strip()]
    secret = config.get("app_secret_key")
    if configured:
        if config.get("crypto_keep_derived") and secret:
            derived = derive_key(secret)  # last: it only decrypts what was written before the dedicated key
            if derived not in configured:
                configured.append(derived)
        return configured
    if not secret:
        raise RuntimeError(
            "No encryption key. Set USHKA_CRYPTO_KEYS (make one with: ushka crypto genkey) "
            "or USHKA_APP_SECRET_KEY, or pass key=."
        )
    return [derive_key(secret)]


def uses_derived_key(config: Any) -> bool:
    """True when encryption would use the key derived from ``secret_key`` (no ``[crypto] keys``)."""
    return not any(str(k).strip() for k in (config.get("crypto_keys") or []))


def validate_config(config: Any) -> None:
    """Fails now, with a clear message, if encryption cannot work: the extra is
    missing, there is no key, or a key is malformed. The app calls it at startup
    when a feature that encrypts is on."""
    _multi(tuple(keys_from_config(config)))


def _fernet(key: Any):
    if key is None:
        from ushka.core.config import Config

        keys = keys_from_config(Config())
    else:
        keys = _as_list(key)
    return _multi(tuple(k.decode("ascii") if isinstance(k, bytes) else str(k) for k in keys))


# -- the API -------------------------------------------------------------------------


def encrypt_bytes(data: bytes, *, key: Any = None) -> str:
    """Encrypts `data` and returns the Fernet token (urlsafe text).

    `key` is a key or a list of keys (the first encrypts); omitted, the keys of
    the app are used.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("encrypt_bytes() takes bytes; use encrypt() for text")
    return _fernet(key).encrypt(bytes(data)).decode("ascii")


def decrypt_bytes(token: str | bytes, *, key: Any = None, ttl: int | None = None) -> bytes:
    """Decrypts a token from `encrypt_bytes`. With `ttl`, a token older than that
    many seconds is refused. Raises `DecryptionError` for any bad token."""
    if not isinstance(token, (str, bytes)):
        raise TypeError("token must be str or bytes")
    fernet = _fernet(key)
    InvalidToken = _load()[1]
    try:
        raw = token.encode("ascii") if isinstance(token, str) else token
        return fernet.decrypt(raw, ttl=ttl)
    except (InvalidToken, ValueError, TypeError):  # UnicodeEncodeError is a ValueError
        raise DecryptionError() from None


def encrypt(data: str, *, key: Any = None) -> str:
    """Encrypts text and returns the Fernet token (urlsafe text).

    >>> token = encrypt("secret")        # keys from [crypto] / [app] secret_key
    >>> decrypt(token)
    'secret'
    """
    if not isinstance(data, str):
        raise TypeError("encrypt() takes str; use encrypt_bytes() for bytes")
    return encrypt_bytes(data.encode("utf-8"), key=key)


def decrypt(token: str | bytes, *, key: Any = None, ttl: int | None = None) -> str:
    """Decrypts a token from `encrypt` and returns a plain `str`. Raises `DecryptionError`."""
    raw = decrypt_bytes(token, key=key, ttl=ttl)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise DecryptionError() from None
