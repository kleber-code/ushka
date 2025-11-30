class HTTPError(Exception):
    def __init__(
        self, template="error.html", status_code=404, message="NotFound"
    ) -> None:
        self.status_code = status_code
        self.template = template
        self.message = message


class HTTP_NotFound(HTTPError):
    def __init__(
        self, template="error.html", status_code=404, message="NotFound"
    ) -> None:
        self.status_code = status_code
        self.template = template
        self.message = message
