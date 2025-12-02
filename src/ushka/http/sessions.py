import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any, List, Tuple

log = logging.getLogger("ushka")


class Session(dict):
    """
    Secure Client-Side Session (HMAC-SHA256) with Timestamp.
    Prevents Replay Attacks and ensures data integrity.
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
        super().__setitem__(key, value)
        self._modified = True
        self._accessed = True

    def __delitem__(self, key: Any) -> None:
        super().__delitem__(key)
        self._modified = True

    def clear(self) -> None:
        super().clear()
        self._modified = True

    def pop(self, key: Any, default: Any = None) -> Any:
        if key in self:
            self._modified = True
        return super().pop(key, default)

    def update(self, *args, **kwargs) -> None:
        if args or kwargs:
            super().update(*args, **kwargs)
            self._modified = True

    def setdefault(self, key: Any, default: Any = None) -> Any:
        if key not in self:
            self._modified = True
        return super().setdefault(key, default)

    # --- Security Core (Encryption & Signature) ---

    def _sign(self, data: bytes) -> bytes:
        """Generates HMAC-SHA256 signature."""
        return (
            hmac.new(self._secret_key, data, hashlib.sha256).hexdigest().encode("utf-8")
        )

    def _encode(self) -> str:
        """
        Serializes the session for sending to the client.
        Format: B64_DATA . B64_TIMESTAMP . SIGNATURE
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
        """
        Deserializes and validates the received cookie.
        Checks: Integrity (Signature) -> Validity (Timestamp) -> Format (JSON)
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
