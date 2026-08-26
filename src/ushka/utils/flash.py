"""
This module provides "flash messaging" functionality for the Ushka framework,
allowing messages to be stored in the user's session and retrieved for display
on the next request.

It includes a `Category` enum for message types and functions to store (`flash`)
and retrieve (`get_flashed_messages`) these messages.
"""
import sys
from typing import TYPE_CHECKING, List, Tuple, Union

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:  # pragma: no cover - compatibility shim for Python 3.10
    # `enum.StrEnum` only exists from 3.11 on, and a plain `(str, Enum)` keeps
    # `str(member)` as "Category.INFO" instead of "info", so `__str__` is
    # restored explicitly.
    from enum import Enum

    class StrEnum(str, Enum):
        """Minimal backport of :class:`enum.StrEnum`."""

        def __str__(self) -> str:
            return str(self.value)

if TYPE_CHECKING:
    from ushka.http.request import Request


class Category(StrEnum):
    """
    Represents the category or type of a flash message.

    Attributes
    ----------
    SUCCESS : str
        Indicates a successful operation ("success").
    DANGER : str
        Indicates a critical error or danger ("danger").
    WARNING : str
        Indicates a potential issue or warning ("warning").
    INFO : str
        Provides general information ("info").
    """

    SUCCESS = "success"
    DANGER = "danger"
    WARNING = "warning"
    INFO = "info"


def flash(request: "Request", message: str, category: Category | str = Category.INFO) -> None:
    """Stores a flash message in the user's session.

    These messages are typically retrieved and displayed on a subsequent request,
    then automatically removed from the session.

    Parameters
    ----------
    request : Request
        The incoming HTTP request object, which provides access to the session.
    message : str
        The content of the message to be flashed.
    category : Category or str, optional
        The category of the message (e.g., 'info', 'danger', 'success', 'warning').
        Defaults to `Category.INFO`.

    Returns
    -------
    None
    """
    if "_flashes" not in request.session:
        request.session["_flashes"] = []

    category_str = str(category).lower()

    request.session["_flashes"].append((category_str, message))


def get_flashed_messages(
    request: "Request", with_categories: bool = False
) -> Union[List[str], List[Tuple[str, str]]]:
    """
    Pops and retrieves all flashed messages from the session.

    Parameters
    ----------
    request : Request
        The request object containing the session data.
    with_categories : bool, optional
        If True, returns a list of (category, message) tuples.
        If False, returns only a list of messages. Defaults to False.

    Returns
    -------
    list of str or list of tuple of (str, str)
        The list of flashed messages. The messages are removed from the session
        after retrieval.
    """
    flashes = request.session.pop("_flashes", [])
    if not with_categories:
        return [msg for _, msg in flashes]

    return flashes
