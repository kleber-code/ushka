from enum import StrEnum
from typing import TYPE_CHECKING, List, Tuple, Union

if TYPE_CHECKING:
    from ushka.http.request import Request


class Category(StrEnum):
    SUCCESS = "success"
    DANGER = "danger"
    WARNING = "warning"
    INFO = "info"


def flash(request, message: str, category: Category | str = Category.INFO) -> None:
    if "_flashes" not in request.session:
        request.session["_flashes"] = []

    category_str = str(category).lower()

    request.session["_flashes"].append((category_str, message))


def get_flashed_messages(
    request: "Request", with_categories: bool = False
) -> Union[List[str], List[Tuple[str, str]]]:
    flashes = request.session.pop("_flashes", [])
    if not with_categories:
        return [msg for _, msg in flashes]

    return flashes
