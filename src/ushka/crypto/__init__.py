"""Ushka Crypto: authenticated encryption (Fernet) with key rotation.

Needs the ``crypto`` extra (``pip install "ushka[crypto]"``); the cipher is the
audited `cryptography` package, Ushka implements none. Importing this package
does not import `cryptography`: that happens on the first call.
"""

from .fernet import (
    DecryptionError,
    decrypt,
    decrypt_bytes,
    derive_key,
    encrypt,
    encrypt_bytes,
    generate_key,
    is_available,
)

__all__ = [
    "DecryptionError",
    "decrypt",
    "decrypt_bytes",
    "derive_key",
    "encrypt",
    "encrypt_bytes",
    "generate_key",
    "is_available",
]
