from typing import Any, Dict, List, Optional, Tuple


class Cookies(dict):
    """
    Full-Stack Cookie Manager.
    1. Input: Receives raw bytes/string from ASGI and converts it into a dictionary.
    2. Output: Tracks changes to generate 'Set-Cookie' headers only when necessary.
    """

    def __init__(
        self,
        header_value: str | bytes | None = None,
        secure_default: bool = True,
        httponly_default: bool = True,
        samesite_default: str = "lax",
    ):
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
        """Breaks the raw string 'key=val; key2=val'."""
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
        self.set(key, value)

    def __delitem__(self, key: str) -> None:
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
        """Defines a cookie and schedules sending."""
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
        """Forces the removal of the cookie in the browser (Max-Age=0)."""
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
