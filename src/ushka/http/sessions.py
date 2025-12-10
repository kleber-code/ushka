"""
This module provides the `Session` class, a secure client-side session manager
for the Ushka framework.

It implements HMAC-SHA256 for data integrity and timestamp-based validation
to prevent replay attacks, ensuring that session data stored in cookies is
tamper-proof and has a defined lifespan.
"""
import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any, List, Tuple

log = logging.getLogger("ushka")


class Session(dict):
    """Secure Client-Side Session (HMAC-SHA256) with Timestamp.

    This class extends `dict` to provide a secure, client-side session mechanism.
    It uses HMAC-SHA256 for data integrity and includes a timestamp to prevent
    replay attacks and enforce session expiration.

    Parameters
    ----------
    secret_key : str
        A strong, random secret key used for signing the session data.
        Essential for security.
    raw_cookie_value : str, optional
        The raw value of the session cookie received from the client.
        If provided, the session data will be decoded and validated from this.
        Defaults to `None`.
    max_age : int, optional
        The maximum age of the session in seconds. After this period,
        the session is considered expired. Defaults to 1209600 (14 days).
    secure : bool, optional
        If `True`, the session cookie will only be transmitted over HTTPS.
        Defaults to `True`.
    samesite : str, optional
        The `SameSite` attribute for the session cookie ('lax', 'strict', 'none').
        Defaults to `'lax'`.
    """

    COOKIE_NAME = "_ushka_session"
    SEPARATOR = b"."

    def __init__(
        self,
        secret_key: str,
        raw_cookie_value: str | None = None,
        max_age: int = 1209600,  # 14 days in seconds
        secure: bool = True,
        samesite: str = "lax",
    ):
        """Initializes a new Session instance.

        Parameters
        ----------
        secret_key : str
            A strong, random secret key used for signing the session data.
        raw_cookie_value : str, optional
            The raw value of the session cookie received from the client.
        max_age : int, optional
            The maximum age of the session in seconds. Defaults to 14 days.
        secure : bool, optional
            If `True`, the session cookie will only be transmitted over HTTPS.
        samesite : str, optional
            The `SameSite` attribute for the session cookie.
        """
        self._secret_key = secret_key.encode("utf-8")
        self._modified = False
        self._accessed = False

        # Cookie Settings
        self._max_age = max_age
        self._secure = secure
        self._samesite = samesite

        # Tries to load and validate the existing cookie
        initial_data = {}
        if raw_cookie_value:
            initial_data = self._decode(raw_cookie_value, max_age)

        super().__init__(initial_data)

    # --- Change Tracking (Dict Wrapper) ---

    def __setitem__(self, key: Any, value: Any) -> None:
        """Sets a session item and marks the session as modified.

        Parameters
        ----------
        key : Any
            The key for the session item.
        value : Any
            The value to store in the session.
        """
        super().__setitem__(key, value)
        self._modified = True
        self._accessed = True

    def __delitem__(self, key: Any) -> None:
        """Deletes a session item and marks the session as modified.

        Parameters
        ----------
        key : Any
            The key of the session item to delete.
        """
        super().__delitem__(key)
        self._modified = True

    def clear(self) -> None:
        """Removes all items from the session and marks it as modified."""
        super().clear()
        self._modified = True

    def pop(self, key: Any, default: Any = None) -> Any:
        """Removes the specified key from the session and returns its value.

        Marks the session as modified if the key existed.

        Parameters
        ----------
        key : Any
            The key of the item to remove.
        default : Any, optional
            The value to return if the key is not found. Defaults to `None`.

        Returns
        -------
        Any
            The value associated with the key, or `default` if the key is not found.
        """
        if key in self:
            self._modified = True
        return super().pop(key, default)

    def update(self, *args, **kwargs) -> None:
        """Updates the session with key-value pairs from another dictionary or iterable.

        Marks the session as modified if any updates occur.

        Parameters
        ----------
        *args
            Positional arguments passed to the underlying `dict.update` method.
        **kwargs
            Keyword arguments passed to the underlying `dict.update` method.
        """
        if args or kwargs:
            super().update(*args, **kwargs)
            self._modified = True

    def setdefault(self, key: Any, default: Any = None) -> Any:
        """Inserts a key with a default value if the key is not already in the session.

        Marks the session as modified if the key is newly inserted.

        Parameters
        ----------
        key : Any
            The key to check and potentially insert.
        default : Any, optional
            The value to insert if the key is not found. Defaults to `None`.

        Returns
        -------
        Any
            The value for the key (either existing or newly inserted).
        """
        if key not in self:
            self._modified = True
        return super().setdefault(key, default)

    # --- Security Core (Encryption & Signature) ---

    def _sign(self, data: bytes) -> bytes:
        """Generates an HMAC-SHA256 signature for the given data.

        Parameters
        ----------
        data : bytes
            The data to be signed.

        Returns
        -------
        bytes
            The hexadecimal representation of the HMAC-SHA256 signature.
        """
        return (
            hmac.new(self._secret_key, data, hashlib.sha256).hexdigest().encode("utf-8")
        )

    def _encode(self) -> str:
        """Serializes the current session data into a secure string for the client.

        The format is: `base64(JSON_DATA).base64(TIMESTAMP).SIGNATURE`.
        This format ensures data integrity and allows for expiration checks.

        Returns
        -------
        str
            The encoded and signed session string, ready to be sent as a cookie value.
            Returns an empty string if serialization fails.
        """
        try:
            # 1. Serialize data to JSON
            json_data = json.dumps(self, separators=(",", ":"))
            b64_payload = base64.urlsafe_b64encode(json_data.encode("utf-8"))

            # 2. Generate current Timestamp (for age validation)
            timestamp = str(int(time.time()))
            b64_time = base64.urlsafe_b64encode(timestamp.encode("utf-8"))

            # 3. Sign the set (Payload + Timestamp)
            # The signature also protects the date, preventing a hacker from changing the time.
            content_to_sign = b64_payload + self.SEPARATOR + b64_time
            signature = self._sign(content_to_sign)

            # 4. Join everything
            return (content_to_sign + self.SEPARATOR + signature).decode("utf-8")
        except Exception as e:
            # In case of serialization error, return empty to not break the app
            log.critical(f"CRITICAL ERROR ON SESSION (Encode): {e}")
            log.critical(f"ATTEMPT TO SAVE THIS: {self}")
            return ""

    def _decode(self, cookie_value: str, max_age: int) -> dict:
        """Deserializes and validates a session cookie value.

        Performs integrity checks (HMAC signature), validates the timestamp
        against `max_age`, and deserializes the JSON payload.

        Parameters
        ----------
        cookie_value : str
            The raw session cookie value received from the client.
        max_age : int
            The maximum allowed age for the session in seconds.

        Returns
        -------
        dict
            The decoded session data if validation is successful,
            otherwise an empty dictionary.
        """
        if not cookie_value:
            return {}

        try:
            cookie_bytes = cookie_value.encode("utf-8")

            # We expect 3 parts separated by a dot
            parts = cookie_bytes.rsplit(self.SEPARATOR, 2)
            if len(parts) != 3:
                return {}

            b64_payload, b64_time, signature = parts

            # 1. Integrity Validation (HMAC)
            # We recalculate the signature with the received data.
            content_to_verify = b64_payload + self.SEPARATOR + b64_time
            expected_signature = self._sign(content_to_verify)

            # compare_digest prevents Timing Attacks
            if not hmac.compare_digest(signature, expected_signature):
                return {}

            # 2. Expiration Validation (Timestamp)
            timestamp_str = base64.urlsafe_b64decode(b64_time).decode("utf-8")
            timestamp = int(timestamp_str)

            # If max_age is set, check if the cookie is too old
            if max_age > 0:
                age = time.time() - timestamp
                if age > max_age:
                    # Session expired
                    return {}
                if age < 0:
                    # Timestamp in the future? Someone tampered with the clock or it's an attack.
                    return {}

            # 3. Data Deserialization
            json_data = base64.urlsafe_b64decode(b64_payload).decode("utf-8")
            return json.loads(json_data)

        except (ValueError, KeyError, json.JSONDecodeError, IndexError, TypeError):
            # Any parsing error (garbage in the cookie) results in a new empty session
            return {}

    # --- HTTP Response Contract ---

    @property
    def should_save(self) -> bool:
        """Indicates if the cookie needs to be re-sent to the client."""
        return self._modified

    def get_response_headers(self) -> List[Tuple[bytes, bytes]]:
        """Generates the Set-Cookie header ready for the WSGI/ASGI server."""

        # If the session is empty, but was modified (e.g., session.clear()),
        # we send an expired cookie to clear the browser.
        if not self and self._modified:
            return self._expire_cookie()

        if not self:
            return []

        val = self._encode()
        if not val:
            return []

        # Manual construction of the Set-Cookie header
        parts = [f"{self.COOKIE_NAME}={val}"]
        parts.append("Path=/")
        parts.append("HttpOnly")  # Prevents access via JavaScript (XSS Mitigation)

        if self._max_age:
            parts.append(f"Max-Age={self._max_age}")

        if self._secure:
            parts.append("Secure")  # Only transmitted over HTTPS

        if self._samesite:
            parts.append(f"SameSite={self._samesite}")  # Basic CSRF protection

        return [(b"set-cookie", "; ".join(parts).encode("latin-1"))]

    def _expire_cookie(self) -> List[Tuple[bytes, bytes]]:
        """Generates an instruction for the browser to delete the cookie."""
        expired = f"{self.COOKIE_NAME}=; Path=/; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT"
        return [(b"set-cookie", expired.encode("latin-1"))]
