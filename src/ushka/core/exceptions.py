class ServerError(Exception):
    pass


# Router
class RouterError(ServerError):
    pass


class InvalidArgument(RouterError):
    pass


# Response
class ResponseError(ServerError):
    pass


class ContentToTextParserFailed(ResponseError):
    pass


class ContentToJsonParserFailed(ResponseError):
    pass
