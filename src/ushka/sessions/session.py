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
import secrets
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
            # Never log the session contents: they may hold user data/tokens.
            log.critical(
                "CRITICAL ERROR ON SESSION (Encode): %s (keys: %s)",
                e,
                sorted(map(str, self.keys())),
            )
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


class ServerSession(Session):
    """A session whose data lives in a `SessionStore`, not in the cookie.

    The cookie holds only ``<id>.<signature>``: an unguessable random id signed
    with the secret key. Revoking the session deletes the record, so a copied
    cookie stops working at once. There is no 4 KB limit, and values must be
    JSON serializable.

    Create it with `ServerSession.load()`; the response saves it (`commit`).
    Use `revoke()` (or `clear()`) to log out, `rotate()` to change the id at
    login, and `revoke_user_sessions()` to log a user out everywhere.
    """

    def __init__(
        self,
        store: Any,
        secret_key: str,
        max_age: int = 1209600,
        idle_timeout: int = 0,
        user_key: str = "user_id",
        secure: bool = True,
        samesite: str = "lax",
    ):
        dict.__init__(self)
        self._secret_key = secret_key.encode("utf-8")
        self._modified = False
        self._accessed = False
        self._max_age = max_age
        self._secure = secure
        self._samesite = samesite
        self._store = store
        self._idle = idle_timeout
        self._user_key = user_key
        self._sid: str | None = None
        self._created = 0.0
        self._last_seen = 0.0
        self._loaded_user: str | None = None
        self._rotate = False
        self._doomed: list[str] = []  # store keys to delete on commit
        self._cookie_dirty = False

    # --- ids ---

    @staticmethod
    def _key(sid: str) -> str:
        return hashlib.sha256(sid.encode("utf-8")).hexdigest()

    def _parse_cookie(self, raw: str) -> str | None:
        """The session id of a cookie value, or None if it is not ours."""
        sid, dot, signature = raw.partition(".")
        if not dot or not sid or not signature:
            return None
        if not hmac.compare_digest(signature.encode("utf-8"), self._sign(sid.encode("utf-8"))):
            return None
        return sid

    @classmethod
    async def load(cls, store: Any, raw_cookie_value: str | None, **options: Any) -> "ServerSession":
        """Builds the session of a request: from the store when the cookie is
        valid, empty otherwise (forged, unknown, revoked or expired)."""
        session = cls(store, **options)
        sid = session._parse_cookie(str(raw_cookie_value)) if raw_cookie_value else None
        if sid is None:
            return session
        key = cls._key(sid)
        record = await store.load(key)
        if record is None:
            return session
        now = time.time()
        expired = (session._max_age > 0 and now - record.created_at > session._max_age) or (
            session._idle > 0 and now - record.last_seen > session._idle
        )
        if expired:
            await store.delete(key)
            return session
        try:
            data = json.loads(record.data)
        except ValueError:
            return session
        if not isinstance(data, dict):
            return session
        dict.update(session, data)
        session._sid = sid
        session._created = record.created_at
        session._last_seen = record.last_seen
        session._loaded_user = record.user_id
        return session

    # --- the API of a server-side session ---

    @property
    def user_id(self) -> str | None:
        """The owner of the session: ``str(self[user_key])``, or None."""
        value = self.get(self._user_key)
        return None if value is None else str(value)

    def revoke(self) -> None:
        """Ends the session: the record is deleted and the cookie expired.
        Anything written afterwards starts a new session with a new id."""
        if self._sid is not None:
            self._doomed.append(self._key(self._sid))
            self._sid = None
        dict.clear(self)
        self._modified = True
        self._cookie_dirty = True

    def clear(self) -> None:
        """Same as `revoke()`: logging out really invalidates the session."""
        self.revoke()

    def rotate(self) -> None:
        """Gives the session a new id and keeps its data. Call it at login, so
        an id planted beforehand (session fixation) is worthless. The first
        time ``[session] user_key`` is set on a session, it rotates by itself."""
        if self._sid is not None:
            self._rotate = True
            self._modified = True

    # --- HTTP contract ---

    @property
    def should_save(self) -> bool:
        return self._cookie_dirty

    def _encode(self) -> str:
        if self._sid is None:
            return ""
        return f"{self._sid}.{self._sign(self._sid.encode('utf-8')).decode('ascii')}"

    async def commit(self) -> None:
        """Writes the changes to the store. The response calls it. A session
        nobody changed costs one read, plus an occasional ``last_seen``
        update when there is an idle timeout."""
        store = self._store
        user = self.user_id
        if self._sid is not None and user is not None and user != self._loaded_user:
            self._rotate = True  # login on an existing id: change the id
        if self._rotate and self._sid is not None:
            self._doomed.append(self._key(self._sid))
            self._sid = None
            self._cookie_dirty = True
        self._rotate = False
        for key in self._doomed:
            await store.delete(key)
        self._doomed = []
        now = time.time()
        if not self:
            if self._sid is not None and self._modified:  # emptied key by key
                await store.delete(self._key(self._sid))
                self._sid = None
                self._cookie_dirty = True
            return
        if self._sid is None or self._modified:
            try:
                data = json.dumps(self, separators=(",", ":"))
            except (TypeError, ValueError):
                # Never log the contents: they may hold user data or tokens.
                raise TypeError(
                    f"Session values must be JSON serializable (keys: {sorted(map(str, self.keys()))})"
                ) from None
            if self._sid is None:
                self._sid = secrets.token_urlsafe(32)
                self._created = now
                self._cookie_dirty = True
                if secrets.randbelow(100) == 0:  # housekeeping, now and then
                    await store.purge(
                        now - self._max_age if self._max_age > 0 else None,
                        now - self._idle if self._idle > 0 else None,
                    )
            self._last_seen = now
            from ushka.sessions.stores import SessionRecord

            await store.save(SessionRecord(self._key(self._sid), data, user, self._created, now))
            self._loaded_user = user
            self._modified = False
        elif self._idle > 0 and now - self._last_seen >= min(60, self._idle / 4):
            self._last_seen = now
            await store.touch(self._key(self._sid), now)
