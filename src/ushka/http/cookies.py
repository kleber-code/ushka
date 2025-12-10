"""
This module provides a full-stack cookie management utility, the `Cookies` class.

It handles parsing raw cookie headers from incoming ASGI requests and
manages changes to generate appropriate `Set-Cookie` headers for outgoing responses.
"""

from typing import Any, Dict, List, Optional, Tuple


class Cookies(dict):
    """Full-Stack Cookie Manager.

    This class extends `dict` to provide comprehensive management of HTTP cookies.
    It handles parsing `Cookie` headers from incoming requests and tracks
    changes to generate `Set-Cookie` headers for outgoing responses efficiently.

    Parameters
    ----------
    header_value : str or bytes, optional
        The raw `Cookie` header value from an incoming request. If provided,
        it will be parsed upon initialization. Defaults to `None`.
    secure_default : bool, optional
        The default `Secure` attribute for new cookies. Defaults to `True`.
    httponly_default : bool, optional
        The default `HttpOnly` attribute for new cookies. Defaults to `True`.
    samesite_default : str, optional
        The default `SameSite` attribute for new cookies ('lax', 'strict', 'none').
        Defaults to `'lax'`.
    """

    def __init__(
        self,
        header_value: str | bytes | None = None,
        secure_default: bool = True,
        httponly_default: bool = True,
        samesite_default: str = "lax",
    ):
        """Initializes the Cookies manager.

        Parameters
        ----------
        header_value : str or bytes, optional
            The raw `Cookie` header value from an incoming request. If provided,
            it will be parsed upon initialization. Defaults to `None`.
        secure_default : bool, optional
            The default `Secure` attribute for new cookies. Defaults to `True`.
        httponly_default : bool, optional
            The default `HttpOnly` attribute for new cookies. Defaults to `True`.
        samesite_default : str, optional
            The default `SameSite` attribute for new cookies ('lax', 'strict', 'none').
            Defaults to `'lax'`.
        """
        super().__init__()

        # Internal State: What needs to be sent to the client
        self._changes: Dict[str, dict] = {}

        # Default security settings
        self._defaults = {
            "secure": secure_default,
            "httponly": httponly_default,
            "samesite": samesite_default,
            "path": "/",
            "domain": None,
        }

        # Eager Parsing: Process the header immediately
        if header_value:
            self._parse_cookie_header(header_value)

    def _parse_cookie_header(self, header: str | bytes):
        """Parses a raw 'Cookie' header string into key-value pairs.



        This internal method populates the `Cookies` dictionary with the

        parsed cookie data.



        Parameters

        ----------

        header : str or bytes

            The raw 'Cookie' header string (e.g., "key1=value1; key2=value2").



        Returns

        -------

        None

            This method populates the instance directly and does not return a value.

        """
        if isinstance(header, bytes):
            try:
                header = header.decode("latin-1")
            except UnicodeDecodeError:
                return

        for chunk in header.split(";"):
            if "=" in chunk:
                key, val = chunk.split("=", 1)
                # Note: Populates only the memory (dict), without marking as a change
                super().__setitem__(key.strip(), val.strip())

    # --- Public Modification API ---

    def __setitem__(self, key: str, value: str) -> None:
        """Sets a cookie value, triggering `set()` for full option handling.

        Parameters
        ----------
        key : str
            The name of the cookie.
        value : str
            The value of the cookie.
        """
        self.set(key, value)

    def __delitem__(self, key: str) -> None:
        """Deletes a cookie, triggering `delete()` to expire it in the browser.

        Parameters
        ----------
        key : str
            The name of the cookie to delete.
        """
        self.delete(key)

    def set(
        self,
        key: str,
        value: str,
        max_age: Optional[int] = None,
        expires: Optional[int] = None,
        path: str | None = None,
        domain: Optional[str] = None,
        secure: bool | None = None,
        httponly: bool | None = None,
        samesite: str | None = None,
    ) -> None:
        """Defines a cookie and schedules it to be sent with the response.



        This method updates the cookie's value and attributes. Changes are

        tracked internally, and `Set-Cookie` headers will be generated

        only if modifications have occurred.



        Parameters

        ----------

        key : str

            The name of the cookie.

        value : str

            The value of the cookie.

        max_age : int, optional

            The maximum age of the cookie in seconds. If `None`, it's a session cookie.

        expires : int, optional

            The expiration date of the cookie as a Unix timestamp.

        path : str, optional

            The path for which the cookie is valid. Defaults to "/".

        domain : str, optional

            The domain for which the cookie is valid. Defaults to `None` (current host only).

        secure : bool, optional

            If `True`, the cookie will only be sent over HTTPS. Defaults to `True`.

        httponly : bool, optional

            If `True`, the cookie cannot be accessed via client-side scripts. Defaults to `True`.

        samesite : str, optional

            Controls cross-site cookie behavior ('lax', 'strict', 'none'). Defaults to 'lax'.



        Returns

        -------

        None

            This method modifies the instance in place and does not return a value.

        """
        super().__setitem__(key, value)

        self._changes[key] = {
            "value": value,
            "max_age": max_age,
            "expires": expires,
            "path": path if path is not None else self._defaults["path"],
            "domain": domain if domain is not None else self._defaults["domain"],
            "secure": secure if secure is not None else self._defaults["secure"],
            "httponly": httponly
            if httponly is not None
            else self._defaults["httponly"],
            "samesite": samesite
            if samesite is not None
            else self._defaults["samesite"],
        }

    def delete(self, key: str, path: str = "/", domain: Optional[str] = None) -> None:
        """Forces the removal of a cookie from the client's browser.



        This is achieved by setting its `Max-Age` to 0 and `Expires` to a past date.



        Parameters

        ----------

        key : str

            The name of the cookie to delete.

        path : str, optional

            The path of the cookie to delete. Defaults to "/".

        domain : str, optional

            The domain of the cookie to delete. Defaults to `None`.



        Returns

        -------

        None

            This method modifies the instance in place and does not return a value.

        """
        if key in self:
            super().__delitem__(key)

        self._changes[key] = {
            "value": "",
            "max_age": 0,
            "expires": 0,
            "path": path,
            "domain": domain,
            "secure": False,
            "httponly": False,
            "samesite": "lax",  # Necessary in some browsers to allow deletion
        }

    # --- Response Contract (App Integration) ---

    @property
    def should_save(self) -> bool:
        """Returns True if there are pending cookies to be sent."""
        return bool(self._changes)

    def get_response_headers(self) -> List[Tuple[bytes, bytes]]:
        """Generates the list of ASGI headers (bytes)."""
        if not self._changes:
            return []

        headers = []
        for key, options in self._changes.items():
            header_val = self._format_cookie_header(key, options)
            headers.append((b"set-cookie", header_val.encode("latin-1")))
        return headers

    def _format_cookie_header(self, key: str, options: Dict[str, Any]) -> str:
        """Formats a single `Set-Cookie` header string.



        This internal method constructs the full cookie header value based on

        the provided key and options, ready to be sent in an HTTP response.



        Parameters

        ----------

        key : str

            The name of the cookie.

        options : dict

            A dictionary containing the cookie's attributes (value, max_age, path, etc.).



        Returns

        -------

        str

            The formatted `Set-Cookie` header string.

        """

        parts = [f"{key}={options['value']}"]

        if options.get("max_age") is not None:
            parts.append(f"Max-Age={options['max_age']}")
        if options.get("expires"):
            parts.append(f"Expires={options['expires']}")
        if options.get("path"):
            parts.append(f"Path={options['path']}")
        if options.get("domain"):
            parts.append(f"Domain={options['domain']}")
        if options.get("secure"):
            parts.append("Secure")
        if options.get("httponly"):
            parts.append("HttpOnly")
        if options.get("samesite"):
            parts.append(f"SameSite={options['samesite']}")

        return "; ".join(parts)
