"""What browsers and search engines see: ``seo``, ``pwa`` and ``i18n``.

Each is a piece, ``app.use(Seo(url=...))``, or a section of ``ushka.toml``
(``[seo]``, ``[pwa]``, ``[i18n]``). Importing this package imports none of them.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ushka.web.i18n import I18n
    from ushka.web.pwa import Pwa
    from ushka.web.seo import Seo

_PIECES = {"Seo": "ushka.web.seo", "Pwa": "ushka.web.pwa", "I18n": "ushka.web.i18n"}

__all__ = ["I18n", "Pwa", "Seo"]


def __getattr__(name: str) -> Any:
    if name in _PIECES:
        return getattr(import_module(_PIECES[name]), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
