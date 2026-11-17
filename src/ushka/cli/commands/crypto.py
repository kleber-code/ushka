"""``ushka crypto genkey``: print a new Fernet key for ``USHKA_CRYPTO_KEYS``."""

from __future__ import annotations

from ushka.cli import ui


def genkey() -> int:
    """Prints a new key, and nothing else, to stdout. Returns 1 when the extra is missing."""
    from ushka.crypto.fernet import INSTALL_HINT, generate_key, is_available

    if not is_available():
        ui.fail(INSTALL_HINT)
    print(generate_key())
    return 0
