"""Ushka Guard: untrusted data is a type, and dangerous sinks refuse it.

Everything that comes from outside the program (request query, form, JSON,
headers, cookies, path parameters, and the output of language models) is an
`Untrusted` string. It reads like a normal `str`, but raw HTML responses,
redirects, file paths and raw SQL refuse it with an `UnsafeValueError` that
explains the risk and the fix. Sanitisers in `safe` are the explicit way out.

This package does not import anything else from Ushka, so it can be used
(and later shipped) on its own.

    from ushka.guard import safe, taint

    reply = taint(llm_response.text, source="llm")
    return redirect(safe.url(request.query.get("next"), allow=["/"], default="/"))
"""

from . import safe
from .errors import UnsafeValueError
from .safe import RejectedValueError
from .sinks import check_html, check_markup, check_path, check_redirect, check_sql
from .templates import TEMPLATES_SUPPORTED, is_template
from .untrusted import Untrusted, is_untrusted, source_of, taint, taint_deep

__all__ = [
    "TEMPLATES_SUPPORTED",
    "RejectedValueError",
    "UnsafeValueError",
    "Untrusted",
    "check_html",
    "check_markup",
    "check_path",
    "check_redirect",
    "check_sql",
    "is_template",
    "is_untrusted",
    "llm",
    "safe",
    "source_of",
    "taint",
    "taint_deep",
]


def llm(text: str, model: str | None = None) -> Untrusted:
    """Marks the output of a language model as untrusted.

    Model output can carry a prompt-injection payload from any document the
    model read, so it gets the same treatment as a request parameter
    (OWASP LLM05: improper output handling).
    """
    return Untrusted(text, f"llm:{model}" if model else "llm")
