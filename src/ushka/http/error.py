from ushka.http.exceptions import HTTPError


def raise_error(
    status_code=404, message: str | None = None, template: str | None = None
):
    error = HTTPError(status_code=404)
    if template:
        error.template = template
    if message:
        error.message = message
    raise error
